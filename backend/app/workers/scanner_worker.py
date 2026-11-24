"""Run with python -m app.workers.scanner_worker, using the same private DB as FastAPI."""

import logging
import multiprocessing as mp
import os
import signal
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.exc import OperationalError

from app.core.database import SessionLocal
from app.models.scheduled_job import ScheduledJob
from app.schemas.scanner import ENV
from app.services.scanner_repository import (
    claim,
    fail,
    heartbeat,
    prune,
    publish,
    renew,
)
from app.workers.trading_scheduler import tick

LOG = logging.getLogger("egx.scanner")


def compute(pipe, job):
    from app.services.market_scanner import collect

    # Scanner operational logs use fixed codes. Provider exceptions never reach stdout.
    logging.disable(logging.CRITICAL)
    try:
        pipe.send(("OK", collect(SessionLocal, job, datetime.now(UTC))))
    except Exception:  # noqa: BLE001 — The parent receives only fixed failure codes.
        pipe.send(("ERROR", None))
    finally:
        pipe.close()


async def finish_broker(job_id, token, data):
    from app.services.scanner_broker import local_broker_state

    async with local_broker_state(data["broker_sync"]) as authorized:
        if not authorized:
            data = {"error": "THNDR_AUTHORIZATION_OR_SYNC_REQUIRED", "rows": []}
        with SessionLocal() as db:
            return publish(db, job_id, token, time.time(), data)


def run_job(job_id, token, worker, stop):
    import asyncio

    with SessionLocal() as db:
        row = db.get(ScheduledJob, job_id)
        job = {k: getattr(row, k) for k in ("session", "mode", "revision")}
    ctx = mp.get_context("spawn")
    read, send = ctx.Pipe(duplex=False)
    process = ctx.Process(target=compute, args=(send, job), daemon=True)
    process.start()
    send.close()
    started = time.monotonic()
    next_beat = started
    failure = "WORKER_SHUTDOWN"
    try:
        while not stop.is_set():
            monotonic = time.monotonic()
            if monotonic - started >= ENV.SCANNER_JOB_TIMEOUT_SECONDS:
                failure = "JOB_TIMEOUT"
                break
            if monotonic >= next_beat:
                now = time.time()
                with SessionLocal() as db:
                    if not renew(db, job_id, token, now):
                        return
                with SessionLocal() as db:
                    heartbeat(db, worker, now, job_id)
                next_beat = monotonic + ENV.SCANNER_HEARTBEAT_SECONDS
            if read.poll(0.25):
                try:
                    result, payload = read.recv()
                except EOFError:
                    result, payload = "ERROR", None
                if result == "OK":
                    if payload.get("broker_sync"):
                        saved = asyncio.run(finish_broker(job_id, token, payload))
                    else:
                        with SessionLocal() as db:
                            saved = publish(db, job_id, token, time.time(), payload)
                    LOG.info("job=%d %s", job_id, "published" if saved else "fenced")
                    return
                failure = "SCAN_COMPUTE_FAILED"
                break
            if not process.is_alive():
                failure = "SCAN_PROCESS_EXITED"
                break
        with SessionLocal() as db:
            fail(db, job_id, token, time.time(), failure)
        LOG.warning("job=%d %s", job_id, failure)
    finally:
        read.close()
        if process.is_alive():
            process.terminate()
        process.join(3)
        if process.is_alive():
            process.kill()
            process.join()


def main():
    os.umask(0o077)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    stop = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stop.set())
    worker = uuid4().hex
    last_prune = 0
    LOG.info("scanner worker started")
    while not stop.is_set():
        now = time.time()
        try:
            with SessionLocal() as db:
                heartbeat(db, worker, now)
            if now - last_prune >= 3600:
                with SessionLocal() as db:
                    prune(db, now)
                last_prune = now
            tick(SessionLocal, now)
            with SessionLocal() as db:
                job = claim(db, now)
            if job:
                run_job(*job, worker, stop)
        except OperationalError:
            LOG.warning("database unavailable; verify migration and database path")
        stop.wait(ENV.SCANNER_HEARTBEAT_SECONDS)
    LOG.info("scanner worker stopped")


if __name__ == "__main__":
    main()
