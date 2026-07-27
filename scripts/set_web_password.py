#!/usr/bin/env python3
"""Reset web panel username/password in .env without reinstall."""
from __future__ import annotations

import getpass
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"


def validate_password(p: str) -> str | None:
    if len(p) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", p):
        return "Password must include at least one uppercase letter (A-Z)."
    if not re.search(r"[^a-zA-Z0-9]", p):
        return "Password must include at least one special character."
    return None


def upsert(key: str, value: str, text: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    line = f'{key}="{escaped}"'
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    if pattern.search(text):
        return pattern.sub(line, text)
    return text.rstrip() + "\n" + line + "\n"


def main() -> None:
    if not ENV.exists():
        print("No .env found. Run ./install.sh first.", file=sys.stderr)
        sys.exit(1)

    print("Reset web panel credentials")
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

    text = ENV.read_text(encoding="utf-8")
    text = upsert("WEB_ADMIN_USER", user, text)
    text = upsert("WEB_ADMIN_PASSWORD", p1, text)
    ENV.write_text(text, encoding="utf-8")
    ENV.chmod(0o600)
    print("Saved. Restart the bot: sudo systemctl restart pgclockbot")


if __name__ == "__main__":
    main()
