from __future__ import annotations

"""PasarGuard-connected admin pages (Persian UI)."""

from urllib.parse import quote

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.pasarguard import get_pg


def _q(msg: str) -> str:
    return quote(str(msg), safe="")


def register_pg_pages(app, *, render, require_admin, get_db):
    @app.get("/pg", response_class=HTMLResponse)
    async def pg_home(request: Request, staff: dict = Depends(require_admin)):
        err = None
        stats_rows: list[tuple[str, str]] = []
        nodes = []
        try:
            pg = get_pg()
            raw = await pg.get_system_stats()
            if isinstance(raw, dict):
                for key, val in raw.items():
                    if isinstance(val, (str, int, float, bool)):
                        stats_rows.append((str(key), str(val)))
            nodes = await pg.get_nodes_simple()
        except Exception as e:
            err = str(e)
        return render(
            request,
            "pg_home.html",
            {"staff": staff, "stats_rows": stats_rows, "nodes": nodes, "flash_err": err},
        )

    @app.get("/pg/templates", response_class=HTMLResponse)
    async def pg_templates(request: Request, staff: dict = Depends(require_admin)):
        err = request.query_params.get("err")
        ok = request.query_params.get("ok")
        templates = []
        groups = []
        try:
            pg = get_pg()
            templates = await pg.get_user_templates_simple()
            # full list may have more fields
            full = await pg.get_user_templates()
            if isinstance(full, list) and full:
                templates = full
            elif isinstance(full, dict):
                from app.services.pasarguard import as_list

                templates = as_list(full, "templates") or templates
            groups = await pg.get_groups_simple()
        except Exception as e:
            err = str(e)
        return render(
            request,
            "pg_templates.html",
            {
                "staff": staff,
                "templates": templates,
                "groups": groups,
                "flash_err": err,
                "flash_ok": ok,
            },
        )

    @app.post("/pg/templates")
    async def pg_templates_create(
        request: Request,
        name: str = Form(...),
        data_limit_gb: str = Form(""),
        expire_days: str = Form("30"),
        staff: dict = Depends(require_admin),
    ):
        form = await request.form()
        group_ids = [int(v) for k, v in form.items() if k.startswith("g_") and str(v).isdigit()]
        if not group_ids:
            return RedirectResponse(f"/pg/templates?err={_q('حداقل یک گروه انتخاب کنید')}", status_code=303)
        try:
            days = int(expire_days or "30")
            gb = float(data_limit_gb) if data_limit_gb.strip() else None
            payload = {
                "name": name.strip(),
                "group_ids": group_ids,
                "expire_duration": days * 86400 if days else None,
                "data_limit": int(gb * (1024**3)) if gb is not None else None,
                "status": "active",
            }
            await get_pg().create_user_template(payload)
        except Exception as e:
            return RedirectResponse(f"/pg/templates?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/templates?ok={_q('تمپلیت در پاسارگارد ساخته شد')}", status_code=303)

    @app.post("/pg/templates/{template_id}/delete")
    async def pg_templates_delete(template_id: int, staff: dict = Depends(require_admin)):
        try:
            await get_pg().delete_user_template(template_id)
        except Exception as e:
            return RedirectResponse(f"/pg/templates?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/templates?ok={_q('تمپلیت حذف شد')}", status_code=303)

    @app.get("/pg/groups", response_class=HTMLResponse)
    async def pg_groups(request: Request, staff: dict = Depends(require_admin)):
        err = request.query_params.get("err")
        ok = request.query_params.get("ok")
        groups = []
        inbounds = []
        try:
            pg = get_pg()
            groups = await pg.get_groups_simple()
            full = await pg.get_groups()
            from app.services.pasarguard import as_list

            if isinstance(full, list) and full:
                groups = full
            else:
                groups = as_list(full, "groups") or groups
            inbounds = await pg.get_inbounds()
            # inbounds may be list of strings (tags) or objects
        except Exception as e:
            err = str(e)
        inbound_tags = []
        for item in inbounds:
            if isinstance(item, str):
                inbound_tags.append(item)
            elif isinstance(item, dict):
                inbound_tags.append(item.get("tag") or item.get("name") or str(item.get("id")))
        return render(
            request,
            "pg_groups.html",
            {
                "staff": staff,
                "groups": groups,
                "inbound_tags": inbound_tags,
                "flash_err": err,
                "flash_ok": ok,
            },
        )

    @app.post("/pg/groups")
    async def pg_groups_create(
        request: Request,
        name: str = Form(...),
        staff: dict = Depends(require_admin),
    ):
        form = await request.form()
        tags = [str(v) for k, v in form.items() if k.startswith("tag_")]
        if not tags:
            return RedirectResponse(f"/pg/groups?err={_q('حداقل یک اینباند انتخاب کنید')}", status_code=303)
        try:
            await get_pg().create_group({"name": name.strip(), "inbound_tags": tags})
        except Exception as e:
            return RedirectResponse(f"/pg/groups?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/groups?ok={_q('گروه در پاسارگارد ساخته شد')}", status_code=303)

    @app.post("/pg/groups/{group_id}/delete")
    async def pg_groups_delete(group_id: int, staff: dict = Depends(require_admin)):
        try:
            await get_pg().delete_group(group_id)
        except Exception as e:
            return RedirectResponse(f"/pg/groups?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/groups?ok={_q('گروه حذف شد')}", status_code=303)

    @app.get("/pg/nodes", response_class=HTMLResponse)
    async def pg_nodes(request: Request, staff: dict = Depends(require_admin)):
        err = None
        nodes = []
        try:
            nodes = await get_pg().get_nodes()
        except Exception as e:
            err = str(e)
        return render(request, "pg_nodes.html", {"staff": staff, "nodes": nodes, "flash_err": err})

    @app.post("/pg/nodes/{node_id}/reconnect")
    async def pg_node_reconnect(node_id: int, staff: dict = Depends(require_admin)):
        try:
            await get_pg().reconnect_node(node_id)
        except Exception as e:
            return RedirectResponse(f"/pg/nodes?err={_q(e)}", status_code=303)
        return RedirectResponse("/pg/nodes", status_code=303)

    @app.get("/pg/hosts", response_class=HTMLResponse)
    async def pg_hosts(request: Request, staff: dict = Depends(require_admin)):
        err = None
        hosts = []
        try:
            hosts = await get_pg().get_hosts()
        except Exception as e:
            err = str(e)
        return render(request, "pg_hosts.html", {"staff": staff, "hosts": hosts, "flash_err": err})

    @app.get("/pg/inbounds", response_class=HTMLResponse)
    async def pg_inbounds(request: Request, staff: dict = Depends(require_admin)):
        err = None
        inbounds = []
        details = None
        try:
            pg = get_pg()
            inbounds = await pg.get_inbounds()
            details = await pg.get_inbounds_details()
        except Exception as e:
            err = str(e)
        return render(
            request,
            "pg_inbounds.html",
            {"staff": staff, "inbounds": inbounds, "details": details, "flash_err": err},
        )
