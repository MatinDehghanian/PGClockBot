"""Alembic runner — upgrade/downgrade/stamp without requiring CLI cwd."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import ROOT_DIR

log = logging.getLogger(__name__)

ALEMBIC_INI = ROOT_DIR / "alembic.ini"
ALEMBIC_DIR = ROOT_DIR / "alembic"


def alembic_config(database_url: str | None = None) -> Config:
    if not ALEMBIC_INI.is_file():
        raise FileNotFoundError(f"Missing {ALEMBIC_INI}")
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(ALEMBIC_DIR))
    if database_url:
        from app.db.engine_url import to_sync_url

        cfg.set_main_option("sqlalchemy.url", to_sync_url(database_url))
    return cfg


def current_revision(database_url: str | None = None) -> str | None:
    cfg = alembic_config(database_url)
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    url = cfg.get_main_option("sqlalchemy.url")
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            return ctx.get_current_revision()
    finally:
        engine.dispose()


def upgrade_head(database_url: str | None = None) -> None:
    cfg = alembic_config(database_url)
    log.info("Alembic upgrade head")
    command.upgrade(cfg, "head")


def downgrade_one(database_url: str | None = None) -> None:
    cfg = alembic_config(database_url)
    command.downgrade(cfg, "-1")


def stamp_head(database_url: str | None = None) -> None:
    cfg = alembic_config(database_url)
    command.stamp(cfg, "head")


def heads() -> list[str]:
    cfg = alembic_config()
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(cfg)
    return list(script.get_heads())
