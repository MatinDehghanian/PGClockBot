"""Plans page button polish + naming block spacing (2.8.3)."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PlansPageActionsTests(unittest.TestCase):
    def test_title_actions_same_primary_style(self):
        html = (ROOT / "app/web/templates/plans.html").read_text(encoding="utf-8")
        head = html.split("{% block content %}", 1)[1].split("{% if pg_error %}", 1)[0]
        add_plan_btn = head.split('data-modal-open="modal-plan-unified">افزودن پلن</button>', 1)[0].rsplit("<button", 1)[-1]
        self.assertIn('data-modal-open="modal-plan-unified">افزودن پلن</button>', head)
        # The primary "افزودن پلن" action must stay the solid/primary style —
        # only the later, unrelated "کد هدیه" (gift codes) button legitimately
        # uses btn-ghost as its secondary-action styling.
        self.assertNotIn("btn-ghost", add_plan_btn)
        # Legacy separate trial/custom/fixed buttons removed
        self.assertNotIn('data-modal-open="modal-trial"', head)
        self.assertNotIn('data-modal-open="modal-custom"', head)
        self.assertNotIn('data-modal-open="modal-plan-create"', head)

    def test_empty_state_mentions_fixed_plan(self):
        html = (ROOT / "app/web/templates/plans.html").read_text(encoding="utf-8")
        self.assertIn("پلن ثابت", html)
        self.assertIn("از «افزودن پلن»", html)


class PlanNamingSpacingTests(unittest.TestCase):
    def test_title_not_stuck_to_border(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        block = css.split(".plan-naming-block {", 1)[1].split("}", 1)[0]
        self.assertIn("padding-top: var(--space-3)", block)
        self.assertIn("border-top:", block)
        self.assertIn(
            ".plan-naming-block .plan-naming-title",
            css,
        )
        self.assertIn(
            ".ui-modal-panel .plan-naming-block .plan-naming-title",
            css,
        )


if __name__ == "__main__":
    unittest.main()
