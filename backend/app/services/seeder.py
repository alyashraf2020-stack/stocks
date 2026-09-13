import json
import os
from sqlalchemy.orm import Session
from app.core.database import SessionLocal, Base, engine
from app.models.security import EGXSecurity

def seed_security_master(db: Session) -> int:
    Base.metadata.create_all(bind=engine)
    existing_count = db.query(EGXSecurity).count()
    if existing_count > 0:
        return existing_count

    json_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "egx_equities.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Equities data file not found at {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    metadata = data.get("metadata", {})
    source = metadata.get("source", "EGX Official Listed Equities Directory")
    updated_at = metadata.get("source_updated_at", "2026-09-10T14:30:00+02:00")

    count = 0
    for item in data.get("equities", []):
        sec = EGXSecurity(
            ticker=item["ticker"].upper().strip(),
            arabic_name=item["arabic_name"].strip(),
            english_name=item["english_name"].strip(),
            isin=item.get("isin"),
            sector=item["sector"].strip(),
            listing_status=item.get("listing_status", "ACTIVE"),
            indices=json.dumps(item.get("indices", [])),
            source=source,
            source_updated_at=updated_at
        )
        db.add(sec)
        count += 1

    db.commit()
    return count

if __name__ == "__main__":
    db = SessionLocal()
    try:
        total = seed_security_master(db)
        print(f"Successfully seeded {total} EGX securities into database.")
    finally:
        db.close()