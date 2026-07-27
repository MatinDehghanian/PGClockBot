from __future__ import annotations

import json
import secrets
from pathlib import Path

from app.config import DATA_DIR

AUTH_FILE = DATA_DIR / "web_admin.json"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_web_admin(username: str, password: str) -> Path:
    """Persist web panel credentials in a dedicated JSON file (not fragile .env)."""
    _ensure_data_dir()
    username = (username or "admin").strip()
    password = password or ""
    if not username or not password:
        raise ValueError("username and password are required")
    payload = {
        "username": username,
        "password": password,
        "token": secrets.token_hex(16),
    }
    AUTH_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        AUTH_FILE.chmod(0o600)
    except OSError:
        pass
    return AUTH_FILE


def load_web_admin() -> dict[str, str]:
    _ensure_data_dir()
    if AUTH_FILE.exists():
        data = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        return {
            "username": str(data.get("username", "admin")).strip(),
            "password": str(data.get("password", "")),
        }

    # Fallback for old installs: migrate from .env once
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    user = (settings.web_admin_user or "admin").strip()
    password = settings.web_admin_password or ""
    if password:
        save_web_admin(user, password)
        return {"username": user, "password": password}
    return {"username": "admin", "password": ""}


def verify_web_admin(username: str, password: str) -> bool:
    creds = load_web_admin()
    u = (username or "").strip()
    p = password or ""
    expected_u = creds.get("username") or ""
    expected_p = creds.get("password") or ""
    if not expected_u or not expected_p:
        return False
    try:
        user_ok = secrets.compare_digest(u.encode("utf-8"), expected_u.encode("utf-8"))
        pass_ok = secrets.compare_digest(p.encode("utf-8"), expected_p.encode("utf-8"))
    except ValueError:
        # different lengths — reject without crashing
        return False
    return user_ok and pass_ok
