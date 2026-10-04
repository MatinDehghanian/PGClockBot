"""Premium / custom emoji on message-body settings + button icons."""

from __future__ import annotations

import unittest

from aiogram.types import MessageEntity

from app.services.rich_text import (
    MESSAGE_RICH_KEYS,
    TERMS_RICH_KEYS,
    button_icon_custom_emoji_id,
    is_button_label_key,
    is_message_rich_key,
    outbound_setting_text,
    pack_rich_text,
    pack_setting_from_message,
    rich_plain_text,
    unpack_rich_text,
)


class MessageRichKeysTests(unittest.TestCase):
    def test_covers_user_facing_bodies(self):
        required = {
            "welcome_text",
            "guide_text",
            "faq_text",
            "support_text",
            "referral_text",
            "force_join_msg",
            "purchase_success_text",
            "wallet_success_text",
            "payment_reject_text",
            "card_pay_text",
            "qr_caption",
            "shop_maintenance_text",
            "admin_daily_report_template",
        }
        self.assertTrue(required <= MESSAGE_RICH_KEYS)
        self.assertTrue(TERMS_RICH_KEYS <= MESSAGE_RICH_KEYS)

    def test_button_labels_not_message_rich(self):
        # btn_* are not MESSAGE_RICH_KEYS — they use icon_custom_emoji_id instead.
        self.assertFalse(is_message_rich_key("btn_buy"))
        self.assertFalse(is_message_rich_key("btn_menu_home"))
        self.assertTrue(is_button_label_key("btn_buy"))
        self.assertTrue(is_button_label_key("btn_menu_home"))


class OutboundSettingTextTests(unittest.TestCase):
    def test_plain_uses_format_message_card(self):
        text, kw = outbound_setting_text("سلام", title="عنوان")
        self.assertIn("عنوان", text)
        self.assertIn("سلام", text)
        self.assertEqual(kw, {})

    def test_packed_custom_emoji_returns_entities(self):
        # "Hi😀" with custom emoji on the emoji (UTF-16 length 2)
        body = "Hi😀"
        ent = MessageEntity(
            type="custom_emoji", offset=2, length=2, custom_emoji_id="99"
        )
        packed = pack_rich_text(body, [ent])
        text, kw = outbound_setting_text(packed, title="T")
        self.assertTrue(text.startswith("T\n"))
        self.assertIn("entities", kw)
        self.assertEqual(kw.get("parse_mode"), None)
        self.assertEqual(kw["entities"][0].custom_emoji_id, "99")
        # Title prefix shifts entity offsets
        self.assertGreater(kw["entities"][0].offset, 2)

    def test_pack_setting_from_message_message_and_button_keys(self):
        class Msg:
            text = "x😀"
            entities = [
                MessageEntity(
                    type="custom_emoji", offset=1, length=2, custom_emoji_id="1"
                )
            ]

        packed = pack_setting_from_message("welcome_text", Msg())
        plain, ents = unpack_rich_text(packed)
        self.assertEqual(plain, "x😀")
        self.assertTrue(ents)
        packed_btn = pack_setting_from_message("btn_buy", Msg())
        self.assertTrue(packed_btn.startswith("\x1eRICH1:"))
        self.assertEqual(rich_plain_text(packed_btn), "x😀")
        self.assertEqual(button_icon_custom_emoji_id(packed_btn), "1")


if __name__ == "__main__":
    unittest.main()
