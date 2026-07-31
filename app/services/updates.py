from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.version import (
    GITHUB_RELEASES_API,
    GITHUB_REPO_URL,
    GITHUB_TAGS_API,
    GITHUB_VERSION_URL,
    __version__,
)

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"at": 0.0, "data": None, "ok": False}
_CACHE_TTL_OK = 300.0  # successful checks
_CACHE_TTL_FAIL = 30.0  # failed checks — retry soon
_RELEASES_CACHE: dict[str, Any] = {"at": 0.0, "data": None, "ok": False}
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
    _RELEASES_CACHE["at"] = 0.0
    _RELEASES_CACHE["data"] = None
    _RELEASES_CACHE["ok"] = False


def normalize_version_tag(value: str | None) -> str | None:
    """Return bare semver (no leading v) when value looks like a release tag."""
    if not value:
        return None
    raw = str(value).strip()
    if not _valid_version(raw):
        return None
    return raw.lstrip("vV")


def _github_headers() -> dict[str, str]:
    return {
        "User-Agent": "PGClockBot-Panel",
        "Accept": "application/vnd.github+json",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def _dedupe_versions(items: list[dict[str, str]], *, limit: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        ver = normalize_version_tag(item.get("version") or item.get("tag"))
        if not ver or ver in seen:
            continue
        seen.add(ver)
        tag = str(item.get("tag") or f"v{ver}").strip() or f"v{ver}"
        out.append(
            {
                "version": ver,
                "tag": tag if tag.startswith("v") else f"v{ver}",
                "name": str(item.get("name") or f"v{ver}").strip() or f"v{ver}",
                "published_at": str(item.get("published_at") or "").strip(),
            }
        )
        if len(out) >= limit:
            break
    return out


async def fetch_recent_versions(
    *,
    limit: int = 3,
    timeout: float = 5.0,
    force: bool = False,
) -> list[dict[str, str]]:
    """Latest GitHub releases/tags suitable for in-panel rollback (newest first)."""
    now = time.monotonic()
    cached = _RELEASES_CACHE.get("data")
    ttl = _CACHE_TTL_OK if _RELEASES_CACHE.get("ok") else _CACHE_TTL_FAIL
    if (
        not force
        and isinstance(cached, list)
        and (now - float(_RELEASES_CACHE["at"])) < ttl
    ):
        return list(cached)[:limit]

    items: list[dict[str, str]] = []
    ok = False
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(
                GITHUB_RELEASES_API,
                headers=_github_headers(),
                params={"per_page": max(10, limit * 3)},
            )
            if resp.status_code == 200:
                for row in resp.json() or []:
                    if not isinstance(row, dict) or row.get("draft"):
                        continue
                    tag = str(row.get("tag_name") or "").strip()
                    ver = normalize_version_tag(tag)
                    if not ver:
                        continue
                    items.append(
                        {
                            "version": ver,
                            "tag": tag if tag.startswith(("v", "V")) else f"v{ver}",
                            "name": str(row.get("name") or tag or ver).strip(),
                            "published_at": str(row.get("published_at") or "").strip(),
                        }
                    )
                ok = True
            if len(_dedupe_versions(items, limit=limit)) < limit:
                tags_resp = await client.get(
                    GITHUB_TAGS_API,
                    headers=_github_headers(),
                    params={"per_page": max(15, limit * 4)},
                )
                if tags_resp.status_code == 200:
                    for row in tags_resp.json() or []:
                        if not isinstance(row, dict):
                            continue
                        tag = str(row.get("name") or "").strip()
                        ver = normalize_version_tag(tag)
                        if not ver:
                            continue
                        items.append(
                            {
                                "version": ver,
                                "tag": tag if tag.startswith(("v", "V")) else f"v{ver}",
                                "name": tag or ver,
                                "published_at": "",
                            }
                        )
                    ok = True
    except Exception as e:
        logger.debug("github releases fetch failed: %s", e)

    result = _dedupe_versions(items, limit=limit)
    if not result and isinstance(cached, list) and cached:
        result = list(cached)[:limit]
    _RELEASES_CACHE.update({"at": now, "data": list(result), "ok": ok and bool(result)})
    return result
