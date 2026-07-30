from __future__ import annotations

import re
import secrets
from pathlib import Path

from app.config import DATA_DIR, ROOT_DIR, get_settings
from app.services.web_auth import load_web_admin

SETUP_FLAG = DATA_DIR / "setup_complete.flag"
SETUP_IN_PROGRESS = DATA_DIR / "setup_in_progress.flag"
SETUP_GATE_FILE = DATA_DIR / "setup_gate.token"
ENV_PATH = ROOT_DIR / ".env"

# Keys the wizard may write; unknown keys in .env are preserved on merge.
WIZARD_ENV_KEYS = (
    "BOT_TOKEN",
    "BOT_USERNAME",
    "ADMIN_IDS",
    "PG_BASE_URL",
    "PG_USERNAME",
    "PG_PASSWORD",
    "WEB_HOST",
    "WEB_PORT",
    "WEB_SECRET",
    "PUBLIC_BASE_URL",
    "CURRENCY",
)


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def mark_setup_complete() -> Path:
    _ensure_data_dir()
    SETUP_FLAG.write_text("ok\n", encoding="utf-8")
    try:
        SETUP_FLAG.chmod(0o600)
    except OSError:
        pass
    try:
        if SETUP_IN_PROGRESS.exists():
            SETUP_IN_PROGRESS.unlink()
    except OSError:
        pass
    try:
        if SETUP_GATE_FILE.exists():
            SETUP_GATE_FILE.unlink()
    except OSError:
        pass
    return SETUP_FLAG


def ensure_setup_gate_token() -> str:
    """One-time gate for the first-run wizard so the open panel cannot be claimed remotely."""
    _ensure_data_dir()
    if SETUP_GATE_FILE.exists():
        token = SETUP_GATE_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    SETUP_GATE_FILE.write_text(token + "\n", encoding="utf-8")
    try:
        SETUP_GATE_FILE.chmod(0o600)
    except OSError:
        pass
    return token


def setup_gate_ok(provided: str | None) -> bool:
    if is_setup_complete():
        return True
    expected = ensure_setup_gate_token()
    got = (provided or "").strip()
    if not got or not expected:
        return False
    try:
        return secrets.compare_digest(got, expected)
    except (TypeError, ValueError):
        return False


def begin_setup() -> None:
    """Mark wizard in progress so partial saves do not auto-complete setup."""
    _ensure_data_dir()
    if SETUP_FLAG.exists():
        return
    SETUP_IN_PROGRESS.write_text("1\n", encoding="utf-8")


def _read_env_file() -> dict[str, str]:
    """Parse KEY=VALUE pairs from .env (best-effort, preserves simple quoted values)."""
    out: dict[str, str] = {}
    if not ENV_PATH.exists():
        return out
    for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        val = val.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
        out[key] = val.replace("\r", "").strip()
    return out


def _env_get(key: str) -> str:
    data = _read_env_file()
    if key in data and data[key]:
        return data[key]
    try:
        get_settings.cache_clear()
        settings = get_settings()
        mapping = {
            "BOT_TOKEN": settings.bot_token,
            "BOT_USERNAME": settings.bot_username,
            "ADMIN_IDS": ",".join(str(i) for i in settings.admin_ids),
            "PG_BASE_URL": settings.pg_base_url,
            "PG_USERNAME": settings.pg_username,
            "PG_PASSWORD": settings.pg_password,
            "WEB_HOST": settings.web_host,
            "WEB_PORT": str(settings.web_port),
            "WEB_SECRET": settings.web_secret,
            "PUBLIC_BASE_URL": settings.public_base_url,
            "CURRENCY": settings.currency,
        }
        return str(mapping.get(key, "") or "").strip()
    except Exception:
        return ""


def _has_web_password() -> bool:
    creds = load_web_admin()
    return bool((creds.get("password") or "").strip())


def _has_bot_token() -> bool:
    return bool(_env_get("BOT_TOKEN"))


def _has_admin_ids() -> bool:
    raw = _env_get("ADMIN_IDS")
    if not raw:
        return False
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for p in parts:
        try:
            int(p)
            return True
        except ValueError:
            continue
    return False


def is_setup_complete() -> bool:
    """True when first-run wizard is done and required config exists.

    Existing installs that already have a bot token and web password are
    auto-flagged on first check so the wizard never traps them — unless a
    setup session is in progress (partial wizard saves).
    """
    # Wizard mid-flight: do not treat partial credentials as "done"
    if SETUP_IN_PROGRESS.exists():
        return False

    has_pw = _has_web_password()
    has_token = _has_bot_token()
    has_admins = _has_admin_ids()
    ready = has_pw and has_token

    if SETUP_FLAG.exists():
        # Stale flag after wipe / incomplete scaffold → force wizard again
        if ready:
            return True
        try:
            SETUP_FLAG.unlink()
        except OSError:
            pass
        return False

    if ready:
        # Prefer also having admin ids, but don't trap old installs without them
        if has_admins or has_pw:
            mark_setup_complete()
            return True

    return False


def _escape_env_value(val: str) -> str:
    return (
        (val or "")
        .replace("\r", "")
        .strip()
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
    )


def update_env_keys(updates: dict[str, str | int | None]) -> Path:
    """Merge keys into .env without wiping unknown keys or comments when possible.

    Known keys are upserted; if the file is missing, a minimal file is created.
    Ensures WEB_SECRET exists (generates one if blank/missing).
    """
    cleaned: dict[str, str] = {}
    for k, v in updates.items():
        if v is None:
            continue
        cleaned[str(k)] = str(v).replace("\r", "").strip()

    if ENV_PATH.exists():
        text = ENV_PATH.read_text(encoding="utf-8")
    else:
        text = ""

    def upsert(src: str, key: str, value: str) -> str:
        line = f'{key}="{_escape_env_value(value)}"'
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
        if pattern.search(src):
            return pattern.sub(line, src)
        if src and not src.endswith("\n"):
            src += "\n"
        return src + line + "\n"

    for key, value in cleaned.items():
        text = upsert(text, key, value)

    # Ensure WEB_SECRET is present and not a known placeholder
    placeholders = {"", "change-me", "change-this-long-random-secret"}
    merged_secret = (cleaned.get("WEB_SECRET") or _read_env_file().get("WEB_SECRET") or "").strip()
    if merged_secret in placeholders:
        text = upsert(text, "WEB_SECRET", secrets.token_hex(32))

    ENV_PATH.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    try:
        ENV_PATH.chmod(0o600)
    except OSError:
        pass
    get_settings.cache_clear()
    return ENV_PATH


def ensure_web_secret() -> str:
    """Return current WEB_SECRET, generating and persisting one if missing."""
    placeholders = {"", "change-me", "change-this-long-random-secret"}
    secret = (_env_get("WEB_SECRET") or "").strip()
    if secret in placeholders:
        secret = secrets.token_hex(32)
        update_env_keys({"WEB_SECRET": secret})
        return secret
    return secret


def current_setup_values() -> dict[str, str]:
    """Values for pre-filling the wizard form."""
    creds = load_web_admin()
    # Only prefill username when credentials already exist (re-running wizard).
    # Never force-write "admin" into an empty first-time form.
    has_creds = bool(creds.get("password"))
    return {
        "username": (creds.get("username") or "") if has_creds else "",
        "BOT_TOKEN": _env_get("BOT_TOKEN"),
        "BOT_USERNAME": _env_get("BOT_USERNAME"),
        "ADMIN_IDS": _env_get("ADMIN_IDS"),
        "PG_BASE_URL": _env_get("PG_BASE_URL"),
        "PG_USERNAME": _env_get("PG_USERNAME"),
        "PG_PASSWORD": _env_get("PG_PASSWORD"),
        "WEB_PORT": _env_get("WEB_PORT") or "9000",
        "PUBLIC_BASE_URL": _env_get("PUBLIC_BASE_URL"),
        "CURRENCY": _env_get("CURRENCY") or "تومان",
    }


def parse_admin_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        ids.append(int(part))
    return ids


def detect_server_ip() -> str:
    """Best-effort public/LAN IP for panel links shown to resellers."""
    import socket
    import urllib.request

    for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                ip = (resp.read() or b"").decode("utf-8", errors="ignore").strip()
            if ip and " " not in ip and len(ip) < 64 and not ip.lower().startswith("<"):
                return ip
        except Exception:
            continue
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        # Outbound UDP trick — no packets sent; reveals preferred local IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip:
                return ip
    except Exception:
        pass
    return "127.0.0.1"


def default_panel_base_url(*, public_base: str | None = None, web_port: int | str | None = None) -> str:
    """PUBLIC_BASE_URL if set, else http://{server_ip}:{WEB_PORT} (default 9000)."""
    from app.config import get_settings

    settings = get_settings()
    base = (public_base if public_base is not None else settings.public_base_url or "").strip().rstrip("/")
    if base:
        return base
    port = web_port if web_port is not None else settings.web_port
    try:
        port_s = str(int(port or 9000))
    except (TypeError, ValueError):
        port_s = "9000"
    return f"http://{detect_server_ip()}:{port_s}"


def panel_url_hint(public_base: str = "", web_port: str = "9000") -> str:
    base = default_panel_base_url(public_base=public_base, web_port=web_port)
    return base.rstrip("/") + "/"
