"""Shared PATH-safe binary lookup (systemd often has a short PATH)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

_EXTRA_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


def which(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    expanded = os.environ.get("PATH") or ""
    if _EXTRA_PATH not in expanded:
        found = shutil.which(name, path=f"{expanded}:{_EXTRA_PATH}" if expanded else _EXTRA_PATH)
        if found:
            return found
    for prefix in ("/usr/bin", "/bin", "/usr/local/bin", "/usr/sbin", "/sbin"):
        candidate = Path(prefix) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None
