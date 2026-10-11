import datetime
import json
from unittest.mock import Mock, patch
import pytest
from app.services.data_provider.investing_provider import InvestingHistoricalProvider
from tests.test_bioc import chart_context_html


def rubex_context(changes=None):
    return chart_context_html(changes={"name.symbol": "RUBX", "underlying.isin": "EGS3A221C018",
                                       "base.id": "12950", **(changes or {})})


def test_rubex_chart_requires_directory_identity_and_public_request_context():
    stamp = int(datetime.datetime(2026, 10, 5, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    chart = Mock(status_code=200)
    chart.json.return_value = {"data": [[stamp, 18, 19, 17, 18.5, 10000]]}
    with patch("curl_cffi.requests.Session.get", side_effect=[Mock(text=rubex_context()), chart]) as get:
        result = InvestingHistoricalProvider()._fetch_chart("RUBX", 12950, 160)
    assert result[0]["ticker"] == "RUBX"
    assert result[0]["close"] == 18.5
    assert "/financialdata/12950/" in get.call_args_list[1].args[0]
    assert get.call_args_list[1].kwargs["headers"]["domain-id"] == "sa"


@pytest.mark.parametrize("changes", [{"name.symbol": "BIOC"}, {"underlying.isin": "WRONG"},
                                      {"price.currency": "USD"}, {"underlying.market": "United States"}, {"base.id": "99"}])
def test_generic_stock_cannot_use_another_company_or_currency(changes):
    with patch("curl_cffi.requests.Session.get", return_value=Mock(text=rubex_context(changes))) as get:
        assert InvestingHistoricalProvider()._fetch_chart("RUBX", 12950, 160) == []
    assert all("api.investing.com" not in call.args[0] for call in get.call_args_list)


@pytest.mark.parametrize("url", ["https://example.com/equities/rubex-plastic", "https://investing.com.example.com/equities/rubex-plastic",
                                 "http://www.investing.com/equities/rubex-plastic", "https://www.investing.com/not-equities/123"])
def test_chart_context_does_not_fetch_untrusted_urls(url):
    with patch("curl_cffi.requests.Session.get") as get:
        result = InvestingHistoricalProvider()._verified_page_chart_headers("RUBX", 12950, url, "EGS3A221C018")
    assert result is None
    get.assert_not_called()


def test_pinned_instrument_without_url_resolves_url_without_changing_identity(monkeypatch):
    provider = InvestingHistoricalProvider()
    monkeypatch.setattr(provider, "_resolved_url_cache", {})
    monkeypatch.setattr(provider, "_bioc_chart_headers", lambda: {"domain-id": "sa"})
    monkeypatch.setattr(provider, "_load_egypt_directory", lambda: {})
    response = Mock(status_code=200)
    response.json.return_value = {"items": [
        {"id": 99999, "symbol": "KORA", "country": "Egypt", "type": "Stock", "url": "/equities/wrong"},
        {"id": 1244005, "symbol": "KORA", "country": "Egypt", "type": "Stock", "url": "/equities/correct"},
    ]}
    with patch("curl_cffi.requests.Session.get", return_value=response):
        result = provider._resolve_metadata("KORA")
    assert result["id"] == 1244005
    assert result["url"] == "https://www.investing.com/equities/correct"


def test_public_egypt_directory_resolves_exact_symbols_and_discards_prices(monkeypatch):
    cls = InvestingHistoricalProvider
    monkeypatch.setattr(cls, "_egypt_metadata_cache", {})
    monkeypatch.setattr(cls, "_egypt_cache_at", -1e9)
    correct = {"id": "12865", "symbol": "COMI", "exchangeId": 33, "flagCode": "EG",
               "pairType": "Equities", "url": "/equities/com-intl-bk", "last": 999999}
    rows = [correct, {**correct, "symbol": "OTHER", "flagCode": "US"},
            {**correct, "symbol": "CFD", "isCFD": True}, {**correct, "symbol": "WRONGEX", "exchangeId": 1}]
    html = '<script id="__NEXT_DATA__">' + json.dumps({"props": {"pageProps": {"state": {"quotes": rows}}}}) + '</script>'
    with patch("curl_cffi.requests.get", return_value=Mock(text=html)) as get:
        result = cls._load_egypt_directory()
        assert cls._load_egypt_directory() == result
    assert result == {"COMI": {"id": 12865, "url": "https://www.investing.com/equities/com-intl-bk"}}
    assert get.call_count == 1
