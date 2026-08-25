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
        # Service / volume / expiry are the columns users actually need, so
        # they stay visible (and separate) on every breakpoint instead of
        # hiding or collapsing into a static text summary — the table simply
        # scrolls horizontally on narrow phones if it must, same as any
        # other data table in the panel.
        self.assertNotIn('col-svc col-hide-sm', users)
        self.assertNotIn('col-vol col-hide-sm', users)
        self.assertNotIn('col-exp col-hide-sm', users)
        self.assertIn("users-svc-select", users)

if __name__ == "__main__":
    unittest.main()
