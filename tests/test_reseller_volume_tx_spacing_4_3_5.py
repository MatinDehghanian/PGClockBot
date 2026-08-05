"""v4.3.5 — reseller volume cell + wallet tx title spacing."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ResellerVolumeCellTests(unittest.TestCase):
    def test_quota_nowrap_markup(self):
        html = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")
        self.assertIn("reseller-quota-line", html)
        self.assertIn("reseller-quota-cell", html)
        self.assertIn('class="col-hide-sm">نقش</th>', html.replace("\n", ""))
        # role cell also hidden on small screens
        self.assertIn('td class="col-hide-sm"', html)

    def test_quota_css_nowrap(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".reseller-quota-line", css)
        block = css.split(".reseller-quota-line")[1].split("}")[0]
        self.assertIn("white-space: nowrap", block)
        self.assertIn("min-width: 7.5rem", css)


class WalletTxSpacingTests(unittest.TestCase):
    def test_wallet_tx_block_gap(self):
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        block = css.split(".wallet-tx-block {")[1].split("}")[0]
        self.assertIn("gap: var(--space-3)", block)

    def test_templates_use_block(self):
        for rel in (
            "app/web/templates/_reseller_edit_body.html",
            "app/web/templates/_user_edit_body.html",
        ):
            src = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("wallet-tx-block", src)


class VersionTests(unittest.TestCase):
    def test_version(self):
        from app.version import __version__

        self.assertEqual(__version__, "4.3.5")


if __name__ == "__main__":
    unittest.main()
