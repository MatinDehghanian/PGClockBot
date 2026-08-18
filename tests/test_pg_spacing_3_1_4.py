"""PasarGuard list pages use flush cards (3.1.4); title gaps unified in 3.1.8."""

from __future__ import annotations

import unittest
from pathlib import Path


class PgSpacingAlignTests(unittest.TestCase):
    def test_pg_list_pages_use_flush_cards(self):
        pages = [
            "app/web/templates/pg_users.html",
            "app/web/templates/pg_nodes.html",
            "app/web/templates/pg_admins.html",
            "app/web/templates/pg_hosts.html",
            "app/web/templates/pg_templates.html",
            "app/web/templates/pg_groups.html",
            "app/web/templates/pg_inbounds.html",
        ]
        for path in pages:
            src = Path(path).read_text(encoding="utf-8")
            self.assertIn("card-flush", src, msg=path)
        home = Path("app/web/templates/pg_home.html").read_text(encoding="utf-8")
        self.assertIn('class="page-head"', home)
        self.assertNotIn("pg_tabs(", home)


if __name__ == "__main__":
    unittest.main()
