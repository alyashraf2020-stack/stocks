from typing import Literal

from pydantic import BaseModel

Severity = Literal["INFO", "OPPORTUNITY", "WARNING", "CRITICAL"]


class AlertUpdate(BaseModel):
    read: bool = True
    acknowledge: bool = False
