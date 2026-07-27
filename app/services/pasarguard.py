from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import get_settings, normalize_pg_base_url

logger = logging.getLogger(__name__)


class PasarGuardError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class PasarGuardClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = normalize_pg_base_url(self.settings.pg_base_url)
        self._token: str | None = (self.settings.pg_access_token or None) or None
        if self._token == "":
            self._token = None
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            follow_redirects=True,
        )
        if self.base_url != (self.settings.pg_base_url or "").rstrip("/"):
            logger.warning(
                "PG_BASE_URL normalized: %r → %r",
                self.settings.pg_base_url,
                self.base_url,
            )

    async def close(self) -> None:
        await self._client.aclose()

    async def ensure_token(self) -> str:
        if self._token:
            return self._token
        username = (self.settings.pg_username or "").strip()
        password = (self.settings.pg_password or "").replace("\r", "").strip()
        if not username or not password:
            raise PasarGuardError("PG_USERNAME / PG_PASSWORD missing in .env")

        attempts = [
            {"grant_type": "password", "username": username, "password": password},
            {"username": username, "password": password},
        ]
        last: httpx.Response | None = None
        for data in attempts:
            last = await self._client.post("/api/admin/token", data=data)
            if last.status_code < 400:
                break
        assert last is not None
        if last.status_code >= 400:
            detail = (last.text or "")[:300]
            raise PasarGuardError(
                f"PasarGuard login failed ({last.status_code}) at "
                f"{self.base_url}/api/admin/token — check PG_BASE_URL / user / password. {detail}",
                last.status_code,
                last.text,
            )
        payload = last.json()
        token = payload.get("access_token")
        if not token:
            raise PasarGuardError("PasarGuard login response missing access_token", body=payload)
        self._token = token
        logger.info("PasarGuard login OK · base=%s", self.base_url)
        return self._token

    async def _headers(self) -> dict[str, str]:
        token = await self.ensure_token()
        return {"Authorization": f"Bearer {token}"}

    async def request(
        self,
        method: str,
        path: str,
        *,
        auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        headers = kwargs.pop("headers", {})
        if auth:
            headers.update(await self._headers())
        resp = await self._client.request(method, path, headers=headers, **kwargs)
        if resp.status_code == 401 and auth:
            self._token = None
            headers.update(await self._headers())
            resp = await self._client.request(method, path, headers=headers, **kwargs)
        if resp.status_code >= 400:
            raise PasarGuardError(
                f"{method} {path} failed ({resp.status_code})",
                resp.status_code,
                resp.text,
            )
        if resp.status_code == 204 or not resp.content:
            return None
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            return resp.json()
        return resp.text

    async def get_users(self, **params: Any) -> dict:
        return await self.request("GET", "/api/users", params=params)

    async def get_user_by_username(self, username: str) -> dict:
        return await self.request("GET", f"/api/user/by-username/{username}")

    async def get_user_by_id(self, user_id: int) -> dict:
        return await self.request("GET", f"/api/user/by-id/{user_id}")

    async def create_user(self, payload: dict) -> dict:
        return await self.request("POST", "/api/user", json=payload)

    async def create_user_from_template(self, payload: dict) -> dict:
        return await self.request("POST", "/api/user/from_template", json=payload)

    async def modify_user_by_id(self, user_id: int, payload: dict) -> dict:
        return await self.request("PUT", f"/api/user/by-id/{user_id}", json=payload)

    async def modify_user_with_template(self, user_id: int, payload: dict) -> dict:
        return await self.request(
            "PUT", f"/api/user/from_template/by-id/{user_id}", json=payload
        )

    async def delete_user_by_id(self, user_id: int) -> None:
        await self.request("DELETE", f"/api/user/by-id/{user_id}")

    async def reset_user_by_id(self, user_id: int) -> dict:
        return await self.request("POST", f"/api/user/by-id/{user_id}/reset")

    async def revoke_sub_by_id(self, user_id: int) -> dict:
        return await self.request("POST", f"/api/user/by-id/{user_id}/revoke_sub")

    async def set_disabled_by_id(self, user_id: int, disabled: bool) -> dict:
        return await self.request(
            "PUT",
            f"/api/user/by-id/{user_id}/disabled",
            json={"disabled": disabled},
        )

    async def set_owner_by_id(self, user_id: int, admin_username: str) -> dict:
        return await self.request(
            "PUT",
            f"/api/user/by-id/{user_id}/set_owner",
            params={"admin_username": admin_username},
        )

    async def get_user_usage(self, user_id: int) -> Any:
        return await self.request("GET", f"/api/user/by-id/{user_id}/usage")

    async def get_user_templates(self) -> Any:
        return await self.request("GET", "/api/user_templates")

    async def get_user_templates_simple(self) -> Any:
        return await self.request("GET", "/api/user_templates/simple")

    async def get_groups_simple(self) -> Any:
        return await self.request("GET", "/api/groups/simple")

    async def get_system_stats(self) -> dict:
        return await self.request("GET", "/api/system")

    async def get_nodes(self) -> Any:
        return await self.request("GET", "/api/nodes")

    async def get_nodes_realtime(self) -> Any:
        return await self.request("GET", "/api/nodes/realtime_stats")

    async def reconnect_node(self, node_id: int) -> Any:
        return await self.request("POST", f"/api/node/{node_id}/reconnect")

    async def subscription_info(self, token: str) -> dict:
        return await self.request("GET", f"/sub/{token}/info", auth=False)

    async def subscription_usage(self, token: str) -> Any:
        return await self.request("GET", f"/sub/{token}/usage", auth=False)


_pg: Optional[PasarGuardClient] = None


def get_pg() -> PasarGuardClient:
    global _pg
    if _pg is None:
        _pg = PasarGuardClient()
    return _pg


def reset_pg() -> None:
    global _pg
    _pg = None


def extract_sub_token(subscription_url: str | None) -> str | None:
    if not subscription_url:
        return None
    url = subscription_url.rstrip("/")
    parts = url.split("/sub/")
    if len(parts) < 2:
        return None
    token = parts[-1].split("?")[0].strip("/")
    return token or None
