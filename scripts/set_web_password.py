#!/usr/bin/env python3
"""Reset web panel login (writes data/web_admin.json and syncs .env)."""
from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.web_auth import save_web_admin  # noqa: E402


def _sync_env(user: str, password: str) -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    text = env_path.read_text(encoding="utf-8")

    def esc(v: str) -> str:
        return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "").replace("\r", "")

    def upsert(src: str, key: str, value: str) -> str:
        line = f'{key}="{esc(value)}"'
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
        if pattern.search(src):
            return pattern.sub(line, src)
        return src.rstrip() + "\n" + line + "\n"

    text = upsert(text, "WEB_ADMIN_USER", user)
    text = upsert(text, "WEB_ADMIN_PASSWORD", password)
    env_path.write_text(text, encoding="utf-8")


def main() -> None:
    print("Reset web panel login")
    print("(saved to data/web_admin.json and .env)")
    user = input("Web username [admin]: ").strip() or "admin"
    while True:
        p1 = getpass.getpass("New password: ").replace("\r", "").strip()
        if not p1:
            print("Password cannot be empty.")
            continue
        p2 = getpass.getpass("Confirm password: ").replace("\r", "").strip()
        if p1 != p2:
            print("Passwords do not match.")
            continue
        break
    path = save_web_admin(user, p1)
    _sync_env(user, p1)
    print(f"Saved: {path}")
    print("Restart recommended:")
    print("  sudo systemctl restart pgclockbot")


if __name__ == "__main__":
    main()
