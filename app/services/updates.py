from __future__ import annotations

import logging
from typing import Any

import httpx

from app.version import GITHUB_REPO_URL, GITHUB_VERSION_URL, __version__

logger = logging.getLogger(__name__)


def local_version() -> str:
    return (__version__ or "").strip()


async def check_github_update(*, timeout: float = 4.0) -> dict[str, Any]:
    """
    Compare local VERSION with GitHub main/VERSION.
    Returns: version, remote_version, update_available, label, tone (ok|warn|err)
    """
    local = local_version()
    result: dict[str, Any] = {
        "version": local,
        "remote_version": None,
        "update_available": False,
        "label": "آخرین نسخه",
        "tone": "ok",
        "repo_url": GITHUB_REPO_URL,
        "checked": False,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(GITHUB_VERSION_URL, headers={"User-Agent": "PGClockBot-Panel"})
            if resp.status_code != 200:
                result["label"] = "بررسی آپدیت ناموفق"
                result["tone"] = "warn"
                return result
            remote = (resp.text or "").strip().splitlines()[0].strip()
            result["remote_version"] = remote
            result["checked"] = True
            if remote and remote != local:
                result["update_available"] = True
                result["label"] = "آپدیت شود"
                result["tone"] = "err"
            else:
                result["label"] = "آخرین نسخه"
                result["tone"] = "ok"
    except Exception as e:
        logger.debug("github version check failed: %s", e)
        result["label"] = "بررسی آپدیت ناموفق"
        result["tone"] = "warn"
    return result
