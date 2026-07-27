from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(alias="BOT_TOKEN")
    bot_username: str = Field(default="", alias="BOT_USERNAME")
    admin_ids: List[int] = Field(default_factory=list, alias="ADMIN_IDS")

    pg_base_url: str = Field(alias="PG_BASE_URL")
    pg_username: str = Field(default="", alias="PG_USERNAME")
    pg_password: str = Field(default="", alias="PG_PASSWORD")
    pg_access_token: str = Field(default="", alias="PG_ACCESS_TOKEN")

    web_host: str = Field(default="0.0.0.0", alias="WEB_HOST")
    web_port: int = Field(default=9000, alias="WEB_PORT")
    web_secret: str = Field(default="change-me", alias="WEB_SECRET")
    web_admin_user: str = Field(default="admin", alias="WEB_ADMIN_USER")
    web_admin_password: str = Field(default="admin123", alias="WEB_ADMIN_PASSWORD")

    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{DATA_DIR / 'bot.db'}",
        alias="DATABASE_URL",
    )

    webhook_url: str = Field(default="", alias="WEBHOOK_URL")
    webhook_path: str = Field(default="/telegram/webhook", alias="WEBHOOK_PATH")
    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")

    currency: str = Field(default="تومان", alias="CURRENCY")
    default_locale: str = Field(default="fa", alias="DEFAULT_LOCALE")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> List[int]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [int(v) for v in value]
        return [int(x.strip()) for x in str(value).split(",") if x.strip()]

    @property
    def miniapp_enabled(self) -> bool:
        return bool(self.public_base_url.strip())

    @property
    def miniapp_url(self) -> str:
        base = self.public_base_url.rstrip("/")
        return f"{base}/miniapp/" if base else ""


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()  # type: ignore[call-arg]
