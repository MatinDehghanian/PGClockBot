"""Guard: product installer must never scaffold SQLite for fresh installs."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pgclock_install_requires_postgresql_scaffold():
    src = (ROOT / "pgclock.sh").read_text(encoding="utf-8")
    assert "ensure_postgresql" in src
    assert "scripts/setup_postgres.sh" in src
    # Old zero-config SQLite fallback must stay gone.
    assert "sqlite+aiosqlite:///{Path.cwd()" not in src
    assert 'or f"sqlite+aiosqlite:///' not in src
    assert "SQLite for zero-config labs" not in src


def test_setup_postgres_emits_url_file():
    src = (ROOT / "scripts" / "setup_postgres.sh").read_text(encoding="utf-8")
    assert "PGCLOCK_EMIT_URL_FILE" in src
    assert "postgresql+asyncpg://" in src


def test_readme_documents_auto_postgres_install():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "PostgreSQL automatically" in readme
    assert "PGCLOCK_DATABASE_URL" in readme
