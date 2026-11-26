"""Personal deployment tests without a real tailnet or brokerage account."""

from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
from threading import Thread
import time

import httpx
import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
sys.path.insert(0, str(DEPLOY / "windows"))
local = importlib.import_module("local")
storage = importlib.import_module("storage")
processes = importlib.import_module("processes")


def records(path):
    with closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT n FROM records ORDER BY n").fetchall()


def prepare(path):
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE records (n INTEGER)")
        db.execute("INSERT INTO records VALUES (1)")
        db.commit()


def test_snapshot_preserves_wal_and_restores_verified_state(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    source = data / "market.db"
    prepare(source)
    (data / "thndr.enc").write_bytes(b"encrypted fixture data")
    with closing(sqlite3.connect(source)) as writer:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("INSERT INTO records VALUES (2)")
        writer.commit()
        saved = storage.snapshot(data, tmp_path / "backups", "a" * 40)
        writer.execute("INSERT INTO records VALUES (3)")
        writer.commit()
    assert records(source) == [(1,), (2,), (3,)]
    assert storage.verify(saved)["release"] == "a" * 40
    prepare(data / "ai_usage.sqlite3")
    storage.restore(saved, data)
    assert records(source) == [(1,), (2,)]
    assert not (data / "ai_usage.sqlite3").exists()
    (saved / "thndr.enc").write_bytes(b"modified")
    with pytest.raises(ValueError, match="checksum mismatch"):
        storage.restore(saved, data)
    assert (data / "thndr.enc").read_bytes() == b"encrypted fixture data"


def test_failed_upgrade_restores_database_and_release(tmp_path, monkeypatch):
    app = local.Installation(tmp_path)
    app.data.mkdir()
    old, new = {"commit": "a" * 40}, {"commit": "b" * 40}
    prepare(app.data / "market.db")
    safety = storage.snapshot(app.data, app.backups, old["commit"])
    storage.write_json(app.current, old)

    def migrate(*_):
        with closing(sqlite3.connect(app.data / "market.db")) as db:
            db.execute("INSERT INTO records VALUES (2)")
            db.commit()
        raise local.LocalError("Simulated migration failure")

    monkeypatch.setattr(app, "migrate", migrate)
    with pytest.raises(local.LocalError, match="Simulated migration failure"):
        app.activate({}, old, new, safety)
    assert records(app.data / "market.db") == [(1,)]
    assert app.pointer() == old
    assert not app.pending.exists()


def test_paid_and_private_environment_values_do_not_cross_processes(
    tmp_path, monkeypatch
):
    app = local.Installation(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "billable")
    monkeypatch.setenv("BACKEND_UPSTREAM", "unexpected")
    source = {
        "host": "laptop.example.ts.net",
        "owner_hash": "hash",
        "gateway_secret": "server-only",
        "environment": {
            "AI_ENABLED": "true",
            "SCANNER_AI_ENABLED": "true",
            "OPENAI_API_KEY": "still-billable",
            "TELEGRAM_BOT_TOKEN": "secret",
        },
    }
    backend, gateway = app.environments(source)
    assert backend["AI_ENABLED"] == backend["SCANNER_AI_ENABLED"] == "false"
    assert "OPENAI_API_KEY" not in backend.keys() | gateway.keys()
    assert backend["TELEGRAM_BOT_TOKEN"] == "secret"
    assert "TELEGRAM_BOT_TOKEN" not in gateway
    assert "BACKEND_UPSTREAM" not in gateway
    assert "OWNER_PASSWORD_HASH" not in backend
    assert (
        backend["THNDR_REDIRECT_URI"]
        == "https://laptop.example.ts.net/api/v1/integrations/thndr/callback"
    )


def test_supervisor_lock_and_owned_children(tmp_path):
    lockfile = tmp_path / "running.lock"
    with processes.lock(lockfile):
        with pytest.raises(BlockingIOError):
            with processes.lock(lockfile):
                pytest.fail("duplicate supervisor")
    with processes.lock(lockfile):
        children = processes.Children()
        try:
            began = tmp_path / "began"
            child = children.spawn(
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; import sys,time; Path(sys.argv[1]).touch(); time.sleep(120)",
                    str(began),
                ]
            )
            for _ in range(100):
                if began.exists():
                    break
                time.sleep(0.05)
            assert began.exists()
            assert child.poll() is None
        finally:
            children.close()
        assert child.poll() is not None


@pytest.mark.skipif(
    not shutil.which("caddy"), reason="Caddy needed for Serve ingress acceptance"
)
def test_tailscale_origin_and_gateway_headers(tmp_path):
    class Echo(BaseHTTPRequestHandler):
        def do_GET(self):
            observed = {
                name: self.headers.get(name)
                for name in (
                    "Authorization",
                    "Origin",
                    "X-EGX-Gateway",
                    "X-Forwarded-Proto",
                    "X-Forwarded-Host",
                    "Forwarded",
                )
            }
            self.send_response(200)
            self.send_header("Set-Cookie", "__Host-fixture=1; Secure; HttpOnly; Path=/")
            self.end_headers()
            self.wfile.write(json.dumps(observed).encode())

        do_POST = do_GET

        def log_message(self, *_):
            pass

    caddy = shutil.which("caddy")
    secret = secrets.token_urlsafe(32)
    password = secrets.token_urlsafe(24)
    hashed = subprocess.run(
        [caddy, "hash-password"],
        input=password + "\n",
        text=True,
        check=True,
        capture_output=True,
    ).stdout.strip()
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        port = unused.getsockname()[1]
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    Thread(target=upstream.serve_forever, daemon=True).start()
    address = f"127.0.0.1:{upstream.server_port}"
    host = "laptop.example.ts.net"
    env = os.environ | {
        "APP_HOST": host,
        "OWNER_PASSWORD_HASH": hashed,
        "INTEGRATIONS_GATEWAY_SECRET": secret,
        "BACKEND_UPSTREAM": address,
        "FRONTEND_UPSTREAM": address,
        "XDG_DATA_HOME": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path),
    }
    caddyfile = tmp_path / "Caddyfile"
    caddyfile.write_text(
        (DEPLOY / "Caddyfile.tailscale").read_text().replace(":8788", f":{port}")
    )
    shutil.copyfile(DEPLOY / "owner-route.caddy", tmp_path / "owner-route.caddy")
    process = subprocess.Popen(
        [caddy, "run", "--config", str(caddyfile), "--adapter", "caddyfile"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", trust_env=False
        ) as client:
            for _ in range(150):
                assert process.poll() is None
                try:
                    denied = client.get(
                        "/api/v1/system", headers={"X-EGX-Gateway": secret}
                    )
                    break
                except httpx.ConnectError:
                    time.sleep(0.05)
            else:
                pytest.fail("Caddy did not bind")
            assert denied.status_code == 401
            auth = ("owner", password)
            api = "/api/v1/integrations/thndr"
            malicious = {
                "X-EGX-Gateway": "forged",
                "X-Forwarded-Proto": "http",
                "X-Forwarded-Host": "forged.example",
                "Forwarded": "proto=http",
            }
            for headers in (
                malicious,
                malicious | {"Origin": "https://forged.example"},
            ):
                assert (
                    client.post(
                        api + "/connect", headers=headers, auth=auth
                    ).status_code
                    == 403
                )
            result = client.post(
                api + "/connect",
                headers=malicious | {"Origin": f"https://{host}"},
                auth=auth,
            )
            assert result.status_code == 200
            assert result.json() == {
                "Authorization": None,
                "Origin": None,
                "X-EGX-Gateway": secret,
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": host,
                "Forwarded": None,
            }
            callback = client.get(api + "/callback?code=fixture&state=mock", auth=auth)
            assert (
                callback.status_code == 200
                and "Secure" in callback.headers["Set-Cookie"]
            )
            assert "no-store" in callback.headers["Cache-Control"]
            assert (
                client.get("/portfolio", headers=malicious, auth=auth).json()[
                    "X-EGX-Gateway"
                ]
                is None
            )
            assert (
                "no-store" in client.get("/orders", auth=auth).headers["Cache-Control"]
            )
            shell = client.get("/pwa/offline.html", auth=auth)
            assert shell.headers["Cache-Control"] == "public, max-age=3600"
            assert shell.headers["Strict-Transport-Security"] == "max-age=31536000"
    finally:
        process.terminate()
        process.wait(timeout=10)
        upstream.shutdown()
        upstream.server_close()
