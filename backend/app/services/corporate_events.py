import datetime
from typing import Dict, List, Any


class CorporateEventService:
    """Small verified-event registry used only as context, never as a buy trigger.

    Events should be sourced from company/EGX disclosures and reviewed before
    being added. The service intentionally does not infer that an event is bullish.
    """

    _EVENTS: Dict[str, List[Dict[str, Any]]] = {
        "KORA": [
            {
                "event_type": "EXTRAORDINARY_GENERAL_ASSEMBLY",
                "event_date": "2026-09-14",
                "title_ar": "جمعية عامة غير عادية لقرة لمشروعات الطاقة والاستثمار",
                "summary_ar": (
                    "مناقشة زيادة رأس المال المرخص به والمصدر والمدفوع وفق إفصاح الشركة. "
                    "الحدث قد يرفع التذبذب لكنه لا يعني ارتفاع السعر تلقائيًا."
                ),
                "impact_bias": "UNCERTAIN",
                "source_name": "إفصاح الشركة عبر معلومات مباشر",
                "source_url": "https://www.mubasher.info/news/4661562/",
            }
        ]
    }

    @classmethod
    def get_relevant_events(cls, ticker: str, today: datetime.date | None = None) -> List[Dict[str, Any]]:
        clean = ticker.strip().upper()
        current = today or datetime.date.today()
        results: List[Dict[str, Any]] = []
        for event in cls._EVENTS.get(clean, []):
            event_date = datetime.date.fromisoformat(event["event_date"])
            # Keep events visible from 14 days before until 3 days after the event.
            if event_date - datetime.timedelta(days=14) <= current <= event_date + datetime.timedelta(days=3):
                item = dict(event)
                item["days_to_event"] = (event_date - current).days
                results.append(item)
        return results
