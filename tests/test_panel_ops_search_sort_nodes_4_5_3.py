"""Panel ops: search, sort, order/payment actions, node traffic (4.5.3)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ListQueryTests(unittest.TestCase):
    def test_case_insensitive_substring(self):
        from app.services.list_query import filter_by_search, text_matches

        self.assertTrue(text_matches("AliReza", needle="ali"))
        self.assertTrue(text_matches("علی‌رضا", needle="علی"))
        self.assertTrue(text_matches("User01", needle="ER0"))
        self.assertFalse(text_matches("abc", needle="xyz"))
        rows = [{"name": "Alpha"}, {"name": "betaTest"}, {"name": "GAMMA"}]
        out = filter_by_search(rows, "eta", lambda r: (r["name"],))
        self.assertEqual([r["name"] for r in out], ["betaTest"])
        self.assertEqual(filter_by_search(rows, "", lambda r: (r["name"],)), rows)

    def test_ilike_escapes_wildcards(self):
        from app.services.list_query import ilike_pattern

        self.assertEqual(ilike_pattern("a%b_c"), r"%a\%b\_c%")


class NodeTrafficTests(unittest.TestCase):
    def test_enrich_merges_realtime_and_formats(self):
        from app.services.node_traffic import enrich_nodes_with_traffic

        nodes = [{"id": 1, "name": "n1"}, {"id": 2, "name": "n2", "upload": 100}]
        rt = {"1": {"uplink": 1024, "downlink": 2048}, "nodes": []}
        # id-keyed map path
        out = enrich_nodes_with_traffic(nodes, {"1": {"uplink": 1024, "downlink": 2048}})
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["_traffic_up"], 1024)
        self.assertEqual(out[0]["_traffic_down"], 2048)
        self.assertEqual(out[0]["_traffic_total"], 3072)
        self.assertNotEqual(out[0]["_traffic_total_text"], "—")
        self.assertEqual(out[1]["_traffic_up"], 100)

    def test_list_payload_shape(self):
        from app.services.node_traffic import enrich_nodes_with_traffic

        out = enrich_nodes_with_traffic(
            [{"id": 7, "name": "x"}],
            {"nodes": [{"node_id": 7, "upload": 10, "download": 20}]},
        )
        self.assertEqual(out[0]["_traffic_total"], 30)


class OrdersCancelServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_order_rejects_pending_payment(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.db.models import Base, BotUser, Order, OrderStatus, Payment, PaymentStatus, Role
        from app.services.orders import cancel_order

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            user = BotUser(telegram_id=111, role=Role.USER.value, username="u1", referral_code="ref111")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            order = Order(user_id=user.id, amount=1000, status=OrderStatus.PENDING.value)
            session.add(order)
            await session.commit()
            await session.refresh(order)
            pay = Payment(
                order_id=order.id,
                user_id=user.id,
                amount=1000,
                status=PaymentStatus.PENDING.value,
            )
            session.add(pay)
            await session.commit()
            await session.refresh(pay)
            await cancel_order(session, order, note="test cancel")
            await session.refresh(order)
            await session.refresh(pay)
            self.assertEqual(order.status, OrderStatus.CANCELLED.value)
            self.assertEqual(pay.status, PaymentStatus.REJECTED.value)

    async def test_cancel_blocks_delivered(self):
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.db.models import Base, BotUser, Order, OrderStatus, Role
        from app.services.orders import cancel_order

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            user = BotUser(telegram_id=222, role=Role.USER.value, referral_code="ref222")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            order = Order(user_id=user.id, amount=1, status=OrderStatus.DELIVERED.value)
            session.add(order)
            await session.commit()
            await session.refresh(order)
            with self.assertRaises(ValueError):
                await cancel_order(session, order)


class PanelTemplateContractTests(unittest.TestCase):
    def test_orders_actions_and_search_sort(self):
        html = (ROOT / "app/web/templates/orders.html").read_text(encoding="utf-8")
        self.assertIn('action="/orders"', html)
        self.assertIn('name="q"', html)
        self.assertIn("data-sortable", html)
        self.assertIn("/orders/{{ o.id }}/cancel", html)
        self.assertIn("/orders/{{ o.id }}/approve", html)
        self.assertIn("/orders/{{ o.id }}/reject", html)
        self.assertIn("data-sort-type", html)

    def test_payments_search_sort_and_actions(self):
        html = (ROOT / "app/web/templates/payments.html").read_text(encoding="utf-8")
        self.assertIn('action="/payments"', html)
        self.assertIn('name="q"', html)
        self.assertIn("data-sortable", html)
        self.assertIn("/payments/{{ p.id }}/approve", html)
        self.assertIn("payers", html)

    def test_nodes_traffic_columns(self):
        html = (ROOT / "app/web/templates/pg_nodes.html").read_text(encoding="utf-8")
        self.assertIn("_traffic_total_text", html)
        self.assertIn("_traffic_up_text", html)
        self.assertIn("_traffic_down_text", html)
        self.assertIn("مجموع ترافیک", html)
        self.assertIn("data-sortable", html)

    def test_users_resellers_search(self):
        users = (ROOT / "app/web/templates/users.html").read_text(encoding="utf-8")
        resellers = (ROOT / "app/web/templates/resellers.html").read_text(encoding="utf-8")
        self.assertIn('action="/users"', users)
        self.assertIn('name="q"', users)
        self.assertIn("data-sortable", users)
        self.assertIn('action="/resellers"', resellers)
        self.assertIn('name="q"', resellers)

    def test_panel_js_sortable(self):
        js = (ROOT / "app/web/static/panel.js").read_text(encoding="utf-8")
        self.assertIn("table[data-sortable]", js)
        self.assertIn("data-sort-type", js)
        self.assertIn("aria-sort", js)

    def test_api_wires_cancel_and_search(self):
        app = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        self.assertIn("order_cancel", app)
        self.assertIn("cancel_order", app)
        self.assertIn("notify_payer", app)
        self.assertIn("filter_by_search", app)
        self.assertIn("normalize_search_q", app)
        pg = (ROOT / "app/api/pg_pages.py").read_text(encoding="utf-8")
        self.assertIn("enrich_nodes_with_traffic", pg)
        self.assertIn("get_nodes_realtime", pg)

    def test_cancel_keeps_shop_isolation(self):
        app = (ROOT / "app/api/app.py").read_text(encoding="utf-8")
        # cancel block must mirror approve/reject reseller isolation
        m = re.search(
            r"async def order_cancel\([\s\S]*?return _redirect_msg\(\"/orders\", ok=",
            app,
        )
        self.assertIsNotNone(m)
        block = m.group(0)
        self.assertIn("reseller_id", block)
        self.assertIn("assert_order_in_scope", block)
        self.assertIn("notify_payer", block)


if __name__ == "__main__":
    unittest.main()
