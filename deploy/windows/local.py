"""Personal Windows install, supervision and maintenance for the existing EGX services."""

import argparse
import base64
from contextlib import contextmanager
import getpass
import json
from pathlib import Path
import re
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from processes import Children, WINDOWS, lock
from storage import (
    backup_database,
    quarantine,
    read_json,
    restore,
    snapshot,
    verify,
    write_json,
)

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parents[1]
BRANCH = "feature/ai-trading-assistant"
REF = f"refs/heads/{BRANCH}"
SHA = re.compile(r"[a-f0-9]{40}")
HOST = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.){2,}ts\.net")
PORTS = {"api": 8000, "web": 3000, "gateway": 8788}
BACKEND_KEYS = frozenset(
    """
    THNDR_ENCRYPTION_KEY NOTIFICATION_ENCRYPTION_KEY TELEGRAM_ENABLED TELEGRAM_BOT_TOKEN
    TELEGRAM_OWNER_USER_ID WEB_PUSH_ENABLED VAPID_PRIVATE_KEY VAPID_PUBLIC_KEY VAPID_SUBJECT
    SCANNER_ENABLED SCANNER_INTERVAL_SECONDS SCANNER_MAX_CONCURRENCY
    SCANNER_MAX_SYMBOLS_PER_SCAN SCANNER_LEASE_SECONDS SCANNER_HEARTBEAT_SECONDS
    SCANNER_JOB_TIMEOUT_SECONDS SCANNER_THNDR_MIN_INTERVAL_SECONDS SCANNER_HISTORY_RETENTION_DAYS
    ALERT_COOLDOWN_SECONDS EOD_IMPORT_ENABLED EOD_IMPORT_INTERVAL_SECONDS EOD_IMPORT_MAX_PER_DAY
    EOD_IMPORT_PAPER_FOLLOW
    """.split()
)
RUNTIME_BASE = frozenset(
    "SYSTEMROOT SYSTEMDRIVE WINDIR COMSPEC PATH USERPROFILE APPDATA LOCALAPPDATA TEMP TMP HOME".split()
)


class LocalError(Exception):
    pass


def command(args, *, cwd=None, env=None, capture=False):
    result = subprocess.run(
        args, cwd=cwd, env=env, check=False, text=True, capture_output=capture
    )
    if result.returncode:
        raise LocalError(f"{Path(args[0]).name} failed (exit {result.returncode}).")
    return result.stdout.strip() if capture else None


def executable(name):
    path = shutil.which(name)
    if not path:
        raise LocalError(f"{name} is required. Install it and reopen this window.")
    return path


def runtime_env():
    return {
        name: value
        for name, value in os.environ.items()
        if name.upper() in RUNTIME_BASE
    }


def enabled(value):
    return str(value).lower() in {"true", "1", "yes", "on"}


def assert_sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise LocalError("Invalid pinned release identifier.")
    return value


class Installation:
    def __init__(self, root, repo=REPO):
        self.root = root
        self.repo = repo
        self.data = root / "data"
        self.backups = root / "backups"
        self.releases = root / "releases"
        self.logs = root / "logs"
        self.config_path = root / "private.json"
        self.current = root / "current.json"
        self.pending = root / "maintenance.json"
        self.stop_file = root / "stop"
        self.running_lock = root / "running.lock"

    def init_storage(self):
        self.root.mkdir(exist_ok=True)
        if WINDOWS:
            command(
                [
                    executable("powershell.exe"),
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPTS / "Protect-State.ps1"),
                    "-Path",
                    str(self.root),
                ]
            )
        for path in (self.data, self.releases, self.logs, self.data / "inbox"):
            path.mkdir(exist_ok=True)

    def config(self):
        data = read_json(self.config_path)
        if (
            not HOST.fullmatch(data.get("host", ""))
            or not data.get("owner_hash", "").startswith(("$2a$", "$2b$", "$2y$"))
            or len(data.get("gateway_secret", "")) < 32
            or not isinstance(data.get("environment"), dict)
        ):
            raise LocalError(
                "Invalid private.json. Check the Tailscale host and generated settings."
            )
        return data

    def environments(self, config):
        os_env = runtime_env()
        backend = {
            key: str(value)
            for key, value in config["environment"].items()
            if key in BACKEND_KEYS
        }
        backend.update(
            APP_HOST=config["host"],
            AI_ENABLED="false",
            SCANNER_AI_ENABLED="false",
            DATABASE_URL="sqlite:///" + (self.data / "market.db").as_posix(),
            AI_LEDGER_PATH=str(self.data / "ai_usage.sqlite3"),
            THNDR_PRIVATE_DIR=str(self.data),
            THNDR_REDIRECT_URI=f"https://{config['host']}/api/v1/integrations/thndr/callback",
            EOD_IMPORT_DIRECTORY=str(self.data / "inbox"),
            INTEGRATIONS_GATEWAY_SECRET=config["gateway_secret"],
            PYTHONUNBUFFERED="1",
            PYTHONNOUSERSITE="1",
        )
        gateway = os_env | {
            "APP_HOST": config["host"],
            "OWNER_PASSWORD_HASH": config["owner_hash"],
            "INTEGRATIONS_GATEWAY_SECRET": config["gateway_secret"],
            "XDG_DATA_HOME": str(self.root / "caddy"),
            "XDG_CONFIG_HOME": str(self.root / "caddy"),
        }
        return os_env | backend, gateway

    def release(self, commit):
        return self.releases / assert_sha(commit)

    def pointer(self):
        value = read_json(self.current)
        assert_sha(value["commit"])
        return value

    def python(self, release):
        return str(
            release / ("venv/Scripts/python.exe" if WINDOWS else "venv/bin/python")
        )

    def build(self, commit):
        target = self.release(commit)
        if (target / "installed").is_file():
            return target
        if target.exists():
            shutil.rmtree(target)
        target.mkdir()
        archive = self.releases / f"{commit}.zip"
        try:
            command(
                ["git", "archive", "--format=zip", "-o", str(archive), commit],
                cwd=self.repo,
            )
            shutil.unpack_archive(archive, target)
        finally:
            archive.unlink(missing_ok=True)
        command([sys.executable, "-m", "venv", str(target / "venv")])
        python = self.python(target)
        command(
            [python, "-m", "pip", "install", "-r", "requirements.txt"],
            cwd=target / "backend",
        )
        command([python, "-m", "pip", "check"])
        npm = executable("npm.cmd" if WINDOWS else "npm")
        build_env = os.environ | {
            "NEXT_PUBLIC_API_URL": "/api/v1",
            "NEXT_TELEMETRY_DISABLED": "1",
        }
        command([npm, "ci"], cwd=target / "frontend", env=build_env)
        command([npm, "run", "type-check"], cwd=target / "frontend", env=build_env)
        command([npm, "run", "build"], cwd=target / "frontend", env=build_env)
        (target / "installed").touch()
        return target

    def migrate(self, release, config):
        backend, gateway = self.environments(config)
        command(
            [
                executable("caddy"),
                "validate",
                "--config",
                str(release / "deploy/Caddyfile.tailscale"),
                "--adapter",
                "caddyfile",
            ],
            env=gateway,
            capture=True,
        )
        command(
            [self.python(release), "-m", "alembic", "upgrade", "head"],
            cwd=release / "backend",
            env=backend,
        )
        command(
            [self.python(release), "-m", "alembic", "current", "--check-heads"],
            cwd=release / "backend",
            env=backend,
        )

    def onboarding(self):
        if self.config_path.exists():
            return self.config()
        host = (
            input("Paste your laptop's complete Tailscale DNS name (*.ts.net): ")
            .strip()
            .lower()
            .rstrip(".")
        )
        if not HOST.fullmatch(host):
            raise LocalError(
                "Enter the full DNS name without https://, a path, or a port."
            )
        password = getpass.getpass("Create an owner password (16-72 UTF-8 bytes): ")
        if (
            not 16 <= len(password.encode()) <= 72
            or "\r" in password
            or "\n" in password
        ):
            raise LocalError("Invalid owner password length.")
        if getpass.getpass("Repeat the password: ") != password:
            raise LocalError("Passwords did not match.")
        hashed = subprocess.run(
            [executable("caddy"), "hash-password"],
            input=password.encode() + b"\n",
            capture_output=True,
            check=False,
        )
        owner_hash = hashed.stdout.decode().strip()
        if hashed.returncode or not owner_hash.startswith(("$2a$", "$2b$", "$2y$")):
            raise LocalError("Caddy could not create the password hash.")
        imported = self.legacy().get("environment", {})
        values = {
            "THNDR_ENCRYPTION_KEY": base64.urlsafe_b64encode(
                secrets.token_bytes(32)
            ).decode(),
            "NOTIFICATION_ENCRYPTION_KEY": base64.urlsafe_b64encode(
                secrets.token_bytes(32)
            ).decode(),
            "SCANNER_ENABLED": "true",
        }
        values.update(
            {
                key: value
                for key, value in imported.items()
                if key in BACKEND_KEYS and value
            }
        )
        config = {
            "host": host,
            "owner_hash": owner_hash,
            "gateway_secret": secrets.token_urlsafe(48),
            "environment": values,
        }
        write_json(self.config_path, config)
        return config

    def legacy(self):
        path = self.root / "legacy.json"
        return read_json(path) if path.exists() else {}

    def seed(self, release):
        old = self.legacy()
        instance = self.repo / "backend/instance"
        sources = {
            "market.db": old.get("database")
            or (
                instance / "egx_platform.db"
                if (instance / "egx_platform.db").exists()
                else release / "backend/egx_platform.db"
            ),
            "ai_usage.sqlite3": old.get("ledger") or instance / "ai_usage.sqlite3",
            "thndr.enc": old.get("vault") or instance / "thndr.enc",
        }
        if (
            Path(sources["thndr.enc"]).is_file()
            and not (self.data / "thndr.enc").exists()
        ):
            if not old.get("environment", {}).get("THNDR_ENCRYPTION_KEY"):
                raise LocalError(
                    "Existing Thndr vault found. Put its original key in private legacy.json."
                )
        for name, source in sources.items():
            source = Path(source)
            path = self.data / name
            if path.exists():
                continue
            if not source.is_file():
                if name == "market.db" or any(
                    old.get(k) == str(source) for k in ("database", "ledger", "vault")
                ):
                    raise LocalError(f"Existing {name} source was not found.")
                continue
            if name == "thndr.enc":
                with path.open("xb") as target, source.open("rb") as original:
                    shutil.copyfileobj(original, target)
            else:
                backup_database(source, path)

    def install(self):
        if self.current.exists():
            print("Already installed. Use START.bat or UPDATE.bat.")
            return
        executable("git")
        executable("node")
        executable("caddy")
        config = self.onboarding()
        commit = assert_sha(
            command(["git", "rev-parse", "HEAD"], cwd=self.repo, capture=True)
        )
        if (
            command(["git", "branch", "--show-current"], cwd=self.repo, capture=True)
            != BRANCH
        ):
            raise LocalError(f"Check out {BRANCH} before installing.")
        release = self.build(commit)
        self.seed(release)
        saved = snapshot(self.data, self.backups, commit)
        try:
            self.migrate(release, config)
        except (LocalError, OSError):
            restore(saved, self.data)
            raise
        write_json(self.current, {"commit": commit})
        print(
            f"Installed. Configure Tailscale Serve, then run START.bat. https://{config['host']}/"
        )

    def running(self):
        try:
            with lock(self.running_lock):
                return False
        except BlockingIOError:
            return True

    def start(self):
        if self.pending.exists():
            raise LocalError(
                "Maintenance was interrupted. Use RESTORE.bat with a verified backup."
            )
        if self.running():
            print("EGX is already running.")
            return
        self.pointer()
        self.config()
        self.stop_file.unlink(missing_ok=True)
        with (self.logs / "supervisor.log").open("ab") as log:
            subprocess.Popen(
                [sys.executable, str(SCRIPTS / "local.py"), "task"],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if WINDOWS else 0,
                start_new_session=not WINDOWS,
            )
        for _ in range(60):
            if self.running():
                try:
                    if (
                        self.probe(PORTS["gateway"], "/api/v1/system") == 401
                        and self.probe(PORTS["web"], "/") == 200
                        and (self.health().get("migration") or {}).get("ready") is True
                    ):
                        print(
                            "EGX is running. Open https://"
                            + self.config()["host"]
                            + "/"
                        )
                        return
                except (OSError, KeyError, ValueError):
                    pass
            time.sleep(1)
        raise LocalError(
            "Startup is incomplete. Run STATUS.bat and check private logs."
        )

    def stop(self):
        if not self.running():
            return
        self.stop_file.touch()
        for _ in range(75):
            if not self.running():
                return
            time.sleep(0.4)
        raise LocalError("Could not stop EGX. No data or release was changed.")

    @contextmanager
    def paused(self):
        restart = self.running()
        self.stop()
        try:
            with lock(self.running_lock):
                yield
        finally:
            if restart and not self.pending.exists():
                self.start()

    def backup(self):
        with self.paused():
            folder = snapshot(self.data, self.backups, self.pointer()["commit"])
            print(f"Verified backup: {folder}")

    def activate(self, config, previous, candidate, safety, incoming=None):
        write_json(
            self.pending, {"backup": safety.name, "previous": previous["commit"]}
        )
        try:
            if incoming:
                restore(incoming, self.data)
            self.migrate(self.release(candidate["commit"]), config)
            write_json(self.current, candidate)
        except (LocalError, OSError, ValueError, sqlite3.Error, KeyboardInterrupt):
            restore(safety, self.data)
            write_json(self.current, previous)
            self.pending.unlink()
            raise
        self.pending.unlink()

    def update(self):
        if self.pending.exists():
            raise LocalError("Resolve interrupted maintenance before updating.")
        previous = self.pointer()
        command(["git", "fetch", "--no-tags", "origin", REF], cwd=self.repo)
        commit = assert_sha(
            command(["git", "rev-parse", "FETCH_HEAD"], cwd=self.repo, capture=True)
        )
        if commit == previous["commit"]:
            print("Already up to date.")
            return
        command(
            ["git", "merge-base", "--is-ancestor", previous["commit"], commit],
            cwd=self.repo,
        )
        self.build(commit)
        restart = self.running()
        self.stop()
        try:
            with lock(self.running_lock):
                safety = snapshot(self.data, self.backups, previous["commit"])
                self.activate(
                    self.config(),
                    previous,
                    {
                        "commit": commit,
                        "previous": previous["commit"],
                        "backup": safety.name,
                    },
                    safety,
                )
        finally:
            if (
                restart
                and not self.pending.exists()
                and self.pointer()["commit"] == previous["commit"]
            ):
                self.start()
        if restart:
            try:
                self.start()
            except LocalError:
                self.stop()
                with lock(self.running_lock):
                    write_json(
                        self.pending,
                        {"backup": safety.name, "previous": previous["commit"]},
                    )
                    restore(safety, self.data)
                    write_json(self.current, previous)
                    self.pending.unlink()
                self.start()
                raise LocalError(
                    "Updated services did not become healthy. Previous release restored."
                ) from None
        print(f"Active release: {commit}")

    def backup_folder(self, name):
        if not re.fullmatch(r"\d{8}T\d{6}\.\d{6}Z", name):
            raise LocalError("Enter the name of a verified backup directory.")
        return self.backups / name

    def recover(self, kind, argument):
        previous = self.pointer()
        if kind == "rollback" and self.pending.exists():
            raise LocalError(
                "Use RESTORE.bat with the backup named in maintenance.json."
            )
        if kind == "rollback" and not previous.get("previous"):
            raise LocalError("No earlier installed release to roll back to.")
        if kind == "restore" and not argument:
            for candidate in sorted(self.backups.glob("*Z"), reverse=True):
                print(candidate.name)
            argument = input("Backup folder name: ").strip()
        incoming = self.backup_folder(
            previous["backup"] if kind == "rollback" else argument
        )
        saved_commit = assert_sha(verify(incoming)["release"])
        if kind == "rollback" and saved_commit != previous["previous"]:
            raise LocalError("Backup does not match the recorded previous release.")
        if not (self.release(saved_commit) / "installed").is_file():
            raise LocalError(
                "The backup's software release is missing. Keep the matching release."
            )
        if (
            input(
                "Current records will be replaced after a safety backup. Type RESTORE: "
            )
            != "RESTORE"
        ):
            raise LocalError("Restore cancelled.")
        with self.paused():
            config = self.config()
            try:
                safety = snapshot(self.data, self.backups, previous["commit"])
            except (sqlite3.DatabaseError, ValueError):
                if kind != "restore":
                    raise LocalError(
                        "Current SQLite state is damaged. Use RESTORE.bat."
                    ) from None
                damaged = quarantine(self.data, self.backups)
                print(f"Unreadable database files preserved in: {damaged}")
                write_json(
                    self.pending, {"backup": incoming.name, "damaged": damaged.name}
                )
                restore(incoming, self.data)
                self.migrate(self.release(saved_commit), config)
                write_json(self.current, {"commit": saved_commit})
                self.pending.unlink()
            else:
                self.activate(
                    config, previous, {"commit": saved_commit}, safety, incoming
                )
        print(f"Restored a verified snapshot for {saved_commit}.")

    def probe(self, port, path, headers=None):
        request = Request(f"http://127.0.0.1:{port}{path}", headers=headers or {})
        try:
            with build_opener(ProxyHandler({})).open(request, timeout=2) as result:
                return json.load(result) if headers else result.status
        except HTTPError as exc:
            return exc.code

    def health(self):
        result = self.probe(
            PORTS["api"],
            "/api/v1/system",
            {"X-EGX-Gateway": self.config()["gateway_secret"]},
        )
        return result if isinstance(result, dict) else {}

    def status(self):
        print("Private storage:", self.root)
        print("Release:", self.pointer()["commit"])
        print("URL: https://" + self.config()["host"] + "/")
        print("Interrupted maintenance:", self.pending.exists())
        if not self.running():
            print("Supervisor: STOPPED")
            return
        try:
            health = self.health()
            gateway = self.probe(PORTS["gateway"], "/api/v1/system") == 401
            web = self.probe(PORTS["web"], "/") == 200
        except (OSError, ValueError):
            print(
                "Supervisor: RUNNING; a local service is still starting or unavailable."
            )
            return
        print(
            f"Owner gateway: {'OK' if gateway else 'UNAVAILABLE'}; frontend: {'OK' if web else 'UNAVAILABLE'}"
        )
        print("Database:", health.get("database", "UNAVAILABLE"))
        print("Migration:", health.get("migration"))
        for name, worker in health.get("workers", {}).items():
            state = (
                "DISABLED"
                if not worker["configured"]
                else "ONLINE"
                if worker["running"]
                else "CHECK LOGS"
            )
            print(f"Worker {name}: {state}")
        print("For tailnet routing, also run: tailscale serve status")

    def supervise(self):
        with lock(self.running_lock):
            if self.pending.exists():
                raise LocalError("Interrupted maintenance; refusing to start.")
            release = self.release(self.pointer()["commit"])
            config = self.config()
            backend, gateway = self.environments(config)
            web = runtime_env() | {
                "NODE_ENV": "production",
                "NEXT_TELEMETRY_DISABLED": "1",
            }
            for port in PORTS.values():
                with socket.socket() as probe:
                    if WINDOWS:
                        probe.setsockopt(
                            socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1
                        )
                    probe.bind(("127.0.0.1", port))
            python = self.python(release)
            node = executable("node")
            caddy = executable("caddy")
            commands = {
                "api": (
                    release / "backend",
                    backend,
                    [
                        python,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                        "--forwarded-allow-ips",
                        "127.0.0.1",
                        "--no-access-log",
                    ],
                ),
                "web": (
                    release / "frontend",
                    web,
                    [
                        node,
                        "node_modules/next/dist/bin/next",
                        "start",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        "3000",
                    ],
                ),
                "gateway": (
                    release / "deploy",
                    gateway,
                    [
                        caddy,
                        "run",
                        "--config",
                        "Caddyfile.tailscale",
                        "--adapter",
                        "caddyfile",
                    ],
                ),
            }
            roles = ["scanner", "paper", "backtest", "notification"]
            if enabled(backend.get("EOD_IMPORT_ENABLED")):
                roles.append("import")
            for worker in roles:
                commands[worker] = (
                    release / "backend",
                    backend,
                    [python, "-m", f"app.workers.{worker}_worker"],
                )
            processes = Children()
            active = {}
            delay_until = {}
            try:
                while not self.stop_file.exists():
                    for name, (cwd, env, command_line) in commands.items():
                        child = active.get(name)
                        if child and child.poll() is None:
                            continue
                        if child:
                            processes.exited(child)
                            print(
                                f"{name} exited ({child.returncode}); restarting after 5s.",
                                flush=True,
                            )
                            delay_until[name] = time.monotonic() + 5
                            del active[name]
                            continue
                        if delay_until.get(name, 0) > time.monotonic():
                            continue
                        path = self.logs / (name + ".log")
                        if path.exists() and path.stat().st_size >= 2_000_000:
                            path.replace(path.with_suffix(".previous.log"))
                        with path.open("ab") as log:
                            active[name] = processes.spawn(
                                command_line,
                                cwd=cwd,
                                env=env,
                                stdin=subprocess.DEVNULL,
                                stdout=log,
                                stderr=log,
                            )
                    time.sleep(0.5)
            finally:
                processes.close()
                self.stop_file.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "install",
            "start",
            "stop",
            "restart",
            "update",
            "backup",
            "status",
            "restore",
            "rollback",
            "task",
        ],
    )
    parser.add_argument("backup_name", nargs="?")
    options = parser.parse_args()
    if not WINDOWS or not os.getenv("LOCALAPPDATA"):
        parser.error("The launchers require Windows and a signed-in local user.")
    app = Installation(Path(os.environ["LOCALAPPDATA"]) / "EGXTradingAssistant")
    try:
        if options.action == "install":
            app.init_storage()
        if not app.root.is_dir():
            raise LocalError("Run INSTALL.bat first.")
        if options.action == "task":
            app.supervise()
        else:
            with lock(app.root / "maintenance.lock"):
                if options.action == "restart":
                    app.stop()
                    app.start()
                elif options.action in {"restore", "rollback"}:
                    app.recover(options.action, options.backup_name)
                else:
                    getattr(app, options.action)()
    except FileNotFoundError:
        print(
            "EGX: a required file is missing. Check installation and STATUS.bat.",
            file=sys.stderr,
        )
        return 1
    except BlockingIOError:
        if options.action == "task" and app.running():
            return 0
        print("EGX: another maintenance command is running.", file=sys.stderr)
        return 1
    except (LocalError, OSError, ValueError, sqlite3.Error, KeyboardInterrupt) as exc:
        # Output operator actions without dumping configuration, environment or command arguments.
        info = str(exc) if isinstance(exc, LocalError) else type(exc).__name__
        print(f"EGX: {info}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
