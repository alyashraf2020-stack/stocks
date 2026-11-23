from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Dict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
LEGACY_DATABASE = BACKEND_ROOT / "egx_platform.db"
RUNTIME_DATABASE = BACKEND_ROOT / "instance" / "egx_platform.db"


class Settings(BaseSettings):
    PROJECT_NAME: str = "EGX Investment and Live Price Analysis Platform"
    API_V1_STR: str = "/api/v1"

    # Database
    DATABASE_URL: str = f"sqlite:///{RUNTIME_DATABASE.as_posix()}"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Risk Management Rules (Fixed and Strict)
    MAX_RISK_PER_TRADE_PCT: float = 0.015
    MAX_ALLOCATION_PCT: float = 0.20

    # Transparent Profit Target R-Multiples
    TARGET_1_R_MULTIPLE: float = 1.5
    TARGET_2_R_MULTIPLE: float = 2.5
    TARGET_3_R_MULTIPLE: float = 3.5

    # ZERO-SESSION-LAG POLICY (Strict Zero Delay)
    MAX_ACCEPTABLE_SESSIONS_BEHIND: int = 0

    # Multi-Factor Score Weighting (Sum = 100)
    SCORE_WEIGHTS: Dict[str, int] = {
        "trend": 25,
        "momentum": 25,
        "price_structure": 25,
        "liquidity_volatility": 25,
    }

    MIN_REQUIRED_BARS: int = 50

    model_config = ConfigDict(case_sensitive=True)


settings = Settings()
