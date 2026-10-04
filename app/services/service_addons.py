"""Customer service addon packs (extra GB / days) — shop-scoped, fail-closed."""

from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BotUser,
    Order,
    OrderStatus,
    ServiceAddonPack,
    UserService,
)
from app.services.plans_catalog import require_catalog_owner_id
from app.services.shop_scope import ShopScopeError, is_platform_admin, shop_owner_id

log = logging.getLogger(__name__)

KIND_VOLUME = "volume"
KIND_DURATION = "duration"
VALID_KINDS = frozenset({KIND_VOLUME, KIND_DURATION})

# note: svc_addon:{pack_id}:{service_id}
_NOTE_RE = re.compile(r"^svc_addon:(\d+):(\d+)$")

MAX_VOLUME_GB = 10_000.0
MAX_DURATION_DAYS = 3650
MAX_PRICE = 2_000_000_000


def apply_pack_owner_filter(query, staff: dict | None):
    if is_platform_admin(staff):
        return query.where(ServiceAddonPack.owner_reseller_id.is_(None))
    if not staff:
        return query.where(ServiceAddonPack.owner_reseller_id.is_(None))
    rid = shop_owner_id(staff)
    if not rid:
        return query.where(ServiceAddonPack.id < 0)
    return query.where(ServiceAddonPack.owner_reseller_id == rid)


def pack_belongs_to_staff(pack: ServiceAddonPack | None, staff: dict | None) -> bool:
    if not pack:
        return False
    if is_platform_admin(staff):
        return pack.owner_reseller_id is None
    if not staff:
        return pack.owner_reseller_id is None
    rid = shop_owner_id(staff)
    if not rid:
        return False
    return int(pack.owner_reseller_id or 0) == int(rid)


def pack_matches_shop(pack: ServiceAddonPack | None, shop_rid: int | None) -> bool:
    if not pack or not pack.is_active:
        return False
    if shop_rid:
        return int(pack.owner_reseller_id or 0) == int(shop_rid)
    return pack.owner_reseller_id is None


def parse_addon_note(note: str | None) -> tuple[int, int] | None:
    m = _NOTE_RE.match((note or "").strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def is_addon_order(order: Order | None) -> bool:
    return bool(order and parse_addon_note(order.note))


def kind_label(kind: str) -> str:
    return "حجم" if kind == KIND_VOLUME else "زمان"


def amount_label(pack: ServiceAddonPack) -> str:
    if pack.kind == KIND_VOLUME:
        amt = float(pack.amount)
        if amt == int(amt):
            return f"{int(amt)} گیگ"
        return f"{amt:g} گیگ"
    days = int(float(pack.amount))
    return f"{days} روز"


async def list_packs(
    session: AsyncSession,
    staff: dict | None,
    *,
    active_only: bool = False,
    kind: str | None = None,
) -> list[ServiceAddonPack]:
    q = select(ServiceAddonPack).order_by(
        ServiceAddonPack.kind, ServiceAddonPack.sort_order, ServiceAddonPack.id
    )
    q = apply_pack_owner_filter(q, staff)
    if active_only:
        q = q.where(ServiceAddonPack.is_active.is_(True))
    if kind:
        if kind not in VALID_KINDS:
            raise ValueError("نوع بسته نامعتبر است")
        q = q.where(ServiceAddonPack.kind == kind)
    return list((await session.execute(q)).scalars().all())


async def list_shop_packs(
    session: AsyncSession,
    *,
    reseller_id: int | None = None,
    active_only: bool = True,
    kind: str | None = None,
) -> list[ServiceAddonPack]:
    from app.services.users import current_shop_reseller_id

    rid = reseller_id if reseller_id is not None else current_shop_reseller_id()
    q = select(ServiceAddonPack).order_by(
        ServiceAddonPack.kind, ServiceAddonPack.sort_order, ServiceAddonPack.id
    )
    if rid:
        q = q.where(ServiceAddonPack.owner_reseller_id == int(rid))
    else:
        q = q.where(ServiceAddonPack.owner_reseller_id.is_(None))
    if active_only:
        q = q.where(ServiceAddonPack.is_active.is_(True))
    if kind:
        q = q.where(ServiceAddonPack.kind == kind)
    return list((await session.execute(q)).scalars().all())


async def get_owned_pack(
    session: AsyncSession, pack_id: int, staff: dict | None
) -> ServiceAddonPack | None:
    pack = await session.get(ServiceAddonPack, int(pack_id))
    if not pack_belongs_to_staff(pack, staff):
        return None
    return pack


def _validate_pack_fields(
    *,
    name: str,
    kind: str,
    amount: float,
    price: int,
    description: str | None,
) -> tuple[str, str, float, int, str | None]:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("نام بسته الزامی است")
    if len(cleaned) > 128:
        raise ValueError("نام بسته خیلی طولانی است")
    k = (kind or "").strip().lower()
    if k not in VALID_KINDS:
        raise ValueError("نوع بسته باید حجم یا زمان باشد")
    try:
        amt = float(amount)
    except (TypeError, ValueError) as e:
        raise ValueError("مقدار بسته نامعتبر است") from e
    if amt <= 0:
        raise ValueError("مقدار باید بزرگ‌تر از صفر باشد")
    if k == KIND_VOLUME and amt > MAX_VOLUME_GB:
        raise ValueError("حجم بیش از حد مجاز است")
    if k == KIND_DURATION:
        if amt != int(amt):
            raise ValueError("روز باید عدد صحیح باشد")
        if amt > MAX_DURATION_DAYS:
            raise ValueError("مدت بیش از حد مجاز است")
        amt = float(int(amt))
    try:
        price_i = int(price)
    except (TypeError, ValueError) as e:
        raise ValueError("قیمت نامعتبر است") from e
    if price_i < 0 or price_i > MAX_PRICE:
        raise ValueError("قیمت نامعتبر است")
    desc = (description or "").strip() or None
    if desc and len(desc) > 255:
        raise ValueError("توضیح خیلی طولانی است")
    return cleaned, k, amt, price_i, desc


async def create_pack(
    session: AsyncSession,
    staff: dict | None,
    *,
    name: str,
    kind: str,
    amount: float,
    price: int,
    description: str | None = None,
    sort_order: int = 0,
) -> ServiceAddonPack:
    owner_id = require_catalog_owner_id(staff)
    cleaned, k, amt, price_i, desc = _validate_pack_fields(
        name=name, kind=kind, amount=amount, price=price, description=description
    )
    pack = ServiceAddonPack(
        name=cleaned,
        kind=k,
        amount=amt,
        price=price_i,
        description=desc,
        owner_reseller_id=owner_id,
        sort_order=int(sort_order or 0),
        is_active=True,
    )
    session.add(pack)
    await session.commit()
    await session.refresh(pack)
    return pack


async def update_pack(
    session: AsyncSession,
    staff: dict | None,
    pack_id: int,
    *,
    name: str | None = None,
    kind: str | None = None,
    amount: float | None = None,
    price: int | None = None,
    description: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> ServiceAddonPack:
    pack = await get_owned_pack(session, pack_id, staff)
    if not pack:
        raise ShopScopeError("بسته یافت نشد")
    cleaned, k, amt, price_i, desc = _validate_pack_fields(
        name=name if name is not None else pack.name,
        kind=kind if kind is not None else pack.kind,
        amount=amount if amount is not None else pack.amount,
        price=price if price is not None else pack.price,
        description=description if description is not None else (pack.description or ""),
    )
    pack.name = cleaned
    pack.kind = k
    pack.amount = amt
    pack.price = price_i
    if description is not None:
        pack.description = desc
    if sort_order is not None:
        pack.sort_order = int(sort_order)
    if is_active is not None:
        pack.is_active = bool(is_active)
    await session.commit()
    await session.refresh(pack)
    return pack


async def delete_pack(
    session: AsyncSession, staff: dict | None, pack_id: int
) -> None:
    pack = await get_owned_pack(session, pack_id, staff)
    if not pack:
        raise ShopScopeError("بسته یافت نشد")
    await session.delete(pack)
    await session.commit()


async def create_addon_order(
    session: AsyncSession,
    *,
    user_id: int,
    service: UserService,
    pack: ServiceAddonPack,
) -> Order:
    """Create a pending addon order. Price is snapshotted from the pack."""
    from app.services.orders import _shop_reseller_id

    if not pack or not pack.is_active:
        raise ValueError("بسته یافت نشد")
    if pack.kind not in VALID_KINDS:
        raise ValueError("نوع بسته نامعتبر است")
    shop_rid = _shop_reseller_id()
    if not pack_matches_shop(pack, shop_rid):
        raise ValueError("این بسته در این فروشگاه موجود نیست")
    if int(service.bot_user_id) != int(user_id):
        raise ValueError("سرویس متعلق به شما نیست")
    if not service.pg_user_id:
        raise ValueError("سرویس به پنل متصل نیست")
    if (service.remark or "").strip() == "linked":
        raise ValueError("سرویس متصل‌شده فقط مشاهده است؛ خرید افزونه ممکن نیست")

    # Fail closed: service owner must live in the same shop as the pack.
    user = await session.get(BotUser, int(user_id))
    if not user:
        raise ValueError("کاربر یافت نشد")
    if shop_rid:
        if int(user.reseller_id or 0) != int(shop_rid):
            raise ValueError("سرویس این فروشگاه نیست")
    elif user.reseller_id is not None:
        # Platform bot must not sell addons onto shop-owned customer rows.
        raise ValueError("سرویس این فروشگاه نیست")

    order = Order(
        user_id=user_id,
        plan_id=None,
        amount=int(pack.price),
        status=OrderStatus.PENDING.value,
        note=f"svc_addon:{int(pack.id)}:{int(service.id)}",
        service_id=int(service.id),
        reseller_id=shop_rid,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def apply_service_addon(
    session: AsyncSession, order: Order
) -> Order:
    """Apply paid addon to the linked UserService (additive volume/time)."""
    parsed = parse_addon_note(order.note)
    if not parsed:
        raise ValueError("سفارش افزونه نامعتبر است")
    pack_id, service_id = parsed
    order_id = int(order.id)

    with session.no_autoflush:
        claim = await session.execute(
            update(Order)
            .where(
                Order.id == order_id,
                Order.status == OrderStatus.PAID.value,
            )
            .values(status=OrderStatus.DELIVERING.value)
            .execution_options(synchronize_session=False)
        )
    if claim.rowcount != 1:
        await session.refresh(order)
        if order.status == OrderStatus.DELIVERED.value:
            return order
        raise ValueError("سفارش افزونه قابل پردازش نیست")
    await session.commit()
    await session.refresh(order)

    async def _release() -> None:
        await session.execute(
            update(Order)
            .where(
                Order.id == order_id,
                Order.status == OrderStatus.DELIVERING.value,
            )
            .values(status=OrderStatus.PAID.value)
            .execution_options(synchronize_session=False)
        )
        await session.commit()

    try:
        pack = await session.get(ServiceAddonPack, pack_id)
        service = await session.get(UserService, service_id)
        if not pack or not service:
            raise ValueError("بسته یا سرویس یافت نشد")
        if int(order.service_id or 0) != int(service.id):
            raise ValueError("سرویس سفارش با یادداشت همخوان نیست")
        if int(service.bot_user_id) != int(order.user_id):
            raise ValueError("سرویس متعلق به خریدار نیست")
        # Shop isolation: pack + order must match
        if order.reseller_id:
            if int(pack.owner_reseller_id or 0) != int(order.reseller_id):
                raise ValueError("بسته متعلق به این فروشگاه نیست")
        elif pack.owner_reseller_id is not None:
            raise ValueError("بسته متعلق به این فروشگاه نیست")

        await _apply_pack_to_service(session, service, pack, order_reseller_id=order.reseller_id)

        with session.no_autoflush:
            done = await session.execute(
                update(Order)
                .where(
                    Order.id == order_id,
                    Order.status == OrderStatus.DELIVERING.value,
                )
                .values(status=OrderStatus.DELIVERED.value)
                .execution_options(synchronize_session=False)
            )
        if done.rowcount != 1:
            raise ValueError("ثبت تحویل افزونه ناموفق بود")
        await session.commit()
        await session.refresh(order)
        return order
    except Exception:
        try:
            await _release()
        except Exception:
            log.exception("addon claim release failed order=%s", order_id)
        raise


async def _apply_pack_to_service(
    session: AsyncSession,
    service: UserService,
    pack: ServiceAddonPack,
    *,
    order_reseller_id: int | None,
) -> None:
    """Additive PG mutate — never falls back across shop PG credentials."""
    from app.services.bot_user_admin import sync_service_quota_cache
    from app.services.pasarguard import get_pg, get_pg_for_reseller

    if not service.pg_user_id:
        raise ValueError("سرویس به پنل متصل نیست")

    if order_reseller_id:
        pg = await get_pg_for_reseller(session, int(order_reseller_id))
    else:
        from app.services.users import current_shop_reseller_id

        if current_shop_reseller_id():
            raise ValueError("فروشگاه بدون اعتبار پاسارگارد معتبر است")
        pg = get_pg()

    info = await pg.get_user_by_id(int(service.pg_user_id))
    if not isinstance(info, dict):
        raise ValueError("کاربر پاسارگارد یافت نشد")

    payload: dict[str, Any] = {"status": "active"}
    expire_ts = None
    data_limit_bytes = None

    if pack.kind == KIND_VOLUME:
        add_bytes = int(float(pack.amount) * (1024**3))
        if add_bytes <= 0:
            raise ValueError("حجم نامعتبر است")
        try:
            current = int(info.get("data_limit") or 0)
        except (TypeError, ValueError):
            current = 0
        if current <= 0:
            # Unlimited → start from purchased extra only
            data_limit_bytes = add_bytes
        else:
            data_limit_bytes = current + add_bytes
        payload["data_limit"] = data_limit_bytes
    elif pack.kind == KIND_DURATION:
        import time
        from app.services.formatting import parse_expire

        days = int(float(pack.amount))
        if days <= 0:
            raise ValueError("مدت نامعتبر است")
        now = int(time.time())
        cur = parse_expire(info.get("expire") or info.get("expire_date"))
        if cur is not None:
            base = max(now, int(cur.timestamp()))
        else:
            base = now
        expire_ts = base + days * 86400
        payload["expire"] = expire_ts
    else:
        raise ValueError("نوع بسته پشتیبانی نمی‌شود")

    await pg.modify_user_by_id(int(service.pg_user_id), payload)
    await sync_service_quota_cache(
        session,
        service,
        expire_ts=expire_ts,
        data_limit_bytes=data_limit_bytes,
    )
    await session.flush()
