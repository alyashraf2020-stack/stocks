import datetime
from typing import List, Dict, Any, Optional
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
    CAIRO_TZ
)
from app.models.candle import EGXCandle
from app.models.security import EGXSecurity


class ProviderManager:
    def __init__(
        self,
        primary_provider: Optional[BaseHistoricalProvider] = None,
        fallback_providers: Optional[List[BaseHistoricalProvider]] = None
    ):
        # No API key or secret is required. The platform uses public market-data
        # sources only and keeps the strict zero-session-lag rule.
        self.primary_provider: BaseHistoricalProvider = primary_provider or YahooEGXProvider()
        self.fallback_providers: List[BaseHistoricalProvider] = fallback_providers or [
            # DirectFN exposes the latest completed EGX trading table with an
            # explicit market date, so try it first for a missing latest session.
            DirectFNCompletedSessionProvider(),
            InvestingHistoricalProvider(),
            InvestingLegacySearchProvider(),
            StooqEGXProvider(),
        ]

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

    def get_raw_historical_bars(
        self, ticker: str, limit: int = 250, db: Optional[Session] = None, force_refresh: bool = False
    ) -> Dict[str, Any]:
        clean_ticker = ticker.strip().upper()
        now_cairo = datetime.datetime.now(CAIRO_TZ)
        expected_session = get_expected_latest_completed_session(now_cairo)
        expected_session_str = expected_session.isoformat()
        english_name = self._security_english_name(db, clean_ticker)

        if db is not None and not force_refresh:
            cached_rows = (
                db.query(EGXCandle)
                .filter(EGXCandle.ticker == clean_ticker)
                .order_by(EGXCandle.session_date.asc())
                .all()
            )
            if cached_rows and len(cached_rows) >= 20:
                last_cached = cached_rows[-1]
                last_cached_date = datetime.date.fromisoformat(last_cached.session_date)
                sessions_behind = calculate_sessions_behind(last_cached_date, now_cairo)

                if sessions_behind == 0:
                    raw_bars = [c.to_dict() for c in cached_rows[-limit:]]
                    validated_bars = CandleValidator.validate_bars(raw_bars)
                    has_min_history = len(validated_bars) >= 50
                    is_eligible = has_min_history
                    status = "SUCCESS" if is_eligible else "INSUFFICIENT_DATA"
                    return {
                        "status": status,
                        "ticker": clean_ticker,
                        "actual_provider": last_cached.actual_provider,
                        "raw_bars_count": len(validated_bars),
                        "analytical_bars_count": len(validated_bars),
                        "expected_latest_session": expected_session_str,
                        "latest_available_session": last_cached.session_date,
                        "sessions_behind": 0,
                        "freshness": "CURRENT",
                        "freshness_ar": "محدث",
                        "current_analysis_eligible": is_eligible,
                        "bars": validated_bars
                    }

        all_providers = [self.primary_provider] + self.fallback_providers
        best_bars: List[Dict[str, Any]] = []
        best_provider: Optional[str] = None
        best_sessions_behind: Optional[int] = None

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
                if not val_p_bars:
                    continue

                p_latest_date = datetime.date.fromisoformat(val_p_bars[-1]["session_date"])
                p_sessions_behind = calculate_sessions_behind(p_latest_date, now_cairo)

                if p_sessions_behind == 0:
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

        if best_bars and best_sessions_behind is not None and best_sessions_behind > 0:
            for fallback in self.fallback_providers:
                try:
                    missing_bar = self._fetch_provider_session_bar(
                        provider=fallback,
                        ticker=clean_ticker,
                        session_date=expected_session_str,
                        english_name=english_name,
                    )
                    if missing_bar is not None:
                        validated_missing = CandleValidator.validate_bar(missing_bar)
                        if validated_missing.get("hlcv_status") == "VALID":
                            if not any(
                                b.get("session_date") == validated_missing.get("session_date")
                                for b in best_bars
                            ):
                                best_bars.append(validated_missing)
                                best_bars.sort(key=lambda x: x["session_date"])
                            best_sessions_behind = 0
                            best_provider = f"{best_provider} + {missing_bar.get('actual_provider', fallback.provider_name)}"
                            break
                except Exception:
                    continue

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
                "bars": []
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
                            EGXCandle.session_date == b["session_date"]
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
                            validation_status=b["validation_status"]
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
            "bars": validated_bars
        }

    def get_analytical_bars(
        self, ticker: str, limit: int = 250, db: Optional[Session] = None, force_refresh: bool = False
    ) -> Dict[str, Any]:
        raw_result = self.get_raw_historical_bars(
            ticker, limit=limit, db=db, force_refresh=force_refresh
        )
        if raw_result["status"] == "DATA_UNAVAILABLE":
            return raw_result

        raw_bars = raw_result["bars"]
        analytical_bars = CandleValidator.extract_analytical_bars(raw_bars)

        invalid_hlcv_count = sum(
            1 for b in raw_bars if b.get("hlcv_status") != "VALID"
        )
        open_unverified_count = sum(
            1 for b in raw_bars
            if b.get("open_status") in (
                "OPEN_UNVERIFIED", "OPEN_REFERENCE_ARTIFACT", "INVALID_OPEN"
            )
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
            "bars": analytical_bars
        }


default_provider_manager = ProviderManager()
