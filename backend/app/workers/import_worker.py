"""Poll a service-owned inbox for authorized files, never external endpoints."""

import hashlib
import os
import signal
import threading
from datetime import datetime
from pathlib import Path

from sqlalchemy.exc import OperationalError

from app.core.database import SessionLocal
from app.schemas.market_import import ImportEnvironment, ImportFile
from app.services.market_import import persist
from app.services.scanner_calendar import CAIRO
from app.services.worker_pulse import pulse


def read(path):
    # A producer must close and atomically rename its complete file into the inbox.
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        return None
    raw = path.read_bytes()
    if len(raw) > 2_000_000:
        return None
    try:
        value = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        value = '"unsupported-encoding:' + hashlib.sha256(raw).hexdigest() + '"'
    return ImportFile(format="JSON", content=value or "null")


def ingest(factory, directory, now, settings):
    for path in sorted(directory.glob("*.json"))[:500]:
        envelope = read(path)
        if envelope:
            with factory() as db:
                result = persist(db, envelope, now, "INBOX", settings)
            if result["status"] == "QUOTA":
                break


def main():
    os.umask(0o077)
    settings = ImportEnvironment()
    if not settings.EOD_IMPORT_ENABLED or not settings.EOD_IMPORT_DIRECTORY:
        print("AUTHORIZED_IMPORT_NOT_ENABLED", flush=True)
        return
    directory = Path(settings.EOD_IMPORT_DIRECTORY)
    if not directory.is_absolute() or not directory.is_dir() or directory.is_symlink():
        raise SystemExit("AUTHORIZED_IMPORT_DIRECTORY_INVALID")
    stop = threading.Event()
    for key in (signal.SIGTERM, signal.SIGINT):
        signal.signal(key, lambda *_: stop.set())
    while not stop.is_set():
        try:
            pulse(SessionLocal, "import")
            ingest(SessionLocal, directory, datetime.now(CAIRO), settings)
        except (OperationalError, OSError):
            print("AUTHORIZED_IMPORT_TEMPORARILY_UNAVAILABLE", flush=True)
        stop.wait(settings.EOD_IMPORT_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
