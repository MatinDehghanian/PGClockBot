"""Contract tests for safe panel speed work (timing, shell-first, display timeouts)."""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]


class PanelTimingTests(unittest.TestCase):
    def test_should_time_home_and_pg(self):
        from app.services.panel_timing import should_time

        self.assertTrue(should_time("/home"))
        self.assertTrue(should_time("/home/body"))
        self.assertTrue(should_time("/pg"))
        self.assertTrue(should_time("/pg/users"))
        self.assertFalse(should_time("/static/panel.js"))
        self.assertFalse(should_time("/login"))

    def test_mark_computes_auth_and_page(self):
        from app.services.panel_timing import begin, finish_log, mark, server_timing_header

        req = MagicMock()
        req.url.path = "/home"
        req.state = MagicMock()
        begin(req)
        mark(req, "handler")
        mark(req, "page_data")
        snap = finish_log(req, status_code=200)
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertIn("total_ms", snap)
        self.assertIn("auth_ms", snap)
        self.assertIn("page_ms", snap)
        hdr = server_timing_header(snap)
        self.assertIsNotNone(hdr)
        assert hdr is not None
        self.assertIn("total;dur=", hdr)


class PanelDisplayTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_returns_fallback_not_raise(self):
        from app.services.panel_display_timeout import display_await

        async def slow():
            await asyncio.sleep(5)
            return "done"

        out = await display_await(slow(), fallback={"unchecked": True}, label="t")
        self.assertEqual(out, {"unchecked": True})

    async def test_success_passes_through(self):
        from app.services.panel_display_timeout import display_await

        async def ok():
            return {"ok": True}

        out = await display_await(ok(), fallback={"unchecked": True}, label="t")
        self.assertEqual(out, {"ok": True})


class PanelShellFirstContractTests(unittest.TestCase):
    def test_home_body_uses_require_staff(self):
        src = (ROOT / "app/api/home_pages.py").read_text(encoding="utf-8")
        self.assertIn('@app.get("/home/body"', src)
        # Body route must re-run require_staff (not inherit shell auth).
        body = src[src.find("async def home_dashboard_body") : src.find("def _degraded_home_shell")]
        self.assertIn("Depends(require_staff)", body)

    def test_home_shell_after_require_staff(self):
        src = (ROOT / "app/api/home_pages.py").read_text(encoding="utf-8")
        home = src[src.find("async def home_dashboard") : src.find("async def home_dashboard_body")]
        # Depends must appear before fast shell work.
        self.assertLess(home.find("Depends(require_staff)"), home.find("_fast_home_shell"))
        self.assertIn("_wants_full_widgets", home)

    def test_no_panel_navigate(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertNotIn("panelNavigate", js)
        defer = (ROOT / "app/web/templates/_panel_widgets_defer.html").read_text(encoding="utf-8")
        self.assertNotIn("panelNavigate", defer)
        self.assertIn("redirect: 'manual'", defer)

    def test_templates_include_defer_and_body_partials(self):
        home = (ROOT / "app/web/templates/home.html").read_text(encoding="utf-8")
        self.assertIn("_home_dash_body.html", home)
        self.assertIn("widgets_deferred", home)
        self.assertIn("_panel_widgets_loading.html", home)
        self.assertIn('id="home-dash"', home)
        # Fetch starts before loading placeholder so body overlaps parse.
        self.assertLess(
            home.find("_panel_widgets_defer.html"),
            home.find('id="home-dash"'),
        )
        self.assertLess(
            home.find("_panel_widgets_defer.html"),
            home.find("_home_dash_body.html"),
        )
        reseller = (ROOT / "app/web/templates/reseller_home.html").read_text(encoding="utf-8")
        self.assertIn("_reseller_home_dash_body.html", reseller)
        self.assertIn("_panel_widgets_loading.html", reseller)
        self.assertLess(
            reseller.find("_panel_widgets_defer.html"),
            reseller.find("_reseller_home_dash_body.html"),
        )
        body = (ROOT / "app/web/templates/_home_dash_body.html").read_text(encoding="utf-8")
        self.assertIn('id="home-dash"', body)

    def test_home_body_skips_sidebar_unread(self):
        from app.services.panel_tickets import should_skip_unread_count

        self.assertTrue(should_skip_unread_count("/home/body", "GET"))
        self.assertFalse(should_skip_unread_count("/home", "GET"))

    def test_pg_keeps_require_pg_perm_and_display_timeout(self):
        src = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        pg = src[src.find("async def pg_home") : src.find("async def pg_home_body")]
        self.assertIn('Depends(require_pg_perm("pg_overview"))', pg)
        self.assertIn("_pg_chrome_context", src)
        self.assertIn("_pg_display_widgets", src)
        self.assertIn('"/pg/body"', src)
        self.assertIn("widgets_deferred", pg)
        # Body route re-runs same perm.
        body = src[src.find("async def pg_home_body") : src.find("async def pg_host_metrics_json")]
        self.assertIn('Depends(require_pg_perm("pg_overview"))', body)
        self.assertIn('"_pg_dash_body.html"', body)
        # No SPA nav.
        self.assertNotIn("panelNavigate", src)

    def test_pg_shell_first_templates(self):
        home = (ROOT / "app/web/templates/pg_home.html").read_text(encoding="utf-8")
        self.assertIn("widgets_deferred", home)
        self.assertIn("_pg_dash_body.html", home)
        self.assertIn("_panel_widgets_defer.html", home)
        self.assertIn("_panel_widgets_loading.html", home)
        self.assertIn("_pg_live_metrics_script.html", home)
        self.assertNotIn("در حال بارگذاری آمار پاسارگارد…", home)
        # Early fetch before loading placeholder.
        self.assertLess(
            home.find("_panel_widgets_defer.html"),
            home.find('id="pg-dash"'),
        )
        body = (ROOT / "app/web/templates/_pg_dash_body.html").read_text(encoding="utf-8")
        self.assertIn('id="pg-dash"', body)
        loading = (ROOT / "app/web/templates/_panel_widgets_loading.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("panel-widgets-loading", loading)
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".panel-widgets-loading", css)
        self.assertIn("min-height: min(52vh", css)
        defer = (ROOT / "app/web/templates/_panel_widgets_defer.html").read_text(encoding="utf-8")
        self.assertIn("panel-widgets-ready", defer)
        self.assertIn("DOMContentLoaded", defer)
        live = (ROOT / "app/web/templates/_pg_live_metrics_script.html").read_text(encoding="utf-8")
        self.assertIn("panel-widgets-ready", live)
        self.assertIn("function els()", live)

    def test_pg_body_skips_ticket_chrome(self):
        src = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        body = src[src.find("async def pg_home_body") : src.find("async def pg_host_metrics_json")]
        self.assertIn("resolve_pg_open_url", body)
        self.assertIn("_pg_display_widgets", body)
        self.assertNotIn("_pg_chrome_context", body)

    def test_pg_users_paginated(self):
        src = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        users_fn = src[src.find("async def pg_users") : src.find("async def pg_users_create")]
        self.assertIn("parse_list_page", users_fn)
        self.assertIn("DEFAULT_LIST_PAGE_SIZE", users_fn)
        self.assertIn("build_list_pager", users_fn)
        self.assertNotIn('"limit": 200', users_fn)
        self.assertIn('Depends(require_pg_perm("pg_users"))', users_fn)
        tmpl = (ROOT / "app/web/templates/pg_users.html").read_text(encoding="utf-8")
        self.assertIn("list-pager", tmpl)
        self.assertIn("pager.has_next", tmpl)
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".list-pager", css)

    def test_pg_body_skips_sidebar_unread(self):
        from app.services.panel_tickets import should_skip_unread_count

        self.assertTrue(should_skip_unread_count("/pg/body", "GET"))
        self.assertFalse(should_skip_unread_count("/pg", "GET"))

    def test_middleware_registered_observation_only(self):
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("panel_timing_middleware", src)
        self.assertIn("Observation-only timing", src)

    def test_guardrails_untouched(self):
        """Hard security surfaces must not be edited by this speed work."""
        # Spot-check: require_staff definition still present; this file is huge —
        # we only assert timing middleware does not wrap/replace require_staff.
        src = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("async def require_staff(", src)
        timing = src[src.find("panel_timing_middleware") : src.find("async def security_headers")]
        self.assertNotIn("require_staff", timing)

    def test_home_body_ops_use_isolated_parallel_sessions(self):
        src = (ROOT / "app/api/home_pages.py").read_text(encoding="utf-8")
        self.assertIn("async def _parallel_home_ops(", src)
        self.assertIn("async with SessionLocal() as s:", src)
        self.assertIn("asyncio.gather(_funnel(), _periods(), _action())", src)
        # Must not gather concurrent work on the request session.
        self.assertNotIn(
            "await asyncio.gather(\n                _safe_funnel(session",
            src,
        )

    def test_loading_mark_is_clock(self):
        loading = (ROOT / "app/web/templates/_panel_widgets_loading.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("panel-load-clock", loading)
        self.assertNotIn("panel-widgets-loading-ring", loading)
        css = (ROOT / "app/web/static/panel.css").read_text(encoding="utf-8")
        self.assertIn(".panel-load-clock-face", css)
        self.assertIn("html.page-loading .page-load-veil", css)
        # PG ACL cache stays short — speed must not stale sidebar permissions.
        acl = (ROOT / "app/services/pg_access.py").read_text(encoding="utf-8")
        self.assertIn("_ROLE_CACHE_TTL = 8.0", acl)
        self.assertIn("_PLATFORM_CAPS_TTL = 8.0", acl)


if __name__ == "__main__":
    unittest.main()
