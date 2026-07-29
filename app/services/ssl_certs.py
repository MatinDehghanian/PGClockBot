"""Let's Encrypt SSL for the web panel + mini-app (single domain, automatic)."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, ROOT_DIR, get_settings
from app.util_which import which

logger = logging.getLogger(__name__)

CERT_DIR = DATA_DIR / "certs"
WEBROOT_DIR = DATA_DIR / "acme-www"
META_PATH = CERT_DIR / "meta.json"
PROGRESS_PATH = CERT_DIR / "progress.json"
LIVE_CERT = CERT_DIR / "fullchain.pem"
LIVE_KEY = CERT_DIR / "privkey.pem"

_PROGRESS_LOCK = threading.Lock()
_JOB_LOCK = threading.Lock()
_JOB_RUNNING = False

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]+(?:\.[a-z0-9-]+)+$",
    re.IGNORECASE,
)


def ensure_dirs() -> None:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    WEBROOT_DIR.mkdir(parents=True, exist_ok=True)
    (WEBROOT_DIR / ".well-known" / "acme-challenge").mkdir(parents=True, exist_ok=True)


def normalize_domain(raw: str | None) -> str:
    s = (raw or "").strip().lower()
    if not s:
        return ""
    for prefix in ("https://", "http://"):
        if s.startswith(prefix):
            s = s[len(prefix) :]
    s = s.split("/", 1)[0].split(":", 1)[0].strip(".")
    return s


def is_valid_domain(domain: str) -> bool:
    d = normalize_domain(domain)
    if not d or d in {"localhost", "127.0.0.1"}:
        return False
    return bool(_DOMAIN_RE.match(d))


def certbot_bin() -> str | None:
    return which("certbot")


def certbot_available() -> bool:
    return certbot_bin() is not None


def _set_progress(
    *,
    pct: int,
    stage: str,
    message: str,
    done: bool = False,
    ok: bool | None = None,
) -> None:
    ensure_dirs()
    payload = {
        "pct": max(0, min(100, int(pct))),
        "stage": stage,
        "message": message,
        "done": bool(done),
        "ok": ok,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with _PROGRESS_LOCK:
        PROGRESS_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def read_progress() -> dict[str, Any]:
    if not PROGRESS_PATH.is_file():
        return {"pct": 0, "stage": "idle", "message": "", "done": True, "ok": None}
    try:
        data = json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"pct": 0, "stage": "idle", "message": "", "done": True}
    except Exception:
        return {"pct": 0, "stage": "idle", "message": "", "done": True, "ok": None}


def read_meta() -> dict[str, Any]:
    if not META_PATH.is_file():
        return {}
    try:
        data = json.loads(META_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_meta(data: dict[str, Any]) -> None:
    ensure_dirs()
    META_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        META_PATH.chmod(0o600)
    except OSError:
        pass


def cert_files_exist() -> bool:
    return LIVE_CERT.is_file() and LIVE_KEY.is_file()


def resolve_cert_paths() -> tuple[Path, Path]:
    return LIVE_CERT, LIVE_KEY


def job_running() -> bool:
    return _JOB_RUNNING


def _run(cmd: list[str], *, timeout: int = 300) -> tuple[int, str]:
    env = {
        **os.environ,
        "DEBIAN_FRONTEND": "noninteractive",
        "PATH": (os.environ.get("PATH") or "")
        + ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    }
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT_DIR),
            env=env,
        )
        out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 1, "timeout"
    except Exception as exc:
        return 1, str(exc)


def _with_sudo(cmd: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return cmd
    sudo = which("sudo")
    if sudo:
        return [sudo, "-n", *cmd]
    return cmd


def install_certbot() -> dict[str, Any]:
    if certbot_available():
        return {"ok": True, "path": certbot_bin()}
    apt = which("apt-get") or which("apt")
    if not apt:
        return {"ok": False, "error": "apt پیدا نشد — دستی نصب کنید: sudo apt install certbot"}
    _set_progress(pct=12, stage="install", message="در حال نصب certbot…", done=False)
    code, out = _run(_with_sudo([apt, "install", "-y", "certbot"]), timeout=360)
    path = certbot_bin()
    if code != 0 or not path:
        return {"ok": False, "error": (out or "نصب certbot ناموفق بود")[-1200:]}
    return {"ok": True, "path": path}


def _parse_expiry(cert_path: Path) -> tuple[str | None, bool]:
    if not cert_path.is_file():
        return None, True
    openssl = which("openssl")
    if not openssl:
        return None, False
    code, out = _run([openssl, "x509", "-in", str(cert_path), "-noout", "-enddate"], timeout=20)
    if code != 0 or "notAfter=" not in out:
        return None, False
    raw = out.split("notAfter=", 1)[-1].strip().splitlines()[0].strip()
    # e.g. Jul 29 12:00:00 2027 GMT
    exp_dt = None
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b %d %H:%M:%S %Y GMT"):
        try:
            exp_dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue
    if not exp_dt:
        return raw, False
    return exp_dt.isoformat(), exp_dt <= datetime.now(timezone.utc)


def cert_status() -> dict[str, Any]:
    ensure_dirs()
    meta = read_meta()
    cert_path, key_path = resolve_cert_paths()
    has = cert_path.is_file() and key_path.is_file()
    expires_at, expired = (None, True)
    if has:
        expires_at, expired = _parse_expiry(cert_path)
        if expires_at and not meta.get("expires_at"):
            meta["expires_at"] = expires_at
    port = int(get_settings().web_port or 9000)
    domain = normalize_domain(meta.get("domain") or meta.get("panel_domain") or "")
    public_https = ""
    if domain:
        public_https = f"https://{domain}" if port in (443, 8443) else f"https://{domain}:{port}"
    return {
        "has_cert": has,
        "certbot": certbot_available(),
        "certbot_path": certbot_bin(),
        "cert_path": str(cert_path.resolve()) if cert_path.is_file() else str(LIVE_CERT),
        "key_path": str(key_path.resolve()) if key_path.is_file() else str(LIVE_KEY),
        "letsencrypt_live": meta.get("letsencrypt_live") or "",
        "domain": domain,
        "email": meta.get("email") or "",
        "issued_at": meta.get("issued_at"),
        "expires_at": expires_at or meta.get("expires_at"),
        "expired": bool(expired) if has else True,
        "ssl_enabled": bool(meta.get("ssl_enabled")) and has,
        "last_error": meta.get("last_error"),
        "public_https": public_https,
        "web_port": port,
        "progress": read_progress(),
        "running": job_running(),
    }


def _sudo_read_file(path: Path) -> bytes | None:
    cmd = _with_sudo(["cat", str(path)])
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            env={
                **os.environ,
                "PATH": (os.environ.get("PATH") or "")
                + ":/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            },
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
    except Exception:
        return None
    return None


def _copy_live_from_letsencrypt(name: str) -> str | None:
    live = Path("/etc/letsencrypt/live") / name
    fullchain = live / "fullchain.pem"
    privkey = live / "privkey.pem"

    def _exists(p: Path) -> bool:
        try:
            return p.exists()
        except PermissionError:
            return True

    if not _exists(fullchain) or not _exists(privkey):
        return None
    ensure_dirs()
    try:
        shutil.copy2(fullchain, LIVE_CERT)
        shutil.copy2(privkey, LIVE_KEY)
    except OSError:
        cert_bytes = _sudo_read_file(fullchain)
        key_bytes = _sudo_read_file(privkey)
        if not cert_bytes or not key_bytes:
            return None
        LIVE_CERT.write_bytes(cert_bytes)
        LIVE_KEY.write_bytes(key_bytes)
    try:
        os.chmod(LIVE_KEY, 0o600)
        os.chmod(LIVE_CERT, 0o644)
    except OSError:
        pass
    if not LIVE_CERT.is_file() or not LIVE_KEY.is_file():
        return None
    return str(live)


def _find_and_copy_cert(primary: str) -> str | None:
    for name in (f"pgclock-{primary}", primary):
        found = _copy_live_from_letsencrypt(name)
        if found:
            return found
    live_root = Path("/etc/letsencrypt/live")
    if live_root.is_dir():
        try:
            children = sorted(
                [p for p in live_root.iterdir() if p.is_dir() and not p.name.startswith(".")],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except PermissionError:
            code, out = _run(_with_sudo(["ls", "-1", str(live_root)]), timeout=20)
            children = [live_root / line.strip() for line in (out or "").splitlines() if line.strip()]
        for child in children:
            found = _copy_live_from_letsencrypt(child.name if isinstance(child, Path) else str(child))
            if found:
                return found
    return None


def _apply_https_env(domain: str) -> str:
    """Point PUBLIC_BASE_URL at the HTTPS panel/mini-app URL."""
    settings = get_settings()
    port = int(settings.web_port or 9000)
    url = f"https://{domain}" if port == 443 else f"https://{domain}:{port}"
    try:
        from app.services.setup_wizard import update_env_keys

        update_env_keys({"PUBLIC_BASE_URL": url})
        get_settings.cache_clear()
    except Exception as exc:
        logger.warning("PUBLIC_BASE_URL update failed: %s", exc)
    return url


def _certbot_issue(domain: str, email: str, *, force: bool = False) -> tuple[bool, str]:
    bin_path = certbot_bin()
    if not bin_path:
        return False, "certbot پیدا نشد"

    base = [
        bin_path,
        "certonly",
        "--agree-tos",
        "--non-interactive",
        "--email",
        email,
        "--cert-name",
        f"pgclock-{domain}",
        "-d",
        domain,
    ]
    if force:
        base.append("--force-renewal")

    # Prefer standalone (port 80) — most reliable on a fresh VPS without nginx.
    _set_progress(pct=40, stage="challenge", message="درخواست گواهی (standalone روی پورت ۸۰)…", done=False)
    cmd = _with_sudo([*base, "--standalone", "--preferred-challenges", "http"])
    code, out = _run(cmd, timeout=240)
    if code == 0:
        return True, out

    # Fallback: webroot (works if port 80 already reverse-proxies to this app)
    _set_progress(pct=55, stage="challenge", message="تلاش دوم با webroot…", done=False)
    ensure_dirs()
    cmd2 = _with_sudo([*base, "--webroot", "-w", str(WEBROOT_DIR)])
    code2, out2 = _run(cmd2, timeout=240)
    if code2 == 0:
        return True, out2

    combined = (out or "") + "\n" + (out2 or "")
    hint = ""
    low = combined.lower()
    if "bind" in low or "80" in low or "address already in use" in low:
        hint = (
            "\nپورت ۸۰ اشغال است. موقتاً سرویس روی پورت ۸۰ را متوقف کنید "
            "یا DNS/فایروال را بررسی کنید."
        )
    elif "nxdomain" in low or "dns" in low or "no valid" in low:
        hint = "\nرکورد DNS دامنه باید به IP همین سرور اشاره کند و پورت ۸۰ باز باشد."
    return False, (combined.strip()[-1800:] + hint).strip()


def issue_or_renew(
    *,
    domain: str,
    email: str,
    force: bool = False,
    enable_https: bool = True,
) -> dict[str, Any]:
    """Issue or renew a Let's Encrypt cert and enable HTTPS for panel + mini-app."""
    ensure_dirs()
    domain = normalize_domain(domain)
    email = (email or "").strip()
    if not is_valid_domain(domain):
        _set_progress(pct=100, stage="error", message="دامنه نامعتبر است", done=True, ok=False)
        return {"ok": False, "error": "دامنه نامعتبر است (مثال: panel.example.com)"}
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        _set_progress(pct=100, stage="error", message="ایمیل نامعتبر است", done=True, ok=False)
        return {"ok": False, "error": "ایمیل معتبر برای Let's Encrypt لازم است"}

    _set_progress(pct=5, stage="start", message="شروع…", done=False)

    if not certbot_available():
        inst = install_certbot()
        if not inst.get("ok"):
            err = str(inst.get("error") or "نصب certbot ناموفق")
            _set_progress(pct=100, stage="error", message=err[:200], done=True, ok=False)
            meta = read_meta()
            meta.update({"last_error": err, "domain": domain, "email": email})
            write_meta(meta)
            return {"ok": False, "error": err}

    _set_progress(pct=25, stage="ready", message="certbot آماده است", done=False)
    ok, log = _certbot_issue(domain, email, force=force)
    if not ok:
        meta = read_meta()
        meta.update({"last_error": log[-2000:], "domain": domain, "email": email, "ssl_enabled": False})
        write_meta(meta)
        _set_progress(pct=100, stage="error", message=(log[-280:] or "ناموفق"), done=True, ok=False)
        return {"ok": False, "error": log[-1500:] or "صدور گواهی ناموفق بود"}

    _set_progress(pct=78, stage="copy", message="کپی گواهی به مسیر پنل…", done=False)
    live = _find_and_copy_cert(domain)
    if not live or not cert_files_exist():
        msg = "گواهی صادر شد ولی خواندن فایل‌ها ممکن نشد — دسترسی /etc/letsencrypt را بررسی کنید"
        meta = read_meta()
        meta.update({"last_error": msg, "domain": domain, "email": email})
        write_meta(meta)
        _set_progress(pct=100, stage="error", message=msg, done=True, ok=False)
        return {"ok": False, "error": msg}

    expires_at, _expired = _parse_expiry(LIVE_CERT)
    now = datetime.now(timezone.utc).isoformat()
    public_url = ""
    if enable_https:
        _set_progress(pct=90, stage="enable", message="فعال‌سازی HTTPS و آدرس عمومی…", done=False)
        public_url = _apply_https_env(domain)

    meta = {
        "domain": domain,
        "panel_domain": domain,
        "miniapp_domain": domain,
        "email": email,
        "issued_at": now,
        "expires_at": expires_at,
        "ssl_enabled": bool(enable_https),
        "last_error": None,
        "letsencrypt_live": live,
        "log_tail": (log or "")[-800:],
        "public_https": public_url,
    }
    write_meta(meta)
    _set_progress(pct=100, stage="done", message="گواهی آماده است — در حال راه‌اندازی مجدد…", done=True, ok=True)
    return {
        "ok": True,
        "domain": domain,
        "public_https": public_url,
        "expires_at": expires_at,
        "cert_path": str(LIVE_CERT),
        "key_path": str(LIVE_KEY),
    }


def start_issue_job(
    *,
    domain: str,
    email: str,
    force: bool = False,
    restart: bool = True,
) -> dict[str, Any]:
    """Run issue/renew in a background thread; UI polls /settings/ssl/progress."""
    global _JOB_RUNNING
    with _JOB_LOCK:
        if _JOB_RUNNING:
            return {"ok": False, "error": "یک عملیات SSL در حال اجراست"}
        _JOB_RUNNING = True

    def _worker() -> None:
        global _JOB_RUNNING
        try:
            result = issue_or_renew(domain=domain, email=email, force=force, enable_https=True)
            if result.get("ok") and restart:
                try:
                    from app.services.service_control import schedule_panel_restart

                    schedule_panel_restart(delay_sec=2.0, reason="ssl certificate ready")
                except Exception:
                    logger.exception("SSL restart schedule failed")
        except Exception as exc:
            logger.exception("SSL job failed")
            _set_progress(pct=100, stage="error", message=str(exc)[:240], done=True, ok=False)
            meta = read_meta()
            meta["last_error"] = str(exc)
            write_meta(meta)
        finally:
            with _JOB_LOCK:
                _JOB_RUNNING = False

    _set_progress(pct=3, stage="queued", message="صف انتظار…", done=False)
    threading.Thread(target=_worker, name="pgclock-ssl", daemon=True).start()
    return {"ok": True, "started": True}


def uvicorn_ssl_kwargs() -> dict[str, str] | None:
    meta = read_meta()
    if not meta.get("ssl_enabled"):
        return None
    cert, key = resolve_cert_paths()
    if not cert.is_file() or not key.is_file():
        return None
    return {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}


def disable_ssl() -> None:
    meta = read_meta()
    meta["ssl_enabled"] = False
    write_meta(meta)
