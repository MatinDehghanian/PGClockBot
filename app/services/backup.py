"""Full data backup / restore for PGClockBot (DB, uploads, credentials, env).

Archive format (ZIP):
  manifest.json
  data/bot.db
  data/web_admin.json          (if present)
  data/uploads/**              (if present)
  data/setup_complete.flag     (if present)
  env/.env                     (optional; included by default for full restore)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import DATA_DIR, ROOT_DIR, get_settings
from app.services.updates import local_version

log = logging.getLogger(__name__)

BACKUP_DIR = DATA_DIR / "backups"
BACKUP_PREFIX = "pgclock-backup-"
MANIFEST_NAME = "manifest.json"
MAX_BACKUPS = 20
RESTORE_STATUS_FILE = DATA_DIR / "backup_restore.json"
MAGIC = "pgclock-backup-v1"

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
        m = re.search(r":///(.+)$", url)
        if m:
            raw = m.group(1)
            if raw.startswith("/"):
                return Path(raw)
            return (ROOT_DIR / raw).resolve()
    return DATA_DIR / "bot.db"


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
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if zf.testzip() is not None:
                return False, "آرشیو آسیب دیده است", None
            names = set(zf.namelist())
            if MANIFEST_NAME not in names:
                return False, "manifest.json موجود نیست", None
            manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
            if not isinstance(manifest, dict) or manifest.get("magic") != MAGIC:
                return False, "فرمت بکاپ نامعتبر است", None
            if "data/bot.db" not in names:
                return False, "دیتابیس داخل بکاپ نیست", None
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
    """Create a full backup ZIP under data/backups/. Thread-safe."""
    with _lock:
        ensure_backup_dir()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        stamp = _utcnow_stamp()
        backup_id = f"{stamp}-{uuid4().hex[:8]}"
        out_path = BACKUP_DIR / f"{BACKUP_PREFIX}{backup_id}.zip"
        db_src = sqlite_db_path()

        with tempfile.TemporaryDirectory(prefix="pgclock-bak-") as tmp:
            tmp_root = Path(tmp)
            data_tmp = tmp_root / "data"
            data_tmp.mkdir(parents=True, exist_ok=True)

            # DB (online-safe)
            db_copy = data_tmp / "bot.db"
            _safe_copy_sqlite(db_src, db_copy)

            files_meta: list[dict[str, Any]] = [
                {
                    "path": "data/bot.db",
                    "sha256": _sha256_file(db_copy),
                    "size": db_copy.stat().st_size,
                }
            ]

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

            # uploads tree
            uploads = DATA_DIR / "uploads"
            if uploads.is_dir():
                for path in uploads.rglob("*"):
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
                "db_path": str(db_src),
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
        # Rewrite manifest inside zip with archive hash (best-effort sidecar)
        sidecar = out_path.with_suffix(".json")
        manifest["archive_sha256"] = archive_sha
        manifest["archive_size"] = out_path.stat().st_size
        sidecar.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

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
                if not extracted_db.is_file():
                    raise FileNotFoundError("bot.db در بکاپ نیست")

                _set_restore_status(
                    {
                        "state": "running",
                        "step": "db",
                        "message": "بازیابی دیتابیس…",
                        "started_at": _now_iso(),
                        "actor": actor,
                        "safety_id": safety_id,
                    }
                )
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                live_db = sqlite_db_path()
                live_db.parent.mkdir(parents=True, exist_ok=True)
                # Replace DB via temp then rename (atomic on same FS)
                tmp_db = live_db.with_suffix(".db.restoring")
                shutil.copy2(extracted_db, tmp_db)
                os.replace(tmp_db, live_db)

                # web_admin.json
                auth_src = tmp_root / "data" / "web_admin.json"
                if auth_src.is_file():
                    shutil.copy2(auth_src, DATA_DIR / "web_admin.json")

                # flags
                for flag_name in ("setup_complete.flag", "setup_in_progress.flag"):
                    src = tmp_root / "data" / flag_name
                    dest = DATA_DIR / flag_name
                    if src.is_file():
                        shutil.copy2(src, dest)
                    elif flag_name == "setup_in_progress.flag" and dest.exists():
                        dest.unlink(missing_ok=True)

                # uploads: replace tree
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
                uploads_src = tmp_root / "data" / "uploads"
                uploads_dest = DATA_DIR / "uploads"
                if uploads_src.is_dir():
                    if uploads_dest.exists():
                        shutil.rmtree(uploads_dest)
                    shutil.copytree(uploads_src, uploads_dest)
                elif uploads_dest.exists():
                    # Backup had no uploads — clear existing to match snapshot
                    shutil.rmtree(uploads_dest)
                    uploads_dest.mkdir(parents=True, exist_ok=True)

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
