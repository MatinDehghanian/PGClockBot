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
        }
        for col, typ in alters.items():
            if col not in rcols:
                sync_conn.execute(
                    text(f"ALTER TABLE reseller_profiles ADD COLUMN {col} {typ}")
                )
