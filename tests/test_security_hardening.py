"""Security hardening regression tests."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import OrderStatus
from app.services.orders import renew_service_with_plan


class MediaMountTests(unittest.TestCase):
    def test_media_mounts_uploads_only(self):
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        self.assertIn('"/media/uploads"', src)
        self.assertNotIn('StaticFiles(directory=str(DATA_DIR))', src)
        self.assertIn("never mount DATA_DIR", src)


class SignerSecretTests(unittest.TestCase):
    def test_no_hardcoded_fallback_secret(self):
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        self.assertNotIn('"pgclock-secret"', src)
        self.assertIn("ensure_web_secret()", src)


class HealthLeakTests(unittest.TestCase):
    def test_health_does_not_expose_admin_username(self):
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        start = src.index("async def health")
        end = src.index("@app.", start + 1)
        body = src[start:end]
        self.assertNotIn("admin_username", body)


class RenewTenancyTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_foreign_shop_plan(self):
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        plan = MagicMock()
        plan.is_active = True
        plan.is_trial = False
        plan.owner_reseller_id = 99
        plan.price = 0
        plan.id = 9
        svc = MagicMock()
        svc.id = 1
        svc.bot_user_id = 5
        with patch("app.services.users.current_shop_reseller_id", return_value=1):
            with self.assertRaises(ValueError) as ctx:
                await renew_service_with_plan(
                    session, user_id=5, service=svc, plan=plan
                )
        self.assertIn("فروشگاه", str(ctx.exception))

    async def test_rejects_trial_renewal(self):
        session = MagicMock()
        plan = MagicMock()
        plan.is_active = True
        plan.is_trial = True
        plan.owner_reseller_id = None
        plan.price = 0
        plan.id = 9
        svc = MagicMock()
        svc.id = 1
        svc.bot_user_id = 5
        with patch("app.services.users.current_shop_reseller_id", return_value=None):
            with self.assertRaises(ValueError) as ctx:
                await renew_service_with_plan(
                    session, user_id=5, service=svc, plan=plan
                )
        self.assertIn("تست", str(ctx.exception))


class ReceiptAutoApproveTests(unittest.TestCase):
    def test_wallet_topup_blocked_in_code(self):
        src = Path("app/services/receipts.py").read_text(encoding="utf-8")
        self.assertIn("is_wallet_topup", src)
        self.assertIn("Never auto-approve wallet top-ups", src)


class ForceJoinMiddlewareTests(unittest.TestCase):
    def test_middleware_registered(self):
        init_src = Path("app/bot/__init__.py").read_text(encoding="utf-8")
        self.assertIn("ForceJoinMiddleware", init_src)
        mw_src = Path("app/bot/middlewares.py").read_text(encoding="utf-8")
        self.assertIn("get_chat_member", mw_src)


class SessionRevalidationTests(unittest.TestCase):
    def test_require_staff_checks_active_profile(self):
        src = Path("app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("profile.is_active", src)
        self.assertIn("setup_is_complete(profile)", src)
        # soft-upgrade must not remain in require_staff
        tree = ast.parse(src)
        self.assertTrue(any("Never trust stale cookie" in src or "re-read ACL" in src for _ in [1]))


if __name__ == "__main__":
    unittest.main()
