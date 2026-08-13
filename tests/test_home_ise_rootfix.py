"""Regression tests for dashboard Internal Server Error root causes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from jinja2 import DictLoader, Environment


class SessionRollbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_rollback_quiet_calls_session(self):
        from app.services.db_safe import rollback_quiet

        session = AsyncMock()
        await rollback_quiet(session)
        session.rollback.assert_awaited_once()

    async def test_rollback_quiet_none(self):
        from app.services.db_safe import rollback_quiet

        await rollback_quiet(None)


class HomeOverviewFailSoftTests(unittest.IsolatedAsyncioTestCase):
    async def test_gather_exception_returns_complete_shell(self):
        from app.services.home_overview import build_home_overview, empty_home_overview

        session = AsyncMock()
        with (
            patch(
                "app.services.home_overview.host_metrics",
                side_effect=RuntimeError("metrics boom"),
            ),
            patch(
                "app.services.home_overview.check_bot_connection",
                new_callable=AsyncMock,
                side_effect=RuntimeError("bot boom"),
            ),
            patch(
                "app.services.home_overview.bot_panel_summary",
                new_callable=AsyncMock,
                side_effect=RuntimeError("db boom"),
            ),
            patch(
                "app.services.home_overview.pg_home_bundle",
                new_callable=AsyncMock,
                side_effect=RuntimeError("pg boom"),
            ),
            patch(
                "app.services.home_overview.current_setup_values",
                return_value={"BOT_TOKEN": "1:x"},
            ),
        ):
            overview = await build_home_overview(session)

        shell = empty_home_overview()
        for key in shell:
            self.assertIn(key, overview)
            self.assertIsInstance(overview[key], dict)
        self.assertIn("cpu_percent", overview["host"])
        self.assertIn("users", overview["bot_summary"])
        self.assertIn("nodes", overview["nodes"])


class HomeTemplateGaugeTests(unittest.TestCase):
    def test_missing_cpu_percent_does_not_raise(self):
        tpl = (
            "{% set host = ov.host %}"
            "{% if host.cpu_percent is number %}"
            "{{ '%.0f'|format(host.cpu_percent) }}٪"
            "{% else %}—{% endif %}"
        )
        env = Environment(loader=DictLoader({"t": tpl}))
        # Incomplete host used to 500 via is not none + format(Undefined).
        html = env.get_template("t").render(ov={"host": {}})
        self.assertEqual(html, "—")

    def test_home_html_uses_number_test(self):
        src = Path("app/web/templates/home.html").read_text(encoding="utf-8")
        self.assertIn("host.cpu_percent is number", src)
        self.assertIn("host.memory_percent is number", src)
        self.assertNotIn("host.cpu_percent is not none", src)


class WebAdminCorruptFileTests(unittest.TestCase):
    def test_corrupt_json_does_not_raise(self):
        from app.services import web_auth

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "web_admin.json"
            path.write_text("{not-json", encoding="utf-8")
            with patch.object(web_auth, "AUTH_FILE", path), patch.object(
                web_auth, "DATA_DIR", Path(tmp)
            ):
                creds = web_auth.load_web_admin()
                self.assertEqual(creds.get("password"), "")
                self.assertEqual(web_auth.admin_session_version(), "")


class SafeHelpersRollbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_funnel_rolls_back(self):
        from app.api import home_pages

        session = AsyncMock()
        with patch(
            "app.services.ux20.funnel_summary",
            new_callable=AsyncMock,
            side_effect=RuntimeError("missing table"),
        ):
            out = await home_pages._safe_funnel(session, reseller_id=None)
        self.assertEqual(out["shop_open"], 0)
        session.rollback.assert_awaited()

    async def test_finance_behavior_uses_safe_funnel(self):
        src = Path("app/api/finance_pages.py").read_text(encoding="utf-8")
        self.assertIn("_safe_funnel", src)
        self.assertNotIn(
            "ctx[\"funnel\"] = await funnel_summary",
            src,
        )
        self.assertIn("rollback_quiet", src)
        self.assertIn("list_open_delivery_failures", src)

    async def test_funnel_page_uses_shared_panel(self):
        page = Path("app/web/templates/funnel.html").read_text(encoding="utf-8")
        self.assertIn('_funnel_panel.html', page)
        self.assertNotIn("رها می‌کنند", page)

    async def test_pg_quota_gauge_uses_number_test(self):
        src = Path("app/web/templates/_pg_quota_gauges.html").read_text(encoding="utf-8")
        self.assertIn("remain_pct is number", src)
        self.assertNotIn("remain_pct is not none", src)


class RecoverSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_recover_heals_pending_rollback(self):
        from sqlalchemy.exc import PendingRollbackError

        from app.services.db_safe import recover_session

        session = AsyncMock()
        session.connection = AsyncMock(side_effect=PendingRollbackError())
        session.rollback = AsyncMock()
        await recover_session(session)
        session.rollback.assert_awaited()


class EnrichAdminFailClosedTests(unittest.IsolatedAsyncioTestCase):
    async def test_probe_exception_keeps_admin_session(self):
        from app.services.pg_access import enrich_platform_admin_staff

        with patch(
            "app.services.pg_access.resolve_platform_pg_capabilities",
            new_callable=AsyncMock,
            side_effect=RuntimeError("pg timeout"),
        ):
            out = await enrich_platform_admin_staff({"role": "admin", "username": "owner"})
        self.assertEqual(out.get("role"), "admin")
        self.assertFalse(out.get("pg_capabilities_ok"))
        self.assertEqual(out.get("pg_permissions") or [], [])


if __name__ == "__main__":
    unittest.main()
