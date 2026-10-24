"""Daily charts for the finance reports tab: orders by outcome and new users per Tehran day.

Two aggregate queries per page (conditional sums per day, like ``dashboard_trend``), scoped
to one shop. The bars' heights are computed here so the template only draws them.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TypedDict

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, Order
from app.services.daily_report import gregorian_to_jalali
from app.services.dashboard_trend import _day_starts, _labels
from app.services.db_safe import rollback_quiet
from app.services.demo_users import non_demo_customer
from app.services.shop_membership import shop_member_clause

logger = logging.getLogger(__name__)

# The month report charts 30 days; today and 7-day reports chart the last week.
CHART_DAYS = {"day": 7, "week": 7, "month": 30}
# Method shares beyond this many are grouped, so the share bar stays readable.
MAX_METHOD_SEGMENTS = 5


class ChartDay(TypedDict):
    date: str
    jalali: str
    weekday: str
    orders: int
    delivered: int
    not_delivered: int
    new_users: int
    orders_pct: int
    delivered_share: int
    users_pct: int


class FinanceCharts(TypedDict):
    days: list[ChartDay]
    total_orders: int
    total_delivered: int
    total_new_users: int
    has_orders: bool
    has_users: bool


class MethodSegment(TypedDict):
    label: str
    amount: int
    share_pct: int
    tone: int


def _jalali(iso_date: str) -> str:
    year, month, day = (int(part) for part in iso_date.split("-"))
    jy, jm, jd = gregorian_to_jalali(year, month, day)
    return f"{jy}/{jm:02d}/{jd:02d}"


def _pct(value: int, peak: int) -> int:
    """Bar height in whole percent of the busiest day; a non-zero day is always visible."""
    if peak <= 0 or value <= 0:
        return 0
    return max(2, round(value * 100 / peak))


def _per_day(column, starts: list[datetime], expr) -> list:
    return [
        func.coalesce(func.sum(case(((column >= starts[i]) & (column < starts[i + 1]), expr), else_=0)), 0)
        for i in range(len(starts) - 1)
    ]


async def _daily_counts(
    session: AsyncSession, *, reseller_id: int | None, starts: list[datetime]
) -> tuple[list[int], list[int], list[int]]:
    scope = Order.reseller_id.is_(None) if reseller_id is None else Order.reseller_id == int(reseller_id)
    delivered = case((Order.status == "delivered", 1), else_=0)
    orders_row = (
        await session.execute(
            select(*_per_day(Order.created_at, starts, 1), *_per_day(Order.created_at, starts, delivered))
            .select_from(Order)
            .where(Order.created_at >= starts[0], Order.created_at < starts[-1], scope, non_demo_customer(Order.user_id))
        )
    ).one()
    users_row = (
        await session.execute(
            select(*_per_day(BotUser.created_at, starts, 1))
            .select_from(BotUser)
            .where(
                BotUser.created_at >= starts[0],
                BotUser.created_at < starts[-1],
                shop_member_clause(reseller_id),
                BotUser.is_demo.is_(False),
            )
        )
    ).one()
    days = len(starts) - 1
    values = [int(v or 0) for v in orders_row]
    return values[:days], values[days:], [int(v or 0) for v in users_row]


def _empty(days: int) -> FinanceCharts:
    rows: list[ChartDay] = [
        {"date": d, "jalali": _jalali(d), "weekday": w, "orders": 0, "delivered": 0, "not_delivered": 0, "new_users": 0,
         "orders_pct": 0, "delivered_share": 0, "users_pct": 0}
        for d, w in _labels(days)
    ]
    return {"days": rows, "total_orders": 0, "total_delivered": 0, "total_new_users": 0,
            "has_orders": False, "has_users": False}


async def finance_charts(
    session: AsyncSession, *, reseller_id: int | None, period: str, now: datetime | None = None
) -> FinanceCharts:
    """Orders (delivered and not) and new users per day for the report's period; empty on a DB error."""
    days = CHART_DAYS.get(period, 7)
    starts = _day_starts(days, now=now)
    try:
        orders, delivered, users = await _daily_counts(session, reseller_id=reseller_id, starts=starts)
    except SQLAlchemyError:
        logger.warning("finance charts failed reseller_id=%s", reseller_id, exc_info=True)
        await rollback_quiet(session)
        return _empty(days)
    order_peak, user_peak = max(orders), max(users)
    rows: list[ChartDay] = []
    for (date, weekday), count, done, joined in zip(_labels(days, now=now), orders, delivered, users, strict=True):
        rows.append({
            "date": date, "jalali": _jalali(date), "weekday": weekday, "orders": count, "delivered": done,
            "not_delivered": max(0, count - done), "new_users": joined,
            "orders_pct": _pct(count, order_peak), "delivered_share": round(done * 100 / count) if count else 0,
            "users_pct": _pct(joined, user_peak),
        })
    return {
        "days": rows, "total_orders": sum(orders), "total_delivered": sum(delivered),
        "total_new_users": sum(users), "has_orders": order_peak > 0, "has_users": user_peak > 0,
    }


def method_segments(methods: list[dict]) -> list[MethodSegment]:
    """The payment-method rows as share-bar segments; the smallest are grouped as «سایر»."""
    rows = [m for m in methods if int(m.get("amount") or 0) > 0]
    head, rest = rows[: MAX_METHOD_SEGMENTS - 1], rows[MAX_METHOD_SEGMENTS - 1:]
    if len(rest) == 1:
        head, rest = rows, []
    segments: list[MethodSegment] = [
        {"label": str(m["label"]), "amount": int(m["amount"]), "share_pct": int(m.get("share_pct") or 0), "tone": i + 1}
        for i, m in enumerate(head)
    ]
    if rest:
        segments.append({
            "label": "سایر", "amount": sum(int(m["amount"]) for m in rest),
            "share_pct": sum(int(m.get("share_pct") or 0) for m in rest), "tone": len(segments) + 1,
        })
    return segments
