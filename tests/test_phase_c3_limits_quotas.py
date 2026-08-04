"""Phase C3 — HWID / device quota enforcement tests."""

from __future__ import annotations

import time
import unittest
from unittest.mock import AsyncMock, patch

from app.services.pg_quota import (
    PgQuotaError,
    assert_can_create_user,
    assert_can_modify_user,
    hwid_bounds,
    merge_role_limits,
)
from app.services.pasarguard import build_user_create_payload, build_user_modify_payload

GB = 1024**3


class HwidBoundsHelperTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(hwid_bounds({"min_hwid_per_user": 1, "max_hwid_per_user": 3}), (1, 3))
        self.assertEqual(hwid_bounds({"max_devices": 5}), (None, 5))
        self.assertEqual(hwid_bounds({"device_limit": 2}), (None, 2))


class HwidCreateQuotaTests(unittest.IsolatedAsyncioTestCase):
    async def test_hwid_above_max_rejected(self):
        admin = {"username": "r1", "status": "active", "total_users": 0}
        role = {
            "limits": {
                "max_users": 10,
                "data_limit_max": 50 * GB,
                "expire_max": 90 * 86400,
                "max_hwid_per_user": 2,
            }
        }
        with patch("app.services.pasarguard.get_pg") as get_pg:
            client = AsyncMock()
            client.get_admin = AsyncMock(return_value=admin)
            client.get_admin_role = AsyncMock(return_value=role)
            get_pg.return_value = client
            with self.assertRaises(PgQuotaError) as ctx:
                await assert_can_create_user(
                    {"role": "reseller", "pg_admin_username": "r1", "pg_role_id": 1},
                    data_limit=5 * GB,
                    expire_ts=int(time.time()) + 7 * 86400,
                    hwid_limit=5,
                )
            self.assertIn("HWID", ctx.exception.message)

    async def test_hwid_below_min_rejected(self):
        admin = {"username": "r1", "status": "active", "total_users": 0}
        role = {
            "limits": {
                "data_limit_max": 50 * GB,
                "expire_max": 90 * 86400,
                "min_hwid_per_user": 2,
                "max_hwid_per_user": 5,
            }
        }
        with patch("app.services.pasarguard.get_pg") as get_pg:
            client = AsyncMock()
            client.get_admin = AsyncMock(return_value=admin)
            client.get_admin_role = AsyncMock(return_value=role)
            get_pg.return_value = client
            with self.assertRaises(PgQuotaError) as ctx:
                await assert_can_create_user(
                    {"role": "reseller", "pg_admin_username": "r1", "pg_role_id": 1},
                    data_limit=5 * GB,
                    expire_ts=int(time.time()) + 7 * 86400,
                    hwid_limit=1,
                )
            self.assertIn("حداقل", ctx.exception.message)

    async def test_omitted_hwid_defaults_to_role_max(self):
        admin = {"username": "r1", "status": "active", "total_users": 0}
        role = {
            "limits": {
                "data_limit_max": 50 * GB,
                "expire_max": 90 * 86400,
                "max_hwid_per_user": 3,
            }
        }
        with patch("app.services.pasarguard.get_pg") as get_pg:
            client = AsyncMock()
            client.get_admin = AsyncMock(return_value=admin)
            client.get_admin_role = AsyncMock(return_value=role)
            get_pg.return_value = client
            # None hwid → defaults to max=3 → passes
            await assert_can_create_user(
                {"role": "reseller", "pg_admin_username": "r1", "pg_role_id": 1},
                data_limit=5 * GB,
                expire_ts=int(time.time()) + 7 * 86400,
                hwid_limit=None,
            )

    async def test_valid_hwid(self):
        admin = {"username": "r1", "status": "active", "total_users": 0}
        role = {
            "limits": {
                "data_limit_min": 1 * GB,
                "data_limit_max": 50 * GB,
                "expire_min": 86400,
                "expire_max": 90 * 86400,
                "min_hwid_per_user": 1,
                "max_hwid_per_user": 4,
            }
        }
        with patch("app.services.pasarguard.get_pg") as get_pg:
            client = AsyncMock()
            client.get_admin = AsyncMock(return_value=admin)
            client.get_admin_role = AsyncMock(return_value=role)
            get_pg.return_value = client
            await assert_can_create_user(
                {"role": "reseller", "pg_admin_username": "r1", "pg_role_id": 1},
                data_limit=5 * GB,
                expire_ts=int(time.time()) + 14 * 86400,
                hwid_limit=2,
            )

    async def test_owner_bypass(self):
        await assert_can_create_user(
            {"role": "admin"},
            hwid_limit=999,
        )


class HwidModifyQuotaTests(unittest.IsolatedAsyncioTestCase):
    async def test_modify_rejects_over_max(self):
        admin = {"username": "r1", "status": "active"}
        role = {"limits": {"max_hwid_per_user": 2}}
        with patch("app.services.pasarguard.get_pg") as get_pg:
            client = AsyncMock()
            client.get_admin = AsyncMock(return_value=admin)
            client.get_admin_role = AsyncMock(return_value=role)
            get_pg.return_value = client
            with self.assertRaises(PgQuotaError):
                await assert_can_modify_user(
                    {"role": "reseller", "pg_admin_username": "r1", "pg_role_id": 1},
                    hwid_limit=9,
                    hwid_changed=True,
                    data_limit_changed=False,
                    expire_changed=False,
                )


class PayloadHwidTests(unittest.TestCase):
    def test_create_payload_includes_positive_hwid(self):
        p = build_user_create_payload(
            username="u1", group_ids=[1], hwid_limit=3
        )
        self.assertEqual(p["hwid_limit"], 3)

    def test_create_payload_omits_unlimited(self):
        p = build_user_create_payload(
            username="u1", group_ids=[1], hwid_limit=0
        )
        self.assertNotIn("hwid_limit", p)

    def test_modify_payload_clears_with_zero(self):
        p = build_user_modify_payload(hwid_limit=0)
        self.assertIn("hwid_limit", p)
        self.assertIsNone(p["hwid_limit"])


class ExistingQuotaStillWorks(unittest.IsolatedAsyncioTestCase):
    async def test_max_users_still_enforced(self):
        admin = {
            "username": "r1",
            "status": "active",
            "total_users": 2,
            "permission_overrides": {"max_users": 2},
        }
        with patch("app.services.pasarguard.get_pg") as get_pg:
            client = AsyncMock()
            client.get_admin = AsyncMock(return_value=admin)
            client.get_admin_role = AsyncMock(return_value={"limits": {}})
            get_pg.return_value = client
            with self.assertRaises(PgQuotaError):
                await assert_can_create_user(
                    {"role": "reseller", "pg_admin_username": "r1"},
                    data_limit=1 * GB,
                    expire_ts=int(time.time()) + 86400,
                )


if __name__ == "__main__":
    unittest.main()
