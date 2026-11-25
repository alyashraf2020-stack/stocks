"""Run independently of the site and scanner. Secrets only come from the environment."""

import os
import signal
import threading
import time

from sqlalchemy.exc import OperationalError

from app.core.database import SessionLocal
from app.services.notification_delivery import delivery_step, env, prune
from app.services.worker_pulse import pulse


def main():
    os.umask(0o077)
    settings = env()
    stop = threading.Event()
    for item in (signal.SIGINT, signal.SIGTERM):
        signal.signal(item, lambda *_: stop.set())
    maintenance = 0
    while not stop.is_set():
        try:
            now = time.time()
            pulse(SessionLocal, "notifications", now)
            if now - maintenance > 3600:
                with SessionLocal() as db:
                    prune(db, now)
                maintenance = now
            for channel in ("TELEGRAM", "PUSH"):
                if not stop.is_set():
                    delivery_step(SessionLocal, channel, time.time, settings)
        except OperationalError:
            print("NOTIFICATION_DATABASE_UNAVAILABLE", flush=True)
        stop.wait(2)


if __name__ == "__main__":
    main()
