from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db import Base

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_sqlite)


def _migrate_sqlite(sync_conn) -> None:
    from sqlalchemy import inspect, text

    insp = inspect(sync_conn)
    if not insp.has_table("plans"):
        return
    cols = {c["name"] for c in insp.get_columns("plans")}
    if "pg_group_ids" not in cols:
        sync_conn.execute(text("ALTER TABLE plans ADD COLUMN pg_group_ids VARCHAR(255)"))

    if insp.has_table("reseller_profiles"):
        rcols = {c["name"] for c in insp.get_columns("reseller_profiles")}
        alters = {
            "pg_role_id": "INTEGER",
            "web_username": "VARCHAR(128)",
            "web_password_hash": "VARCHAR(255)",
            "web_permissions": "TEXT",
            "bot_permissions": "TEXT",
            "plan_id": "INTEGER",
            "created_at": "DATETIME",
            "setup_token": "VARCHAR(64)",
            "setup_token_expires": "DATETIME",
            "setup_completed_at": "DATETIME",
            "bot_token": "TEXT",
            "bot_username": "VARCHAR(64)",
            "bot_telegram_id": "BIGINT",
            "share_pg_panel_url": "BOOLEAN DEFAULT 0",
        }
        for col, typ in alters.items():
            if col not in rcols:
                sync_conn.execute(
                    text(f"ALTER TABLE reseller_profiles ADD COLUMN {col} {typ}")
                )

    if insp.has_table("reseller_plans"):
        pcols = {c["name"] for c in insp.get_columns("reseller_plans")}
        if "share_pg_panel_url" not in pcols:
            sync_conn.execute(
                text("ALTER TABLE reseller_plans ADD COLUMN share_pg_panel_url BOOLEAN DEFAULT 0")
            )

    # Ensure shop_settings exists on legacy reseller profiles / plans (1.7+)
    _ensure_shop_settings_perm_column(sync_conn, "reseller_profiles")
    _ensure_shop_settings_perm_column(sync_conn, "reseller_plans")


def _ensure_shop_settings_perm_column(sync_conn, table: str) -> None:
    from sqlalchemy import text

    try:
        rows = sync_conn.execute(
            text(f"SELECT id, web_permissions, bot_permissions FROM {table}")
        ).fetchall()
    except Exception:
        return
    for row in rows:
        rid, web, bot = row[0], row[1], row[2]
        new_web = _append_shop_settings_csv(web)
        new_bot = _append_shop_settings_csv(bot if bot is not None else web)
        if new_web != (web or "") or new_bot != (bot or ""):
            sync_conn.execute(
                text(
                    f"UPDATE {table} SET web_permissions = :w, bot_permissions = :b WHERE id = :id"
                ),
                {"w": new_web or None, "b": new_bot or None, "id": rid},
            )


def _append_shop_settings_csv(raw: str | None) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "dashboard,orders,payments,shop_settings,stats,tickets"
    parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    if "shop_settings" not in parts:
        parts.append("shop_settings")
    # stable unique order
    seen: list[str] = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    return ",".join(seen)
