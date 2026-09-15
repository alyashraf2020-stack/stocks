import datetime
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.services.data_provider.base import BaseHistoricalProvider
from app.services.data_provider.yahoo_provider import YahooEGXProvider
from app.services.data_provider.directfn_provider import DirectFNCompletedSessionProvider
from app.services.data_provider.investing_provider import InvestingHistoricalProvider
from app.services.data_provider.investing_legacy_provider import InvestingLegacySearchProvider
from app.services.data_provider.stooq_provider import StooqEGXProvider
from app.services.validator import CandleValidator
from app.services.egx_calendar import (
    get_expected_latest_completed_session,
    calculate_sessions_behind,
    get_freshness_label,
    get_freshness_display_ar,
    is_egx_trading_day,
    CAIRO_TZ,
)
from app.models.candle import EGXCandle
from app.models.security import EGXSecurity


class ProviderManager:
    # A single public source is not allowed to splice a very large one-session
    # price discontinuity into an otherwise continuous EOD series. Such jumps can
    # be caused by stale feeds, reference-price adjustments or corporate actions.
    # We require an independent provider to corroborate the same completed date.
    MAX_UNCORROBORATED_CLOSE_MOVE = 0.25
    CORROBORATION_PRICE_TOLERANCE = 0.03

    def __init__(
        self,
        primary_provider: Optional[BaseHistoricalProvider] = None,
        fallback_providers: Optional[List[BaseHistoricalProvider]] = None,
    ):
        # No API key or secret is required. The platform uses public market-data
        # sources only and keeps the strict zero-session-lag rule.
        self.primary_provider: BaseHistoricalProvider = primary_provider or YahooEGXProvider()
        self.fallback_providers: List[BaseHistoricalProvider] = fallback_providers or [
            DirectFNCompletedSessionProvider(),
            InvestingHistoricalProvider(),
            InvestingLegacySearchProvider(),
            StooqEGXProvider(),
        ]

    @classmethod
    def _is_large_close_jump(cls, previous_close: Any, bar: Dict[str, Any]) -> bool:
        try:
            prev = float(previous_close)
            close = float(bar.get("close"))
        except (TypeError, ValueError):
            return True
        if prev <= 0 or close <= 0:
            return True
        return abs(close / prev - 1.0) > cls.MAX_UNCORROBORATED_CLOSE_MOVE

    @classmethod
    def _bars_corroborate(cls, first: Dict[str, Any], second: Dict[str, Any]) -> bool:
        if first.get("session_date") != second.get("session_date"):
            return False

        for field in ("open", "high", "low", "close"):
            try:
                a = float(first.get(field))
                b = float(second.get(field))
            except (TypeError, ValueError):
                return False
            if a <= 0 or b <= 0:
                return False
            baseline = max(abs(a), abs(b))
            if baseline == 0:
                return False
            if abs(a - b) / baseline > cls.CORROBORATION_PRICE_TOLERANCE:
                return False
        return True

    @staticmethod
    def _missing_completed_sessions(
        latest_session: datetime.date,
        expected_session: datetime.date,
    ) -> List[datetime.date]:
        """Return every EGX trading session missing between latest and expected.

        This matters when a provider is more than one session late. For example,
        if KORA stops at Sep 13 while Sep 15 is expected, the manager must first
        recover Sep 14, then try Sep 15. It must not jump directly from Sep 13 to
        Sep 15 and leave a hole in the analytical series.
        """
        sessions: List[datetime.date] = []
        cursor = latest_session + datetime.timedelta(days=1)
        while cursor <= expected_session:
            if is_egx_trading_day(cursor):
                sessions.append(cursor)
            cursor += datetime.timedelta(days=1)
        return sessions

    def _security_english_name(self, db: Optional[Session], ticker: str) -> Optional[str]:
        if db is None:
            return None
        try:
            sec = db.query(EGXSecurity).filter(EGXSecurity.ticker == ticker).first()
            return sec.english_name if sec else None
        except Exception:
            return None

    def _fetch_provider_bars(
        self,
        provider: BaseHistoricalProvider,
        ticker: str,
        limit: int,
        english_name: Optional[str],
    ) -> List[Dict[str, Any]]:
        if isinstance(provider, InvestingHistoricalProvider):
            return provider.fetch_historical_bars_for_security(
                ticker=ticker,
                english_name=english_name,
                limit=limit,
            )
        return provider.fetch_historical_bars(ticker, limit=limit)

    def _fetch_provider_session_bar(
        self,
        provider: BaseHistoricalProvider,
        ticker: str,
        session_date: str,
        english_name: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        if isinstance(provider, InvestingHistoricalProvider):
            return provider.fetch_session_bar_for_security(
                ticker=ticker,
                session_date=session_date,
                english_name=english_name,
            )
        return provider.fetch_session_bar(ticker, session_date)

    def _recover_one_missing_session(
        self,
        best_bars: List[Dict[str, Any]],
        ticker: str,
        session_date: str,
        english_name: Optional[str],
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Recover exactly one missing completed session from fallback sources.

        A large one-session price jump still requires corroboration from a second
        independent provider. Normal-sized bars can be accepted from one source.
        """
        pending_outlier: Optional[Tuple[Dict[str, Any], str]] = None

        for fallback in self.fallback_providers:
            try:
                missing_bar = self._fetch_provider_session_bar(
                    provider=fallback,
                    ticker=ticker,
                    session_date=session_date,
                    english_name=english_name,
                )
                if missing_bar is None:
                    continue

                validated_missing = CandleValidator.validate_bar(missing_bar)
                if validated_missing.get("hlcv_status") != "VALID":
                    continue
                if validated_missing.get("session_date") != session_date:
                    continue

                previous_close = best_bars[-1].get("close") if best_bars else None
                if self._is_large_close_jump(previous_close, validated_missing):
                    if pending_outlier is None:
                        pending_outlier = (validated_missing, fallback.provider_name)
                        continue

                    first_bar, first_provider = pending_outlier
                    if not self._bars_corroborate(first_bar, validated_missing):
                        continue

                    return (
                        validated_missing,
                        f"{first_provider} + {fallback.provider_name} confirmed discontinuity",
                    )

                return (
                    validated_missing,
                    missing_bar.get("actual_provider", fallback.provider_name),
                )
            except Exception:
                continue

        return None, None

    def get_raw_historical_bars(
        self,
        ticker: str,
        limit: int = 250,
        db: Optional[Session] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        clean_ticker = ticker.strip().upper()
        now_cairo = datetime.datetime.now(CAIRO_TZ)
        expected_session = get_expected_latest_completed_session(now_cairo)
        expected_session_str = expected_session.isoformat()
        english_name = self._security_english_name(db, clean_ticker)

        # Keep a validated local-cache baseline even when it is stale. Previously,
        # if every public full-history request failed temporarily, we threw away a
        # perfectly good cached history and returned DATA_UNAVAILABLE / 0 bars.
        # The cache is safe to use as the historical baseline; the strict
        # zero-session-lag gate still prevents actionable analysis until missing
        # completed sessions are recovered.
        cached_baseline_bars: List[Dict[str, Any]] = []
        cached_baseline_provider: Optional[str] = None
        cached_baseline_sessions_behind: Optional[int] = None

        if db is not None and not force_refresh:
            cached_rows = (
                db.query(EGXCandle)
                .filter(EGXCandle.ticker == clean_ticker)
                .order_by(EGXCandle.session_date.asc())
                .all()
            )

            # Repair a previously cached single-source outlier at the tail. A
            # user-verified EOD candle is intentionally not deleted here.
            if len(cached_rows) >= 2:
                last_cached = cached_rows[-1]
                previous_cached = cached_rows[-2]
                is_user_verified = last_cached.actual_provider == "USER_VERIFIED_EOD"
                if (
                    not is_user_verified
                    and self._is_large_close_jump(previous_cached.close, last_cached.to_dict())
                ):
                    try:
                        db.delete(last_cached)
                        db.commit()
                        cached_rows = cached_rows[:-1]
                    except Exception:
                        db.rollback()

            if cached_rows:
                cached_raw = [c.to_dict() for c in cached_rows[-limit:]]
                cached_validated = CandleValidator.validate_bars(cached_raw)
                cached_validated = [
                    b for b in cached_validated if b.get("hlcv_status") == "VALID"
                ]
                if cached_validated:
                    cached_baseline_bars = cached_validated
                    cached_baseline_provider = cached_rows[-1].actual_provider
                    cached_latest_date = datetime.date.fromisoformat(
                        cached_validated[-1]["session_date"]
                    )
                    cached_baseline_sessions_behind = calculate_sessions_behind(
                        cached_latest_date,
                        now_cairo,
                    )

                    if cached_baseline_sessions_behind == 0:
                        has_min_history = len(cached_validated) >= 50
                        is_eligible = has_min_history
                        status = "SUCCESS" if is_eligible else "INSUFFICIENT_DATA"
                        return {
                            "status": status,
                            "ticker": clean_ticker,
                            "actual_provider": cached_baseline_provider,
                            "raw_bars_count": len(cached_validated),
                            "analytical_bars_count": len(cached_validated),
                            "expected_latest_session": expected_session_str,
                            "latest_available_session": cached_validated[-1]["session_date"],
                            "sessions_behind": 0,
                            "freshness": "CURRENT",
                            "freshness_ar": "محدث",
                            "current_analysis_eligible": is_eligible,
                            "bars": cached_validated,
                        }

        # Start from the local validated history when available, then let fresher
        # public providers replace it. This guarantees we never collapse from
        # hundreds of known bars to zero merely because an upstream site times out.
        best_bars: List[Dict[str, Any]] = list(cached_baseline_bars)
        best_provider: Optional[str] = cached_baseline_provider
        best_sessions_behind: Optional[int] = cached_baseline_sessions_behind

        all_providers = [self.primary_provider] + self.fallback_providers
        current_outlier_candidates: List[Tuple[str, List[Dict[str, Any]]]] = []

        for provider in all_providers:
            try:
                raw_p_bars = self._fetch_provider_bars(
                    provider=provider,
                    ticker=clean_ticker,
                    limit=limit,
                    english_name=english_name,
                )
                if not raw_p_bars:
                    continue

                val_p_bars = CandleValidator.validate_bars(raw_p_bars)
                val_p_bars = [
                    b for b in val_p_bars if b.get("hlcv_status") == "VALID"
                ]
                if not val_p_bars:
                    continue

                p_latest_date = datetime.date.fromisoformat(val_p_bars[-1]["session_date"])
                p_sessions_behind = calculate_sessions_behind(p_latest_date, now_cairo)

                if p_sessions_behind == 0:
                    latest_is_outlier = (
                        len(val_p_bars) >= 2
                        and self._is_large_close_jump(
                            val_p_bars[-2].get("close"),
                            val_p_bars[-1],
                        )
                    )
                    if latest_is_outlier:
                        corroborated_by = None
                        for candidate_provider, candidate_bars in current_outlier_candidates:
                            if candidate_bars and self._bars_corroborate(
                                candidate_bars[-1], val_p_bars[-1]
                            ):
                                corroborated_by = candidate_provider
                                break
                        if corroborated_by is not None:
                            best_bars = val_p_bars
                            best_provider = (
                                f"{provider.provider_name} + {corroborated_by} confirmed"
                            )
                            best_sessions_behind = 0
                            break
                        current_outlier_candidates.append((provider.provider_name, val_p_bars))
                        continue

                    best_bars = val_p_bars
                    best_provider = provider.provider_name
                    best_sessions_behind = 0
                    break

                if best_sessions_behind is None or (
                    p_sessions_behind is not None and p_sessions_behind < best_sessions_behind
                ):
                    best_bars = val_p_bars
                    best_provider = provider.provider_name
                    best_sessions_behind = p_sessions_behind
            except Exception:
                continue

        # Backfill every missing completed trading session in order. If a series
        # ends on Sep 13 while Sep 15 is expected, recover Sep 14 first, then Sep
        # 15. If Sep 15 is unavailable we still keep Sep 14 and report one session
        # behind instead of throwing away all historical bars.
        if best_bars and best_sessions_behind is not None and best_sessions_behind > 0:
            latest_best_date = datetime.date.fromisoformat(best_bars[-1]["session_date"])
            missing_sessions = self._missing_completed_sessions(
                latest_best_date,
                expected_session,
            )

            recovered_providers: List[str] = []
            for missing_date in missing_sessions:
                missing_date_str = missing_date.isoformat()
                recovered_bar, recovered_provider = self._recover_one_missing_session(
                    best_bars=best_bars,
                    ticker=clean_ticker,
                    session_date=missing_date_str,
                    english_name=english_name,
                )
                if recovered_bar is None:
                    break

                if not any(
                    b.get("session_date") == recovered_bar.get("session_date")
                    for b in best_bars
                ):
                    best_bars.append(recovered_bar)
                    best_bars.sort(key=lambda x: x["session_date"])
                if recovered_provider:
                    recovered_providers.append(recovered_provider)

            if best_bars:
                final_latest_date = datetime.date.fromisoformat(best_bars[-1]["session_date"])
                best_sessions_behind = calculate_sessions_behind(final_latest_date, now_cairo)
                if recovered_providers:
                    unique_recovered = list(dict.fromkeys(recovered_providers))
                    base_provider = best_provider or "Cached EOD history"
                    best_provider = base_provider + " + " + " + ".join(unique_recovered)

        if not best_bars:
            return {
                "status": "DATA_UNAVAILABLE",
                "ticker": clean_ticker,
                "actual_provider": None,
                "raw_bars_count": 0,
                "analytical_bars_count": 0,
                "expected_latest_session": expected_session_str,
                "latest_available_session": None,
                "sessions_behind": None,
                "freshness": "DATA_UNAVAILABLE",
                "freshness_ar": "غير متاح",
                "current_analysis_eligible": False,
                "bars": [],
            }

        validated_bars = best_bars
        active_provider = best_provider
        sessions_behind = best_sessions_behind

        is_current = sessions_behind == 0
        has_min_history = len(validated_bars) >= 50
        is_eligible = is_current and has_min_history

        if not is_current:
            status = "DATA_NOT_CURRENT"
        elif not has_min_history:
            status = "INSUFFICIENT_DATA"
        else:
            status = "SUCCESS"

        freshness_label = get_freshness_label(sessions_behind)
        freshness_ar = get_freshness_display_ar(sessions_behind)

        if db is not None:
            try:
                for b in validated_bars:
                    existing = (
                        db.query(EGXCandle)
                        .filter(
                            EGXCandle.ticker == clean_ticker,
                            EGXCandle.session_date == b["session_date"],
                        )
                        .first()
                    )
                    if not existing:
                        candle_record = EGXCandle(
                            ticker=clean_ticker,
                            session_date=b["session_date"],
                            open=b["open"],
                            high=b["high"],
                            low=b["low"],
                            close=b["close"],
                            volume=b["volume"],
                            actual_provider=b.get("actual_provider", active_provider),
                            validation_status=b["validation_status"],
                        )
                        db.add(candle_record)
                db.commit()
            except Exception:
                db.rollback()

        return {
            "status": status,
            "ticker": clean_ticker,
            "actual_provider": active_provider,
            "raw_bars_count": len(validated_bars),
            "analytical_bars_count": len(validated_bars),
            "expected_latest_session": expected_session_str,
            "latest_available_session": validated_bars[-1]["session_date"],
            "sessions_behind": sessions_behind,
            "freshness": freshness_label,
            "freshness_ar": freshness_ar,
            "current_analysis_eligible": is_eligible,
            "bars": validated_bars,
        }

    def get_analytical_bars(
        self,
        ticker: str,
        limit: int = 250,
        db: Optional[Session] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        raw_result = self.get_raw_historical_bars(
            ticker,
            limit=limit,
            db=db,
            force_refresh=force_refresh,
        )
        if raw_result["status"] == "DATA_UNAVAILABLE":
            return raw_result

        raw_bars = raw_result["bars"]
        analytical_bars = CandleValidator.extract_analytical_bars(raw_bars)

        invalid_hlcv_count = sum(
            1 for b in raw_bars if b.get("hlcv_status") != "VALID"
        )
        open_unverified_count = sum(
            1
            for b in raw_bars
            if b.get("open_status")
            in ("OPEN_UNVERIFIED", "OPEN_REFERENCE_ARTIFACT", "INVALID_OPEN")
        )

        first_session = analytical_bars[0]["session_date"] if analytical_bars else None
        latest_session = analytical_bars[-1]["session_date"] if analytical_bars else None

        is_current = raw_result.get("sessions_behind") == 0
        has_min_history = len(analytical_bars) >= 50
        is_eligible = is_current and has_min_history

        if not is_current:
            status = "DATA_NOT_CURRENT"
        elif not has_min_history:
            status = "INSUFFICIENT_DATA"
        else:
            status = "SUCCESS"

        return {
            "status": status,
            "ticker": raw_result["ticker"],
            "actual_provider": raw_result["actual_provider"],
            "raw_bars_count": raw_result["raw_bars_count"],
            "analytical_bars_count": len(analytical_bars),
            "invalid_hlcv_bars": invalid_hlcv_count,
            "open_unverified_bars": open_unverified_count,
            "first_session": first_session,
            "latest_session": latest_session,
            "expected_latest_session": raw_result["expected_latest_session"],
            "sessions_behind": raw_result["sessions_behind"],
            "freshness": raw_result.get("freshness", "DATA_NOT_CURRENT"),
            "freshness_ar": raw_result.get("freshness_ar", "غير محدث"),
            "current_analysis_eligible": is_eligible,
            "bars": analytical_bars,
        }


default_provider_manager = ProviderManager()
