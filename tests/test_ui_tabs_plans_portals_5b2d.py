"""UI polish: tabs ghost gap, plans head actions, ticket status full width."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class SectionTabsNoTransformTests(unittest.TestCase):
    def test_tabs_do_not_translate_or_scale(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        # Isolate the base .section-tabs control block (before settings modal)
        block = css.split(".section-tabs a,\n.section-tabs .tab-btn {", 1)[1]
        block = block.split(".settings-modal-panel {", 1)[0]
        self.assertNotIn("transform:", block)
        self.assertNotIn("translateY(-1px)", block)
        self.assertNotIn("scale(0.96)", block)


class PlansHeadActionsMobileTests(unittest.TestCase):
    def test_no_inline_flex_override(self):
        html = (ROOT / "app/web/templates/plans.html").read_text(encoding="utf-8")
        head = html.split("page-head-actions", 1)[1].split("</div>", 1)[0]
        self.assertNotIn("style=", head)
        self.assertIn("کد هدیه", head)
        self.assertIn("افزودن پلن", head)

    def test_mobile_grid_keeps_two_cols(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(
            ".page-head > .page-head-actions {\n    display: grid;\n    grid-template-columns: repeat(2, minmax(0, 1fr));",
            css,
        )


class TicketStatusFullWidthTests(unittest.TestCase):
    def test_mobile_status_select_full_width(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".ticket-status-form .form-field", css)
        self.assertIn(".ticket-status-form .ui-select-toggle", css)
        chunk = css[css.find(".ticket-status-form .ui-select-toggle") :][:120]
        self.assertIn("width: 100%", chunk)


if __name__ == "__main__":
    unittest.main()
