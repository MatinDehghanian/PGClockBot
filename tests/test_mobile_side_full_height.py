"""Mobile sidebar must reach the viewport bottom (no black body strip)."""
from __future__ import annotations
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class MobileSideFullHeightTests(unittest.TestCase):
    def test_side_uses_bottom_zero(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("bottom: 0", side)
        self.assertIn("height: auto", side)
        self.assertNotIn("100dvh - var(--topbar-h)", side)

    def test_users_mobile_hides_secondary_cols(self):
        users = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
        # id / telegram / wallet stay hidden on mobile — they're secondary lookups.
        self.assertIn('col-id col-hide-sm', users)
        self.assertIn('col-tg col-hide-sm', users)
        self.assertIn('col-wallet col-hide-sm', users)
        # The service cell (switcher + live volume/expiry + alert dot) is the
        # thing users actually need on mobile, so it now stays visible on all
        # breakpoints instead of collapsing into a static, non-interactive
        # text summary under the name.
        self.assertNotIn('col-svc col-hide-sm', users)
        self.assertIn("users-svc-cell", users)

if __name__ == "__main__":
    unittest.main()
