from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class PasarGuardError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class PasarGuardClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.pg_base_url.rstrip("/")
        self._token: str | None = self.settings.pg_access_token or None
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def ensure_token(self) -> str:
        if self._token:
            return self._token
        resp = await self._client.post(
            "/api/admin/token",
            data={
                "username": self.settings.pg_username,
                "password": self.settings.pg_password,
            },
        )
        if resp.status_code >= 400:
            raise PasarGuardError("Login failed", resp.status_code, resp.text)
        data = resp.json()
        self._token = data["access_token"]
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
                f"{method} {path} failed",
                resp.status_code,
                resp.text,
            )
        if resp.status_code == 204 or not resp.content:
            return None
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            return resp.json()
        return resp.text

    # ---- users ----
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

    # ---- templates / groups / system ----
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

    # ---- subscription (no admin auth) ----
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


def extract_sub_token(subscription_url: str | None) -> str | None:
    if not subscription_url:
        return None
    url = subscription_url.rstrip("/")
    # typical: https://host/sub/TOKEN or .../sub/TOKEN/
    parts = url.split("/sub/")
    if len(parts) < 2:
        return None
    token = parts[-1].split("?")[0].strip("/")
    return token or None
