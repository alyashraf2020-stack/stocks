"""Company identity and optional, timestamped provider metrics for MBSC."""
import datetime
import json
import math
import re

MBSC_URL = "https://www.investing.com/equities/misr-beni-suef-cement"
MBSC_ISIN = "EGS3C371C019"


def finite_number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def parse_snapshot(html):
    match = re.search(
        r'<script\b(?=[^>]*\bid="__NEXT_DATA__")[^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    if not match:
        raise ValueError("Provider payload unavailable")
    payload = json.loads(match.group(1))
    instrument = payload["props"]["pageProps"]["state"]["equityStore"]["instrument"]
    if (instrument["name"]["symbol"] != "MBSC"
            or instrument["underlying"]["isin"] != MBSC_ISIN):
        raise ValueError("Provider identity mismatch")
    price = instrument.get("price", {})
    if price.get("currency") != "EGP":
        raise ValueError("Unexpected quote currency")
    fundamental = instrument.get("fundamental", {})
    fields = {
        "price": price.get("last"), "open": price.get("open"),
        "high": price.get("high"), "low": price.get("low"),
        "change": price.get("change"), "change_percent": price.get("changePcr"),
        "volume": price.get("volume"),
        "average_volume": instrument.get("volume", {}).get("average"),
        "week_52_high": price.get("fiftyTwoWeekHigh"),
        "week_52_low": price.get("fiftyTwoWeekLow"),
        "market_cap": fundamental.get("marketCapRaw"),
        "shares_outstanding": fundamental.get("sharesOutstanding"),
        "revenue": fundamental.get("revenueRaw"), "eps": fundamental.get("eps"),
        "pe_ratio": fundamental.get("ratio"),
        "dividend_per_share": fundamental.get("dividend"),
        "dividend_yield_percent": fundamental.get("yield"),
        "one_year_return_percent": fundamental.get("oneYearReturn"),
        "beta": instrument.get("performance", {}).get("beta"),
    }
    timestamp = finite_number(price.get("lastUpdateTime"))
    quote_time = (datetime.datetime.fromtimestamp(timestamp / 1000, datetime.timezone.utc).isoformat()
                  if timestamp and timestamp > 0 else None)
    return {
        "metrics": {key: finite_number(value) for key, value in fields.items()},
        "quote_updated_at": quote_time,
        "is_delayed": price.get("isDelayed") if isinstance(price.get("isDelayed"), bool) else None,
    }


def get_mbsc_company_profile():
    profile = {
        "ticker": "MBSC", "currency": "EGP", "listed_on": "1999-08-11",
        "description_ar": "شركة مصرية تعمل في إنتاج وبيع الأسمنت ومواد التعبئة المرتبطة به.",
        "identity_source": "https://www.egx.com.eg/ar/CompanyDetails.aspx?ISIN=EGS3C371C019",
        "metrics_source": MBSC_URL,
        "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "quote_updated_at": None, "is_delayed": None,
        "status": "UNAVAILABLE", "metrics": {},
        "resources": [
            {"label": "القيد والإفصاحات الرسمية — البورصة المصرية", "url": "https://www.egx.com.eg/ar/CompanyDetails.aspx?ISIN=EGS3C371C019"},
            {"label": "موقع الشركة", "url": "https://mbccegypt.com/"},
            {"label": "القوائم المالية والتوزيعات", "url": MBSC_URL + "-financial-summary"},
            {"label": "أخبار الشركة", "url": MBSC_URL + "-news"},
            {"label": "الأسعار التاريخية", "url": MBSC_URL + "-historical-data"},
        ],
    }
    try:
        from curl_cffi import requests
        with requests.Session(impersonate="chrome124") as session:
            response = session.get(MBSC_URL, timeout=15)
            response.raise_for_status()
            profile.update(parse_snapshot(response.text))
        values = profile["metrics"].values()
        profile["status"] = "AVAILABLE" if all(v is not None for v in values) else "PARTIAL"
    except Exception:
        # Company identity and official links remain available during provider outages.
        pass
    return profile
