from datetime import datetime
from typing import Literal

from pydantic import BaseModel

CheckState = Literal["PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"]


class Check(BaseModel):
    code: str
    status: CheckState
    evidence: str
    action: str
    checked_at: datetime
    mandatory: bool = True
