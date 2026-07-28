from __future__ import annotations

"""Restart the panel/bot process so new .env (BOT_TOKEN, etc.) takes effect."""

import logging
import threading
import time

logger = logging.getLogger(__name__)

_restart_lock = threading.Lock()
_restart_scheduled = False


def restart_panel_service() -> tuple[bool, str]:
    """Try systemd restart (with and without sudo); return (ok, message)."""
    try:
        from app.services.panel_update import SERVICE_NAME, _run, _which

        systemctl = _which("systemctl")
        if not systemctl:
            return False, "systemd موجود نیست — دستی: sudo systemctl restart pgclockbot"

        attempts = [
            [systemctl, "restart", SERVICE_NAME],
            [systemctl, "try-restart", SERVICE_NAME],
        ]
        sudo = _which("sudo")
        if sudo:
            attempts.append([sudo, "-n", systemctl, "restart", SERVICE_NAME])

        last = "systemctl restart failed"
        for cmd in attempts:
            code, out = _run(cmd, timeout=60)
            if code == 0:
                return True, " ".join(cmd)
            last = (out or last)[:300]
        return False, last
    except Exception as exc:
        logger.exception("restart_panel_service failed")
        return False, str(exc)


def schedule_panel_restart(
    *,
    delay_sec: float = 2.5,
    reason: str = "config change",
) -> bool:
    """Schedule a one-shot restart after the HTTP response can flush.

    Returns True if a restart was newly scheduled.
    """
    global _restart_scheduled
    with _restart_lock:
        if _restart_scheduled:
            return False
        _restart_scheduled = True

    def _worker() -> None:
        global _restart_scheduled
        try:
            logger.warning("Panel restart in %.1fs (%s)", delay_sec, reason)
            time.sleep(max(0.8, delay_sec))
            ok, note = restart_panel_service()
            if ok:
                logger.info("Panel restarted: %s", note)
            else:
                logger.error("Panel restart failed: %s", note)
        finally:
            with _restart_lock:
                _restart_scheduled = False

    threading.Thread(target=_worker, name="pgclock-restart", daemon=True).start()
    return True
