import json
import os
import datetime
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, Base, engine
from app.models.security import EGXSecurity
from app.models.candle import EGXCandle
from app.models.security_data_correction import SecurityDataCorrection


def _correct_bioc_identity(db: Session, item, previously_existed: bool):
    correction_id = "BIOC_GLAXO_IDENTITY_V1"
    if db.get(SecurityDataCorrection, correction_id) is not None:
        return

    security = db.get(EGXSecurity, "BIOC")
    candles = db.query(EGXCandle).filter(EGXCandle.ticker == "BIOC").all()
    # Previous BIOC prices were resolved using a different company's identity.
    # Archive them before invalidation, even if somebody already fixed the name.
    archive = {
        "previous_security": security.to_dict() if previously_existed else None,
        "previous_candles": [candle.to_dict() for candle in candles],
    }
    db.add(SecurityDataCorrection(
        correction_id=correction_id, ticker="BIOC",
        applied_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        archived_data=json.dumps(archive, ensure_ascii=False),
    ))
    for candle in candles:
        db.delete(candle)
    for field in ("arabic_name", "english_name", "isin", "sector", "listing_status", "source", "source_updated_at"):
        setattr(security, field, item[field])
    security.indices = json.dumps(item.get("indices", []), ensure_ascii=False)

def seed_security_master(db: Session) -> int:
    Base.metadata.create_all(bind=engine)
    # Backfill new listings even when the database was seeded previously.
    existing_tickers = {row[0] for row in db.query(EGXSecurity.ticker).all()}
    bioc_previously_existed = "BIOC" in existing_tickers

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

    bioc = next((item for item in data.get("equities", []) if item["ticker"] == "BIOC"), None)
    if bioc:
        _correct_bioc_identity(db, bioc, bioc_previously_existed)
    db.commit()
    return len(existing_tickers)

if __name__ == "__main__":
    db = SessionLocal()
    try:
        total = seed_security_master(db)
        print(f"Successfully seeded {total} EGX securities into database.")
    finally:
        db.close()
