from __future__ import annotations

import logging
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import event, text

from app.config import get_settings
from app.db import Base
from app.db.engine_url import normalize_async_url, parse_engine

# Register models on Base.metadata for Alembic / legacy paths
import app.db.models  # noqa: F401

log = logging.getLogger(__name__)

settings = get_settings()
_db_url = normalize_async_url(settings.database_url)
_engine_info = parse_engine(_db_url)
_engine_kwargs: dict = {"echo": False, "future": True}
if _engine_info.is_sqlite:
    _engine_kwargs["connect_args"] = {"timeout": 30}
elif _engine_info.is_postgresql:
    # Production-friendly pool defaults (override via env later if needed)
    _engine_kwargs.setdefault("pool_pre_ping", True)
engine = create_async_engine(_db_url, **_engine_kwargs)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

# Allow tests / migrator to force legacy create_all bootstrap
_ALLOW_CREATE_ALL = os.environ.get("PGCLOCK_ALLOW_CREATE_ALL", "").strip() in {
    "1",
    "true",
    "yes",
}


if _engine_info.is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_on_connect(dbapi_conn, _connection_record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _tables_exist(sync_conn) -> bool:
    from sqlalchemy import inspect

    insp = inspect(sync_conn)
    return insp.has_table("bot_users") and insp.has_table("settings")


def _alembic_version_exists(sync_conn) -> bool:
    from sqlalchemy import inspect

    return inspect(sync_conn).has_table("alembic_version")


async def init_db() -> None:
    """Initialize schema via Alembic; legacy create_all only as controlled fallback."""
    from app.db.alembic_runner import stamp_head, upgrade_head

    async with engine.begin() as conn:
        has_tables = await conn.run_sync(lambda c: _tables_exist(c))
        has_alembic = await conn.run_sync(lambda c: _alembic_version_exists(c))

    if has_tables and not has_alembic:
        # Existing production DB created before Alembic — apply legacy additive
        # migrations once, then stamp baseline so future changes use Alembic.
        log.warning(
            "Existing database without alembic_version — applying legacy "
            "compatibility migrator then stamping Alembic head"
        )
        async with engine.begin() as conn:
            await conn.run_sync(_migrate_sqlite_legacy)
            if _engine_info.is_sqlite:
                await conn.execute(text("PRAGMA journal_mode=WAL"))
                await conn.execute(text("PRAGMA busy_timeout=30000"))
                await conn.execute(text("PRAGMA synchronous=NORMAL"))
                await conn.execute(text("PRAGMA foreign_keys=ON"))
                await conn.run_sync(_ensure_indexes)
        stamp_head(_db_url)
    else:
        # Fresh DB or already under Alembic — upgrade to head (no create_all).
        try:
            upgrade_head(_db_url)
        except Exception:
            if _ALLOW_CREATE_ALL or not has_tables:
                log.exception(
                    "Alembic upgrade failed; falling back to create_all "
                    "(set PGCLOCK_ALLOW_CREATE_ALL=1 to silence in labs)"
                )
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                    await conn.run_sync(_migrate_sqlite_legacy)
                    if _engine_info.is_sqlite:
                        await conn.run_sync(_ensure_indexes)
                try:
                    stamp_head(_db_url)
                except Exception:
                    log.exception("Failed to stamp Alembic head after create_all fallback")
            else:
                raise

    # Idempotent additive columns for DBs already stamped at an older Alembic
    # head (create_all in 0001 only runs once). Keeps ORM fields like
    # reseller_plans.billing_mode from 500'ing /plans before a new revision lands.
    async with engine.begin() as conn:
        await conn.run_sync(_migrate_sqlite_legacy)
        if _engine_info.is_sqlite:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=30000"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA foreign_keys=ON"))
            await conn.run_sync(_ensure_indexes)


# ---------------------------------------------------------------------------
# Legacy additive migrator (SQLite-era). Kept only to bring pre-Alembic DBs
# up to the baseline shape before stamping. New installs must use Alembic.
# ---------------------------------------------------------------------------


def _migrate_sqlite_legacy(sync_conn) -> None:
    from sqlalchemy import inspect, text as sql_text

    insp = inspect(sync_conn)
    if not insp.has_table("plans"):
        return
    cols = {c["name"] for c in insp.get_columns("plans")}
    if "pg_group_ids" not in cols:
        sync_conn.execute(sql_text("ALTER TABLE plans ADD COLUMN pg_group_ids VARCHAR(255)"))
    if "owner_reseller_id" not in cols:
        sync_conn.execute(sql_text("ALTER TABLE plans ADD COLUMN owner_reseller_id INTEGER"))
    if "pg_username_prefix" not in cols:
        sync_conn.execute(sql_text("ALTER TABLE plans ADD COLUMN pg_username_prefix VARCHAR(64)"))
    if "pg_username_suffix" not in cols:
        sync_conn.execute(sql_text("ALTER TABLE plans ADD COLUMN pg_username_suffix VARCHAR(64)"))
    if "pg_username_pattern" not in cols:
        sync_conn.execute(sql_text("ALTER TABLE plans ADD COLUMN pg_username_pattern VARCHAR(255)"))

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
            "bot_admin_ids": "TEXT",
            "pg_admin_password_enc": "TEXT",
            "billing_mode": "VARCHAR(16) DEFAULT 'fixed'",
            "billing_balance": "INTEGER DEFAULT 0",
            "billing_watermark_bytes": "BIGINT DEFAULT 0",
            "billing_low_warned_at": "DATETIME",
        }
        for col, typ in alters.items():
            if col not in rcols:
                sync_conn.execute(
                    sql_text(f"ALTER TABLE reseller_profiles ADD COLUMN {col} {typ}")
                )

    if insp.has_table("reseller_plans"):
        pcols = {c["name"] for c in insp.get_columns("reseller_plans")}
        if "share_pg_panel_url" not in pcols:
            sync_conn.execute(
                sql_text("ALTER TABLE reseller_plans ADD COLUMN share_pg_panel_url BOOLEAN DEFAULT 0")
            )
        if "billing_mode" not in pcols:
            sync_conn.execute(
                sql_text(
                    "ALTER TABLE reseller_plans ADD COLUMN billing_mode VARCHAR(16) DEFAULT 'fixed'"
                )
            )

    if insp.has_table("pg_staff_access"):
        scols = {c["name"] for c in insp.get_columns("pg_staff_access")}
        if "pg_admin_password_enc" not in scols:
            sync_conn.execute(
                sql_text("ALTER TABLE pg_staff_access ADD COLUMN pg_admin_password_enc TEXT")
            )
        if "pg_role_id" not in scols:
            sync_conn.execute(
                sql_text("ALTER TABLE pg_staff_access ADD COLUMN pg_role_id INTEGER")
            )

    if insp.has_table("panel_tickets"):
        tcols = {c["name"] for c in insp.get_columns("panel_tickets")}
        if "owner_unread" not in tcols:
            sync_conn.execute(
                sql_text("ALTER TABLE panel_tickets ADD COLUMN owner_unread BOOLEAN DEFAULT 1")
            )

    if insp.has_table("panel_ticket_messages"):
        mcols = {c["name"] for c in insp.get_columns("panel_ticket_messages")}
        alters_msg = {
            "attachment_path": "VARCHAR(512)",
            "attachment_name": "VARCHAR(255)",
            "attachment_mime": "VARCHAR(128)",
        }
        for col, typ in alters_msg.items():
            if col not in mcols:
                sync_conn.execute(sql_text(f"ALTER TABLE panel_ticket_messages ADD COLUMN {col} {typ}"))

    if insp.has_table("orders"):
        ocols = {c["name"] for c in insp.get_columns("orders")}
        if "quantity" not in ocols:
            sync_conn.execute(
                sql_text("ALTER TABLE orders ADD COLUMN quantity INTEGER DEFAULT 1")
            )

    if insp.has_table("tickets"):
        ticols = {c["name"] for c in insp.get_columns("tickets")}
        if "reseller_id" not in ticols:
            sync_conn.execute(
                sql_text("ALTER TABLE tickets ADD COLUMN reseller_id INTEGER")
            )
            try:
                sync_conn.execute(
                    sql_text(
                        "UPDATE tickets SET reseller_id = ("
                        "SELECT bot_users.reseller_id FROM bot_users "
                        "WHERE bot_users.id = tickets.user_id"
                        ") WHERE reseller_id IS NULL"
                    )
                )
            except Exception:
                pass

    marker = None
    try:
        from app.config import DATA_DIR

        marker = DATA_DIR / ".migrated_core_reseller_perms_v1"
        if not marker.exists():
            _ensure_core_reseller_perms(sync_conn, "reseller_profiles")
            _ensure_core_reseller_perms(sync_conn, "reseller_plans")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            marker.write_text("1\n", encoding="utf-8")
    except Exception:
        _ensure_core_reseller_perms(sync_conn, "reseller_profiles")
        _ensure_core_reseller_perms(sync_conn, "reseller_plans")


# Backwards-compatible alias used by older tests / callers
_migrate_sqlite = _migrate_sqlite_legacy


def _ensure_core_reseller_perms(sync_conn, table: str) -> None:
    from sqlalchemy import text as sql_text

    try:
        rows = sync_conn.execute(
            sql_text(f"SELECT id, web_permissions, bot_permissions FROM {table}")
        ).fetchall()
    except Exception:
        return
    for row in rows:
        rid, web, bot = row[0], row[1], row[2]
        new_web = _append_core_reseller_perms_csv(web)
        new_bot = _append_core_reseller_perms_csv(bot if bot is not None else web)
        if new_web != (web or "") or new_bot != (bot or ""):
            sync_conn.execute(
                sql_text(
                    f"UPDATE {table} SET web_permissions = :w, bot_permissions = :b WHERE id = :id"
                ),
                {"w": new_web or None, "b": new_bot or None, "id": rid},
            )


def _append_core_reseller_perms_csv(raw: str | None) -> str:
    raw = (raw or "").strip()
    if not raw:
        return "dashboard,orders,payments,plans,shop_settings,stats,tickets"
    parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    for key in ("shop_settings", "plans"):
        if key not in parts:
            parts.append(key)
    seen: list[str] = []
    for p in parts:
        if p not in seen:
            seen.append(p)
    return ",".join(seen)


def _ensure_indexes(sync_conn) -> None:
    """Additive indexes for frequent dashboard / payment filters (legacy SQLite path)."""
    from sqlalchemy import text as sql_text

    statements = (
        "CREATE INDEX IF NOT EXISTS ix_orders_reseller_id ON orders (reseller_id)",
        "CREATE INDEX IF NOT EXISTS ix_orders_plan_id ON orders (plan_id)",
        "CREATE INDEX IF NOT EXISTS ix_orders_service_id ON orders (service_id)",
        "CREATE INDEX IF NOT EXISTS ix_payments_order_id ON payments (order_id)",
        "CREATE INDEX IF NOT EXISTS ix_discount_codes_code ON discount_codes (code)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_wallet_referral_reason "
        "ON wallet_transactions (user_id, reason) WHERE reason LIKE 'referral:%'",
    )
    for stmt in statements:
        try:
            sync_conn.execute(sql_text(stmt))
        except Exception:
            pass
