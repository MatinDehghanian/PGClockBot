from __future__ import annotations

"""PasarGuard manager pages — categorized CRUD wired to live API."""

from urllib.parse import quote

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.services.formatting import format_metric
from app.services.pasarguard import as_list, get_pg


def _q(msg: str) -> str:
    return quote(str(msg), safe="")


def _inbound_tags(raw) -> list[str]:
    tags = []
    for item in raw or []:
        if isinstance(item, str):
            tags.append(item)
        elif isinstance(item, dict):
            tags.append(str(item.get("tag") or item.get("name") or item.get("id") or ""))
    return [t for t in tags if t]


def _addr_set(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").replace("؛", ",").split(",") if p.strip()]


def register_pg_pages(app, *, render, require_admin, get_db):
    @app.get("/pg", response_class=HTMLResponse)
    async def pg_home(request: Request, staff: dict = Depends(require_admin)):
        err = None
        stats_rows: list[tuple[str, str]] = []
        nodes = []
        counts = {"templates": 0, "groups": 0, "hosts": 0, "nodes": 0}
        try:
            pg = get_pg()
            raw = await pg.get_system_stats()
            if isinstance(raw, dict):
                for key, val in raw.items():
                    if isinstance(val, (dict, list)):
                        continue
                    stats_rows.append((str(key), format_metric(str(key), val)))
            nodes = await pg.get_nodes_simple()
            counts["nodes"] = len(nodes)
            counts["templates"] = len(await pg.get_user_templates_simple())
            counts["groups"] = len(await pg.get_groups_simple())
            counts["hosts"] = len(await pg.get_hosts())
        except Exception as e:
            err = str(e)
        return render(
            request,
            "pg_home.html",
            {
                "staff": staff,
                "stats_rows": stats_rows,
                "nodes": nodes,
                "counts": counts,
                "flash_err": err,
            },
        )

    # ---- templates ----
    @app.get("/pg/templates", response_class=HTMLResponse)
    async def pg_templates(request: Request, staff: dict = Depends(require_admin)):
        err = request.query_params.get("err")
        ok = request.query_params.get("ok")
        templates, groups = [], []
        try:
            pg = get_pg()
            templates = await pg.get_user_templates_simple()
            full = await pg.get_user_templates()
            if isinstance(full, list) and full:
                templates = full
            elif isinstance(full, dict):
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
        group_ids = [int(v) for k, v in form.items() if str(k).startswith("g_") and str(v).isdigit()]
        if not group_ids:
            return RedirectResponse(f"/pg/templates?err={_q('حداقل یک گروه انتخاب کنید')}", status_code=303)
        try:
            days = int(expire_days or "30")
            gb = float(data_limit_gb) if str(data_limit_gb).strip() else None
            await get_pg().create_user_template(
                {
                    "name": name.strip(),
                    "group_ids": group_ids,
                    "expire_duration": days * 86400 if days else None,
                    "data_limit": int(gb * (1024**3)) if gb is not None else None,
                    "status": "active",
                }
            )
        except Exception as e:
            return RedirectResponse(f"/pg/templates?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/templates?ok={_q('تمپلیت ساخته شد')}", status_code=303)

    @app.post("/pg/templates/{template_id}/delete")
    async def pg_templates_delete(template_id: int, staff: dict = Depends(require_admin)):
        try:
            await get_pg().delete_user_template(template_id)
        except Exception as e:
            return RedirectResponse(f"/pg/templates?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/templates?ok={_q('تمپلیت حذف شد')}", status_code=303)

    # ---- groups ----
    @app.get("/pg/groups", response_class=HTMLResponse)
    async def pg_groups(request: Request, staff: dict = Depends(require_admin)):
        err = request.query_params.get("err")
        ok = request.query_params.get("ok")
        groups, inbound_tags = [], []
        edit_id = request.query_params.get("edit")
        edit_group = None
        try:
            pg = get_pg()
            full = await pg.get_groups()
            groups = full if isinstance(full, list) else as_list(full, "groups")
            if not groups:
                groups = await pg.get_groups_simple()
            inbound_tags = _inbound_tags(await pg.get_inbounds())
            if edit_id and str(edit_id).isdigit():
                edit_group = await pg.get_group(int(edit_id))
        except Exception as e:
            err = str(e)
        return render(
            request,
            "pg_groups.html",
            {
                "staff": staff,
                "groups": groups,
                "inbound_tags": inbound_tags,
                "edit_group": edit_group,
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
        tags = [str(v) for k, v in form.items() if str(k).startswith("tag_")]
        if not tags:
            return RedirectResponse(f"/pg/groups?err={_q('حداقل یک اینباند انتخاب کنید')}", status_code=303)
        try:
            await get_pg().create_group({"name": name.strip(), "inbound_tags": tags})
        except Exception as e:
            return RedirectResponse(f"/pg/groups?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/groups?ok={_q('گروه ساخته شد')}", status_code=303)

    @app.post("/pg/groups/{group_id}/edit")
    async def pg_groups_edit(
        request: Request,
        group_id: int,
        name: str = Form(...),
        staff: dict = Depends(require_admin),
    ):
        form = await request.form()
        tags = [str(v) for k, v in form.items() if str(k).startswith("tag_")]
        disabled = bool(form.get("is_disabled"))
        try:
            await get_pg().modify_group(
                group_id,
                {"name": name.strip(), "inbound_tags": tags, "is_disabled": disabled},
            )
        except Exception as e:
            return RedirectResponse(f"/pg/groups?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/groups?ok={_q('گروه به‌روز شد')}", status_code=303)

    @app.post("/pg/groups/{group_id}/delete")
    async def pg_groups_delete(group_id: int, staff: dict = Depends(require_admin)):
        try:
            await get_pg().delete_group(group_id)
        except Exception as e:
            return RedirectResponse(f"/pg/groups?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/groups?ok={_q('گروه حذف شد')}", status_code=303)

    # ---- hosts ----
    @app.get("/pg/hosts", response_class=HTMLResponse)
    async def pg_hosts(request: Request, staff: dict = Depends(require_admin)):
        err = request.query_params.get("err")
        ok = request.query_params.get("ok")
        hosts, inbound_tags = [], []
        try:
            pg = get_pg()
            hosts = await pg.get_hosts()
            inbound_tags = _inbound_tags(await pg.get_inbounds())
        except Exception as e:
            err = str(e)
        return render(
            request,
            "pg_hosts.html",
            {
                "staff": staff,
                "hosts": hosts,
                "inbound_tags": inbound_tags,
                "flash_err": err,
                "flash_ok": ok,
            },
        )

    @app.post("/pg/hosts")
    async def pg_hosts_create(
        remark: str = Form(...),
        address: str = Form(...),
        port: str = Form(""),
        inbound_tag: str = Form(...),
        priority: int = Form(0),
        staff: dict = Depends(require_admin),
    ):
        addrs = _addr_set(address)
        if not addrs:
            return RedirectResponse(f"/pg/hosts?err={_q('آدرس هاست الزامی است')}", status_code=303)
        payload = {
            "remark": remark.strip(),
            "address": addrs,
            "inbound_tag": inbound_tag.strip(),
            "priority": priority,
            "is_disabled": False,
        }
        if str(port).strip().isdigit():
            payload["port"] = int(port)
        try:
            await get_pg().create_host(payload)
        except Exception as e:
            return RedirectResponse(f"/pg/hosts?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/hosts?ok={_q('هاست ساخته شد')}", status_code=303)

    @app.post("/pg/hosts/{host_id}/toggle")
    async def pg_hosts_toggle(host_id: int, staff: dict = Depends(require_admin)):
        try:
            host = await get_pg().get_host(host_id)
            disabled = bool(host.get("is_disabled"))
            await get_pg().set_host_disabled(host_id, not disabled)
        except Exception as e:
            return RedirectResponse(f"/pg/hosts?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/hosts?ok={_q('وضعیت هاست تغییر کرد')}", status_code=303)

    @app.post("/pg/hosts/{host_id}/delete")
    async def pg_hosts_delete(host_id: int, staff: dict = Depends(require_admin)):
        try:
            await get_pg().delete_host(host_id)
        except Exception as e:
            return RedirectResponse(f"/pg/hosts?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/hosts?ok={_q('هاست حذف شد')}", status_code=303)

    # ---- nodes / inbounds / admins ----
    @app.get("/pg/nodes", response_class=HTMLResponse)
    async def pg_nodes(request: Request, staff: dict = Depends(require_admin)):
        err = request.query_params.get("err")
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

    @app.get("/pg/inbounds", response_class=HTMLResponse)
    async def pg_inbounds(request: Request, staff: dict = Depends(require_admin)):
        err = request.query_params.get("err")
        inbounds, details = [], None
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

    @app.get("/pg/admins", response_class=HTMLResponse)
    async def pg_admins(request: Request, staff: dict = Depends(require_admin)):
        err = request.query_params.get("err")
        ok = request.query_params.get("ok")
        admins = []
        try:
            admins = await get_pg().get_admins()
            if not admins:
                admins = await get_pg().get_admins_simple()
        except Exception as e:
            err = str(e)
        return render(
            request,
            "pg_admins.html",
            {"staff": staff, "admins": admins, "flash_err": err, "flash_ok": ok},
        )

    @app.post("/pg/admins")
    async def pg_admins_create(
        username: str = Form(...),
        password: str = Form(...),
        is_sudo: str = Form(""),
        staff: dict = Depends(require_admin),
    ):
        try:
            payload = {
                "username": username.strip(),
                "password": password,
                "is_sudo": bool(is_sudo),
            }
            await get_pg().create_admin(payload)
        except Exception as e:
            return RedirectResponse(f"/pg/admins?err={_q(e)}", status_code=303)
        return RedirectResponse(f"/pg/admins?ok={_q('ادمین پنل ساخته شد')}", status_code=303)
