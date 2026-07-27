#!/usr/bin/env python3
"""Reset web panel login (writes data/web_admin.json)."""
from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services.web_auth import save_web_admin  # noqa: E402


def validate_password(p: str) -> str | None:
    if len(p) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", p):
        return "Password must include at least one uppercase letter (A-Z)."
    if not re.search(r"[^a-zA-Z0-9]", p):
        return "Password must include at least one special character."
    return None


def main() -> None:
    print("Reset web panel login")
    print("(credentials are stored in data/web_admin.json)")
    user = input("Web username [admin]: ").strip() or "admin"
    while True:
        p1 = getpass.getpass("New password: ")
        err = validate_password(p1)
        if err:
            print(err)
            continue
        p2 = getpass.getpass("Confirm password: ")
        if p1 != p2:
            print("Passwords do not match.")
            continue
        break
    path = save_web_admin(user, p1)
    print(f"Saved: {path}")
    print("Restart is NOT required for next login attempt, but recommended:")
    print("  sudo systemctl restart pgclockbot")


if __name__ == "__main__":
    main()
