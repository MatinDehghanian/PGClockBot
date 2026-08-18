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

    def test_page_head_actions_hug_label_width(self):
        """Opposite-title buttons size like «افزودن نماینده» — not stretched grid cells."""
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 900px)", 1)[1]
        block = mobile.split(".page-head > .page-head-actions {", 1)[1].split("}", 1)[0]
        self.assertIn("display: flex", block)
        self.assertNotIn("display: grid", block)
        self.assertNotIn("minmax(0, 1fr)", block)
        self.assertIn("padding-inline: var(--space-2)", css)
        # Direct page-head btn and wrapped actions share content width
        self.assertIn(".page-head > .page-head-actions > .btn", css)
        hug = css.split(".page-head > .page-head-actions > .btn", 1)[1][:280]
        self.assertIn("width: auto", hug)


class TicketStatusFullWidthTests(unittest.TestCase):
    def test_mobile_status_select_full_width(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".ticket-status-form .form-field", css)
        self.assertIn(".ticket-status-form .ui-select-toggle", css)
        chunk = css[css.find(".ticket-status-form .ui-select-toggle") :][:120]
        self.assertIn("width: 100%", chunk)


class PlanStatusTagsLayoutTests(unittest.TestCase):
    def test_status_tags_wrap_with_gap(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        after = css.split(".status-tags {", 1)[1]
        block = after.split("}", 1)[0]
        self.assertIn("display: flex", block)
        self.assertIn("flex-wrap: wrap", block)
        self.assertIn("gap: var(--space-1)", block)
        self.assertIn("flex-wrap: nowrap", after[:900])

    def test_plan_status_column_uses_status_tags(self):
        html = (ROOT / "app/web/templates/plans.html").read_text(encoding="utf-8")
        self.assertIn('class="status-tags"', html)
        self.assertNotIn("<div><small class=\"badge warn\"", html)
        self.assertGreaterEqual(html.count("خارج از سقف"), 3)


if __name__ == "__main__":
    unittest.main()
