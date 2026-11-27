"""Official EODHD transport. No provider URL, token or raw error leaves this module."""

from datetime import date
from http.client import HTTPException
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

PROVIDER = "EODHD"
CODE = re.compile(r"[A-Z0-9]{2,20}")
TOKEN = re.compile(r"[A-Za-z0-9._-]{8,256}")
MAX_BYTES = 1_000_000


class ProviderError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


class EodhdProvider:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def _fetch(self, path, token, **params):
        # The official API authenticates by query parameter. urllib does not log requests.
        url = (
            "https://eodhd.com/api/"
            + path
            + "?"
            + urlencode({"api_token": token, "fmt": "json", **params})
        )
        try:
            with self.opener.open(
                Request(url, headers={"Accept": "application/json"}), timeout=8
            ) as response:
                body = response.read(MAX_BYTES + 1)
        except HTTPError as error:
            status = error.code
            error.close()
            raise ProviderError(
                {
                    401: "AUTH_FAILED",
                    402: "FREE_QUOTA_EXHAUSTED",
                    403: "ACCESS_DENIED",
                    404: "SYMBOL_UNAVAILABLE",
                    429: "RATE_LIMITED",
                }.get(status, "UPSTREAM_UNAVAILABLE")
            ) from None
        except (OSError, URLError, HTTPException, ValueError):
            raise ProviderError("UPSTREAM_UNAVAILABLE") from None
        if len(body) > MAX_BYTES:
            raise ProviderError("INVALID_RESPONSE")
        try:
            return json.loads(body)
        except (ValueError, RecursionError):
            raise ProviderError("INVALID_RESPONSE") from None

    def usage(self, token, day):
        value = self._fetch("user", token)
        if not isinstance(value, dict):
            raise ProviderError("USAGE_UNVERIFIED")
        cap = usage_integer(value.get("dailyRateLimit"))
        count = usage_integer(value.get("apiRequests"))
        last = value.get("apiRequestsDate")
        if cap != 20:
            raise ProviderError("FREE_PLAN_UNVERIFIED")
        if count is None:
            raise ProviderError("USAGE_UNVERIFIED")
        if last is None and count == 0:
            return 0
        try:
            used_on = date.fromisoformat(last)
        except (TypeError, ValueError):
            raise ProviderError("USAGE_UNVERIFIED") from None
        if last != used_on.isoformat() or used_on > day:
            raise ProviderError("USAGE_UNVERIFIED")
        return count if used_on == day else 0

    def catalog(self, token):
        raw = self._fetch("exchange-symbol-list/EGX", token, type="common_stock")
        if not isinstance(raw, list) or not raw:
            raise ProviderError("INVALID_RESPONSE")
        mapped = {}
        blocked = set()
        for record in raw:
            if not isinstance(record, dict):
                raise ProviderError("INVALID_RESPONSE")
            ticker = record.get("Code")
            if not isinstance(ticker, str) or not CODE.fullmatch(ticker):
                continue
            if (
                record.get("Exchange") != "EGX"
                or record.get("Currency") != "EGP"
                or record.get("Type") != "Common Stock"
                or ticker in mapped
            ):
                blocked.add(ticker)
                continue
            isin = record.get("Isin")
            if isin not in (None, "") and (
                not isinstance(isin, str) or not re.fullmatch(r"EG[A-Z0-9]{10}", isin)
            ):
                blocked.add(ticker)
                continue
            mapped[ticker] = isin or None
        result = {
            ticker: isin for ticker, isin in mapped.items() if ticker not in blocked
        }
        if not result:
            raise ProviderError("INVALID_RESPONSE")
        return result

    def history(self, token, ticker, start, end):
        if not CODE.fullmatch(ticker):
            raise ProviderError("SYMBOL_UNAVAILABLE")
        raw = self._fetch(
            f"eod/{ticker}.EGX",
            token,
            **{"from": start.isoformat(), "to": end.isoformat()},
            period="d",
            order="a",
        )
        if not isinstance(raw, list) or len(raw) > 366:
            raise ProviderError("INVALID_RESPONSE")
        return raw


def usage_integer(value):
    if type(value) is int and 0 <= value < 10**10:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,10}", value):
        return int(value)
    return None
