from __future__ import annotations

"""Restart the panel/bot process so new .env (BOT_TOKEN, etc.) takes effect."""

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

_restart_lock = threading.Lock()
_restart_scheduled = False


def restart_panel_service() -> tuple[bool, str]:
    """Try systemd restart; return (ok, message)."""
    try:
        from app.services.panel_update import _restart_service

        return _restart_service()
    except Exception as exc:
        logger.exception("restart_panel_service failed")
        return False, str(exc)


def schedule_panel_restart(
    *,
    delay_sec: float = 1.2,
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
            time.sleep(delay_sec)
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
