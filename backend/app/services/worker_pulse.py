import time

from app.models.delivery import WorkerPulse
from app.services.scanner_repository import writer


def pulse(factory, role, now=None):
    with factory() as db, writer(db):
        db.merge(WorkerPulse(role=role, seen=time.time() if now is None else now))
