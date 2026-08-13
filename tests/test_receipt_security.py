"""Security checks for finance receipt proxy scoping."""

from __future__ import annotations

import unittest

from app.api.finance_pages import _safe_telegram_file_path


class ReceiptPathSafetyTests(unittest.TestCase):
    def test_accepts_normal_telegram_paths(self):
        self.assertEqual(
            _safe_telegram_file_path("photos/file_123.jpg"),
            "photos/file_123.jpg",
        )
        self.assertEqual(
            _safe_telegram_file_path("/photos/file_123.jpg"),
            "photos/file_123.jpg",
        )

    def test_rejects_traversal_and_schemes(self):
        self.assertIsNone(_safe_telegram_file_path("../etc/passwd"))
        self.assertIsNone(_safe_telegram_file_path("photos/../../etc/passwd"))
        self.assertIsNone(_safe_telegram_file_path("https://evil.example/a.jpg"))
        self.assertIsNone(_safe_telegram_file_path("file:foo"))
        self.assertIsNone(_safe_telegram_file_path("photos\\file.jpg"))
        self.assertIsNone(_safe_telegram_file_path("photos/file.jpg?x=1"))
        self.assertIsNone(_safe_telegram_file_path(""))
        self.assertIsNone(_safe_telegram_file_path(None))


class ReceiptSourceGuardsTests(unittest.TestCase):
    def test_receipt_route_has_tenant_guards(self):
        src = open("app/api/finance_pages.py", encoding="utf-8").read()
        self.assertIn("_authorize_receipt_access", src)
        self.assertIn("payer_reseller_id", src)
        self.assertIn('startswith("image/")', src)
        self.assertIn("no-store", src)
        # Must not fall back from reseller token to platform token.
        token_fn = src.split("async def _payment_bot_token", 1)[1].split(
            "async def _safe_telegram_file_path", 1
        )[0]
        self.assertNotIn("or platform", token_fn.lower())
        # Platform payments list excludes reseller tenants.
        self.assertIn("BotUser.reseller_id.is_(None)", src)


if __name__ == "__main__":
    unittest.main()
