"""Reliable panel service restart helpers for SSL / updates / bot settings."""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from app.config import DATA_DIR

logger = logging.getLogger(__name__)

SERVICE_NAME = "pgclockbot"
STATUS_PATH = DATA_DIR / "restart_status.json"
HELPER_INSTALL_PATH = Path("/usr/local/lib/pgclockbot/ctl")
HELPER_SOURCE = Path(__file__).resolve().parents[2] / "scripts" / "pgclockbot-ctl"
SUDOERS_PATH = Path("/etc/sudoers.d/pgclockbot")

_restart_lock = threading.Lock()
_restart_scheduled = False


def _write_status(payload: dict[str, Any]) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        STATUS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.debug("restart status write failed", exc_info=True)


def get_restart_status() -> dict[str, Any]:
    try:
        if STATUS_PATH.is_file():
            data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        logger.debug("restart status read failed", exc_info=True)
    return {"state": "idle"}


def service_user() -> str:
    return (
        os.environ.get("PGCLOCKBOT_SERVICE_USER")
        or os.environ.get("SUDO_USER")
        or os.environ.get("USER")
        or "root"
    ).strip() or "root"


def _run(cmd: list[str], *, timeout: float = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)


def can_passwordless_sudo() -> bool:
    try:
        return _run(["sudo", "-n", "true"], timeout=5).returncode == 0
    except Exception:
        return False


def ensure_restart_helper() -> tuple[bool, str]:
    """Install ctl helper + sudoers so the service user can restart without a password."""
    if HELPER_INSTALL_PATH.is_file() and SUDOERS_PATH.is_file():
        # Quick validate: helper exists; sudoers may already be fine.
        if can_passwordless_sudo() or _helper_restart_allowed():
            return True, "helper آماده است"

    if not HELPER_SOURCE.is_file():
        return False, "فایل کمکی ریستارت پیدا نشد (scripts/pgclockbot-ctl)."

    if not can_passwordless_sudo():
        return False, (
            "sudo بدون پسورد در دسترس نیست. یک‌بار روی سرور اجرا کنید: "
            "bash pgclock.sh  → Service / یا: sudo bash -c '…install helper…'"
        )

    user = service_user()
    try:
        with tempfile.TemporaryDirectory(prefix="pgclock-ctl-") as tmp:
            tmp_path = Path(tmp)
            ctl_copy = tmp_path / "ctl"
            shutil.copy2(HELPER_SOURCE, ctl_copy)
            ctl_copy.chmod(0o755)

            sudoers = tmp_path / "sudoers"
            sudoers.write_text(
                "# Managed by PGClockBot — passwordless service control\n"
                f"{user} ALL=(root) NOPASSWD: {HELPER_INSTALL_PATH} *\n"
                f"{user} ALL=(root) NOPASSWD: "
                f"/bin/systemctl restart {SERVICE_NAME}, "
                f"/usr/bin/systemctl restart {SERVICE_NAME}, "
                f"/bin/systemctl try-restart {SERVICE_NAME}, "
                f"/usr/bin/systemctl try-restart {SERVICE_NAME}, "
                f"/bin/systemctl is-active {SERVICE_NAME}, "
                f"/usr/bin/systemctl is-active {SERVICE_NAME}, "
                f"/usr/bin/certbot, /bin/certbot\n",
                encoding="utf-8",
            )
            sudoers.chmod(0o440)

            install_script = tmp_path / "install.sh"
            install_script.write_text(
                "#!/bin/bash\n"
                "set -euo pipefail\n"
                f"install -d -m 755 {shlex.quote(str(HELPER_INSTALL_PATH.parent))}\n"
                f"install -m 755 {shlex.quote(str(ctl_copy))} {shlex.quote(str(HELPER_INSTALL_PATH))}\n"
                f"install -m 440 {shlex.quote(str(sudoers))} {shlex.quote(str(SUDOERS_PATH))}\n"
                f"visudo -cf {shlex.quote(str(SUDOERS_PATH))}\n",
                encoding="utf-8",
            )
            install_script.chmod(0o700)

            result = _run(["sudo", "-n", "bash", str(install_script)], timeout=30)
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "").strip() or f"exit {result.returncode}"
                return False, f"نصب helper ریستارت ناموفق: {err[:240]}"
        return True, "helper ریستارت نصب شد"
    except Exception as exc:
        return False, f"نصب helper ریستارت ناموفق: {exc}"


def _helper_restart_allowed() -> bool:
    try:
        listed = _run(["sudo", "-n", "-l"], timeout=5)
        text = (listed.stdout or "") + (listed.stderr or "")
        if listed.returncode != 0:
            return False
        return SERVICE_NAME in text or "pgclockbot" in text.lower() or str(HELPER_INSTALL_PATH) in text
    except Exception:
        return False


def _detached_restart(cmd: list[str], *, delay_sec: float) -> bool:
    """Fire-and-forget restart so the current HTTP worker can exit cleanly."""
    delay = max(0.8, float(delay_sec))
    delay_str = f"{delay:.1f}"
    try:
        probe = _run(["systemd-run", "--version"], timeout=3)
        if probe.returncode == 0:
            # Run as root unit so restart survives killing this service.
            wrapped = [
                "sudo",
                "-n",
                "systemd-run",
                "--quiet",
                "--collect",
                f"--on-active={delay_str}",
                "--timer-property=AccuracySec=100ms",
                *cmd,
            ]
            # If cmd already starts with sudo -n, strip duplicate by using bare cmd under root unit.
            if cmd[:2] == ["sudo", "-n"]:
                inner = cmd[2:]
                wrapped = [
                    "sudo",
                    "-n",
                    "systemd-run",
                    "--quiet",
                    "--collect",
                    f"--on-active={delay_str}",
                    "--timer-property=AccuracySec=100ms",
                    *inner,
                ]
            r = _run(wrapped, timeout=10)
            if r.returncode == 0:
                return True
            # systemd-run without sudo (root process)
            wrapped2 = [
                "systemd-run",
                "--quiet",
                "--collect",
                f"--on-active={delay_str}",
                "--timer-property=AccuracySec=100ms",
                *(cmd[2:] if cmd[:2] == ["sudo", "-n"] else cmd),
            ]
            r2 = _run(wrapped2, timeout=10)
            if r2.returncode == 0:
                return True
    except Exception:
        logger.debug("systemd-run restart schedule failed", exc_info=True)

    try:
        shell_cmd = f"sleep {delay_str}; " + " ".join(shlex.quote(c) for c in cmd)
        subprocess.Popen(
            ["bash", "-lc", shell_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return True
    except Exception:
        logger.exception("detached restart spawn failed")
        return False


def restart_panel_service(*, reason: str = "manual", delay_sec: float = 0.0) -> tuple[bool, str]:
    """Schedule (or immediately queue) a service restart. Returns (ok, message)."""
    _write_status(
        {
            "state": "scheduled",
            "reason": reason,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "pid": os.getpid(),
            "delay_sec": delay_sec,
        }
    )

    candidates: list[list[str]] = [
        ["sudo", "-n", str(HELPER_INSTALL_PATH), "restart"],
        ["sudo", "-n", "systemctl", "restart", SERVICE_NAME],
        ["sudo", "-n", str(HELPER_SOURCE), "restart"],
        ["systemctl", "restart", SERVICE_NAME],
    ]
    for cmd in candidates:
        if _detached_restart(cmd, delay_sec=delay_sec or 1.5):
            logger.info("panel restart scheduled via %s (%s)", " ".join(cmd), reason)
            return True, "ریستارت سرویس زمان‌بندی شد. چند ثانیه صبر کنید."

    _write_status(
        {
            "state": "failed",
            "reason": reason,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "error": "no restart method available",
        }
    )
    return False, (
        "ریستارت خودکار در دسترس نیست. روی سرور اجرا کنید: "
        f"sudo systemctl restart {SERVICE_NAME}"
    )


def schedule_panel_restart(
    *,
    delay_sec: float = 2.5,
    reason: str = "config change",
    ensure_helper: bool = True,
) -> bool:
    """Schedule a one-shot restart after the HTTP response can flush.

    Returns True if a restart was newly scheduled.
    """
    global _restart_scheduled
    with _restart_lock:
        if _restart_scheduled:
            return False
        _restart_scheduled = True

    if ensure_helper:
        ok_h, msg_h = ensure_restart_helper()
        if not ok_h:
            logger.warning("restart helper setup: %s", msg_h)

    ok, note = restart_panel_service(reason=reason, delay_sec=delay_sec)
    if not ok:
        with _restart_lock:
            _restart_scheduled = False
        logger.error("Panel restart schedule failed (%s): %s", reason, note)
        return False

    # Clear the in-process flag after the delay window so later requests can schedule again
    # if this process somehow survives (e.g. restart failed later).
    def _clear() -> None:
        global _restart_scheduled
        time.sleep(max(5.0, float(delay_sec) + 3.0))
        with _restart_lock:
            _restart_scheduled = False

    threading.Thread(target=_clear, name="pgclock-restart-flag", daemon=True).start()
    logger.warning("Panel restart scheduled in %.1fs (%s): %s", delay_sec, reason, note)
    return True
