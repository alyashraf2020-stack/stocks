"""EGX26 v1: a transparent EOD rating, not a prediction or trained AI model."""
import math
import numpy as np
import pandas as pd
from app.core.config import settings
from app.services.smoothing import ema, rsi, wilder


def number(value):
    return round(float(value), 6) if value is not None and math.isfinite(float(value)) else None


def sign(value):
    return 1 if value > 1e-10 else -1 if value < -1e-10 else 0


def compare(left, right):
    # Flat slopes must not change votes because prices use a different scale.
    return 0 if math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-10) else sign(left - right)


def wma(series, period):
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda values: np.dot(values, weights) / weights.sum(), raw=True)


class TechnicalRatingEngine:
    @staticmethod
    def calculate(bars, current=False):
        if len(bars) < settings.MIN_REQUIRED_BARS:
            return None
        df = pd.DataFrame(bars)
        close, high, low, volume = (df[key].astype(float) for key in ("close", "high", "low", "volume"))
        rows = []

        def add(key, group, series, rule, vote, related=()):
            value = number(series.iloc[-1])
            ready = value is not None and all(number(item.iloc[-1]) is not None for item in related)
            result = int(vote()) if ready else None
            rows.append({"key": key, "group": group, "value": value,
                         "vote": result, "signal": {1: "BUY", -1: "SELL", 0: "NEUTRAL"}.get(result, "UNAVAILABLE"),
                         "rule_ar": rule})

        for period in (10, 20, 30, 50, 100, 200):
            for name, series in (("SMA", close.rolling(period).mean()), ("EMA", ema(close, period))):
                add(f"{name}{period}", "TREND", series, "مقارنة الإغلاق بالمتوسط: أعلى شراء، أدنى بيع، مساوي محايد",
                    lambda s=series: compare(close.iloc[-1], s.iloc[-1]))
        vwma = (close * volume).rolling(20).sum() / volume.rolling(20).sum().replace(0, np.nan)
        hull = wma(2 * wma(close, 4) - wma(close, 9), 3)
        for name, series in (("VWMA20", vwma), ("HMA9", hull)):
            add(name, "TREND", series, "مقارنة الإغلاق بالمتوسط: أعلى شراء، أدنى بيع، مساوي محايد",
                lambda s=series: compare(close.iloc[-1], s.iloc[-1]))

        rsi_series = rsi(close)
        add("RSI14", "MOMENTUM", rsi_series, "شراء تحت 30 مع تحسن؛ بيع فوق 70 مع تراجع؛ غير ذلك محايد",
            lambda: 1 if rsi_series.iloc[-1] < 30 and rsi_series.iloc[-1] > rsi_series.iloc[-2] else
            -1 if rsi_series.iloc[-1] > 70 and rsi_series.iloc[-1] < rsi_series.iloc[-2] else 0,
            (rsi_series.shift(1),))
        spread = high.rolling(14).max() - low.rolling(14).min()
        raw_k = 100 * (close - low.rolling(14).min()) / spread.replace(0, np.nan)
        raw_k = raw_k.mask(spread == 0, 50)
        k, d = raw_k.rolling(3).mean(), raw_k.rolling(3).mean().rolling(3).mean()
        add("STOCH14_3_3", "MOMENTUM", k, "شراء K وD تحت 20 وK أعلى D؛ بيع فوق 80 وK أدنى D",
            lambda: 1 if k.iloc[-1] < 20 and d.iloc[-1] < 20 and k.iloc[-1] > d.iloc[-1] else
            -1 if k.iloc[-1] > 80 and d.iloc[-1] > 80 and k.iloc[-1] < d.iloc[-1] else 0, (d,))
        typical = (high + low + close) / 3
        deviation = typical.rolling(20).apply(lambda values: np.mean(np.abs(values - values.mean())), raw=True)
        cci = ((typical - typical.rolling(20).mean()) / (0.015 * deviation.replace(0, np.nan))).mask(deviation == 0, 0)
        add("CCI20", "MOMENTUM", cci, "شراء تحت -100 مع تحسن؛ بيع فوق 100 مع تراجع",
            lambda: 1 if cci.iloc[-1] < -100 and cci.iloc[-1] > cci.iloc[-2] else
            -1 if cci.iloc[-1] > 100 and cci.iloc[-1] < cci.iloc[-2] else 0, (cci.shift(1),))
        previous = close.shift(1)
        tr = pd.concat([high - low, (high - previous).abs(), (low - previous).abs()], axis=1).max(axis=1)
        atr = wilder(tr)
        up, down = high.diff(), -low.diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0).mask(up.isna())
        minus_dm = down.where((down > up) & (down > 0), 0.0).mask(down.isna())
        plus, minus = 100 * wilder(plus_dm) / atr.replace(0, np.nan), 100 * wilder(minus_dm) / atr.replace(0, np.nan)
        plus, minus = plus.mask(atr == 0, 0), minus.mask(atr == 0, 0)
        di_sum = plus + minus
        dx = (100 * (plus - minus).abs() / di_sum.replace(0, np.nan)).mask(di_sum == 0, 0)
        adx = wilder(dx)
        add("ADX14", "MOMENTUM", adx, "عند ADX فوق 20: اتجاه +DI أعلى شراء، -DI أعلى بيع؛ غير ذلك محايد",
            lambda: sign(plus.iloc[-1] - minus.iloc[-1]) if adx.iloc[-1] > 20 else 0, (plus, minus))
        median = (high + low) / 2
        ao = median.rolling(5).mean() - median.rolling(34).mean()
        add("AO5_34", "MOMENTUM", ao, "شراء فوق الصفر مع ارتفاع؛ بيع تحت الصفر مع انخفاض",
            lambda: 1 if ao.iloc[-1] > 0 and compare(ao.iloc[-1], ao.iloc[-2]) > 0 else
            -1 if ao.iloc[-1] < 0 and compare(ao.iloc[-1], ao.iloc[-2]) < 0 else 0, (ao.shift(1),))
        momentum = close - close.shift(10)
        add("MOM10", "MOMENTUM", momentum, "ارتفاع الزخم عن الجلسة السابقة شراء؛ انخفاضه بيع",
            lambda: compare(momentum.iloc[-1], momentum.iloc[-2]), (momentum.shift(1),))
        roc = 100 * (close / close.shift(10) - 1)
        add("ROC10", "MOMENTUM", roc, "تغير 10 جلسات موجب شراء؛ سالب بيع؛ صفر محايد", lambda: sign(roc.iloc[-1]))
        macd = close.ewm(span=12, min_periods=12, adjust=False).mean() - close.ewm(span=26, min_periods=26, adjust=False).mean()
        macd_signal = macd.ewm(span=9, min_periods=9, adjust=False).mean()
        add("MACD12_26_9", "MOMENTUM", macd, "MACD أعلى خط الإشارة شراء؛ أدناه بيع", lambda: compare(macd.iloc[-1], macd_signal.iloc[-1]), (macd_signal,))
        rsi_range = rsi_series.rolling(14).max() - rsi_series.rolling(14).min()
        stoch_rsi = (100 * (rsi_series - rsi_series.rolling(14).min()) / rsi_range.replace(0, np.nan)).mask(rsi_range == 0, 50)
        sk, sd = stoch_rsi.rolling(3).mean(), stoch_rsi.rolling(3).mean().rolling(3).mean()
        add("STOCH_RSI14", "MOMENTUM", sk, "شراء K وD تحت 20 وK أعلى D؛ بيع فوق 80 وK أدنى D",
            lambda: 1 if sk.iloc[-1] < 20 and sd.iloc[-1] < 20 and sk.iloc[-1] > sd.iloc[-1] else
            -1 if sk.iloc[-1] > 80 and sd.iloc[-1] > 80 and sk.iloc[-1] < sd.iloc[-1] else 0, (sd,))
        wr = (-100 * (high.rolling(14).max() - close) / spread.replace(0, np.nan)).mask(spread == 0, -50)
        add("WILLIAMS14", "MOMENTUM", wr, "شراء تحت -80 مع تحسن؛ بيع فوق -20 مع تراجع",
            lambda: 1 if wr.iloc[-1] < -80 and wr.iloc[-1] > wr.iloc[-2] else
            -1 if wr.iloc[-1] > -20 and wr.iloc[-1] < wr.iloc[-2] else 0, (wr.shift(1),))
        bp = close - pd.concat([low, previous], axis=1).min(axis=1)
        true_range = pd.concat([high, previous], axis=1).max(axis=1) - pd.concat([low, previous], axis=1).min(axis=1)
        bp.iloc[0], true_range.iloc[0] = np.nan, np.nan
        def buying_pressure(period):
            total = true_range.rolling(period).sum()
            return (bp.rolling(period).sum() / total.replace(0, np.nan)).mask(total == 0, 0.5)
        ultimate = 100 * (4 * buying_pressure(7) + 2 * buying_pressure(14) + buying_pressure(28)) / 7
        add("UO7_14_28", "MOMENTUM", ultimate, "شراء فوق 70؛ بيع تحت 30؛ غير ذلك محايد",
            lambda: 1 if ultimate.iloc[-1] > 70 else -1 if ultimate.iloc[-1] < 30 else 0)
        money_flow = typical * volume
        change = typical.diff()
        positive = money_flow.where(change > 0, 0).mask(change.isna()).rolling(14).sum()
        negative = money_flow.where(change < 0, 0).mask(change.isna()).rolling(14).sum()
        mfi = 100 - 100 / (1 + positive / negative.replace(0, np.nan))
        mfi = mfi.mask((negative == 0) & (positive > 0), 100).mask((positive == 0) & (negative == 0), 50)
        mfi = mfi.mask(volume.rolling(14).sum() == 0)
        add("MFI14", "MOMENTUM", mfi, "شراء تحت 20 مع تحسن؛ بيع فوق 80 مع تراجع",
            lambda: 1 if mfi.iloc[-1] < 20 and mfi.iloc[-1] > mfi.iloc[-2] else
            -1 if mfi.iloc[-1] > 80 and mfi.iloc[-1] < mfi.iloc[-2] else 0, (mfi.shift(1),))

        available = [row for row in rows if row["vote"] is not None]
        group_means = [sum(row["vote"] for row in available if row["group"] == group) /
                       len([row for row in available if row["group"] == group]) for group in ("TREND", "MOMENTUM")]
        score = 100 * sum(group_means) / 2
        signal = "STRONG_BUY" if score > 50 else "BUY" if score > 10 else "STRONG_SELL" if score < -50 else "SELL" if score < -10 else "NEUTRAL"
        counts = {label: sum(row["signal"] == label for row in available) for label in ("BUY", "SELL", "NEUTRAL")}
        direction = "BUY" if score > 10 else "SELL" if score < -10 else "NEUTRAL"
        daily_change = close.iloc[-1] - close.iloc[-2]
        atr_pct = 100 * atr.iloc[-1] / close.iloc[-1]
        mean_volume = volume.iloc[-20:].mean()
        return {
            "methodology": "EGX26_V1", "status": "COMPLETE" if len(available) == 26 else "PARTIAL",
            "as_of_session": bars[-1]["session_date"], "is_current": current,
            "score": round(score, 2), "signal": signal,
            "signal_ar": {"STRONG_BUY": "شراء قوي", "BUY": "شراء", "NEUTRAL": "محايد", "SELL": "بيع", "STRONG_SELL": "بيع قوي"}[signal],
            "available_count": len(available), "total_count": 26, "coverage_pct": round(100 * len(available) / 26, 2),
            "agreement_pct": round(100 * counts[direction] / len(available), 2), "counts": counts,
            "trend_score": round(100 * group_means[0], 2), "momentum_score": round(100 * group_means[1], 2),
            "daily_change": number(daily_change), "daily_change_pct": number(100 * daily_change / close.iloc[-2]),
            "daily_reference_session": bars[-2]["session_date"],
            "atr_pct": number(atr_pct), "volatility_ar": "مرتفعة" if atr_pct >= 5 else "متوسطة" if atr_pct >= 2 else "منخفضة",
            "mean_volume_20": number(mean_volume), "relative_volume": number(volume.iloc[-1] / mean_volume) if mean_volume else None,
            "indicators": rows,
            "note_ar": "تقييم فني يومي حسابي، وليس نموذج ذكاء اصطناعي. اتفاق المؤشرات لا يمثل احتمال الربح؛ المؤشرات قد تكون مترابطة. الأهداف لا تحدد موعد تحققها.",
        }
