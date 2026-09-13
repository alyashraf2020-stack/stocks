import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.services.security_master import SecurityMasterService

client = TestClient(app)

def test_kora_search_provenance():
    db = SessionLocal()
    try:
        # Search by ticker
        res_ticker = SecurityMasterService.get_all(db, query="KORA")
        assert len(res_ticker) >= 1
        assert any(s.ticker == "KORA" for s in res_ticker)
        kora = next(s for s in res_ticker if s.ticker == "KORA")
        assert kora.isin == "EGS07911C018"
        assert "The Egyptian Exchange (EGX)" in kora.source

        # Search by Arabic name (both قرة and كورا)
        res_ar1 = SecurityMasterService.get_all(db, query="قرة")
        assert any(s.ticker == "KORA" for s in res_ar1)
        res_ar2 = SecurityMasterService.get_all(db, query="كورا")
        assert any(s.ticker == "KORA" for s in res_ar2)

        # Search by English name
        res_en = SecurityMasterService.get_all(db, query="Korra")
        assert any(s.ticker == "KORA" for s in res_en)

        # Search by ISIN
        res_isin = SecurityMasterService.get_all(db, query="EGS07911C018")
        assert any(s.ticker == "KORA" for s in res_isin)
    finally:
        db.close()

def test_1w_chart_range_and_indicators():
    response = client.get("/api/v1/egx/stocks/COMI/chart?range=1W")
    assert response.status_code == 200
    data = response.json()
    assert data["range_selected"] == "1W"
    assert data["total_bars"] == 5
    assert len(data["bars"]) == 5
    
    # Verify indicators computed over full history are present and not None on sliced 1W bars
    last_bar = data["bars"][-1]
    assert last_bar["sma_20"] is not None
    assert last_bar["sma_50"] is not None
    assert last_bar["rsi_14"] is not None
    assert last_bar["atr_14"] is not None
    assert last_bar["macd_line"] is not None

def test_canonical_session_consistency_comi():
    ticker = "COMI"
    # 1. Directory
    r_all = client.get(f"/api/v1/egx/stocks?q={ticker}")
    assert r_all.status_code == 200
    stk_all = next((s for s in r_all.json()["items"] if s["ticker"] == ticker), None)
    assert stk_all is not None

    # 2. Detail
    r_detail = client.get(f"/api/v1/egx/stocks/{ticker}")
    assert r_detail.status_code == 200
    stk_detail = r_detail.json()

    # 3. Chart
    r_chart = client.get(f"/api/v1/egx/stocks/{ticker}/chart?range=1W")
    assert r_chart.status_code == 200
    chart = r_chart.json()

    # 4. Live Analysis
    r_live = client.post("/api/v1/egx/live-analysis", json={
        "ticker": ticker,
        "current_price": stk_detail["latest_close"],
        "capital": 100000
    })
    assert r_live.status_code == 200
    live = r_live.json()

    # All 4 must agree
    assert stk_all["latest_session_date"] == stk_detail["latest_session_date"] == chart["latest_available_session"] == live["latest_available_session"]
    assert stk_all["latest_close"] == stk_detail["latest_close"] == chart["latest_close"] == live["latest_close"]
    assert stk_all["sessions_behind"] == stk_detail["sessions_behind"] == chart["sessions_behind"] == live["sessions_behind"] == 0
    assert stk_all["freshness"] == stk_detail["freshness"] == chart["freshness_ar"] == live["freshness_ar"] == "محدث"
    assert stk_all["actual_provider"] == stk_detail["actual_provider"] == chart["actual_provider"] == live["actual_provider"]

def test_refresh_endpoint():
    ticker = "COMI"
    response = client.post(f"/api/v1/egx/stocks/{ticker}/refresh")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == ticker
    assert data["latest_close"] is not None
    assert data["sessions_behind"] == 0
    assert data["freshness"] == "محدث"
