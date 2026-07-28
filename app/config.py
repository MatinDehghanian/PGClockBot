from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, List

from pydantic import BeforeValidator, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


def _clean_str(value: object) -> str:
    s = "" if value is None else str(value).strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    return s


def normalize_pg_base_url(raw: str) -> str:
    """Normalize PG panel URL while preserving path.

    Trims whitespace, adds https:// if scheme is missing, drops query/fragment,
    keeps scheme://host[:port]/path exactly as configured (trailing slash removed).
    """
    from urllib.parse import urlparse, urlunparse

    s = (raw or "").strip().rstrip("/")
    if not s:
        return s
    if "://" not in s:
        s = "https://" + s
    parsed = urlparse(s)
    if not parsed.scheme or not parsed.netloc:
        return s
    path = (parsed.path or "").rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")


def _parse_admin_ids(value: object) -> List[int]:
    """Parse ADMIN_IDS from env/.env without requiring JSON (empty string → [])."""
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [int(v) for v in value]
    cleaned = _clean_str(value)
    if not cleaned:
        return []
    out: list[int] = []
    for part in cleaned.split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part))
    return out


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = Field(default="", alias="BOT_TOKEN")
    bot_username: str = Field(default="", alias="BOT_USERNAME")
    # NoDecode: prevent pydantic-settings from json.loads("") on empty ADMIN_IDS
    admin_ids: Annotated[List[int], NoDecode, BeforeValidator(_parse_admin_ids)] = Field(
        default_factory=list,
        alias="ADMIN_IDS",
    )

    pg_base_url: str = Field(default="", alias="PG_BASE_URL")
    pg_username: str = Field(default="", alias="PG_USERNAME")
    pg_password: str = Field(default="", alias="PG_PASSWORD")
    pg_access_token: str = Field(default="", alias="PG_ACCESS_TOKEN")

    web_host: str = Field(default="0.0.0.0", alias="WEB_HOST")
    web_port: int = Field(default=9000, alias="WEB_PORT")
    web_secret: str = Field(default="change-me", alias="WEB_SECRET")
    web_admin_user: str = Field(default="admin", alias="WEB_ADMIN_USER")
    web_admin_password: str = Field(default="", alias="WEB_ADMIN_PASSWORD")

    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{DATA_DIR / 'bot.db'}",
        alias="DATABASE_URL",
    )

    webhook_url: str = Field(default="", alias="WEBHOOK_URL")
    webhook_path: str = Field(default="/telegram/webhook", alias="WEBHOOK_PATH")
    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")

    currency: str = Field(default="تومان", alias="CURRENCY")
    default_locale: str = Field(default="fa", alias="DEFAULT_LOCALE")

    @field_validator(
        "bot_token",
        "bot_username",
        "pg_base_url",
        "pg_username",
        "pg_password",
        "pg_access_token",
        "web_host",
        "web_secret",
        "web_admin_user",
        "web_admin_password",
        "webhook_url",
        "webhook_path",
        "public_base_url",
        "currency",
        "default_locale",
        "database_url",
        mode="before",
    )
    @classmethod
    def strip_wrap_quotes(cls, value: object) -> str:
        return _clean_str(value)

    @field_validator("pg_base_url", mode="after")
    @classmethod
    def normalize_pg_url(cls, value: str) -> str:
        return normalize_pg_base_url(value) or value

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
