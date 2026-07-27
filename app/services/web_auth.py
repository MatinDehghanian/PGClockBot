from __future__ import annotations

import json
import secrets
from pathlib import Path

from app.config import DATA_DIR

AUTH_FILE = DATA_DIR / "web_admin.json"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _clean_secret(value: str | None) -> str:
    # Fix broken installs that stored leading/trailing newlines in .env / JSON
    return (value or "").replace("\r", "").strip()


def save_web_admin(username: str, password: str) -> Path:
    """Persist web panel credentials in a dedicated JSON file (not fragile .env)."""
    _ensure_data_dir()
    username = _clean_secret(username) or "admin"
    password = _clean_secret(password)
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
        username = _clean_secret(str(data.get("username", "admin")))
        password = _clean_secret(str(data.get("password", "")))
        # Auto-repair dirty credentials written by older installs
        if password and (
            str(data.get("password", "")) != password
            or str(data.get("username", "")).strip() != username
        ):
            save_web_admin(username, password)
        return {"username": username or "admin", "password": password}

    # Fallback for old installs: migrate from .env once
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    user = _clean_secret(settings.web_admin_user) or "admin"
    password = _clean_secret(settings.web_admin_password)
    if password:
        save_web_admin(user, password)
        return {"username": user, "password": password}
    return {"username": "admin", "password": ""}


def verify_web_admin(username: str, password: str) -> bool:
    creds = load_web_admin()
    u = _clean_secret(username)
    p = _clean_secret(password)
    expected_u = creds.get("username") or ""
    expected_p = creds.get("password") or ""
    if not expected_u or not expected_p:
        return False
    try:
        user_ok = secrets.compare_digest(u.encode("utf-8"), expected_u.encode("utf-8"))
        pass_ok = secrets.compare_digest(p.encode("utf-8"), expected_p.encode("utf-8"))
    except ValueError:
        return False
    return user_ok and pass_ok


def repair_web_admin_from_env() -> dict[str, str]:
    """Force-refresh web_admin.json from cleaned .env values."""
    from app.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    user = _clean_secret(settings.web_admin_user) or "admin"
    password = _clean_secret(settings.web_admin_password)
    if not password:
        return load_web_admin()
    save_web_admin(user, password)
    return {"username": user, "password": password}
