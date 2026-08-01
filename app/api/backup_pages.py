"""Admin backup / restore routes for the web panel."""

from __future__ import annotations

import asyncio
from urllib.parse import quote

from fastapi import Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.services.backup import (
    create_backup,
    delete_backup,
    get_backup_path,
    restore_backup,
    save_uploaded_backup,
)


def register_backup_pages(app, *, render, require_admin, get_db):
    @app.get("/settings/backup", response_class=HTMLResponse)
    async def backup_redirect(staff: dict = Depends(require_admin)):
        return RedirectResponse("/settings?tab=backup", status_code=303)

    @app.post("/backup/create")
    async def backup_create(
        staff: dict = Depends(require_admin),
        note: str = Form(""),
        include_env: str = Form(""),
    ):
        try:
            result = await asyncio.to_thread(
                create_backup,
                note=note,
                include_env=str(include_env) in {"1", "on", "true", "yes"},
                created_by=f"web:{staff.get('username') or 'admin'}",
            )
        except Exception as e:
            return RedirectResponse(
                "/settings?tab=backup&err=" + quote(str(e)),
                status_code=303,
            )
        return RedirectResponse(
            "/settings?tab=backup&ok="
            + quote(f"بکاپ ساخته شد: {result.get('filename')} ({result.get('size_human')})"),
            status_code=303,
        )

    @app.get("/backup/download/{backup_id}")
    async def backup_download(backup_id: str, staff: dict = Depends(require_admin)):
        path = get_backup_path(backup_id)
        if not path:
            return RedirectResponse(
                "/settings?tab=backup&err=" + quote("بکاپ یافت نشد"),
                status_code=303,
            )
        return FileResponse(
            path,
            filename=path.name,
            media_type="application/zip",
        )

    @app.post("/backup/delete/{backup_id}")
    async def backup_delete(backup_id: str, staff: dict = Depends(require_admin)):
        ok = delete_backup(backup_id)
        if not ok:
            return RedirectResponse(
                "/settings?tab=backup&err=" + quote("حذف بکاپ ممکن نشد"),
                status_code=303,
            )
        return RedirectResponse(
            "/settings?tab=backup&ok=" + quote("بکاپ حذف شد"),
            status_code=303,
        )

    @app.post("/backup/restore/{backup_id}")
    async def backup_restore(
        backup_id: str,
        staff: dict = Depends(require_admin),
        restore_env: str = Form(""),
        confirm: str = Form(""),
    ):
        confirm_ok = (confirm or "").strip().upper() in {"1", "YES", "ON", "TRUE", "RESTORE"}
        if not confirm_ok:
            return RedirectResponse(
                "/settings?tab=backup&err=" + quote("تأیید ریستور انجام نشد"),
                status_code=303,
            )
        path = get_backup_path(backup_id)
        if not path:
            return RedirectResponse(
                "/settings?tab=backup&err=" + quote("بکاپ یافت نشد"),
                status_code=303,
            )
        # Release DB connections before swapping the file
        from app.db.session import engine

        await engine.dispose()
        result = await asyncio.to_thread(
            restore_backup,
            path,
            restore_env=str(restore_env) in {"1", "on", "true", "yes"},
            safety_backup=True,
            restart=True,
            actor=f"web:{staff.get('username') or 'admin'}",
        )
        if not result.get("ok"):
            return RedirectResponse(
                "/settings?tab=backup&err=" + quote(result.get("error") or "ریستور ناموفق"),
                status_code=303,
            )
        msg = "ریستور انجام شد"
        if result.get("safety_id"):
            msg += f" · بکاپ ایمنی: {result['safety_id']}"
        if result.get("restart_scheduled"):
            msg += " · در حال ری‌استارت سرویس…"
            return RedirectResponse(
                "/login?restarting=1&ok=" + quote(msg),
                status_code=303,
            )
        return RedirectResponse("/settings?tab=backup&ok=" + quote(msg), status_code=303)

    @app.post("/backup/upload")
    async def backup_upload(
        staff: dict = Depends(require_admin),
        file: UploadFile = File(...),
    ):
        max_bytes = 500 * 1024 * 1024
        raw = await file.read(max_bytes + 1)
        if len(raw) > max_bytes:
            return RedirectResponse(
                "/settings?tab=backup&err=" + quote("حجم بکاپ بیش از ۵۰۰ مگابایت است"),
                status_code=303,
            )
        result = await asyncio.to_thread(
            save_uploaded_backup,
            raw,
            filename=file.filename or "",
        )
        if not result.get("ok"):
            return RedirectResponse(
                "/settings?tab=backup&err=" + quote(result.get("error") or "آپلود نامعتبر"),
                status_code=303,
            )
        return RedirectResponse(
            "/settings?tab=backup&ok="
            + quote(f"بکاپ آپلود شد: {result.get('filename')}"),
            status_code=303,
        )
