"""Persistent, atomic single-host budget ledger and private interpretation cache."""

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path

from app.core.config import BACKEND_ROOT
from app.services.egx_calendar import CAIRO_TZ

ATTEMPTS = 2
UNITS = Decimal("1000000")


def micros(dollars):
    return int((dollars * UNITS).to_integral_value(rounding=ROUND_CEILING))


def token_cost(rates, input_tokens, output_tokens):
    return int(
        (rates[0] * input_tokens + rates[1] * output_tokens).to_integral_value(
            rounding=ROUND_CEILING
        )
    )


def periods(now):
    local = datetime.fromtimestamp(now, tz=CAIRO_TZ)
    return local.date().isoformat(), local.strftime("%Y-%m")


class AIBudgetManager:
    def __init__(self):
        self.path = Path(
            os.getenv(
                "AI_LEDGER_PATH", str(BACKEND_ROOT / "instance" / "ai_usage.sqlite3")
            )
        )

    @contextmanager
    def transaction(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(descriptor)
        db = sqlite3.connect(self.path, timeout=3)
        try:
            with db:
                db.execute("""CREATE TABLE IF NOT EXISTS ai_requests (
                    id TEXT PRIMARY KEY, key TEXT NOT NULL, cadence_key TEXT NOT NULL,
                    started REAL NOT NULL, day TEXT NOT NULL, month TEXT NOT NULL,
                    charged INTEGER NOT NULL, reserved INTEGER NOT NULL, input_tokens INTEGER,
                    output_tokens INTEGER, status TEXT NOT NULL, cache_until REAL, result TEXT
                )""")
                db.execute(
                    "CREATE INDEX IF NOT EXISTS ai_requests_period ON ai_requests(month, day)"
                )
                db.execute(
                    "CREATE INDEX IF NOT EXISTS ai_requests_key ON ai_requests(key, started)"
                )
                db.execute(
                    "CREATE INDEX IF NOT EXISTS ai_requests_cadence ON ai_requests(cadence_key, started)"
                )
                db.execute("BEGIN IMMEDIATE")
                yield db
        finally:
            db.close()

    def acquire(self, config, key, cadence_key, estimate):
        now = time.time()
        day, month = periods(now)
        with self.transaction() as db:
            cache = db.execute(
                "SELECT result FROM ai_requests WHERE key=? AND cache_until>? ORDER BY started DESC LIMIT 1",
                (key, now),
            ).fetchone()
            if cache:
                return "CACHED", json.loads(cache[0])
            pending = db.execute(
                "SELECT 1 FROM ai_requests WHERE key=? AND status='PENDING' AND started>?",
                (key, now - 120),
            ).fetchone()
            if pending:
                return "IN_PROGRESS", None
            failures = db.execute(
                "SELECT status, started FROM ai_requests WHERE status!='PENDING' ORDER BY started DESC LIMIT 3"
            ).fetchall()
            if len(failures) == 3 and all(
                s in {"TIMEOUT", "RATE_LIMITED", "UNAVAILABLE"} and t > now - 90
                for s, t in failures
            ):
                return "CIRCUIT_OPEN", None
            recent = db.execute(
                "SELECT COUNT(*) FROM ai_requests WHERE started>?", (now - 60,)
            ).fetchone()[0]
            last = db.execute(
                "SELECT MAX(started) FROM ai_requests WHERE cadence_key=?",
                (cadence_key,),
            ).fetchone()[0]
            if recent >= config.AI_REQUESTS_PER_MINUTE or (
                last and now - last < config.AI_MIN_ANALYSIS_INTERVAL_SECONDS
            ):
                return "RATE_LIMITED", None
            daily, monthly = db.execute(
                "SELECT COALESCE(SUM(CASE WHEN day=? THEN charged ELSE 0 END),0), COALESCE(SUM(charged),0) FROM ai_requests WHERE month=?",
                (day, month),
            ).fetchone()
            reserve = estimate * ATTEMPTS
            if daily + reserve > micros(
                config.AI_DAILY_BUDGET_USD
            ) or monthly + reserve > micros(config.AI_MONTHLY_BUDGET_USD):
                return "BUDGET_EXHAUSTED", None
            request_id = uuid.uuid4().hex
            db.execute(
                """INSERT INTO ai_requests(id,key,cadence_key,started,day,month,charged,reserved,status)
                   VALUES (?,?,?,?,?,?,?,?,'PENDING')""",
                (request_id, key, cadence_key, now, day, month, reserve, reserve),
            )
            return "RESERVED", request_id

    def finish(
        self, request_id, status, charged, input_tokens, output_tokens, selected, ttl
    ):
        with self.transaction() as db:
            db.execute(
                """UPDATE ai_requests SET charged=?, input_tokens=?, output_tokens=?, status=?, cache_until=?, result=?
                   WHERE id=? AND status='PENDING'""",
                (
                    charged,
                    input_tokens,
                    output_tokens,
                    status,
                    time.time() + ttl if selected else None,
                    json.dumps(selected) if selected else None,
                    request_id,
                ),
            )

    def usage(self):
        day, month = periods(time.time())
        with self.transaction() as db:
            daily, monthly, input_tokens, output_tokens = db.execute(
                """SELECT COALESCE(SUM(CASE WHEN day=? THEN charged ELSE 0 END),0), COALESCE(SUM(charged),0),
                          COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0)
                   FROM ai_requests WHERE month=?""",
                (day, month),
            ).fetchone()
        return dict(
            daily_estimated_usd=daily / 1e6,
            monthly_estimated_usd=monthly / 1e6,
            monthly_input_tokens=input_tokens,
            monthly_output_tokens=output_tokens,
        )
