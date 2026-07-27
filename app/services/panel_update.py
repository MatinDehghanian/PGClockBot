from __future__ import annotations

"""In-panel self-update + rollback with persisted progress for the web UI."""

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, ROOT_DIR
from app.services.updates import check_github_update, clear_update_cache, local_version

logger = logging.getLogger(__name__)

STATUS_FILE = DATA_DIR / "panel_update.json"
SNAPSHOTS_FILE = DATA_DIR / "update_snapshots.json"
SERVICE_NAME = "pgclockbot"
_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
MAX_SNAPSHOTS = 8

# systemd often has a short PATH — resolve absolute binaries
_EXTRA_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def _which(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for prefix in ("/usr/bin", "/bin", "/usr/local/bin"):
        candidate = Path(prefix) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _repo_root() -> Path:
    """Prefer ROOT_DIR; walk up if .git lives in a parent (unusual installs)."""
    candidates = [ROOT_DIR, Path.cwd()]
    for base in candidates:
        try:
            cur = base.resolve()
        except Exception:
            cur = base
        for _ in range(6):
            if (cur / ".git").exists() and (cur / "requirements.txt").exists():
                return cur
            if (cur / ".git").exists() and (cur / "run.py").exists():
                return cur
            if cur.parent == cur:
                break
            cur = cur.parent
    return ROOT_DIR.resolve()


def _env_with_path() -> dict[str, str]:
    env = dict(os.environ)
    path = env.get("PATH") or ""
    if _EXTRA_PATH not in path:
        env["PATH"] = f"{_EXTRA_PATH}:{path}" if path else _EXTRA_PATH
    env["DEBIAN_FRONTEND"] = "noninteractive"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env

STEPS = [
    ("prepare", "آماده‌سازی", 5),
    ("backup", "پشتیبان‌گیری", 15),
    ("fetch", "ارتباط با گیت‌هاب", 35),
    ("pull", "اعمال کد", 55),
    ("deps", "نصب وابستگی‌ها", 80),
    ("restart", "راه‌اندازی مجدد سرویس", 95),
    ("done", "تمام شد", 100),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_status() -> dict[str, Any]:
    return {
        "state": "idle",  # idle | running | done | error
        "mode": "update",  # update | rollback
        "percent": 0,
        "step": "",
        "step_key": "",
        "message": "آماده برای آپدیت یا بازگشت",
        "log": [],
        "started_at": None,
        "finished_at": None,
        "from_version": local_version(),
        "to_version": None,
        "error": None,
        "snapshot_id": None,
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
        cur["log"] = log[-100:]
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
        # Resolve first token if it's a bare command name
        exe = cmd[0]
        if "/" not in exe and not Path(exe).exists():
            resolved = _which(exe)
            if not resolved:
                return 1, f"دستور «{exe}» روی سرور پیدا نشد (PATH ناقص است)"
            cmd = [resolved, *cmd[1:]]
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or _repo_root()),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_env_with_path(),
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode, out
    except FileNotFoundError as e:
        return 1, f"فایل/دستور پیدا نشد: {e.filename or e}"
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except Exception as e:
        return 1, str(e)


def _python_bin() -> str:
    root = _repo_root()
    venv_py = root / ".venv" / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def _pip_install() -> tuple[int, str]:
    py = _python_bin()
    req = _repo_root() / "requirements.txt"
    if not req.exists():
        return 0, "no requirements.txt"
    return _run([py, "-m", "pip", "install", "-q", "-r", str(req)], timeout=600)


def _restart_service() -> tuple[bool, str]:
    systemctl = _which("systemctl")
    if systemctl:
        code, out = _run([systemctl, "restart", SERVICE_NAME], timeout=60)
        if code == 0:
            return True, f"systemd restart {SERVICE_NAME}"
        # try without failing hard
        return False, out or "systemctl restart failed"
    return False, "systemd موجود نیست — سرویس را دستی ری‌استارت کنید"


def _git_bin() -> str:
    git = _which("git")
    if not git:
        raise RuntimeError(
            "دستور git روی سرور پیدا نشد. با دسترسی root نصب کنید: apt install -y git"
        )
    return git


def _git_head() -> tuple[str, str]:
    git = _git_bin()
    root = _repo_root()
    code, sha = _run([git, "rev-parse", "HEAD"], cwd=root)
    sha = (sha or "").strip()
    code2, branch = _run([git, "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    branch = (branch or "main").strip() or "main"
    if branch == "HEAD":
        branch = "detached"
    if code != 0 or not sha:
        return "", branch
    return sha, branch


def list_snapshots() -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SNAPSHOTS_FILE.exists():
        return []
    try:
        raw = json.loads(SNAPSHOTS_FILE.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict) and x.get("sha")]
    except Exception:
        pass
    return []


def _save_snapshots(items: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SNAPSHOTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[:MAX_SNAPSHOTS], ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(SNAPSHOTS_FILE)


def create_snapshot(*, reason: str = "before_update") -> dict[str, Any] | None:
    """Save current HEAD so the admin can roll back later."""
    root = _repo_root()
    if not (root / ".git").exists():
        return None
    try:
        sha, branch = _git_head()
    except Exception as e:
        logger.warning("snapshot skipped: %s", e)
        return None
    if not sha:
        return None
    items = list_snapshots()
    # Avoid duplicate consecutive same sha
    if items and items[0].get("sha") == sha:
        return items[0]
    snap = {
        "id": uuid.uuid4().hex[:12],
        "sha": sha,
        "short_sha": sha[:7],
        "version": local_version(),
        "branch": branch,
        "reason": reason,
        "created_at": _now(),
        "label": f"v{local_version()} · {sha[:7]}",
    }
    items.insert(0, snap)
    _save_snapshots(items)
    return snap


def get_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    for item in list_snapshots():
        if item.get("id") == snapshot_id or item.get("sha") == snapshot_id:
            return item
    return None


def _finish_ok(message: str) -> None:
    write_status(
        {
            "state": "done",
            "percent": 100,
            "step_key": "done",
            "step": "تمام شد",
            "message": message,
            "finished_at": _now(),
            "error": None,
        }
    )
    _append_log(message)
    clear_update_cache()


def _finish_error(err: Exception | str) -> None:
    msg = str(err)
    if isinstance(err, Exception):
        logger.exception("panel update/rollback failed: %s", msg)
    else:
        logger.error("panel update/rollback failed: %s", msg)
    write_status(
        {
            "state": "error",
            "message": msg,
            "error": msg,
            "finished_at": _now(),
        }
    )
    _append_log(f"خطا: {msg}")


def _do_update(target_version: str | None) -> None:
    try:
        root = _repo_root()
        write_status(
            {
                "state": "running",
                "mode": "update",
                "percent": 0,
                "error": None,
                "finished_at": None,
                "started_at": _now(),
                "from_version": local_version(),
                "to_version": target_version,
                "log": [],
                "snapshot_id": None,
            }
        )
        _set_step("prepare", "شروع آپدیت…")
        _append_log(f"root={root}")

        git = _git_bin()
        _append_log(f"git={git}")

        _set_step("backup", "ثبت نقطه بازگشت + پشتیبان .env")
        snap = create_snapshot(reason="before_update")
        if snap:
            write_status({"snapshot_id": snap["id"]})
            _append_log(f"نقطه بازگشت ذخیره شد: {snap['label']}")
        else:
            _append_log("هشدار: نتوانستیم نقطه بازگشت git بسازیم")

        env_path = root / ".env"
        if env_path.exists():
            bak = root / f".env.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            shutil.copy2(env_path, bak)
            _append_log(f"پشتیبان env: {bak.name}")

        if not (root / ".git").exists():
            raise RuntimeError(
                f"مخزن git در مسیر پیدا نشد: {root}\n"
                "نصب باید با git clone انجام شده باشد."
            )

        _set_step("fetch", "git fetch…")
        code, out = _run([git, "fetch", "--all", "--tags"], cwd=root, timeout=180)
        if out:
            _append_log(out.splitlines()[-1][:200])
        if code != 0:
            raise RuntimeError(f"git fetch ناموفق: {out[:300]}")

        _set_step("pull", "دریافت کد (origin/main)…")
        _, branch = _run([git, "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
        branch = (branch or "main").strip() or "main"
        if branch == "HEAD":
            branch = "main"
        code, out = _run([git, "pull", "--ff-only", "origin", branch], cwd=root, timeout=180)
        if code != 0:
            _append_log("ff-only ناموفق — همگام‌سازی با origin/main")
            code2, out2 = _run(
                [git, "checkout", "-f", "-B", "main", "origin/main"], cwd=root, timeout=120
            )
            if code2 != 0:
                raise RuntimeError(f"checkout main ناموفق: {out2[:300]}")
            code3, out3 = _run([git, "reset", "--hard", "origin/main"], cwd=root, timeout=120)
            if code3 != 0:
                raise RuntimeError(f"reset ناموفق: {out3[:300]}")
            _run(
                [
                    git,
                    "clean",
                    "-fd",
                    "--exclude=.env",
                    "--exclude=data",
                    "--exclude=.venv",
                    "--exclude=.env.bak.*",
                ],
                cwd=root,
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

        ver_file = root / "VERSION"
        new_ver = (
            ver_file.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            if ver_file.exists()
            else target_version
        )
        write_status({"to_version": new_ver or target_version})

        _set_step("restart", "راه‌اندازی مجدد…")
        ok, note = _restart_service()
        _append_log(note)
        if not ok:
            _finish_ok("کد آپدیت شد؛ سرویس را دستی ری‌استارت کنید. در صورت پشیمانی از «بازگشت» استفاده کنید.")
            return

        time.sleep(1.5)
        _finish_ok("آپدیت با موفقیت انجام شد — در صورت پشیمانی می‌توانید برگردید عقب")
    except Exception as e:
        _finish_error(e)


def _do_rollback(snapshot_id: str) -> None:
    try:
        snap = get_snapshot(snapshot_id)
        if not snap:
            raise RuntimeError("نقطه بازگشت پیدا نشد")
        sha = snap["sha"]
        root = _repo_root()
        git = _git_bin()
        write_status(
            {
                "state": "running",
                "mode": "rollback",
                "percent": 0,
                "error": None,
                "finished_at": None,
                "started_at": _now(),
                "from_version": local_version(),
                "to_version": snap.get("version"),
                "log": [],
                "snapshot_id": snap.get("id"),
            }
        )
        _set_step("prepare", f"شروع بازگشت به {snap.get('label')}")
        _append_log(f"root={root}")

        if not (root / ".git").exists():
            raise RuntimeError(f"مخزن git پیدا نشد: {root}")

        # Snapshot current state before rolling back (so they can undo the undo)
        _set_step("backup", "ثبت وضعیت فعلی قبل از بازگشت")
        pre = create_snapshot(reason="before_rollback")
        if pre:
            _append_log(f"وضعیت فعلی هم ذخیره شد: {pre['label']}")

        env_path = root / ".env"
        if env_path.exists():
            bak = root / f".env.bak.rollback.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            shutil.copy2(env_path, bak)
            _append_log(f"پشتیبان env: {bak.name}")

        _set_step("fetch", "بررسی دسترسی به کامیت…")
        code, out = _run([git, "cat-file", "-t", sha], cwd=root, timeout=30)
        if code != 0 or "commit" not in (out or ""):
            _run([git, "fetch", "--all", "--tags"], cwd=root, timeout=180)
            code, out = _run([git, "cat-file", "-t", sha], cwd=root, timeout=30)
            if code != 0:
                raise RuntimeError(f"کامیت {sha[:7]} در دسترس نیست")

        _set_step("pull", f"بازگردانی کد به {sha[:7]}…")
        code, out = _run([git, "reset", "--hard", sha], cwd=root, timeout=120)
        if code != 0:
            raise RuntimeError(f"reset ناموفق: {out[:300]}")
        _run(
            [
                git,
                "clean",
                "-fd",
                "--exclude=.env",
                "--exclude=data",
                "--exclude=.venv",
                "--exclude=.env.bak.*",
            ],
            cwd=root,
            timeout=60,
        )
        _append_log(f"کد به {sha[:7]} برگشت")

        _set_step("deps", "نصب دوباره وابستگی‌ها…")
        code, out = _pip_install()
        if code != 0:
            raise RuntimeError(f"pip install ناموفق: {out[:400]}")

        ver_file = root / "VERSION"
        new_ver = (
            ver_file.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            if ver_file.exists()
            else snap.get("version")
        )
        write_status({"to_version": new_ver})

        _set_step("restart", "راه‌اندازی مجدد…")
        ok, note = _restart_service()
        _append_log(note)
        if not ok:
            _finish_ok(f"بازگشت به {new_ver or sha[:7]} انجام شد؛ سرویس را دستی ری‌استارت کنید")
            return
        time.sleep(1.5)
        _finish_ok(f"بازگشت موفق به نسخه {new_ver or sha[:7]}")
    except Exception as e:
        _finish_error(e)


def _start_thread(target, *args) -> dict[str, Any]:
    global _THREAD
    with _LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return {"ok": False, "error": "یک عملیات آپدیت/بازگشت در حال اجراست"}
        _THREAD = threading.Thread(target=target, args=args, name="panel-update", daemon=True)
        _THREAD.start()
    return {"ok": True, "status": read_status()}


def start_update(target_version: str | None = None) -> dict[str, Any]:
    return _start_thread(_do_update, target_version)


def start_rollback(snapshot_id: str) -> dict[str, Any]:
    if not get_snapshot(snapshot_id):
        return {"ok": False, "error": "نقطه بازگشت معتبر نیست"}
    return _start_thread(_do_rollback, snapshot_id)


async def update_page_context() -> dict[str, Any]:
    info = await check_github_update()
    status = read_status()
    snaps = list_snapshots()
    return {
        "update_info": info,
        "status": status,
        "local_version": local_version(),
        "steps": [{"key": k, "label": lab, "percent": pct} for k, lab, pct in STEPS],
        "snapshots": snaps,
        "can_rollback": bool(snaps),
    }
