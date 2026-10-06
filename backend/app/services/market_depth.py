from typing import Any, Dict, Optional


class MarketDepthService:
    """Summarize optional order-book totals supplied from a broker screen.

    Until an authenticated EGID/Level-2 feed is configured, the platform must
    not fabricate order-book data. Manual totals are treated as context only and
    never override the technical/freshness gates by themselves.
    """

    @classmethod
    def summarize(
        cls,
        bid_depth_qty: Optional[float],
        ask_depth_qty: Optional[float],
    ) -> Dict[str, Any]:
        if bid_depth_qty is None or ask_depth_qty is None:
            return {
                "status": "UNAVAILABLE",
                "source": None,
                "buy_qty": None,
                "sell_qty": None,
                "imbalance_pct": None,
                "pressure": "UNKNOWN",
                "pressure_ar": "غير متاح",
                "note_ar": "اربط مصدر Level-2/EGID أو أدخل إجمالي أوامر الشراء والبيع من شاشة الوسيط.",
            }

        buy = max(float(bid_depth_qty), 0.0)
        sell = max(float(ask_depth_qty), 0.0)
        total = buy + sell
        imbalance = ((buy - sell) / total) * 100.0 if total > 0 else 0.0

        if imbalance >= 15.0:
            pressure = "BUY_DOMINANT"
            pressure_ar = "ضغط شراء أعلى"
        elif imbalance <= -15.0:
            pressure = "SELL_DOMINANT"
            pressure_ar = "ضغط بيع أعلى"
        else:
            pressure = "BALANCED"
            pressure_ar = "متوازن نسبيًا"

        return {
            "status": "MANUAL_INPUT",
            "source": "MANUAL_BROKER_INPUT",
            "buy_qty": buy,
            "sell_qty": sell,
            "imbalance_pct": round(imbalance, 2),
            "pressure": pressure,
            "pressure_ar": pressure_ar,
            "note_ar": "عمق السوق لقطة لحظية قابلة للتغير والإلغاء؛ يستخدم كسياق فقط وليس إشارة شراء مستقلة.",
        }
