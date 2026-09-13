from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Dict

class Settings(BaseSettings):
    PROJECT_NAME: str = "EGX Investment and Live Price Analysis Platform"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = "sqlite:///./egx_platform.db"
    
    # Risk Management Rules (Fixed and Strict)
    MAX_RISK_PER_TRADE_PCT: float = 0.015  # 1.5% max capital risk per trade
    MAX_ALLOCATION_PCT: float = 0.20       # 20.0% max capital allocation per stock
    
    # Transparent Profit Target R-Multiples
    TARGET_1_R_MULTIPLE: float = 1.5
    TARGET_2_R_MULTIPLE: float = 2.5
    TARGET_3_R_MULTIPLE: float = 3.5
    
    # ZERO-SESSION-LAG POLICY (Strict Zero Delay)
    # The ONLY acceptable state for actionable current analysis is sessions_behind == 0
    MAX_ACCEPTABLE_SESSIONS_BEHIND: int = 0
    
    # Multi-Factor Score Weighting (Sum = 100)
    SCORE_WEIGHTS: Dict[str, int] = {
        "trend": 25,
        "momentum": 25,
        "price_structure": 25,
        "liquidity_volatility": 25,
    }

    # Minimum history bars required for indicator and setup validity
    MIN_REQUIRED_BARS: int = 50

    model_config = ConfigDict(case_sensitive=True)

settings = Settings()