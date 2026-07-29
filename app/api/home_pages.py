"""Top-level overall dashboard (outside Bot / PasarGuard menus)."""

from __future__ import annotations

import asyncio

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.host_metrics import host_metrics
from app.services.home_overview import build_home_overview, _tone_class


def register_home_pages(app, *, render, require_admin, get_db):
    @app.get("/home", response_class=HTMLResponse)
    async def home_dashboard(
        request: Request,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
    ):
        overview = await build_home_overview(session)
        update = None
        try:
            from app.services.updates import check_github_update

            update = await check_github_update(force=True)
        except Exception:
            update = None
        return render(
            request,
            "home.html",
            {
                "staff": staff,
                "overview": overview,
                "update": update,
            },
        )

    @app.get("/home/metrics")
    async def home_metrics_json(staff: dict = Depends(require_admin)):
        # Reuse prior CPU sample when polling (wait_cpu=0); sample off the event loop.
        metrics = await asyncio.to_thread(host_metrics, wait_cpu=0.0)
        if metrics.get("cpu_percent") is None:
            metrics = await asyncio.to_thread(host_metrics, wait_cpu=0.12)
        cpu = metrics.get("cpu_percent")
        mem_pct = metrics.get("memory_percent")
        return JSONResponse(
            {
                "cpu_percent": cpu,
                "memory_percent": mem_pct,
                "memory_used_text": metrics.get("memory_used_text"),
                "memory_total_text": metrics.get("memory_total_text"),
                "cpu_tone": _tone_class(cpu if isinstance(cpu, (int, float)) else None),
                "mem_tone": _tone_class(mem_pct if isinstance(mem_pct, (int, float)) else None),
            }
        )
