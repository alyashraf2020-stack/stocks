import sys, os
import json
from app.services.data_provider.manager import default_provider_manager
from app.core.database import SessionLocal, Base, engine

Base.metadata.create_all(bind=engine)
db = SessionLocal()

stocks_to_test = ["COMI", "SWDY", "MASR", "EGAL", "FWRY", "ABUK", "TMGH"]
results = {}

for ticker in stocks_to_test:
    res = default_provider_manager.get_analytical_bars(ticker, limit=250, db=db)
    results[ticker] = {k: v for k, v in res.items() if k != "bars"}
    print(f"{ticker}: status={res['status']}, provider={res.get('actual_provider')}, raw={res.get('raw_bars_count')}, analytical={res.get('analytical_bars_count')}, first={res.get('first_session')}, latest={res.get('latest_session')}, behind={res.get('sessions_behind')}, invalid_hlcv={res.get('invalid_hlcv_bars')}, open_unverified={res.get('open_unverified_bars')}")

with open("phase2_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print("Saved results to phase2_results.json")