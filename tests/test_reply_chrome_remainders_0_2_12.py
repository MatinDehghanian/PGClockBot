"""Remaining dual-keyboard paths must re-attach lasting reply chrome after inline."""

from __future__ import annotations

import inspect
import unittest


def _last(src: str, needle: str) -> int:
    return src.rindex(needle)


class RemainderChromeSourceGuards(unittest.TestCase):
    def test_loyalty_referral_reattaches(self):
        from app.bot.handlers import loyalty

        src = inspect.getsource(loyalty.open_loyalty_referral_message)
        self.assertIn("attach_reply_keyboard", src)
        self.assertIn("loyalty_reply_keyboard", src)
        self.assertLess(
            src.index("_ref_actions_keyboard"),
            _last(src, "attach_reply_keyboard"),
        )

    def test_loyalty_points_reattaches(self):
        from app.bot.handlers import loyalty

        src = inspect.getsource(loyalty.open_loyalty_points_message)
        self.assertIn("attach_reply_keyboard", src)
        self.assertLess(
            src.index("_points_extras_keyboard"),
            _last(src, "attach_reply_keyboard"),
        )

    def test_loyalty_rewards_reattaches_when_inline(self):
        from app.bot.handlers import loyalty

        src = inspect.getsource(loyalty.open_loyalty_rewards_message)
        self.assertIn("attach_reply_keyboard", src)
        self.assertIn("_rewards_redeem_keyboard", src)
        self.assertLess(
            src.index("_rewards_redeem_keyboard"),
            _last(src, "attach_reply_keyboard"),
        )

    def test_admin_resellers_hub_reattaches_after_mini(self):
        from app.bot.handlers import reply_nav

        src = inspect.getsource(reply_nav.open_admin_resellers_hub)
        self.assertIn("attach_reply_keyboard", src)
        self.assertIn("admin_resellers_reply_keyboard", src)
        self.assertLess(
            src.index("miniapp_inline_keyboard"),
            _last(src, "attach_reply_keyboard"),
        )

    def test_admin_backup_hub_reattaches_after_files(self):
        from app.bot.handlers import reply_nav

        src = inspect.getsource(reply_nav.open_admin_backup_hub)
        self.assertIn("attach_reply_keyboard", src)
        self.assertIn("admin_backup_reply_keyboard", src)
        self.assertLess(
            src.index("backup_files_keyboard"),
            _last(src, "attach_reply_keyboard"),
        )

    def test_support_callback_home_reattaches_after_contacts(self):
        from app.bot.handlers import support

        src = inspect.getsource(support.support_home)
        self.assertIn("attach_reply_keyboard", src)
        self.assertIn("support_reply_keyboard", src)
        self.assertLess(src.index("ارتباط مستقیم"), _last(src, "attach_reply_keyboard"))


if __name__ == "__main__":
    unittest.main()
