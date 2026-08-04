"""pgclock doctor — install / service / database diagnostics."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.cli.context import (
    CliContext,
    SERVICE_NAME,
    database_url,
    env_get,
    service_unit_installed,
    systemctl,
    web_port,
)
from app.cli.install_root import MARKER_PATH, python_bin
from app.cli.output import header, info, kv, ok, warn
from app.cli.service_cmds import _probe_health


def cmd_doctor(ctx: CliContext) -> int:
    header("doctor")
    issues = 0

    def fail(msg: str) -> None:
        nonlocal issues
        issues += 1
        warn(msg)

    kv("install", ctx.root)
    if MARKER_PATH.is_file():
        ok(f"global marker {MARKER_PATH}")
    else:
        warn(f"global marker missing ({MARKER_PATH}) — CLI may still work via PGCLOCK_HOME")

    if Path("/usr/local/bin/pgclock").is_file():
        ok("global binary /usr/local/bin/pgclock")
    else:
        warn("global binary not installed — run: sudo bash scripts/install_global_cli.sh")

    if ctx.env_path.is_file():
        try:
            mode = oct(ctx.env_path.stat().st_mode)[-3:]
            ok(f".env present (mode {mode})")
            if mode not in {"600", "640"}:
                warn(".env permissions should be 600")
        except OSError:
            ok(".env present")
    else:
        fail(".env missing")

    py = python_bin(ctx.root)
    if py.is_file() or shutil.which(str(py)):
        ok(f"python {py}")
    else:
        fail(f"python not found: {py}")

    if service_unit_installed():
        st = systemctl("is-active", SERVICE_NAME)
        state = (st.stdout or "").strip() or "unknown"
        if state == "active":
            ok(f"systemd {SERVICE_NAME} active")
        else:
            warn(f"systemd {SERVICE_NAME} state={state}")
    else:
        warn(f"systemd unit {SERVICE_NAME} not installed")

    # Database
    url = database_url(ctx.root)
    try:
        from app.db.engine_url import parse_engine, to_sync_url
        from sqlalchemy import create_engine, text

        info_eng = parse_engine(url)
        kv("database", info_eng.dialect)
        eng = create_engine(to_sync_url(url))
        try:
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
            ok("database connectivity")
        finally:
            eng.dispose()
        from app.db.alembic_runner import current_revision

        rev = current_revision(url)
        if rev:
            ok(f"alembic revision {rev}")
        else:
            warn("alembic_version empty — run: pgclock migrate")
        if info_eng.is_postgresql:
            if shutil.which("pg_dump") and shutil.which("pg_restore"):
                ok("pg_dump / pg_restore available")
            else:
                warn("postgresql-client missing (pg_dump/pg_restore) — backups will fail")
    except Exception as e:
        fail(f"database check failed: {e}")

    # Health
    port = web_port(ctx.root)
    health = _probe_health(port)
    if health.get("ok"):
        ok(f"web /health on :{port}")
    else:
        warn(f"web /health unreachable on :{port} ({health.get('error')})")

    # Disk
    try:
        usage = shutil.disk_usage(ctx.root)
        free_gb = usage.free / (1024**3)
        kv("disk_free", f"{free_gb:.1f} GiB")
        if free_gb < 1:
            warn("low disk space (<1 GiB)")
    except OSError:
        pass

    # data dir perms
    data = ctx.data_dir
    if data.is_dir():
        ok(f"data dir {data}")
    else:
        warn(f"data dir missing: {data}")

    secret = env_get(ctx.root, "WEB_SECRET", "")
    if not secret or secret in {"change-me", "changeme"}:
        warn("WEB_SECRET is missing or placeholder")
    else:
        ok("WEB_SECRET set")

    header("doctor summary")
    if issues == 0:
        ok("no critical issues")
        return 0
    warn(f"{issues} critical issue(s) found")
    return 1
