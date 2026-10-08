"""Update channel (main=stable / dev) — env-backed, used by panel update + header badge."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

from app.version import GITHUB_REPO

logger = logging.getLogger(__name__)

CHANNELS: tuple[str, ...] = ("main", "dev")
DEFAULT_CHANNEL = "main"

CHANNEL_LABELS_FA: dict[str, str] = {
    "main": "پایدار",
    "dev": "توسعه",
}

_REV_ASSIGN_RE = re.compile(
    r"""^revision\s*=\s*['"]([^'"]+)['"]""",
    re.M,
)

_ALEMBIC_TREE_CACHE: dict[str, Any] = {"at": 0.0, "channel": "", "ids": None, "ok": False}
_ALEMBIC_TREE_TTL_OK = 120.0
_ALEMBIC_TREE_TTL_FAIL = 30.0


def normalize_channel(value: object | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"dev", "develop", "development", "unstable"}:
        return "dev"
    if raw in {"main", "master", "stable", "prod", "production"}:
        return "main"
    return DEFAULT_CHANNEL


def channel_label_fa(channel: object | None = None) -> str:
    ch = normalize_channel(channel if channel is not None else get_update_channel())
    return CHANNEL_LABELS_FA.get(ch, CHANNEL_LABELS_FA[DEFAULT_CHANNEL])


def get_update_channel() -> str:
    try:
        from app.config import get_settings

        return normalize_channel(getattr(get_settings(), "update_channel", None))
    except Exception:
        return DEFAULT_CHANNEL


def set_update_channel(channel: object | None) -> str:
    """Persist UPDATE_CHANNEL in .env and clear settings + update caches."""
    ch = normalize_channel(channel)
    from app.services.setup_wizard import update_env_keys
    from app.services.updates import clear_update_cache

    update_env_keys({"UPDATE_CHANNEL": ch})
    clear_update_cache()
    clear_alembic_tree_cache()
    return ch


def channel_branch(channel: object | None = None) -> str:
    return normalize_channel(channel if channel is not None else get_update_channel())


def github_raw_url(path: str, *, channel: object | None = None) -> str:
    ref = channel_branch(channel)
    clean = str(path or "").lstrip("/")
    return f"https://raw.githubusercontent.com/{GITHUB_REPO}/{ref}/{clean}"


def github_version_url(*, channel: object | None = None) -> str:
    return github_raw_url("VERSION", channel=channel)


def github_release_notes_url(*, channel: object | None = None) -> str:
    return github_raw_url("app/services/release_notes.py", channel=channel)


def channel_context(channel: object | None = None) -> dict[str, Any]:
    ch = normalize_channel(channel if channel is not None else get_update_channel())
    return {
        "channel": ch,
        "channel_label": channel_label_fa(ch),
        "channels": [
            {"id": "main", "label": CHANNEL_LABELS_FA["main"]},
            {"id": "dev", "label": CHANNEL_LABELS_FA["dev"]},
        ],
    }


def clear_alembic_tree_cache() -> None:
    _ALEMBIC_TREE_CACHE.update({"at": 0.0, "channel": "", "ids": None, "ok": False})


def _github_headers() -> dict[str, str]:
    return {
        "User-Agent": "PGClockBot-Panel",
        "Accept": "application/vnd.github+json",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def _revision_ids_from_filenames(paths: list[str]) -> set[str]:
    """This repo uses filename stem == Alembic revision id."""
    out: set[str] = set()
    for path in paths:
        name = path.rsplit("/", 1)[-1]
        if not name.endswith(".py") or name.startswith("__"):
            continue
        stem = name[:-3]
        if stem:
            out.add(stem)
    return out


async def fetch_remote_alembic_revision_ids(
    channel: object | None = None,
    *,
    timeout: float = 6.0,
    force: bool = False,
) -> set[str] | None:
    """Revision ids present under alembic/versions on the channel branch.

    Returns None when the remote tree could not be loaded.
    """
    ch = channel_branch(channel)
    now = time.monotonic()
    cached_ids = _ALEMBIC_TREE_CACHE.get("ids")
    ttl = _ALEMBIC_TREE_TTL_OK if _ALEMBIC_TREE_CACHE.get("ok") else _ALEMBIC_TREE_TTL_FAIL
    if (
        not force
        and _ALEMBIC_TREE_CACHE.get("channel") == ch
        and isinstance(cached_ids, set)
        and (now - float(_ALEMBIC_TREE_CACHE["at"])) < ttl
    ):
        return set(cached_ids)

    url = f"https://api.github.com/repos/{GITHUB_REPO}/git/trees/{ch}?recursive=1"
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=_github_headers())
        if resp.status_code != 200:
            raise RuntimeError(f"status {resp.status_code}")
        payload = resp.json() or {}
        paths = [
            str(item.get("path") or "")
            for item in (payload.get("tree") or [])
            if isinstance(item, dict)
            and str(item.get("path") or "").startswith("alembic/versions/")
            and str(item.get("path") or "").endswith(".py")
        ]
        ids = _revision_ids_from_filenames(paths)
        if not ids:
            raise RuntimeError("empty alembic versions on remote")
        _ALEMBIC_TREE_CACHE.update({"at": now, "channel": ch, "ids": set(ids), "ok": True})
        return set(ids)
    except Exception as e:
        logger.debug("remote alembic tree fetch failed (%s): %s", ch, e)
        _ALEMBIC_TREE_CACHE.update(
            {
                "at": now,
                "channel": ch,
                "ids": set(cached_ids) if isinstance(cached_ids, set) else None,
                "ok": False,
            }
        )
        return set(cached_ids) if isinstance(cached_ids, set) else None


def local_alembic_revision_ids() -> set[str]:
    """Revision ids from the installed alembic/versions tree."""
    try:
        from alembic.script import ScriptDirectory

        from app.db.alembic_runner import alembic_config

        script = ScriptDirectory.from_config(alembic_config())
        return {str(rev.revision) for rev in script.walk_revisions()}
    except Exception as e:
        logger.debug("local alembic revisions failed: %s", e)
        return set()


def evaluate_migration_preflight(
    *,
    db_revision: str | None,
    remote_revision_ids: set[str] | None,
) -> dict[str, Any]:
    """Gate deploy when DB revision is absent from the target channel.

    Panel never downgrades Alembic — switching to an older channel tip that
    lacks the current DB revision must be blocked.
    """
    db_rev = (db_revision or "").strip() or None
    result: dict[str, Any] = {
        "checked": False,
        "blocked": False,
        "db_revision": db_rev,
        "tone": "ok",
        "label": "مایگریشن سازگار است",
        "message": "",
    }
    if not db_rev:
        result["checked"] = True
        result["label"] = "نسخه مایگریشن دیتابیس مشخص نیست"
        result["tone"] = "warn"
        result["message"] = "قبل از آپدیت، در صورت امکان pgclock migrate را بررسی کنید."
        return result
    if remote_revision_ids is None:
        result["label"] = "بررسی مایگریشن کانال ناموفق"
        result["tone"] = "warn"
        result["message"] = (
            "نتوانستیم لیست مایگریشن کانال مقصد را از گیت‌هاب بخوانیم. "
            "اگر اخیراً روی کانال جدیدتری بوده‌اید، با احتیاط ادامه دهید."
        )
        return result
    result["checked"] = True
    if db_rev in remote_revision_ids:
        result["label"] = "مایگریشن سازگار است"
        result["tone"] = "ok"
        result["message"] = ""
        return result
    result["blocked"] = True
    result["tone"] = "err"
    result["label"] = "آپدیت این کانال بلاک شد"
    result["message"] = (
        f"دیتابیس روی مایگریشن «{db_rev}» است که در کانال مقصد وجود ندارد. "
        "پنل مایگریشن را پایین نمی‌آورد؛ ابتدا به کانالی بروید که این revision را دارد "
        "یا دیتابیس را جداگانه هم‌تراز کنید."
    )
    return result


async def migration_preflight(
    channel: object | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    ch = channel_branch(channel)
    db_rev: str | None = None
    try:
        from app.config import get_settings
        from app.db.alembic_runner import current_revision

        db_rev = current_revision(get_settings().database_url)
    except Exception as e:
        logger.debug("current_revision failed: %s", e)
    remote_ids = await fetch_remote_alembic_revision_ids(ch, force=force)
    out = evaluate_migration_preflight(
        db_revision=db_rev,
        remote_revision_ids=remote_ids,
    )
    out["channel"] = ch
    return out


def parse_revision_assignment(source: str) -> str | None:
    """Test helper / fallback: read ``revision = '…'`` from a versions file."""
    m = _REV_ASSIGN_RE.search(source or "")
    return m.group(1).strip() if m else None
