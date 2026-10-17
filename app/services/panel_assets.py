"""Precompute browser cache keys for panel scripts when the process starts."""

from __future__ import annotations

import hashlib
from pathlib import Path

_STATIC_DIR = Path(__file__).resolve().parent.parent / "web" / "static"
_SCRIPT_NAMES = ("panel.js", "panel_widget_request.js", "money-inputs.js", "list-inputs.js", "sales-chart.js")


def build_asset_cache_key(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()[:16]


# Startup computation avoids filesystem work on menu/refresh requests.
_CACHE_KEYS = {name: build_asset_cache_key(_STATIC_DIR / name) for name in _SCRIPT_NAMES}


def get_panel_asset_cache_key(name: str) -> str:
    try:
        return _CACHE_KEYS[name]
    except KeyError:
        raise ValueError("Unsupported panel script") from None
