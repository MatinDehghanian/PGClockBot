"""PSP callback base prefers clean https (no :9000) for Paystar returns."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import public_https as pub


class HttpsPublicBasePspTests(unittest.TestCase):
    def test_strips_nondefault_port(self) -> None:
        self.assertEqual(
            pub.strip_https_nondefault_port("https://bot.example.com:9000"),
            "https://bot.example.com",
        )
        self.assertEqual(
            pub.strip_https_nondefault_port("https://bot.example.com"),
            "https://bot.example.com",
        )

    def test_prefers_clean_env_over_live_with_port(self) -> None:
        with (
            patch.object(pub, "https_is_active", return_value=True),
            patch.object(
                pub, "public_panel_base_url", return_value="https://bot.example.com:9000"
            ),
            patch.object(pub, "env_public_base", return_value="https://bot.example.com"),
        ):
            self.assertEqual(pub.https_public_base(), "https://bot.example.com")

    def test_strips_live_port_when_env_is_http_only(self) -> None:
        with (
            patch.object(pub, "https_is_active", return_value=True),
            patch.object(
                pub, "public_panel_base_url", return_value="https://bot.example.com:9000"
            ),
            patch.object(pub, "env_public_base", return_value="http://203.0.113.5:9000"),
        ):
            self.assertEqual(pub.https_public_base(), "https://bot.example.com")

    def test_clean_live_still_wins_over_http_env(self) -> None:
        with (
            patch.object(pub, "https_is_active", return_value=True),
            patch.object(
                pub, "public_panel_base_url", return_value="https://panel.live.example"
            ),
            patch.object(pub, "env_public_base", return_value="http://203.0.113.5:9000"),
        ):
            self.assertEqual(pub.https_public_base(), "https://panel.live.example")

    def test_empty_when_no_https(self) -> None:
        with (
            patch.object(pub, "https_is_active", return_value=False),
            patch.object(pub, "env_public_base", return_value="http://203.0.113.5:9000"),
        ):
            self.assertEqual(pub.https_public_base(), "")


if __name__ == "__main__":
    unittest.main()
