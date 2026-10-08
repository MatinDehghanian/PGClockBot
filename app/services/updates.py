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
    __version__,
)

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"at": 0.0, "data": None, "ok": False, "channel": ""}
_CACHE_TTL_OK = 300.0  # successful checks
_CACHE_TTL_FAIL = 30.0  # failed checks — retry soon
_RELEASES_CACHE: dict[str, Any] = {"at": 0.0, "data": None, "ok": False}
_VER_RE = re.compile(r"^v?\d+(\.\d+)*([.-][A-Za-z0-9]+)*$")


def _active_channel() -> str:
    from app.services.update_channel import get_update_channel

    return get_update_channel()


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


def _parse_version_body(text: str | None) -> str | None:
    remote = (text or "").strip().splitlines()[0].strip() if text else ""
    if _valid_version(remote):
        return remote.lstrip("vV")
    return None


async def _fetch_version_via_contents_api(
    client: httpx.AsyncClient, *, channel: str
) -> str | None:
    """Read VERSION via GitHub Contents API (bypasses raw.githubusercontent CDN)."""
    import base64

    from app.version import GITHUB_REPO

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/VERSION"
    try:
        resp = await client.get(
            url, headers=_github_headers(), params={"ref": channel}
        )
        if resp.status_code != 200:
            return None
        payload = resp.json() or {}
        raw_b64 = str(payload.get("content") or "")
        if not raw_b64:
            return None
        decoded = base64.b64decode(raw_b64).decode("utf-8", errors="replace")
        return _parse_version_body(decoded)
    except Exception as e:
        logger.debug("github contents VERSION failed (%s): %s", channel, e)
        return None


async def _fetch_remote_version_candidates(
    client: httpx.AsyncClient,
    *,
    channel: str | None = None,
) -> list[str]:
    """Collect version strings for the active update channel.

    Sources (max wins):
    - raw.githubusercontent VERSION (cache-busted)
    - GitHub Contents API VERSION (same file, different CDN — helps when raw is stale)
    - main only: GitHub releases/latest
    - `dev` only: newest prerelease whose target is the `dev` branch
    """
    from app.services.update_channel import github_version_url, normalize_channel

    ch = normalize_channel(channel if channel is not None else _active_channel())
    found: list[str] = []
    bust = {"_": str(int(time.time()))}
    headers = {
        "User-Agent": "PGClockBot-Panel",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    version_url = github_version_url(channel=ch)
    try:
        resp = await client.get(version_url, headers=headers, params=bust)
        if resp.status_code == 200:
            ver = _parse_version_body(resp.text)
            if ver:
                found.append(ver)
    except Exception as e:
        logger.debug("github VERSION fetch failed (%s): %s", ch, e)

    contents_ver = await _fetch_version_via_contents_api(client, channel=ch)
    if contents_ver:
        found.append(contents_ver)

    if ch == "main":
        try:
            resp = await client.get(
                GITHUB_RELEASES_API + "/latest", headers=_github_headers()
            )
            if resp.status_code == 200:
                payload = resp.json()
                tag = normalize_version_tag(
                    (payload or {}).get("tag_name") or (payload or {}).get("name")
                )
                if tag:
                    found.append(tag)
        except Exception as e:
            logger.debug("github releases/latest fetch failed: %s", e)
    elif ch == "dev":
        # Dev tip is published as GitHub prerelease (Latest stays on main).
        try:
            resp = await client.get(
                GITHUB_RELEASES_API,
                headers=_github_headers(),
                params={"per_page": 20},
            )
            if resp.status_code == 200:
                for row in resp.json() or []:
                    if not isinstance(row, dict) or not row.get("prerelease"):
                        continue
                    target = str(row.get("target_commitish") or "").strip().lower()
                    if target in {"main", "master"}:
                        continue
                    tag = normalize_version_tag(
                        row.get("tag_name") or row.get("name")
                    )
                    if tag:
                        found.append(tag)
        except Exception as e:
            logger.debug("github prereleases fetch failed: %s", e)

    return found


async def check_github_update(
    *,
    timeout: float = 4.0,
    force: bool = False,
    channel: str | None = None,
) -> dict[str, Any]:
    """
    Compare local app version with the configured update channel on GitHub.
    Returns: version, remote_version, update_available, label, tone (ok|warn|err)
    """
    from app.services.update_channel import channel_label_fa, normalize_channel

    ch = normalize_channel(channel if channel is not None else _active_channel())
    now = time.monotonic()
    cached = _CACHE.get("data")
    if (
        not force
        and isinstance(cached, dict)
        and _CACHE.get("channel") == ch
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
        "channel": ch,
        "channel_label": channel_label_fa(ch),
    }
    ok = False
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            candidates = await _fetch_remote_version_candidates(client, channel=ch)
        label_fa = channel_label_fa(ch)
        if not candidates:
            result["label"] = f"بررسی آپدیت کانال {label_fa} ناموفق"
            result["tone"] = "warn"
        else:
            remote = max(candidates, key=_parse_ver)
            result["remote_version"] = remote
            result["checked"] = True
            ok = True
            if is_newer(remote, local):
                result["update_available"] = True
                result["label"] = f"برای کانال {label_fa} آپدیت {remote} آماده است"
                result["tone"] = "err"
            else:
                result["label"] = f"برای کانال {label_fa} آپدیت جدیدی نیست"
                result["tone"] = "ok"
    except Exception as e:
        logger.debug("github version check failed: %s", e)
        result["label"] = f"بررسی آپدیت کانال {channel_label_fa(ch)} ناموفق"
        result["tone"] = "warn"
    _CACHE.update({"at": now, "data": dict(result), "ok": ok, "channel": ch})
    return result


def clear_update_cache() -> None:
    _CACHE["at"] = 0.0
    _CACHE["data"] = None
    _CACHE["ok"] = False
    _CACHE["channel"] = ""
    _RELEASES_CACHE["at"] = 0.0
    _RELEASES_CACHE["data"] = None
    _RELEASES_CACHE["ok"] = False
    try:
        from app.services.update_channel import clear_alembic_tree_cache
        from app.services.release_notes import clear_remote_notes_cache

        clear_alembic_tree_cache()
        clear_remote_notes_cache()
    except Exception:
        pass


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
