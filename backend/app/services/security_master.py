import json
import re
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.models.security import EGXSecurity

def normalize_arabic(text: str) -> str:
    """
    Normalizes Arabic text for diacritic-free, typo-tolerant search:
    - Removes tashkeel / harakat
    - Unifies alef variants (أ, إ, آ -> ا)
    - Unifies taa marbuta and haa (ة -> ه)
    - Unifies yaa and alef maksura (ى -> ي)
    """
    if not text:
        return ""
    tashkeel_regex = re.compile(r'[\u064B-\u0652]')
    text = tashkeel_regex.sub('', text)
    text = re.sub(r'[إأآا]', 'ا', text)
    text = re.sub(r'ة', 'ه', text)
    text = re.sub(r'ى', 'ي', text)
    return text.lower().strip()

class SecurityMasterService:
    @staticmethod
    def get_all(
        db: Session,
        query: Optional[str] = None,
        sector: Optional[str] = None,
        status: Optional[str] = None,
        index_filter: Optional[str] = None,
        skip: int = 0,
        limit: int = 500
    ) -> List[EGXSecurity]:
        q = db.query(EGXSecurity)

        if sector:
            q = q.filter(EGXSecurity.sector == sector)
        if status:
            q = q.filter(EGXSecurity.listing_status == status)
        if index_filter:
            q = q.filter(EGXSecurity.indices.like(f"%\"{index_filter}\"%"))

        results = q.all()

        if query:
            norm_q = normalize_arabic(query)
            clean_q = query.strip().upper()
            filtered = []
            for sec in results:
                if clean_q in sec.ticker.upper():
                    filtered.append(sec)
                    continue
                if query.lower() in sec.english_name.lower():
                    filtered.append(sec)
                    continue
                if norm_q in normalize_arabic(sec.arabic_name):
                    filtered.append(sec)
                    continue
                if sec.isin and clean_q in sec.isin.upper():
                    filtered.append(sec)
                    continue
            return filtered[skip : skip + limit]

        return results[skip : skip + limit]

    @staticmethod
    def get_by_ticker(db: Session, ticker: str) -> Optional[EGXSecurity]:
        clean_ticker = ticker.strip().upper()
        if any(clean_ticker.endswith(sfx) for sfx in [".SR", ".US", "=X", "-USD", ".L", ".PA"]):
            return None
        return db.query(EGXSecurity).filter(EGXSecurity.ticker == clean_ticker).first()

    @staticmethod
    def get_total_count(db: Session) -> int:
        return db.query(EGXSecurity).count()

    @staticmethod
    def get_sectors(db: Session) -> List[str]:
        sectors = db.query(EGXSecurity.sector).distinct().all()
        return sorted([s[0] for s in sectors if s[0]])