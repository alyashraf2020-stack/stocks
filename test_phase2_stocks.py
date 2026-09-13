import json
from app.services.data_provider.manager import default_provider_manager
from app.core.database import SessionLocal, Base, engine

Base.metadata.create_all(bind=engine)
db = SessionLocal()

stocks_to_test = ["COMI", "SWDY", "MASR", "EGAL", "FWRY", "ABUK", "TMGH"]
results = {}

for ticker in stocks_to_test:
    res = default_provider_manager.get_analytical_bars(ticker, limit=250, db=db)
    results[ticker] = res
    print(f"Done testing {ticker}: status={res['status']}, bars={res.get('analytical_bars_count', 0)}")

with open("egx-platform/phase2_results.json", "w", encoding="utf-8") as f:
    # Save results without raw bars list for concise display
    summary = {}
    for t, r in results.items():
        summary[t] = {k: v for k, v in r.items() if k != "bars"}
    json.dump(summary, f, indent=2, ensure_ascii=False)

print("Saved Phase 2 stock test summary to phase2_results.json")