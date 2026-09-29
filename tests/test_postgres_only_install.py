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
    # Password must be URL-encoded; TCP auth verified after role create.
    assert "urllib.parse.quote" in src
    assert "PGPASSWORD=" in src
    assert "127.0.0.1" in src
    # Socket-ready alone is not enough — force TCP listen + hba password rules.
    assert "listen_addresses" in src
    assert "_ensure_tcp_listener_and_hba" in src
    assert "scram-sha-256" in src
    assert "systemctl restart postgresql" in src or "pg_ctlcluster" in src
    # Root fix: hex password applied via DO/EXECUTE — never psql -v / :'var' for secrets.
    assert "SET password_encryption" in src
    assert "EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L'" in src
    assert "PASSWORD '${DB_PASS}'" not in src
    assert "-v db_pass=" not in src
    assert ":'db_pass'" not in src
    # v11.0.5: never store md5 verifiers under scram-first HBA; trust is last resort.
    assert 'password_encryption = \'md5\'' not in src
    assert 'password_encryption = "md5"' not in src
    assert "_enable_trust_fallback" in src
    assert 'mode=scram' in src or "mode=${mode}" in src
    assert "_cluster_ver" in src


def test_install_waits_for_panel_health():
    src = (ROOT / "pgclock.sh").read_text(encoding="utf-8")
    assert 'Panel health' in src or "Panel health" in src
    assert "/health" in src
    assert "journalctl -u" in src


def test_install_global_cli_avoids_dev_stdin():
    src = (ROOT / "scripts" / "install_global_cli.sh").read_text(encoding="utf-8")
    # Must not feed /dev/stdin to `install` (fails under some sudo/pipe setups).
    assert "install -m 755 /dev/stdin" not in src
    assert "mktemp" in src
    assert 'install -m 755 "${tmp_bin}"' in src


def test_readme_documents_auto_postgres_install():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "PostgreSQL automatically" in readme
    assert "PGCLOCK_DATABASE_URL" in readme


def test_alembic_revision_ids_documented_over_32():
    """Guard: long revision ids need the PG version_num widen in alembic/env.py."""
    import re

    env = (ROOT / "alembic" / "env.py").read_text(encoding="utf-8")
    assert "_ensure_alembic_version_num_width" in env
    assert "VARCHAR({_ALEMBIC_VERSION_NUM_LEN})" in env

    lengths: list[int] = []
    for path in (ROOT / "alembic" / "versions").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        m = re.search(
            r'^revision\s*(?::\s*str)?\s*=\s*["\']([0-9A-Za-z_]+)["\']',
            text,
            re.M,
        )
        assert m, f"missing revision in {path.name}"
        lengths.append(len(m.group(1)))
    assert max(lengths) > 32, "expected at least one revision id longer than VARCHAR(32)"
    assert max(lengths) <= 128
