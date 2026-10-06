import json
import os
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, Base, engine
from app.models.security import EGXSecurity

def seed_security_master(db: Session) -> int:
    Base.metadata.create_all(bind=engine)
    # Backfill new listings even when the database was seeded previously.
    existing_tickers = {row[0] for row in db.query(EGXSecurity.ticker).all()}

    json_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "egx_equities.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Equities data file not found at {json_path}")

    with open(json_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    metadata = data.get("metadata", {})
    source = metadata.get("source", "EGX Official Listed Equities Directory")
    updated_at = metadata.get("source_updated_at", "2026-09-10T14:30:00+02:00")

    for item in data.get("equities", []):
        ticker = item["ticker"].upper().strip()
        if ticker in existing_tickers:
            continue
        sec = EGXSecurity(
            ticker=ticker,
            arabic_name=item["arabic_name"].strip(),
            english_name=item["english_name"].strip(),
            isin=item.get("isin"),
            sector=item["sector"].strip(),
            listing_status=item.get("listing_status", "ACTIVE"),
            indices=json.dumps(item.get("indices", [])),
            source=item.get("source", source),
            source_updated_at=item.get("source_updated_at", updated_at)
        )
        db.add(sec)
        existing_tickers.add(ticker)

    db.commit()
    return len(existing_tickers)

if __name__ == "__main__":
    db = SessionLocal()
    try:
        total = seed_security_master(db)
        print(f"Successfully seeded {total} EGX securities into database.")
    finally:
        db.close()
