"""Backtest subprocesses have their own lease queue and wall-clock budget."""

import multiprocessing
import os
import signal
import threading
import time

from sqlalchemy.exc import OperationalError

from app.core.database import SessionLocal
from app.services.backtesting import (
    TIMEOUT_SECONDS,
    claim,
    configuration,
    finish,
    heartbeat,
)


def compute(pipe, key):
    from app.services.backtest_engine import run

    try:
        with SessionLocal() as db:
            config = configuration(db, key)
        result = run(config, lambda point: pipe.send(("PROGRESS", point)))
        pipe.send(("RESULT", result))
    except ValueError as err:
        code = str(err)
        pipe.send(
            (
                "ERROR",
                code
                if code
                in {
                    "UNMODELED_CORPORATE_ACTION",
                    "UNMODELED_DELISTING",
                    "FRACTIONAL_CORPORATE_ACTION",
                }
                else "BACKTEST_DATA_OR_CONFIGURATION_INVALID",
            )
        )
    except Exception:  # noqa: BLE001 — redact worker internals.
        pipe.send(("ERROR", "BACKTEST_COMPUTE_FAILED"))
    finally:
        pipe.close()


def run_job(key, token, stop):
    context = multiprocessing.get_context("spawn")
    read, send = context.Pipe(duplex=False)
    task = context.Process(target=compute, args=(send, key), daemon=True)
    task.start()
    send.close()
    deadline = time.monotonic() + TIMEOUT_SECONDS
    next_beat = 0
    progress = 0
    try:
        while not stop.is_set():
            clock = time.monotonic()
            if clock >= deadline:
                with SessionLocal() as db:
                    finish(db, key, token, time.time(), error="BACKTEST_TIME_LIMIT")
                return
            if clock >= next_beat:
                with SessionLocal() as db:
                    if not heartbeat(db, key, token, time.time(), progress):
                        return
                next_beat = clock + 2
            if not read.poll(0.2):
                if not task.is_alive():
                    with SessionLocal() as db:
                        finish(db, key, token, time.time(), error="WORKER_EXITED")
                    return
                continue
            try:
                kind, payload = read.recv()
            except EOFError:
                kind, payload = "ERROR", "WORKER_EXITED"
            if kind == "PROGRESS":
                progress = payload
                continue
            with SessionLocal() as db:
                finish(
                    db,
                    key,
                    token,
                    time.time(),
                    result=payload if kind == "RESULT" else None,
                    error=payload if kind == "ERROR" else None,
                )
            return
    finally:
        read.close()
        if task.is_alive():
            task.terminate()
        task.join(2)
        if task.is_alive():
            task.kill()
            task.join()


def main():
    os.umask(0o077)
    stop = threading.Event()
    for item in (signal.SIGINT, signal.SIGTERM):
        signal.signal(item, lambda *_: stop.set())
    while not stop.is_set():
        try:
            with SessionLocal() as db:
                job = claim(db, time.time())
            if job:
                run_job(*job, stop)
        except OperationalError:
            print("BACKTEST_DATABASE_UNAVAILABLE", flush=True)
        stop.wait(2)


if __name__ == "__main__":
    main()
