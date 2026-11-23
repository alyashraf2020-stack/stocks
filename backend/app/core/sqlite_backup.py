"""Publish a verified SQLite backup atomically without replacing an existing file."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile


def backup_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, staging = tempfile.mkstemp(dir=destination.parent, prefix=".egx-backup-")
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(staging)) as backup:
                original.backup(backup)
                if backup.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                    raise ValueError("SQLite backup integrity check failed")
        # Atomic create-if-absent. Concurrent startups cannot replace a live DB.
        os.link(staging, destination)
    finally:
        os.unlink(staging)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    backup_database(args.source, args.destination)
