"""Full data backup / restore for PGClockBot (DB, uploads, credentials, env).

Archive format (ZIP):
  manifest.json
  data/bot.db                  (SQLite engine)
  data/postgres.dump           (PostgreSQL engine — pg_dump -Fc)
  data/web_admin.json          (if present)
  data/uploads/**              (if present)
  data/setup_complete.flag     (if present)
  env/.env                     (optional; included by default for full restore)

Manifest includes db_engine: sqlite | postgresql. Restore refuses engine mismatch.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import DATA_DIR, ROOT_DIR, get_settings
from app.db.engine_url import parse_engine, pg_connection_parts
from app.services.updates import local_version

log = logging.getLogger(__name__)

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_PREFIX = "pgclock-backup-"
MANIFEST_NAME = "manifest.json"
MAX_BACKUPS = 20
RESTORE_STATUS_FILE = DATA_DIR / "backup_restore.json"
MAGIC = "pgclock-backup-v1"
SQLITE_DB_MEMBER = "data/bot.db"
POSTGRES_DUMP_MEMBER = "data/postgres.dump"

# RLock: restore creates a safety backup while already holding the lock.
_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utcnow_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def sqlite_db_path() -> Path:
    """Resolve on-disk SQLite path from DATABASE_URL (best-effort)."""
    url = (get_settings().database_url or "").strip()
    if "sqlite" in url:
        try:
            info = parse_engine(url)
            if info.sqlite_path:
                return info.sqlite_path
        except Exception:
            pass
        m = re.search(r":///(.+)$", url)
        if m:
            raw = m.group(1)
            if raw.startswith("/"):
                return Path(raw)
            return (ROOT_DIR / raw).resolve()
    return DATA_DIR / "bot.db"


def current_db_engine() -> str:
    """Return 'sqlite' or 'postgresql' for the configured DATABASE_URL."""
    try:
        return parse_engine(get_settings().database_url).dialect
    except Exception:
        return "sqlite"


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def _dump_postgres(dest: Path) -> dict[str, Any]:
    """Create a custom-format pg_dump at dest."""
    pg_dump = _which("pg_dump")
    if not pg_dump:
        raise RuntimeError("pg_dump not found — install postgresql-client")
    parts = pg_connection_parts(get_settings().database_url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    env = os.environ.copy()
    if parts.get("password"):
        env["PGPASSWORD"] = str(parts["password"])
    cmd = [
        pg_dump,
        "--format=custom",
        "--no-owner",
        "--no-acl",
        "--file",
        str(dest),
        "--host",
        str(parts["host"]),
        "--port",
        str(parts["port"]),
        "--username",
        str(parts["user"]),
        "--dbname",
        str(parts["dbname"]),
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 1:
        raise RuntimeError(
            f"pg_dump failed (code={proc.returncode}): {(proc.stderr or proc.stdout or '')[:500]}"
        )
    return {"path": POSTGRES_DUMP_MEMBER, "size": dest.stat().st_size}


def _restore_postgres_dump(dump_path: Path) -> None:
    """Restore a custom-format dump into the configured PostgreSQL database."""
    pg_restore = _which("pg_restore")
    if not pg_restore:
        raise RuntimeError("pg_restore not found — install postgresql-client")
    parts = pg_connection_parts(get_settings().database_url)
    env = os.environ.copy()
    if parts.get("password"):
        env["PGPASSWORD"] = str(parts["password"])
    # Drop+recreate public schema objects via --clean --if-exists
    cmd = [
        pg_restore,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-acl",
        "--host",
        str(parts["host"]),
        "--port",
        str(parts["port"]),
        "--username",
        str(parts["user"]),
        "--dbname",
        str(parts["dbname"]),
        str(dump_path),
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=600)
    # pg_restore may return non-zero for benign notices; require DB connectivity after
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"pg_restore failed (code={proc.returncode}): {(proc.stderr or proc.stdout or '')[:800]}"
        )


def _sha256_file(path: Path, *, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _safe_copy_sqlite(src: Path, dest: Path) -> None:
    """Online-safe SQLite backup using the backup API."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    if not src.exists():
        raise FileNotFoundError(f"دیتابیس یافت نشد: {src}")
    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dst_conn)
            dst_conn.commit()
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def ensure_backup_dir() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUP_DIR


def list_backups() -> list[dict[str, Any]]:
    ensure_backup_dir()
    items: list[dict[str, Any]] = []
    for path in sorted(BACKUP_DIR.glob(f"{BACKUP_PREFIX}*.zip"), reverse=True):
        try:
            st = path.stat()
            meta = read_manifest(path) or {}
            items.append(
                {
                    "id": path.stem.replace(BACKUP_PREFIX, "", 1),
                    "filename": path.name,
                    "path": str(path),
                    "size": st.st_size,
                    "size_human": _human_size(st.st_size),
                    "mtime": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                    "created_at": meta.get("created_at") or datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
                    "app_version": meta.get("app_version") or "—",
                    "include_env": bool(meta.get("include_env")),
                    "files": meta.get("files") or [],
                    "sha256": meta.get("archive_sha256") or "",
                    "note": meta.get("note") or "",
                }
            )
        except Exception:
            log.exception("Failed reading backup %s", path)
    return items


def get_backup_path(backup_id: str) -> Path | None:
    backup_id = (backup_id or "").strip()
    if not backup_id or "/" in backup_id or "\\" in backup_id or ".." in backup_id:
        return None
    # Accept id or full filename stem
    candidates = [
        BACKUP_DIR / f"{BACKUP_PREFIX}{backup_id}.zip",
        BACKUP_DIR / f"{backup_id}.zip",
    ]
    if backup_id.endswith(".zip"):
        candidates.insert(0, BACKUP_DIR / backup_id)
    for p in candidates:
        if p.is_file() and p.resolve().parent == BACKUP_DIR.resolve():
            return p
    return None


def read_manifest(zip_path: Path) -> dict[str, Any] | None:
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if MANIFEST_NAME not in zf.namelist():
                return None
            raw = zf.read(MANIFEST_NAME).decode("utf-8")
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
    except Exception:
        return None


def validate_backup_archive(zip_path: Path) -> tuple[bool, str, dict[str, Any] | None]:
    if not zip_path.is_file():
        return False, "فایل بکاپ یافت نشد", None
    max_members = 5000
    max_uncompressed = 2 * 1024 * 1024 * 1024  # 2 GiB expanded
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if zf.testzip() is not None:
                return False, "آرشیو آسیب دیده است", None
            infos = zf.infolist()
            if len(infos) > max_members:
                return False, "تعداد فایل‌های بکاپ بیش از حد مجاز است", None
            total_uncompressed = 0
            for info in infos:
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/"):
                    return False, "مسیر ناامن داخل بکاپ", None
                total_uncompressed += max(0, int(info.file_size or 0))
                if total_uncompressed > max_uncompressed:
                    return False, "حجم uncompressed بکاپ بیش از حد مجاز است", None
            names = set(zf.namelist())
            if MANIFEST_NAME not in names:
                return False, "manifest.json موجود نیست", None
            manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
            if not isinstance(manifest, dict) or manifest.get("magic") != MAGIC:
                return False, "فرمت بکاپ نامعتبر است", None
            db_engine = str(manifest.get("db_engine") or "").strip().lower()
            has_sqlite = SQLITE_DB_MEMBER in names
            has_pg = POSTGRES_DUMP_MEMBER in names
            if not has_sqlite and not has_pg:
                return False, "دیتابیس داخل بکاپ نیست", None
            if not db_engine:
                db_engine = "postgresql" if has_pg and not has_sqlite else "sqlite"
                manifest["db_engine"] = db_engine
            if db_engine == "sqlite" and not has_sqlite:
                return False, "بکاپ SQLite بدون data/bot.db", None
            if db_engine == "postgresql" and not has_pg:
                # Allow legacy archives that only had bot.db while claiming nothing
                if has_sqlite:
                    manifest["db_engine"] = "sqlite"
                else:
                    return False, "بکاپ PostgreSQL بدون data/postgres.dump", None
            # Verify declared file hashes when present (newer backups)
            files_meta = manifest.get("files")
            if isinstance(files_meta, list):
                for entry in files_meta:
                    if not isinstance(entry, dict):
                        continue
                    rel = str(entry.get("path") or "").replace("\\", "/")
                    expect = str(entry.get("sha256") or "").strip().lower()
                    if not rel or not expect or rel == MANIFEST_NAME:
                        continue
                    if rel not in names:
                        return False, f"فایل اعلام‌شده در بکاپ نیست: {rel}", None
                    digest = hashlib.sha256(zf.read(rel)).hexdigest()
                    if digest != expect:
                        return False, f"هش فایل بکاپ نامعتبر است: {rel}", None
            return True, "ok", manifest
    except zipfile.BadZipFile:
        return False, "فایل ZIP معتبر نیست", None
    except Exception as e:
        return False, f"خطا در بررسی بکاپ: {e}", None


def create_backup(
    *,
    note: str = "",
    include_env: bool = True,
    created_by: str = "panel",
) -> dict[str, Any]:
    """Create a full backup ZIP under data/backups/. Thread-safe. Engine-aware."""
    with _lock:
        ensure_backup_dir()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        stamp = _utcnow_stamp()
        backup_id = f"{stamp}-{uuid4().hex[:8]}"
        out_path = BACKUP_DIR / f"{BACKUP_PREFIX}{backup_id}.zip"
        db_engine = current_db_engine()

        with tempfile.TemporaryDirectory(prefix="pgclock-bak-") as tmp:
            tmp_root = Path(tmp)
            data_tmp = tmp_root / "data"
            data_tmp.mkdir(parents=True, exist_ok=True)

            files_meta: list[dict[str, Any]] = []
            db_member = SQLITE_DB_MEMBER

            if db_engine == "postgresql":
                dump_copy = data_tmp / "postgres.dump"
                _dump_postgres(dump_copy)
                db_member = POSTGRES_DUMP_MEMBER
                files_meta.append(
                    {
                        "path": POSTGRES_DUMP_MEMBER,
                        "sha256": _sha256_file(dump_copy),
                        "size": dump_copy.stat().st_size,
                    }
                )
            else:
                db_src = sqlite_db_path()
                db_copy = data_tmp / "bot.db"
                _safe_copy_sqlite(db_src, db_copy)
                files_meta.append(
                    {
                        "path": SQLITE_DB_MEMBER,
                        "sha256": _sha256_file(db_copy),
                        "size": db_copy.stat().st_size,
                    }
                )

            # web_admin.json
            auth = DATA_DIR / "web_admin.json"
            if auth.is_file():
                dest = data_tmp / "web_admin.json"
                shutil.copy2(auth, dest)
                files_meta.append(
                    {
                        "path": "data/web_admin.json",
                        "sha256": _sha256_file(dest),
                        "size": dest.stat().st_size,
                    }
                )

            # setup flag
            for flag_name in ("setup_complete.flag", "setup_in_progress.flag"):
                flag = DATA_DIR / flag_name
                if flag.is_file():
                    dest = data_tmp / flag_name
                    shutil.copy2(flag, dest)
                    files_meta.append(
                        {
                            "path": f"data/{flag_name}",
                            "sha256": _sha256_file(dest),
                            "size": dest.stat().st_size,
                        }
                    )

            # uploads + private attachment trees
            for tree_name in ("uploads", "private"):
                tree = DATA_DIR / tree_name
                if not tree.is_dir():
                    continue
                for path in tree.rglob("*"):
                    if not path.is_file():
                        continue
                    rel = path.relative_to(DATA_DIR)
                    dest = data_tmp / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest)
                    files_meta.append(
                        {
                            "path": f"data/{rel.as_posix()}",
                            "sha256": _sha256_file(dest),
                            "size": dest.stat().st_size,
                        }
                    )

            include_env_ok = False
            env_src = ROOT_DIR / ".env"
            if include_env and env_src.is_file():
                env_dir = tmp_root / "env"
                env_dir.mkdir(parents=True, exist_ok=True)
                env_dest = env_dir / ".env"
                shutil.copy2(env_src, env_dest)
                files_meta.append(
                    {
                        "path": "env/.env",
                        "sha256": _sha256_file(env_dest),
                        "size": env_dest.stat().st_size,
                    }
                )
                include_env_ok = True

            manifest = {
                "magic": MAGIC,
                "created_at": _now_iso(),
                "app_version": local_version(),
                "backup_id": backup_id,
                "created_by": created_by,
                "note": (note or "").strip()[:200],
                "include_env": include_env_ok,
                "db_engine": db_engine,
                "db_path": db_member,
                "files": files_meta,
                "file_count": len(files_meta),
            }
            (tmp_root / MANIFEST_NAME).write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(tmp_root / MANIFEST_NAME, MANIFEST_NAME)
                for item in files_meta:
                    zf.write(tmp_root / item["path"], item["path"])

        archive_sha = _sha256_file(out_path)
        sidecar = out_path.with_suffix(".json")
        manifest["archive_sha256"] = archive_sha
        manifest["archive_size"] = out_path.stat().st_size
        sidecar.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        for p in (out_path, sidecar):
            try:
                p.chmod(0o600)
            except OSError:
                pass
        try:
            backups_root = out_path.parent
            backups_root.chmod(0o700)
            DATA_DIR.chmod(0o700)
        except OSError:
            pass

        _prune_old_backups()

        return {
            "ok": True,
            "id": backup_id,
            "filename": out_path.name,
            "path": str(out_path),
            "size": out_path.stat().st_size,
            "size_human": _human_size(out_path.stat().st_size),
            "sha256": archive_sha,
            "include_env": include_env_ok,
            "app_version": local_version(),
            "created_at": manifest["created_at"],
            "file_count": manifest["file_count"],
            "note": manifest["note"],
            "db_engine": db_engine,
        }


def delete_backup(backup_id: str) -> bool:
    path = get_backup_path(backup_id)
    if not path:
        return False
    with _lock:
        try:
            path.unlink(missing_ok=True)
            sidecar = path.with_suffix(".json")
            sidecar.unlink(missing_ok=True)
            return True
        except Exception:
            log.exception("delete_backup failed")
            return False


def _prune_old_backups() -> None:
    zips = sorted(BACKUP_DIR.glob(f"{BACKUP_PREFIX}*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in zips[MAX_BACKUPS:]:
        try:
            old.unlink(missing_ok=True)
            old.with_suffix(".json").unlink(missing_ok=True)
        except Exception:
            pass


def _set_restore_status(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = RESTORE_STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(RESTORE_STATUS_FILE)


def read_restore_status() -> dict[str, Any]:
    if not RESTORE_STATUS_FILE.exists():
        return {"state": "idle"}
    try:
        return json.loads(RESTORE_STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "idle"}


def restore_backup(
    zip_path: Path,
    *,
    restore_env: bool = True,
    safety_backup: bool = True,
    restart: bool = True,
    actor: str = "panel",
) -> dict[str, Any]:
    """Restore from a validated backup archive.

    Always creates a safety backup first (unless disabled). Schedules service restart.
    """
    ok, err, manifest = validate_backup_archive(zip_path)
    if not ok or not manifest:
        return {"ok": False, "error": err}

    with _lock:
        _set_restore_status(
            {
                "state": "running",
                "step": "validate",
                "message": "در حال بررسی بکاپ…",
                "started_at": _now_iso(),
                "actor": actor,
                "source": str(zip_path),
            }
        )
        safety_id = None
        try:
            # Keep a private copy so safety-backup pruning cannot delete the source zip.
            with tempfile.TemporaryDirectory(prefix="pgclock-restore-") as tmp:
                tmp_root = Path(tmp)
                source_copy = tmp_root / "source.zip"
                shutil.copy2(zip_path, source_copy)

                if safety_backup:
                    _set_restore_status(
                        {
                            "state": "running",
                            "step": "safety",
                            "message": "پشتیبان ایمنی قبل از ریستور…",
                            "started_at": _now_iso(),
                            "actor": actor,
                        }
                    )
                    safety = create_backup(
                        note=f"safety before restore from {zip_path.name}",
                        include_env=True,
                        created_by=f"safety:{actor}",
                    )
                    safety_id = safety.get("id")

                extract_root = tmp_root / "extract"
                extract_root.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(source_copy, "r") as zf:
                    # Prevent zip-slip
                    for info in zf.infolist():
                        name = info.filename
                        if name.startswith("/") or ".." in Path(name).parts:
                            raise ValueError(f"مسیر نامعتبر در آرشیو: {name}")
                    zf.extractall(extract_root)
                # Point subsequent paths at the extracted tree
                tmp_root = extract_root

                extracted_db = tmp_root / "data" / "bot.db"
                extracted_pg = tmp_root / "data" / "postgres.dump"
                archive_engine = str(manifest.get("db_engine") or "").strip().lower()
                if not archive_engine:
                    archive_engine = "postgresql" if extracted_pg.is_file() and not extracted_db.is_file() else "sqlite"
                live_engine = current_db_engine()
                if archive_engine != live_engine:
                    raise RuntimeError(
                        f"بکاپ مربوط به موتور {archive_engine} است ولی DATABASE_URL فعلی {live_engine} است. "
                        "قبل از ریستور DATABASE_URL را هم‌خوان کنید."
                    )
                if archive_engine == "sqlite" and not extracted_db.is_file():
                    raise FileNotFoundError("bot.db در بکاپ نیست")
                if archive_engine == "postgresql" and not extracted_pg.is_file():
                    raise FileNotFoundError("postgres.dump در بکاپ نیست")

                _set_restore_status(
                    {
                        "state": "running",
                        "step": "db",
                        "message": "بازیابی دیتابیس…",
                        "started_at": _now_iso(),
                        "actor": actor,
                        "safety_id": safety_id,
                        "db_engine": archive_engine,
                    }
                )
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                if archive_engine == "postgresql":
                    _restore_postgres_dump(extracted_pg)
                else:
                    live_db = sqlite_db_path()
                    live_db.parent.mkdir(parents=True, exist_ok=True)
                    # Replace DB via temp then rename (atomic on same FS)
                    tmp_db = live_db.with_suffix(".db.restoring")
                    shutil.copy2(extracted_db, tmp_db)
                    os.replace(tmp_db, live_db)
                    try:
                        live_db.chmod(0o600)
                    except OSError:
                        pass

                # web_admin.json
                auth_src = tmp_root / "data" / "web_admin.json"
                if auth_src.is_file():
                    shutil.copy2(auth_src, DATA_DIR / "web_admin.json")
                    try:
                        (DATA_DIR / "web_admin.json").chmod(0o600)
                    except OSError:
                        pass

                # flags
                for flag_name in ("setup_complete.flag", "setup_in_progress.flag"):
                    src = tmp_root / "data" / flag_name
                    dest = DATA_DIR / flag_name
                    if src.is_file():
                        shutil.copy2(src, dest)
                        try:
                            dest.chmod(0o600)
                        except OSError:
                            pass
                    elif flag_name == "setup_in_progress.flag" and dest.exists():
                        dest.unlink(missing_ok=True)

                # uploads + private attachments: replace trees
                _set_restore_status(
                    {
                        "state": "running",
                        "step": "uploads",
                        "message": "بازیابی فایل‌های آپلود…",
                        "started_at": _now_iso(),
                        "actor": actor,
                        "safety_id": safety_id,
                    }
                )
                for tree_name in ("uploads", "private"):
                    tree_src = tmp_root / "data" / tree_name
                    tree_dest = DATA_DIR / tree_name
                    if tree_src.is_dir():
                        if tree_dest.exists():
                            shutil.rmtree(tree_dest)
                        shutil.copytree(tree_src, tree_dest)
                    elif tree_name == "uploads" and tree_dest.exists():
                        # Backup had no uploads — clear existing to match snapshot
                        shutil.rmtree(tree_dest)
                        tree_dest.mkdir(parents=True, exist_ok=True)
                try:
                    DATA_DIR.chmod(0o700)
                    priv = DATA_DIR / "private"
                    if priv.is_dir():
                        priv.chmod(0o700)
                except OSError:
                    pass

                env_restored = False
                env_src = tmp_root / "env" / ".env"
                if restore_env and env_src.is_file():
                    _set_restore_status(
                        {
                            "state": "running",
                            "step": "env",
                            "message": "بازیابی تنظیمات .env…",
                            "started_at": _now_iso(),
                            "actor": actor,
                            "safety_id": safety_id,
                        }
                    )
                    env_dest = ROOT_DIR / ".env"
                    bak = ROOT_DIR / f".env.bak.restore.{_utcnow_stamp()}"
                    if env_dest.exists():
                        shutil.copy2(env_dest, bak)
                    shutil.copy2(env_src, env_dest)
                    try:
                        env_dest.chmod(0o600)
                    except OSError:
                        pass
                    env_restored = True

            result = {
                "ok": True,
                "message": "ریستور انجام شد",
                "safety_id": safety_id,
                "app_version_in_backup": manifest.get("app_version"),
                "include_env_restored": env_restored,
                "restart_scheduled": False,
            }

            if restart:
                from app.services.service_control import schedule_panel_restart

                result["restart_scheduled"] = schedule_panel_restart(
                    delay_sec=2.0,
                    reason="backup restore",
                )

            _set_restore_status(
                {
                    "state": "done",
                    "step": "done",
                    "message": "ریستور موفق — سرویس در حال راه‌اندازی مجدد است"
                    if result["restart_scheduled"]
                    else "ریستور موفق",
                    "finished_at": _now_iso(),
                    "actor": actor,
                    "safety_id": safety_id,
                    "source": str(zip_path),
                }
            )
            return result
        except Exception as e:
            log.exception("restore_backup failed")
            _set_restore_status(
                {
                    "state": "error",
                    "step": "error",
                    "message": str(e),
                    "finished_at": _now_iso(),
                    "actor": actor,
                    "safety_id": safety_id,
                }
            )
            return {"ok": False, "error": str(e), "safety_id": safety_id}


def save_uploaded_backup(content: bytes, *, filename: str = "") -> dict[str, Any]:
    """Store an uploaded zip into backups dir after validation."""
    if not content or len(content) < 64:
        return {"ok": False, "error": "فایل خالی یا خیلی کوچک است"}
    if len(content) > 500 * 1024 * 1024:
        return {"ok": False, "error": "حجم بکاپ بیش از حد مجاز است (۵۰۰ مگابایت)"}

    ensure_backup_dir()
    stamp = _utcnow_stamp()
    backup_id = f"upload-{stamp}-{uuid4().hex[:8]}"
    dest = BACKUP_DIR / f"{BACKUP_PREFIX}{backup_id}.zip"
    dest.write_bytes(content)

    ok, err, manifest = validate_backup_archive(dest)
    if not ok:
        dest.unlink(missing_ok=True)
        return {"ok": False, "error": err}

    sidecar = dest.with_suffix(".json")
    meta = dict(manifest or {})
    meta["archive_sha256"] = _sha256_file(dest)
    meta["archive_size"] = dest.stat().st_size
    meta["uploaded_as"] = (filename or "")[:120]
    meta["uploaded_at"] = _now_iso()
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    _prune_old_backups()
    return {
        "ok": True,
        "id": backup_id,
        "filename": dest.name,
        "path": str(dest),
        "size": dest.stat().st_size,
        "size_human": _human_size(dest.stat().st_size),
        "app_version": meta.get("app_version"),
        "include_env": bool(meta.get("include_env")),
    }


def _human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(n)
    for u in units:
        if size < 1024 or u == units[-1]:
            if u == "B":
                return f"{int(size)} {u}"
            return f"{size:.1f} {u}"
        size /= 1024
    return f"{n} B"
