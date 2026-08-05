"""PAYG linked to shop wallet + suspend list badge (v4.2.9)."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.billing import BILLING_MODE_PAYG


class PaygWalletLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_link_merges_wallet_and_billing(self):
        from app.services.billing import ensure_payg_shop_wallet

        profile = MagicMock()
        profile.user_id = 5
        profile.billing_balance = -379
        profile.payg_wallet_linked = False

        user = MagicMock()
        user.id = 5
        user.wallet_balance = 9000

        session = AsyncMock()
        session.get = AsyncMock(return_value=user)

        out_user, bal = await ensure_payg_shop_wallet(session, profile)
        self.assertEqual(bal, 8621)
        self.assertEqual(user.wallet_balance, 8621)
        self.assertEqual(profile.billing_balance, 8621)
        self.assertTrue(profile.payg_wallet_linked)
        self.assertIs(out_user, user)

    async def test_linked_mirrors_wallet_only(self):
        from app.services.billing import ensure_payg_shop_wallet

        profile = MagicMock()
        profile.user_id = 5
        profile.billing_balance = 100
        profile.payg_wallet_linked = True

        user = MagicMock()
        user.id = 5
        user.wallet_balance = 5000

        session = AsyncMock()
        session.get = AsyncMock(return_value=user)

        _u, bal = await ensure_payg_shop_wallet(session, profile)
        self.assertEqual(bal, 5000)
        self.assertEqual(profile.billing_balance, 5000)
        self.assertEqual(user.wallet_balance, 5000)


class SuspendListBadgeTests(unittest.TestCase):
    def test_resellers_list_shows_suspended_badge(self):
        src = Path("app/web/templates/resellers.html").read_text(encoding="utf-8")
        self.assertIn("billing_suspended_at", src)
        self.assertIn("مسدود", src)
        self.assertIn("فعال", src)

    def test_edit_shows_wallet_as_payg_source(self):
        src = Path("app/web/templates/reseller_edit.html").read_text(encoding="utf-8")
        self.assertIn("wallet_balance", src)
        self.assertIn("منبع PAYG", src)


class SchemaLinkFlagTests(unittest.TestCase):
    def test_model_and_migrate(self):
        from app.db.models import ResellerProfile

        self.assertTrue(hasattr(ResellerProfile, "payg_wallet_linked"))
        session_src = Path("app/db/session.py").read_text(encoding="utf-8")
        self.assertIn("payg_wallet_linked", session_src)
        alem = Path("alembic/versions/0006_payg_wallet_linked.py").read_text(encoding="utf-8")
        self.assertIn("payg_wallet_linked", alem)


if __name__ == "__main__":
    unittest.main()
