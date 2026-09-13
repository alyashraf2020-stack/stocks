import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_api_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "disclaimer" in data
    assert "Egyptian Exchange" in data["scope"]

def test_api_get_all_stocks():
    response = client.get("/api/v1/egx/stocks")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 150
    assert "provenance_source" in data
    assert any(item["ticker"] == "COMI" for item in data["items"])
    assert any(item["ticker"] == "SWDY" for item in data["items"])

def test_api_search_stocks():
    response = client.get("/api/v1/egx/stocks?q=السويدي")
    assert response.status_code == 200
    data = response.json()
    assert any(item["ticker"] == "SWDY" for item in data["items"])

def test_api_get_single_stock_valid():
    response = client.get("/api/v1/egx/stocks/COMI")
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "COMI"
    assert data["sector"] == "البنوك"
    assert data["expected_session_date"] is not None

def test_api_get_single_stock_invalid():
    response = client.get("/api/v1/egx/stocks/NON_EXISTENT")
    assert response.status_code == 404

def test_api_reject_foreign_ticker():
    # US stocks or foreign tickers must be rejected
    response = client.post(
        "/api/v1/egx/live-analysis",
        json={"ticker": "AAPL", "current_price": 200.0, "capital": 50000.0}
    )
    assert response.status_code == 400
    assert "البورصة المصرية فقط" in response.json()["detail"]

def test_api_live_analysis_valid_stock():
    response = client.post(
        "/api/v1/egx/live-analysis",
        json={"ticker": "COMI", "current_price": 140.0, "capital": 100000.0, "owns_stock": False}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ticker"] == "COMI"
    assert data["decision"] in ["ENTER_NOW", "WAIT", "NEAR_ENTRY", "DO_NOT_ENTER", "DATA_NOT_CURRENT", "INSUFFICIENT_DATA"]
    assert "decision_ar" in data
    assert "reason_ar" in data

def test_api_market_status():
    response = client.get("/api/v1/egx/market/status")
    assert response.status_code == 200
    data = response.json()
    assert "is_open_now" in data
    assert data["total_listed_equities"] >= 150
    assert data["active_equities_count"] >= 140
    assert "Cairo" in data["current_cairo_time"]