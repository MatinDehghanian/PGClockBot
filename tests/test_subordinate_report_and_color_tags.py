"""Subordinate digests + staff color tags — security and formatting guards."""

from __future__ import annotations

import unittest

from app.services.color_tags import (
    FILTER_NONE,
    VALID_COLOR_KEYS,
    apply_color_tag,
    color_tag_meta,
    normalize_color_filter,
    normalize_color_tag,
)
from app.services.subordinate_report import (
    SubordinateShop,
    SubordinateStats,
    format_subordinate_report,
    list_direct_subordinate_shops,
)
from app.services.users_ops import users_list_href


class ColorTagTests(unittest.TestCase):
    def test_palette_is_fixed_and_short(self):
        self.assertGreaterEqual(len(VALID_COLOR_KEYS), 5)
        self.assertLessEqual(len(VALID_COLOR_KEYS), 10)
        for key in VALID_COLOR_KEYS:
            self.assertLessEqual(len(key), 16)

    def test_normalize_rejects_freeform(self):
        self.assertIsNone(normalize_color_tag("#ff0000"))
        self.assertIsNone(normalize_color_tag("javascript:alert(1)"))
        self.assertEqual(normalize_color_tag("RED"), "red")
        self.assertIsNone(normalize_color_tag("none"))

    def test_filter_tokens(self):
        self.assertEqual(normalize_color_filter("_none"), FILTER_NONE)
        self.assertEqual(normalize_color_filter("blue"), "blue")
        self.assertIsNone(normalize_color_filter("all"))
        self.assertIsNone(normalize_color_filter("nope"))

    def test_apply_color_tag(self):
        class U:
            color_tag = None

        u = U()
        self.assertEqual(apply_color_tag(u, "green"), "green")
        self.assertEqual(u.color_tag, "green")
        self.assertIsNone(apply_color_tag(u, ""))
        self.assertIsNone(u.color_tag)

    def test_meta_and_href(self):
        meta = color_tag_meta("orange")
        self.assertIsNotNone(meta)
        self.assertTrue(meta.hex.startswith("#"))
        href = users_list_href(filter_key="alerts", color="red", q="ali")
        self.assertIn("filter=alerts", href)
        self.assertIn("color=red", href)
        self.assertIn("q=ali", href)


class SubordinateReportFormatTests(unittest.TestCase):
    def test_format_escapes_names(self):
        shop = SubordinateShop(
            principal_id=1,
            reseller_profile_id=2,
            reseller_user_id=3,
            display_name='<script>x</script>',
            is_active=True,
        )
        rows = [
            SubordinateStats(
                shop=shop,
                users_new=1,
                users_total=10,
                orders_new=2,
                orders_delivered=1,
                revenue_today=5000,
                services_total=3,
                traffic_text="1/10 GB",
            )
        ]
        text = format_subordinate_report(rows)
        self.assertIn("&lt;script&gt;", text)
        self.assertNotIn("<script>", text)
        self.assertIn("کاربران جدید: 1", text)
        self.assertIn("حجم:", text)

    def test_empty_children_message(self):
        text = format_subordinate_report([])
        self.assertIn("زیرمجموعه‌ای", text)


class SubordinateScopeUnitTests(unittest.IsolatedAsyncioTestCase):
    async def test_l2_parent_returns_empty(self):
        from unittest.mock import AsyncMock, MagicMock

        from app.services.org_principals import DEPTH_TWO, STATUS_ACTIVE

        parent = MagicMock()
        parent.id = 9
        parent.depth = DEPTH_TWO
        parent.status = STATUS_ACTIVE
        parent.parent_id = 1
        session = AsyncMock()
        out = await list_direct_subordinate_shops(session, parent=parent)
        self.assertEqual(out, [])
        session.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
