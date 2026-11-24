import hashlib
import hmac
import sqlite3
import time

from pydantic import ValidationError

from app.integrations.openai_client import (
    PROMPT_VERSION,
    SCHEMA_VERSION,
    STRATEGY_VERSION,
    estimate_input,
    interpret,
    serialized,
)
from app.schemas.ai_analysis import InterpretationSelection
from app.services.ai_budget_manager import ATTEMPTS, AIBudgetManager, token_cost
from app.services.ai_context_builder import PHRASES, model_context


def validated_selection(selection, report):
    parsed = InterpretationSelection.model_validate(selection)
    codes = parsed.priority
    available = set(report.supporting + report.opposing)
    if (
        not codes
        or len(codes) > 5
        or len(set(codes)) != len(codes)
        or not set(codes) <= available
    ):
        raise ValueError("Evidence was not supported by the checked context")
    return codes


def explain(report, request, config, owner_scope):
    report.ai_status = config.status
    if config.status != "CONFIGURED":
        return report
    if not request.explain or report.risk_blockers:
        report.ai_status = "DETERMINISTIC_ONLY"
        return report
    if not report.levels or report.signal in {
        "NO_TRADE",
        "DATA_NOT_CURRENT",
        "INSUFFICIENT_DATA",
    }:
        report.ai_status = "NOT_A_CANDIDATE"
        return report

    # The cache uses private analysis fields but only stores the digest and output evidence.
    # None of these private fields are included in the model payload.
    snapshot = report.model_dump(mode="json", exclude={"expires_at", "ai_status"})
    key_fields = (
        config.OPENAI_MODEL,
        PROMPT_VERSION,
        SCHEMA_VERSION,
        STRATEGY_VERSION,
        config.AI_MAX_OUTPUT_TOKENS,
        snapshot,
        request.model_dump(mode="json"),
    )
    key = hmac.new(
        owner_scope, serialized(key_fields).encode(), hashlib.sha256
    ).hexdigest()
    cadence = hmac.new(owner_scope, report.ticker.encode(), hashlib.sha256).hexdigest()
    context = model_context(report)
    estimate = token_cost(
        config.rates, estimate_input(context), config.AI_MAX_OUTPUT_TOKENS
    )
    ledger = AIBudgetManager()
    try:
        status, value = ledger.acquire(config, key, cadence, estimate)
        if status == "CACHED":
            codes = validated_selection({"priority": value}, report)
            report.ai_explanation_ar = " ".join(PHRASES[code] for code in codes)
            report.ai_status = "CACHED"
        elif status != "RESERVED":
            report.ai_status = status
        else:
            execute_reserved(report, config, context, ledger, value, estimate)
    except (OSError, sqlite3.Error, ValueError):
        report.ai_status = "LEDGER_UNAVAILABLE"
    return report


def execute_reserved(report, config, context, ledger, request_id, estimate):
    input_tokens = output_tokens = charged = 0
    selected = None
    for attempt in range(ATTEMPTS):
        completion = interpret(config, context)
        status = completion.status
        if completion.input_tokens is None or completion.output_tokens is None:
            charged += estimate
        else:
            input_tokens += completion.input_tokens
            output_tokens += completion.output_tokens
            charged += token_cost(
                config.rates, completion.input_tokens, completion.output_tokens
            )
        if status == "OK":
            try:
                selected = validated_selection(completion.selection, report)
            except (ValueError, ValidationError):
                status = "INVALID_RESPONSE"
        if (
            status != "RATE_LIMITED"
            or completion.retry_after is None
            or completion.retry_after > 1
            or attempt + 1 == ATTEMPTS
        ):
            break
        time.sleep(max(0.2, completion.retry_after))
    ledger.finish(
        request_id,
        status,
        charged,
        input_tokens,
        output_tokens,
        selected,
        config.AI_CACHE_TTL_SECONDS,
    )
    report.ai_status = status
    report.usage = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_ceiling_usd": estimate * ATTEMPTS / 1e6,
        "estimated_charge_usd": charged / 1e6,
    }
    if selected:
        report.ai_explanation_ar = " ".join(PHRASES[code] for code in selected)
