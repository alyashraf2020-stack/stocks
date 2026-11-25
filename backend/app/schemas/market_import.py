from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ImportFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["CSV", "JSON"]
    content: str = Field(min_length=1, max_length=2_000_000)
    mapping: dict[str, str] = Field(default_factory=dict, max_length=20)
    metadata: dict = Field(default_factory=dict, max_length=24)


class ImportEnvironment(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True)
    EOD_IMPORT_ENABLED: bool = False
    EOD_IMPORT_DIRECTORY: str = ""
    EOD_IMPORT_INTERVAL_SECONDS: int = Field(default=300, ge=30, le=86400)
    EOD_IMPORT_MAX_PER_DAY: int = Field(default=20, ge=1, le=400)
    EOD_IMPORT_PAPER_FOLLOW: bool = False
