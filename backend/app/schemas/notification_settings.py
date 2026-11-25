from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DeliveryEnvironment(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=True)
    TELEGRAM_ENABLED: bool = False
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_OWNER_USER_ID: int | None = None
    WEB_PUSH_ENABLED: bool = False
    VAPID_PRIVATE_KEY: str = ""
    VAPID_PUBLIC_KEY: str = ""
    VAPID_SUBJECT: str = ""
    NOTIFICATION_ENCRYPTION_KEY: str = ""
    APP_HOST: str = ""


class DeliveryPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    in_app: bool = True
    telegram: bool = False
    push: bool = False
    detailed: bool = False
    severity: Literal["INFO", "OPPORTUNITY", "WARNING", "CRITICAL"] = "INFO"
    muted: list[str] = Field(default_factory=list, max_length=30)
    quiet_start: int | None = Field(default=None, ge=0, le=1439)
    quiet_end: int | None = Field(default=None, ge=0, le=1439)
    critical_bypass: bool = False
    cooldown: int = Field(default=0, ge=0, le=86400)
    revision: int = Field(default=0, ge=0)


class PushKeys(BaseModel):
    model_config = ConfigDict(extra="forbid")
    p256dh: str = Field(pattern=r"^[A-Za-z0-9_-]{87}={0,2}$")
    auth: str = Field(pattern=r"^[A-Za-z0-9_-]{22}={0,2}$")


class PushDevice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    endpoint: str = Field(min_length=20, max_length=2048)
    keys: PushKeys
    name: str = Field(min_length=1, max_length=60)
