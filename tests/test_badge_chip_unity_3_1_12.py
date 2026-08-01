"""Unified delicate chip tags (3.1.12)."""

from __future__ import annotations

import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")


class BadgeChipUnityTests(unittest.TestCase):
    def test_badge_ver_role_share_compact_base(self):
        css = CSS.read_text(encoding="utf-8")
        base = css.split("/* Unified chip tags", 1)[1].split(".badge {", 1)[0]
        self.assertIn(".badge,\n.role-tag {", css)
        self.assertIn("min-height: 20px;", base)
        self.assertIn("padding: 0 var(--space-1);", base)
        self.assertIn("font-weight: 500;", base)
        # spacing audit had fat equal padding — must not return
        fat = css.split(".badge {\n", 1)
        if len(fat) > 1:
            block = fat[1].split("}", 1)[0]
            self.assertNotIn("padding: var(--space-1);", block)


if __name__ == "__main__":
    unittest.main()
