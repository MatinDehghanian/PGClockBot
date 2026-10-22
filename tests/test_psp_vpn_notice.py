"""PSP checkout copy always reminds the customer to turn VPN off."""

from __future__ import annotations

import unittest

from app.services.payment_settlement import PSP_VPN_NOTICE, with_psp_vpn_notice


class PspVpnNoticeTests(unittest.TestCase):
    def test_appends_once_below_body(self) -> None:
        out = with_psp_vpn_notice("مبلغ قابل پرداخت: ۱۰۰۰")
        self.assertTrue(out.startswith("مبلغ قابل پرداخت: ۱۰۰۰"))
        self.assertTrue(out.endswith(PSP_VPN_NOTICE))
        self.assertIn("VPN", out)
        self.assertEqual(out.count(PSP_VPN_NOTICE), 1)

    def test_does_not_duplicate(self) -> None:
        once = with_psp_vpn_notice("متن")
        again = with_psp_vpn_notice(once)
        self.assertEqual(once, again)
        self.assertEqual(again.count(PSP_VPN_NOTICE), 1)

    def test_empty_body_is_just_notice(self) -> None:
        self.assertEqual(with_psp_vpn_notice(""), PSP_VPN_NOTICE)


if __name__ == "__main__":
    unittest.main()
