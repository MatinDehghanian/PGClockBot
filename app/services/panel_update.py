from __future__ import annotations

"""In-panel self-update with persisted progress for the web UI."""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, ROOT_DIR
from app.services.updates import check_github_update, local_version

logger = logging.getLogger(__name__)

STATUS_FILE = DATA_DIR / "panel_update.json"
SERVICE_NAME = "pgclockbot"
_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None

STEPS = [
    ("prepare", "آماده‌سازی", 5),
    ("backup", "پشتیبان از تنظیمات", 15),
    ("fetch", "دریافت نسخه جدید از گیت‌هاب", 35),
    ("pull", "اعمال کد جدید", 55),
    ("deps", "نصب وابستگی‌ها", 80),
    ("restart", "راه‌اندازی مجدد سرویس", 95),
    ("done", "تمام شد", 100),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_status() -> dict[str, Any]:
    return {
        "state": "idle",  # idle | running | done | error
        "percent": 0,
        "step": "",
        "step_key": "",
        "message": "آماده برای آپدیت",
        "log": [],
        "started_at": None,
        "finished_at": None,
        "from_version": local_version(),
        "to_version": None,
        "error": None,
    }


def read_status() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATUS_FILE.exists():
        return _default_status()
    try:
        data = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_status()
        base = _default_status()
        base.update(data)
        return base
    except Exception:
        return _default_status()


def write_status(patch: dict[str, Any]) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        cur = read_status()
        cur.update(patch)
        tmp = STATUS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATUS_FILE)
        return cur


def _append_log(line: str) -> None:
    with _LOCK:
        cur = read_status()
        log = list(cur.get("log") or [])
        log.append(f"{datetime.now().strftime('%H:%M:%S')} {line}")
        cur["log"] = log[-80:]
        tmp = STATUS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATUS_FILE)


def _set_step(key: str, message: str | None = None) -> None:
    meta = next((s for s in STEPS if s[0] == key), None)
    if not meta:
        return
    write_status(
        {
            "state": "running" if key != "done" else "done",
            "step_key": key,
            "step": meta[1],
            "percent": meta[2],
            "message": message or meta[1],
        }
    )
    _append_log(message or meta[1])


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 300) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except Exception as e:
        return 1, str(e)


def _python_bin() -> str:
    venv_py = ROOT_DIR / ".venv" / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def _pip_install() -> tuple[int, str]:
    py = _python_bin()
    req = ROOT_DIR / "requirements.txt"
    if not req.exists():
        return 0, "no requirements.txt"
    return _run([py, "-m", "pip", "install", "-q", "-r", str(req)], timeout=600)


def _restart_service() -> tuple[bool, str]:
    # Prefer systemd when available; otherwise soft signal that UI should reload.
    if shutil.which("systemctl"):
        code, out = _run(["systemctl", "restart", SERVICE_NAME], timeout=60)
        if code == 0:
            return True, f"systemd restart {SERVICE_NAME}"
        # try without privilege escalation already failed; note for user
        return False, out or "systemctl restart failed"
    return False, "systemd موجود نیست — سرویس را دستی ری‌استارت کنید"


def _do_update(target_version: str | None) -> None:
    try:
        write_status(
            {
                "state": "running",
                "percent": 0,
                "error": None,
                "finished_at": None,
                "started_at": _now(),
                "from_version": local_version(),
                "to_version": target_version,
                "log": [],
            }
        )
        _set_step("prepare", "شروع آپدیت…")

        _set_step("backup", "پشتیبان از .env")
        env_path = ROOT_DIR / ".env"
        if env_path.exists():
            bak = ROOT_DIR / f".env.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            shutil.copy2(env_path, bak)
            _append_log(f"پشتیبان: {bak.name}")

        git_dir = ROOT_DIR / ".git"
        if not git_dir.exists():
            raise RuntimeError("مخزن git پیدا نشد — آپدیت از پنل ممکن نیست")

        _set_step("fetch", "git fetch…")
        code, out = _run(["git", "fetch", "--all", "--tags"], timeout=180)
        if out:
            _append_log(out.splitlines()[-1][:200])
        if code != 0:
            raise RuntimeError(f"git fetch ناموفق: {out[:300]}")

        _set_step("pull", "دریافت کد (origin/main)…")
        # Prefer fast-forward of current branch; fall back to origin/main like pgclock.sh
        branch_code, branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        branch = (branch or "main").strip() or "main"
        if branch == "HEAD":
            branch = "main"
        code, out = _run(["git", "pull", "--ff-only", "origin", branch], timeout=180)
        if code != 0:
            _append_log("ff-only ناموفق — همگام‌سازی با origin/main")
            code2, out2 = _run(["git", "checkout", "-f", "-B", "main", "origin/main"], timeout=120)
            if code2 != 0:
                raise RuntimeError(f"checkout main ناموفق: {out2[:300]}")
            code3, out3 = _run(["git", "reset", "--hard", "origin/main"], timeout=120)
            if code3 != 0:
                raise RuntimeError(f"reset ناموفق: {out3[:300]}")
            _run(
                [
                    "git",
                    "clean",
                    "-fd",
                    "--exclude=.env",
                    "--exclude=data",
                    "--exclude=.venv",
                    "--exclude=.env.bak.*",
                ],
                timeout=60,
            )
            _append_log("کد با origin/main همگام شد")
        else:
            _append_log(f"کد به‌روز شد ({branch})")
            if out:
                _append_log(out.splitlines()[-1][:200])

        _set_step("deps", "نصب پکیج‌های پایتون…")
        code, out = _pip_install()
        if code != 0:
            raise RuntimeError(f"pip install ناموفق: {out[:400]}")
        _append_log("وابستگی‌ها نصب شد")

        # Refresh local version from VERSION file if present after pull
        ver_file = ROOT_DIR / "VERSION"
        new_ver = ver_file.read_text(encoding="utf-8").strip().splitlines()[0].strip() if ver_file.exists() else target_version
        write_status({"to_version": new_ver or target_version})

        _set_step("restart", "راه‌اندازی مجدد…")
        ok, note = _restart_service()
        _append_log(note)
        if not ok:
            # Still mark done — code is updated; user may need manual restart
            write_status(
                {
                    "state": "done",
                    "percent": 100,
                    "step_key": "done",
                    "step": "تمام شد",
                    "message": "کد آپدیت شد؛ سرویس را دستی ری‌استارت کنید",
                    "finished_at": _now(),
                    "error": None,
                }
            )
            _append_log("آپدیت کد انجام شد (بدون ری‌استارت خودکار)")
            return

        # Give systemd a moment; then mark done (process may die on restart)
        time.sleep(1.5)
        write_status(
            {
                "state": "done",
                "percent": 100,
                "step_key": "done",
                "step": "تمام شد",
                "message": "آپدیت با موفقیت انجام شد",
                "finished_at": _now(),
                "error": None,
            }
        )
        _append_log("آپدیت کامل شد")
    except Exception as e:
        logger.exception("panel update failed")
        write_status(
            {
                "state": "error",
                "message": str(e),
                "error": str(e),
                "finished_at": _now(),
            }
        )
        _append_log(f"خطا: {e}")


def is_running() -> bool:
    st = read_status()
    if st.get("state") != "running":
        return False
    global _THREAD
    return _THREAD is not None and _THREAD.is_alive()


def start_update(target_version: str | None = None) -> dict[str, Any]:
    global _THREAD
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return {"ok": False, "error": "آپدیت در حال اجراست"}
        st = read_status()
        if st.get("state") == "running":
            # stale flag without live thread — allow restart
            pass
        _THREAD = threading.Thread(
            target=_do_update,
            args=(target_version,),
            name="panel-update",
            daemon=True,
        )
        _THREAD.start()
    return {"ok": True, "status": read_status()}


async def update_page_context() -> dict[str, Any]:
    info = await check_github_update()
    status = read_status()
    return {
        "update_info": info,
        "status": status,
        "local_version": local_version(),
        "steps": [{"key": k, "label": lab, "percent": pct} for k, lab, pct in STEPS],
    }
