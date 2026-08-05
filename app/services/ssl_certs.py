"""Let's Encrypt SSL for panel + mini-app — issue without killing the panel."""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import signal
import socket
import subprocess
import threading
import time
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
ACME_HELPER = CERT_DIR / "acme_http80.py"

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
    restarting: bool = False,
    https_url: str = "",
) -> None:
    ensure_dirs()
    payload = {
        "pct": max(0, min(100, int(pct))),
        "stage": stage,
        "message": message,
        "done": bool(done),
        "ok": ok,
        "restarting": bool(restarting),
        "https_url": https_url or "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    with _PROGRESS_LOCK:
        PROGRESS_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def read_progress() -> dict[str, Any]:
    if not PROGRESS_PATH.is_file():
        return {
            "pct": 0,
            "stage": "idle",
            "message": "",
            "done": True,
            "ok": None,
            "restarting": False,
            "https_url": "",
        }
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


def https_is_active() -> bool:
    """True only when TLS is enabled and cert files are present on disk."""
    meta = read_meta()
    return bool(meta.get("ssl_enabled")) and cert_files_exist()


def public_panel_base_url() -> str:
    """Canonical panel base URL — HTTPS when active, else HTTP+IP."""
    if https_is_active():
        meta = read_meta()
        base = (meta.get("public_https") or "").strip().rstrip("/")
        if base:
            return base
        domain = normalize_domain(meta.get("domain") or "")
        if domain:
            return public_https_url(domain).rstrip("/")
    from app.services.setup_wizard import default_http_panel_url

    return default_http_panel_url().rstrip("/")


def public_https_url(domain: str | None = None) -> str:
    settings = get_settings()
    port = int(settings.web_port or 9000)
    d = normalize_domain(domain or read_meta().get("domain") or "")
    if not d:
        return ""
    return f"https://{d}" if port == 443 else f"https://{d}:{port}"


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
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return cmd
    sudo = which("sudo")
    if sudo:
        return [sudo, "-n", *cmd]
    return cmd


def _port_in_use(port: int = 80) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.8)
        return sock.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def install_certbot() -> dict[str, Any]:
    if certbot_available():
        return {"ok": True, "path": certbot_bin()}
    apt = which("apt-get") or which("apt")
    if not apt:
        return {"ok": False, "error": "apt پیدا نشد — دستی: sudo apt install certbot"}
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
    port = int(get_settings().web_port or 9000)
    domain = normalize_domain(meta.get("domain") or meta.get("panel_domain") or "")
    enabled = bool(meta.get("ssl_enabled")) and has
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
        "ssl_enabled": enabled,
        "last_error": meta.get("last_error"),
        "public_https": public_https_url(domain) if domain else "",
        "web_port": port,
        "progress": read_progress(),
        "running": job_running(),
        "port80_busy": _port_in_use(80),
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
    try:
        is_dir = live_root.is_dir()
    except PermissionError:
        is_dir = True
    if is_dir:
        try:
            children = sorted(
                [p for p in live_root.iterdir() if p.is_dir() and not p.name.startswith(".")],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except PermissionError:
            _code, out = _run(_with_sudo(["ls", "-1", str(live_root)]), timeout=20)
            children = [live_root / line.strip() for line in (out or "").splitlines() if line.strip()]
        for child in children:
            found = _copy_live_from_letsencrypt(child.name if isinstance(child, Path) else Path(child).name)
            if found:
                return found
    return None


def _write_acme_helper() -> Path:
    ensure_dirs()
    ACME_HELPER.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer\n"
        "from pathlib import Path\n"
        "root = Path(sys.argv[1]).resolve()\n"
        "class H(SimpleHTTPRequestHandler):\n"
        "    def __init__(self, *a, **k):\n"
        "        super().__init__(*a, directory=str(root), **k)\n"
        "    def log_message(self, *a):\n"
        "        return\n"
        "ThreadingHTTPServer(('0.0.0.0', 80), H).serve_forever()\n",
        encoding="utf-8",
    )
    try:
        ACME_HELPER.chmod(0o755)
    except OSError:
        pass
    return ACME_HELPER


def _start_acme_http() -> subprocess.Popen | None:
    """Serve WEBROOT on :80 without touching the panel process on WEB_PORT."""
    if _port_in_use(80):
        return None
    helper = _write_acme_helper()
    py = which("python3") or sys_executable()
    cmd = _with_sudo([py, str(helper), str(WEBROOT_DIR)])
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(ROOT_DIR),
        )
    except Exception as exc:
        logger.warning("ACME http80 start failed: %s", exc)
        return None
    # Wait until port 80 answers
    for _ in range(25):
        if proc.poll() is not None:
            return None
        if _port_in_use(80):
            return proc
        time.sleep(0.2)
    _stop_acme_http(proc)
    return None


def sys_executable() -> str:
    import sys

    return sys.executable


def _stop_acme_http(proc: subprocess.Popen | None) -> None:
    if not proc:
        return
    try:
        if proc.poll() is None:
            # Prefer graceful terminate; escalate if needed
            try:
                os.kill(proc.pid, signal.SIGTERM)
            except Exception:
                proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                try:
                    os.kill(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
    except Exception:
        pass
    # Also kill helper by pattern if sudo spawned a child
    _run(_with_sudo(["pkill", "-f", str(ACME_HELPER)]), timeout=10)


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

    ensure_dirs()
    helper: subprocess.Popen | None = None
    try:
        if _port_in_use(80):
            return (
                False,
                "پورت ۸۰ اشغال است. سرویس/پروکسی روی ۸۰ را موقتاً متوقف کنید، "
                "بعد دوباره «دریافت گواهی» را بزنید. پنل روی پورت فعلی دست نخورده می‌ماند.",
            )

        _set_progress(pct=35, stage="acme_http", message="راه‌اندازی موقت ACME روی پورت ۸۰…", done=False)
        helper = _start_acme_http()
        if not helper:
            return (
                False,
                "نتوانستیم پورت ۸۰ را برای تأیید دامنه باز کنیم. "
                "با کاربر root/sudo و پورت ۸۰ آزاد دوباره تلاش کنید.",
            )

        _set_progress(pct=50, stage="challenge", message="درخواست گواهی از Let's Encrypt…", done=False)
        # Prefer constrained ctl helper (no raw certbot sudo). Fall back only if helper missing.
        from app.services.service_control import HELPER_INSTALL_PATH, ensure_restart_helper

        ensure_restart_helper()
        ctl = HELPER_INSTALL_PATH if HELPER_INSTALL_PATH.is_file() else None
        if ctl is not None:
            cmd = _with_sudo(
                [
                    str(ctl),
                    "certbot-certonly",
                    domain,
                    email,
                    str(WEBROOT_DIR),
                    *(["--force"] if force else []),
                ]
            )
        else:
            cmd = _with_sudo([*base, "--webroot", "-w", str(WEBROOT_DIR)])
        code, out = _run(cmd, timeout=240)
        if code == 0:
            return True, out
        hint = ""
        low = (out or "").lower()
        if "nxdomain" in low or "dns" in low or "no valid" in low:
            hint = "\nDNS دامنه باید به IP همین سرور اشاره کند."
        return False, ((out or "certbot failed").strip()[-1800:] + hint).strip()
    finally:
        _stop_acme_http(helper)


def issue_or_renew(
    *,
    domain: str,
    email: str,
    force: bool = False,
) -> dict[str, Any]:
    """Issue/renew certificate, then enable HTTPS and restart the panel."""
    ensure_dirs()
    domain = normalize_domain(domain)
    email = (email or "").strip()
    prev = read_meta()
    was_enabled = bool(prev.get("ssl_enabled"))

    if not is_valid_domain(domain):
        _set_progress(pct=100, stage="error", message="دامنه نامعتبر است", done=True, ok=False)
        return {"ok": False, "error": "دامنه نامعتبر است (مثال: panel.example.com)"}
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        _set_progress(pct=100, stage="error", message="ایمیل نامعتبر است", done=True, ok=False)
        return {"ok": False, "error": "ایمیل معتبر برای Let's Encrypt لازم است"}

    _set_progress(pct=5, stage="start", message="شروع دریافت گواهی…", done=False)

    if not certbot_available():
        inst = install_certbot()
        if not inst.get("ok"):
            err = str(inst.get("error") or "نصب certbot ناموفق")
            _set_progress(pct=100, stage="error", message=err[:200], done=True, ok=False)
            meta = read_meta()
            meta.update({"last_error": err, "domain": domain, "email": email})
            write_meta(meta)
            return {"ok": False, "error": err}

    _set_progress(pct=22, stage="ready", message="certbot آماده است", done=False)
    ok, log = _certbot_issue(domain, email, force=force)
    if not ok:
        meta = read_meta()
        meta.update(
            {
                "last_error": log[-2000:],
                "domain": domain,
                "email": email,
                # keep previous ssl_enabled as-is on failure
                "ssl_enabled": was_enabled,
            }
        )
        write_meta(meta)
        _set_progress(pct=100, stage="error", message=(log[-280:] or "ناموفق"), done=True, ok=False)
        return {"ok": False, "error": log[-1500:] or "صدور گواهی ناموفق بود"}

    _set_progress(pct=82, stage="copy", message="کپی گواهی به data/certs…", done=False)
    live = _find_and_copy_cert(domain)
    if not live or not cert_files_exist():
        msg = "گواهی صادر شد ولی خواندن فایل‌ها ممکن نشد — دسترسی /etc/letsencrypt را بررسی کنید"
        meta = read_meta()
        meta.update({"last_error": msg, "domain": domain, "email": email, "ssl_enabled": was_enabled})
        write_meta(meta)
        _set_progress(pct=100, stage="error", message=msg, done=True, ok=False)
        return {"ok": False, "error": msg}

    expires_at, _expired = _parse_expiry(LIVE_CERT)
    now = datetime.now(timezone.utc).isoformat()
    meta = {
        "domain": domain,
        "panel_domain": domain,
        "miniapp_domain": domain,
        "email": email,
        "issued_at": now,
        "expires_at": expires_at,
        # Critical: do NOT flip HTTPS on here — that used to restart mid-HTTP and "crash" Safari
        "ssl_enabled": was_enabled,
        "last_error": None,
        "letsencrypt_live": live,
        "log_tail": (log or "")[-800:],
        "public_https": public_https_url(domain),
    }
    write_meta(meta)
    _set_progress(pct=90, stage="enable", message="فعال‌سازی HTTPS…", done=False)
    en = enable_https(restart=True)
    if not en.get("ok"):
        msg = (
            "گواهی آماده شد ولی فعال‌سازی HTTPS ناموفق بود — "
            + str(en.get("error") or "خطا")[:400]
        )
        meta = read_meta()
        meta["last_error"] = msg
        write_meta(meta)
        _set_progress(pct=100, stage="error", message=msg[:280], done=True, ok=False)
        return {
            "ok": False,
            "error": msg,
            "domain": domain,
            "cert_path": str(LIVE_CERT),
            "key_path": str(LIVE_KEY),
            "needs_manual_enable": True,
        }
    return {
        "ok": True,
        "domain": domain,
        "expires_at": expires_at,
        "cert_path": str(LIVE_CERT),
        "key_path": str(LIVE_KEY),
        "public_https": en.get("public_https"),
        "auto_enabled": True,
    }


def enable_https(*, restart: bool = True) -> dict[str, Any]:
    """Turn on uvicorn TLS + PUBLIC_BASE_URL, then optionally restart."""
    if not cert_files_exist():
        return {"ok": False, "error": "ابتدا گواهی را دریافت کنید"}
    meta = read_meta()
    domain = normalize_domain(meta.get("domain") or "")
    if not domain:
        return {"ok": False, "error": "دامنه گواهی مشخص نیست"}
    url = public_https_url(domain)
    try:
        from app.services.setup_wizard import update_env_keys

        update_env_keys({"PUBLIC_BASE_URL": url})
        get_settings.cache_clear()
    except Exception as exc:
        logger.warning("PUBLIC_BASE_URL update failed: %s", exc)
    meta["ssl_enabled"] = True
    meta["public_https"] = url
    meta["last_error"] = None
    write_meta(meta)
    if restart:
        _set_progress(
            pct=100,
            stage="restart",
            message="HTTPS فعال شد — ری‌استارت پنل… بعداً با آدرس HTTPS وارد شوید",
            done=True,
            ok=True,
            restarting=True,
            https_url=url,
        )
        try:
            from app.services.service_control import schedule_panel_restart

            ok = schedule_panel_restart(delay_sec=3.5, reason="ssl https enable")
            if not ok:
                return {
                    "ok": False,
                    "error": (
                        "HTTPS در تنظیمات فعال شد ولی ری‌استارت خودکار ممکن نشد. "
                        "روی سرور اجرا کنید: sudo systemctl restart pgclockbot "
                        "سپس با آدرس HTTPS دامنه وارد شوید."
                    ),
                    "public_https": url,
                    "needs_manual_restart": True,
                }
        except Exception as exc:
            return {
                "ok": False,
                "error": f"فعال شد ولی ری‌استارت ممکن نشد: {exc}",
                "public_https": url,
                "needs_manual_restart": True,
            }
    return {"ok": True, "public_https": url}


def disable_https(*, restart: bool = True) -> dict[str, Any]:
    meta = read_meta()
    meta["ssl_enabled"] = False
    write_meta(meta)
    try:
        from app.services.setup_wizard import default_http_panel_url, update_env_keys

        update_env_keys({"PUBLIC_BASE_URL": default_http_panel_url().rstrip("/")})
        get_settings.cache_clear()
    except Exception as exc:
        logger.warning("PUBLIC_BASE_URL http revert failed: %s", exc)
    if restart:
        try:
            from app.services.service_control import schedule_panel_restart

            ok = schedule_panel_restart(delay_sec=2.5, reason="ssl https disable")
            if not ok:
                return {
                    "ok": False,
                    "error": (
                        "HTTPS در تنظیمات خاموش شد ولی ری‌استارت خودکار ممکن نشد. "
                        "دستی: sudo systemctl restart pgclockbot"
                    ),
                    "needs_manual_restart": True,
                }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    return {"ok": True}


def start_issue_job(*, domain: str, email: str, force: bool = False) -> dict[str, Any]:
    """Background issue/renew — enables HTTPS and restarts when cert succeeds."""
    global _JOB_RUNNING
    with _JOB_LOCK:
        if _JOB_RUNNING:
            return {"ok": False, "error": "یک عملیات SSL در حال اجراست"}
        _JOB_RUNNING = True

    def _worker() -> None:
        global _JOB_RUNNING
        try:
            issue_or_renew(domain=domain, email=email, force=force)
        except Exception as exc:
            logger.exception("SSL job failed")
            _set_progress(pct=100, stage="error", message=str(exc)[:240], done=True, ok=False)
            meta = read_meta()
            meta["last_error"] = str(exc)
            write_meta(meta)
        finally:
            with _JOB_LOCK:
                _JOB_RUNNING = False

    _set_progress(pct=3, stage="queued", message="در صف…", done=False)
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
