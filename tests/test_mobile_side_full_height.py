"""Mobile sidebar height matches the v8.5.3 calc (no bottom:0 stretch)."""
from __future__ import annotations
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

class MobileSideFullHeightTests(unittest.TestCase):
    def test_side_uses_dvh_calc_not_bottom_zero(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        side = mobile.split(".side {", 1)[1].split(".side.open", 1)[0]
        self.assertIn("100dvh - var(--topbar-h)", side)
        self.assertNotIn("bottom: 0", side)

    def test_users_mobile_hides_secondary_cols(self):
        users = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
        self.assertIn('col-id col-hide-sm', users)
        self.assertIn('col-tg col-hide-sm', users)
        self.assertIn('col-wallet col-hide-sm', users)
        self.assertNotIn('col-svc col-hide-sm', users)
        self.assertNotIn('col-vol col-hide-sm', users)
        self.assertNotIn('col-exp col-hide-sm', users)
        self.assertIn("users-svc-select", users)

if __name__ == "__main__":
    unittest.main()
