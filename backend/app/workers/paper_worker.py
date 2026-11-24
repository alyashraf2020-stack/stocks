"""One virtual-account writer loop. Each session commit is independently restartable."""

import os
import signal
import threading
from datetime import datetime

from sqlalchemy.exc import OperationalError

from app.core.database import SessionLocal
from app.services.paper_trading import process_batch
from app.services.scanner_calendar import CAIRO


def main():
    os.umask(0o077)
    stop = threading.Event()
    for key in (signal.SIGINT, signal.SIGTERM):
        signal.signal(key, lambda *_: stop.set())
    while not stop.is_set():
        try:
            process_batch(SessionLocal, datetime.now(CAIRO))
        except OperationalError:
            print("VIRTUAL_DATABASE_UNAVAILABLE", flush=True)
        stop.wait(5)


if __name__ == "__main__":
    main()
