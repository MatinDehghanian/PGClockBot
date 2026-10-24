"""Mini App codes: discounted checkout (order → pay or cancel) and gift-code wallet credit.

Thin routes over ``app.services.discount_checkout``. The customer comes from
initData; every order id is re-checked against that customer and the platform.
"""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.miniapp_pages import _no_store, _require_commerce_ready
from app.services.db_safe import rollback_quiet
from app.services.discount_checkout import (
    CodeError,
    cancel_checkout,
    pay_checkout,
    redeem_wallet_code,
    start_discounted_checkout,
)
from app.services.miniapp_auth import load_mini_user
from app.services.redact import user_safe_error
from app.services.users import get_all_settings, on

logger = logging.getLogger(__name__)

_ID_MAX = 2**31 - 1


async def _json_object(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise HTTPException(400, "درخواست نامعتبر است") from None
    if not isinstance(body, dict):
        raise HTTPException(400, "درخواست نامعتبر است")
    return body


def _valid_id(value: object) -> int:
    if type(value) is not int or not 0 < value <= _ID_MAX:
        raise HTTPException(400, "شناسه نامعتبر است")
    return value


async def _require_wallet_pay(session: AsyncSession) -> None:
    if not on((await get_all_settings(session)).get("pay_wallet_enabled")):
        raise HTTPException(403, "پرداخت با کیف پول غیرفعال است")


def register_miniapp_codes(app: FastAPI, *, get_db) -> None:
    @app.post("/api/mini/checkout")
    async def mini_checkout(request: Request, session: AsyncSession = Depends(get_db)):
        user = await load_mini_user(session, request)
        await _require_commerce_ready(session, user)
        await _require_wallet_pay(session)
        user_id = int(user.id)
        body = await _json_object(request)
        try:
            checkout = await start_discounted_checkout(
                session, user_id=user_id, plan_id=_valid_id(body.get("plan_id")),
                expected_price=body.get("price"), code=body.get("code"),
            )
        except ValueError as exc:
            raise HTTPException(400, user_safe_error(exc, fallback="اعمال کد ناموفق بود")) from None
        return _no_store({"checkout": checkout.payload()})

    @app.post("/api/mini/checkout/{order_id}/pay")
    async def mini_checkout_pay(order_id: int, request: Request, session: AsyncSession = Depends(get_db)):
        user = await load_mini_user(session, request)
        await _require_commerce_ready(session, user)
        await _require_wallet_pay(session)
        user_id = int(user.id)
        try:
            order = await pay_checkout(session, user=user, order_id=_valid_id(order_id))
            await session.refresh(user)
        except ValueError as exc:
            await rollback_quiet(session)
            raise HTTPException(400, user_safe_error(exc, fallback="پرداخت ناموفق بود")) from None
        except Exception:
            await rollback_quiet(session)
            logger.exception("mini checkout pay failed user=%s order=%s", user_id, order_id)
            raise HTTPException(500, "پرداخت ناموفق بود") from None
        return _no_store({
            "ok": True, "order_id": int(order.id), "wallet": int(user.wallet_balance or 0),
            "message": "خرید با موفقیت انجام شد",
        })

    @app.post("/api/mini/checkout/{order_id}/cancel")
    async def mini_checkout_cancel(order_id: int, request: Request, session: AsyncSession = Depends(get_db)):
        user = await load_mini_user(session, request)
        await _require_commerce_ready(session, user)
        try:
            await cancel_checkout(session, user_id=int(user.id), order_id=_valid_id(order_id))
        except ValueError as exc:
            await rollback_quiet(session)
            raise HTTPException(400, user_safe_error(exc, fallback="لغو سفارش ناموفق بود")) from None
        return _no_store({"ok": True})

    @app.post("/api/mini/wallet/redeem")
    async def mini_wallet_redeem(request: Request, session: AsyncSession = Depends(get_db)):
        user = await load_mini_user(session, request)
        await _require_commerce_ready(session, user)
        body = await _json_object(request)
        try:
            amount, balance = await redeem_wallet_code(session, user=user, code=body.get("code"))
        except CodeError as exc:
            raise HTTPException(400, user_safe_error(exc, fallback="کد نامعتبر است")) from None
        return _no_store({"amount": amount, "wallet": balance, "message": "کیف پول شارژ شد"})
