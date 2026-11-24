from datetime import datetime, timedelta, timezone

from app.schemas.thndr import CheckedQuote, Quote


def validate_quote(
    quote: Quote,
    *,
    ticker: str,
    instrument_id: str | None,
    realtime_providers: frozenset[str] = frozenset(),
    now: datetime | None = None,
    max_age: timedelta = timedelta(seconds=60),
) -> CheckedQuote:
    """The source adapter supplies classification; entitlement is independent of the payload."""
    now = now or datetime.now(timezone.utc)
    source = quote.source_timestamp
    freshness, validation = "UNKNOWN", "UNVERIFIED"
    if (
        quote.ticker != ticker
        or not instrument_id
        or quote.instrument_id != instrument_id
        or quote.exchange != "EGX"
        or quote.currency != "EGP"
        or quote.retrieved_at > now
        or (source and source > quote.retrieved_at)
    ):
        validation = "INVALID"
    elif quote.delay_class in ("HISTORICAL", "MANUAL"):
        freshness = quote.delay_class
        validation = "VALID" if source else "UNVERIFIED"
    elif source is None:
        pass
    elif quote.delay_class == "DELAYED":
        freshness, validation = "DELAYED", "VALID"
    elif now - source > max_age:
        freshness, validation = "STALE", "VALID"
    elif (
        quote.delay_class == "REALTIME"
        and quote.provider in realtime_providers
        and quote.session_status == "OPEN"
    ):
        freshness, validation = "REALTIME_VERIFIED", "VALID"
    return CheckedQuote(
        **quote.model_dump(),
        freshness=freshness,
        validation_status=validation,
        eligible_for_proposal=freshness == "REALTIME_VERIFIED",
    )
