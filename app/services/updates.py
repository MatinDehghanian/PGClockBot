from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.version import GITHUB_REPO_URL, GITHUB_VERSION_URL, __version__

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_CACHE_TTL = 60.0  # seconds


def local_version() -> str:
    return (__version__ or "").strip()


def _parse_ver(value: str | None) -> tuple[int, ...]:
    if not value:
        return (0,)
    parts: list[int] = []
    for chunk in str(value).strip().lstrip("vV").split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts) or (0,)


def is_newer(remote: str | None, local: str | None) -> bool:
    """True when remote version is strictly newer than local."""
    if not remote or not local:
        return bool(remote and remote != local)
    return _parse_ver(remote) > _parse_ver(local)


async def check_github_update(*, timeout: float = 4.0, force: bool = False) -> dict[str, Any]:
    """
    Compare local VERSION with GitHub main/VERSION.
    Returns: version, remote_version, update_available, label, tone (ok|warn|err)
    """
    now = time.monotonic()
    if not force and _CACHE["data"] is not None and (now - float(_CACHE["at"])) < _CACHE_TTL:
        return dict(_CACHE["data"])

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
                _CACHE.update({"at": now, "data": dict(result)})
                return result
            remote = (resp.text or "").strip().splitlines()[0].strip()
            result["remote_version"] = remote
            result["checked"] = True
            if is_newer(remote, local):
                result["update_available"] = True
                result["label"] = f"آپدیت {remote} آماده است"
                result["tone"] = "err"
            elif remote and remote != local:
                # local ahead of remote (dev/feature) or equal after normalize mismatch
                result["label"] = "آخرین نسخه"
                result["tone"] = "ok"
            else:
                result["label"] = "آخرین نسخه"
                result["tone"] = "ok"
    except Exception as e:
        logger.debug("github version check failed: %s", e)
        result["label"] = "بررسی آپدیت ناموفق"
        result["tone"] = "warn"
    _CACHE.update({"at": now, "data": dict(result)})
    return result


def clear_update_cache() -> None:
    _CACHE["at"] = 0.0
    _CACHE["data"] = None
