"""Versioned, verified snapshots of a stopped personal installation."""

from datetime import UTC, datetime
from hashlib import file_digest
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from contextlib import closing

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.core.sqlite_backup import backup_database

STATE_FILES = {"market.db", "ai_usage.sqlite3", "thndr.enc"}
SQLITE_FILES = {"market.db", "ai_usage.sqlite3"}


def write_json(path, value):
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        staged = Path(stream.name)
        try:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            os.replace(staged, path)
        finally:
            staged.unlink(missing_ok=True)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def sqlite_check(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed")


def verify(folder):
    index = read_json(folder / "manifest.json")
    if (
        index.get("format") != 1
        or not isinstance(index.get("files"), dict)
        or not index["files"].keys() <= STATE_FILES
        or "market.db" not in index["files"]
    ):
        raise ValueError("Invalid backup manifest")
    for name, expected in index["files"].items():
        path = folder / name
        if path.is_symlink() or digest(path) != expected:
            raise ValueError("Backup checksum mismatch")
        if name in SQLITE_FILES:
            sqlite_check(path)
    return index


def snapshot(data, backups, release):
    if not (data / "market.db").is_file():
        raise ValueError("No market database to back up")
    backups.mkdir(exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".pending-", dir=backups))
    try:
        files = {}
        for name in sorted(STATE_FILES):
            original = data / name
            if not original.exists():
                continue
            destination = staged / name
            if name in SQLITE_FILES:
                backup_database(original, destination)
            else:
                shutil.copyfile(original, destination)
            files[name] = digest(destination)
        write_json(
            staged / "manifest.json", {"format": 1, "release": release, "files": files}
        )
        verify(staged)
        name = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        final = backups / name
        os.rename(staged, final)
    finally:
        if staged.exists():
            shutil.rmtree(staged)
    return final


def restore(folder, data):
    index = verify(folder)
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=data) as staging:
        staged = Path(staging)
        for name, expected in index["files"].items():
            shutil.copyfile(folder / name, staged / name)
            if digest(staged / name) != expected:
                raise ValueError("Backup changed during staging")
        for name in sorted(STATE_FILES):
            if name in SQLITE_FILES:
                for suffix in ("-wal", "-shm", "-journal"):
                    (data / (name + suffix)).unlink(missing_ok=True)
            if name in index["files"]:
                os.replace(staged / name, data / name)
            else:
                (data / name).unlink(missing_ok=True)
    sqlite_check(data / "market.db")


def quarantine(data, backups):
    """Preserve raw files for recovery when SQLite cannot create a snapshot."""
    backups.mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="damaged-", dir=backups))
    for name in sorted(STATE_FILES):
        suffixes = ("", "-wal", "-shm", "-journal") if name in SQLITE_FILES else ("",)
        for suffix in suffixes:
            current = data / (name + suffix)
            if current.is_file():
                shutil.copyfile(current, folder / current.name)
    return folder
