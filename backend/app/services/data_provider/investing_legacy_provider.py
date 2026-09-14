from typing import Optional
from urllib.parse import quote_plus

from app.services.data_provider.investing_provider import InvestingHistoricalProvider


class InvestingLegacySearchProvider(InvestingHistoricalProvider):
    """Second public Investing resolver for EGX symbols.

    The inherited historical/region fallback remains the data path; this class
    only supplies an alternate symbol resolver when Investing's v2 search does
    not identify the EGX security.
    """

    @property
    def provider_name(self) -> str:
        return "Investing Historical"

    def _resolve_instrument_id(
        self,
        ticker: str,
        english_name: Optional[str] = None,
    ) -> Optional[int]:
        clean_ticker = ticker.strip().upper()

        resolved = super()._resolve_instrument_id(clean_ticker, english_name)
        if resolved:
            return resolved

        queries = [clean_ticker]
        if english_name:
            queries.extend([english_name, f"{english_name} Egypt"])

        try:
            from curl_cffi import requests

            session = requests.Session(impersonate="chrome124")
            headers = self._headers()

            for query in queries:
                encoded = quote_plus(query)
                urls = [
                    f"https://api.investing.com/api/search/?q={encoded}",
                    f"https://api.investing.com/api/search/?t=Equities&q={encoded}",
                ]

                for url in urls:
                    try:
                        response = session.get(url, headers=headers, timeout=15)
                        if response.status_code != 200:
                            continue
                        payload = response.json()
                    except Exception:
                        continue

                    quotes = payload.get("quotes", []) if isinstance(payload, dict) else []
                    if not isinstance(quotes, list):
                        continue

                    best_id = None
                    best_url = None
                    best_score = -1

                    for item in quotes:
                        if not isinstance(item, dict):
                            continue

                        raw_id = item.get("id") or item.get("pair_ID") or item.get("pairId")
                        try:
                            instrument_id = int(raw_id)
                        except (TypeError, ValueError):
                            continue

                        symbol = str(item.get("symbol") or "").strip().upper()
                        exchange = str(item.get("exchange") or "").strip().lower()
                        flag = str(item.get("flag") or "").strip().upper()
                        item_type = str(item.get("type") or "").strip().lower()
                        description = str(item.get("description") or item.get("name") or "").lower()

                        score = 0
                        if symbol == clean_ticker:
                            score += 120
                        if flag == "EG":
                            score += 80
                        if any(token in exchange for token in ("egypt", "cairo", "egx")):
                            score += 80
                        if any(token in item_type for token in ("equities", "equity", "stock")):
                            score += 15

                        if english_name:
                            wanted = [
                                token for token in english_name.lower().replace("-", " ").split()
                                if len(token) >= 4 and token not in {
                                    "company", "services", "service", "group", "holding",
                                    "egypt", "egyptian", "the", "and", "for", "of",
                                }
                            ]
                            score += min(sum(1 for token in wanted if token in description) * 15, 60)

                        if score > best_score:
                            best_score = score
                            best_id = instrument_id
                            best_url = self._candidate_url(item)

                    if best_id is not None and best_score >= 120:
                        self._resolved_cache[clean_ticker] = best_id
                        if best_url:
                            self._resolved_url_cache[clean_ticker] = best_url
                        return best_id

        except Exception:
            return None

        return None
