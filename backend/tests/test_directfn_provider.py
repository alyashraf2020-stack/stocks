from app.services.data_provider.directfn_provider import DirectFNCompletedSessionProvider


DIRECTFN_HTML = """
<html><body>
<div>EGX Open 13 Sep 2026 Egyptian Exchange</div>
<table>
<tr><th>Company Name</th><th>Symbol</th><th>Open</th><th>Last</th><th>High</th><th>Low</th><th>Change</th><th>Change %</th><th>Volume</th><th>Turnover</th></tr>
<tr><td>Taaleem Management Services</td><td>TALM</td><td>18.00</td><td>18.20</td><td>18.29</td><td>17.61</td><td>0.20</td><td>1.11</td><td>70411</td><td>1267284</td></tr>
</table>
</body></html>
"""

DIRECTFN_ZERO_OPEN_HTML = DIRECTFN_HTML.replace(">18.00</td><td>18.20<", ">0.00</td><td>18.20<")

MUBASHER_MATCHING_HTML = """
<html><body>
<h1>Taaleem Management Services (TALM)</h1>
<div>Open 18.00</div>
<div>Previous Close 18.00</div>
<div>High 18.29</div>
<div>Low 17.61</div>
<div>Stock Statistics</div>
<div>Volume 70,411</div>
</body></html>
"""

MUBASHER_MISMATCH_HTML = MUBASHER_MATCHING_HTML.replace("High 18.29", "High 19.75")


def test_extract_market_date_and_row():
    provider = DirectFNCompletedSessionProvider()
    assert provider._extract_market_date(DIRECTFN_HTML).isoformat() == "2026-09-13"
    row = provider._extract_directfn_row(DIRECTFN_HTML, "TALM")
    assert row == {
        "open": 18.0,
        "close": 18.2,
        "high": 18.29,
        "low": 17.61,
        "volume": 70411.0,
    }


def test_mubasher_open_is_parseable():
    provider = DirectFNCompletedSessionProvider()
    row = provider._extract_mubasher_open_high_low(MUBASHER_MATCHING_HTML)
    assert row["open"] == 18.0
    assert row["high"] == 18.29
    assert row["low"] == 17.61
    assert row["volume"] == 70411.0


def test_zero_open_requires_matching_mubasher(monkeypatch):
    provider = DirectFNCompletedSessionProvider()

    def matching_get(url: str):
        if "directfn" in url:
            return DIRECTFN_ZERO_OPEN_HTML
        return MUBASHER_MATCHING_HTML

    monkeypatch.setattr(provider, "_get_html", matching_get)
    bar = provider.fetch_session_bar("TALM", "2026-09-13")
    assert bar is not None
    assert bar["open"] == 18.0
    assert bar["close"] == 18.2
    assert "Mubasher verified open" in bar["actual_provider"]


def test_zero_open_rejects_conflicting_mubasher(monkeypatch):
    provider = DirectFNCompletedSessionProvider()

    def conflicting_get(url: str):
        if "directfn" in url:
            return DIRECTFN_ZERO_OPEN_HTML
        return MUBASHER_MISMATCH_HTML

    monkeypatch.setattr(provider, "_get_html", conflicting_get)
    assert provider.fetch_session_bar("TALM", "2026-09-13") is None


def test_wrong_market_date_is_rejected(monkeypatch):
    provider = DirectFNCompletedSessionProvider()
    monkeypatch.setattr(provider, "_get_html", lambda url: DIRECTFN_HTML)
    assert provider.fetch_session_bar("TALM", "2026-09-10") is None
