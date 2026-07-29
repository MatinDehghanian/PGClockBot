from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.version import GITHUB_REPO_URL, GITHUB_VERSION_URL, __version__

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"at": 0.0, "data": None, "ok": False}
_CACHE_TTL_OK = 300.0  # successful checks
_CACHE_TTL_FAIL = 30.0  # failed checks — retry soon
_VER_RE = re.compile(r"^v?\d+(\.\d+)*([.-][A-Za-z0-9]+)*$")


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


def is_same_or_newer(candidate: str | None, baseline: str | None) -> bool:
    """True when candidate >= baseline."""
    if not candidate:
        return False
    if not baseline:
        return True
    return _parse_ver(candidate) >= _parse_ver(baseline)


def peek_update_cache() -> dict[str, Any] | None:
    """Return last cached GitHub check without network I/O (for sidebar badge)."""
    data = _CACHE.get("data")
    return dict(data) if isinstance(data, dict) else None


def _valid_version(value: str | None) -> bool:
    if not value:
        return False
    return bool(_VER_RE.match(value.strip()))


async def check_github_update(*, timeout: float = 4.0, force: bool = False) -> dict[str, Any]:
    """
    Compare local app version with GitHub main/VERSION.
    Returns: version, remote_version, update_available, label, tone (ok|warn|err)
    """
    now = time.monotonic()
    cached = _CACHE.get("data")
    if (
        not force
        and isinstance(cached, dict)
        and (now - float(_CACHE["at"])) < (_CACHE_TTL_OK if _CACHE.get("ok") else _CACHE_TTL_FAIL)
    ):
        return dict(cached)

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
    ok = False
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(
                GITHUB_VERSION_URL,
                headers={
                    "User-Agent": "PGClockBot-Panel",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
                params={"_": str(int(time.time()))} if force else None,
            )
            if resp.status_code != 200:
                result["label"] = "بررسی آپدیت ناموفق"
                result["tone"] = "warn"
            else:
                remote = (resp.text or "").strip().splitlines()[0].strip()
                if not _valid_version(remote):
                    result["label"] = "نسخهٔ ریموت نامعتبر"
                    result["tone"] = "warn"
                else:
                    result["remote_version"] = remote
                    result["checked"] = True
                    ok = True
                    if is_newer(remote, local):
                        result["update_available"] = True
                        result["label"] = f"آپدیت {remote} آماده است"
                        result["tone"] = "err"
                    else:
                        result["label"] = "آخرین نسخه"
                        result["tone"] = "ok"
    except Exception as e:
        logger.debug("github version check failed: %s", e)
        result["label"] = "بررسی آپدیت ناموفق"
        result["tone"] = "warn"
    _CACHE.update({"at": now, "data": dict(result), "ok": ok})
    return result


def clear_update_cache() -> None:
    _CACHE["at"] = 0.0
    _CACHE["data"] = None
    _CACHE["ok"] = False
