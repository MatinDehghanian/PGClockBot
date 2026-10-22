"""Branded public/panel status pages (404 look) for HTTP and payment returns."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

WEB_DIR = Path(__file__).resolve().parents[1] / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def render_status_page(
    request: Request,
    *,
    kind: str | int,
    title: str,
    message: str,
    http_status: int | None = None,
    watermark: str | None = None,
    kicker: str | None = None,
    ref: str | None = None,
    primary_href: str | None = None,
    primary_label: str = "",
    secondary_href: str | None = None,
    secondary_label: str = "",
    guide_heading: str | None = None,
    guide_steps: list[dict[str, Any]] | None = None,
    code_block: str | None = None,
    guide_note: str | None = None,
    body_html: str = "",
    footer: str | None = None,
):
    """Render ``panel_status.html``.

    ``kind`` is the ``data-status`` tone: numeric HTTP codes or ``ok`` / ``warn`` /
    ``pending`` / ``error``.
    """
    from app.version import __version__ as app_version

    try:
        from app.services.pwa import panel_display_name

        pname = panel_display_name()
    except Exception:
        pname = "MrClockBot"

    kind_s = str(kind)
    if http_status is None:
        http_status = int(kind) if kind_s.isdigit() else 200

    if kicker is None:
        kicker = f"HTTP {kind_s}" if kind_s.isdigit() else kind_s.upper()

    return templates.TemplateResponse(
        request,
        "panel_status.html",
        {
            "code": kind_s,
            "title": title,
            "message": message,
            "watermark": watermark if watermark is not None else kind_s,
            "kicker": kicker,
            "ref": ref,
            "primary_href": primary_href or "",
            "primary_label": primary_label,
            "secondary_href": secondary_href or "",
            "secondary_label": secondary_label,
            "guide_heading": guide_heading or "",
            "guide_steps": guide_steps or [],
            "code_block": code_block or "",
            "guide_note": guide_note or "",
            "body_html": body_html or "",
            "footer": footer
            or "اگر مشکل ادامه داشت، از حساب خارج شوید و دوباره وارد شوید.",
            "app_version": app_version,
            "pwa_name": pname,
        },
        status_code=int(http_status),
    )
