"""PasarGuard panel spacing aligned with bot panel (3.1.4)."""

from __future__ import annotations

import unittest
from pathlib import Path


CSS = Path("app/web/static/panel.css")


class PgSpacingAlignTests(unittest.TestCase):
    def test_title_to_tabs_is_tight(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(".page-head:has(+ .section-tabs)", css)
        self.assertIn(".page-head:has(+ .settings-tabs)", css)
        block = css.split(".page-head:has(+ .section-tabs)", 1)[1].split("}", 1)[0]
        self.assertIn("margin-bottom: var(--space-2)", block)

    def test_pg_list_pages_use_flush_cards(self):
        pages = [
            "app/web/templates/pg_users.html",
            "app/web/templates/pg_nodes.html",
            "app/web/templates/pg_admins.html",
            "app/web/templates/pg_hosts.html",
            "app/web/templates/pg_templates.html",
            "app/web/templates/pg_groups.html",
            "app/web/templates/pg_inbounds.html",
            "app/web/templates/pg_home.html",
        ]
        for path in pages:
            src = Path(path).read_text(encoding="utf-8")
            self.assertIn("card-flush", src, msg=path)


if __name__ == "__main__":
    unittest.main()
