"""Web panel: Referral + Loyalty / Points admin."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BotUser,
    LoyaltyReward,
    LoyaltyTier,
    PointsRule,
    PointsTransaction,
)
from app.services.loyalty import (
    EVENT_LABELS,
    REWARD_TYPE_LABELS,
    admin_adjust_points,
    ensure_loyalty_defaults,
    overview_metrics,
)
from app.services.shop_scope import (
    ShopScopeError,
    assert_bot_user_in_scope,
    resolve_shop_scope_id,
)
from app.services.users import get_setting, set_setting


def _shop_scope(staff: dict) -> int | None:
    """Platform admin → None (platform shop). Reseller → bot_user_id.

    Scopeless staff (pg_staff / broken reseller) raises — never platform fallthrough.
    """
    try:
        return resolve_shop_scope_id(staff)
    except ShopScopeError as e:
        raise ValueError(e.message) from e


def _rule_in_scope(rule: PointsRule, scope: int | None) -> bool:
    if scope is None:
        return rule.reseller_id is None
    return rule.reseller_id is not None and int(rule.reseller_id) == int(scope)


def _reward_in_scope(reward: LoyaltyReward, scope: int | None) -> bool:
    if scope is None:
        return reward.reseller_id is None
    return reward.reseller_id is not None and int(reward.reseller_id) == int(scope)


def register_loyalty_pages(app, *, render, require_perm, require_admin, get_db):
    require_loyalty = require_perm("loyalty")

    @app.get("/loyalty", response_class=HTMLResponse)
    async def loyalty_overview(
        request: Request,
        staff: dict = Depends(require_loyalty),
        session: AsyncSession = Depends(get_db),
        tab: str = "overview",
    ):
        try:
            scope = _shop_scope(staff)
        except ValueError:
            return RedirectResponse("/home", status_code=303)
        await ensure_loyalty_defaults(session, reseller_id=scope)
        metrics = await overview_metrics(session, reseller_id=scope)
        if scope is None:
            rules_q = select(PointsRule).where(PointsRule.reseller_id.is_(None))
            rewards_q = select(LoyaltyReward).where(LoyaltyReward.reseller_id.is_(None))
        else:
            rules_q = select(PointsRule).where(PointsRule.reseller_id == int(scope))
            rewards_q = select(LoyaltyReward).where(LoyaltyReward.reseller_id == int(scope))
        rules = list(
            (
                await session.execute(
                    rules_q.order_by(PointsRule.sort_order.asc(), PointsRule.id.asc())
                )
            ).scalars().all()
        )
        rewards = list(
            (
                await session.execute(
                    rewards_q.order_by(LoyaltyReward.sort_order.asc(), LoyaltyReward.id.asc())
                )
            ).scalars().all()
        )
        tiers = list(
            (
                await session.execute(
                    select(LoyaltyTier).order_by(LoyaltyTier.sort_order.asc(), LoyaltyTier.id.asc())
                )
            ).scalars().all()
        )
        txs_q = (
            select(PointsTransaction)
            .join(BotUser, BotUser.id == PointsTransaction.user_id)
            .order_by(PointsTransaction.id.desc())
            .limit(50)
        )
        if scope is not None:
            txs_q = txs_q.where(BotUser.reseller_id == int(scope))
        else:
            # Platform shop only — never list sibling/tenant loyalty txs as global.
            txs_q = txs_q.where(BotUser.reseller_id.is_(None))
        txs = list((await session.execute(txs_q)).scalars().all())
        loyalty_enabled = await get_setting(
            session, "loyalty_enabled", "1", reseller_id=scope
        )
        wallet_rate = await get_setting(
            session, "points_to_wallet_rate", "100", reseller_id=scope
        )
        page_tab = tab or "overview"
        # Legacy page tabs moved into the settings modal.
        if page_tab in {"settings", "rules", "rewards", "tiers"}:
            settings_key = "1" if page_tab == "settings" else page_tab
            return RedirectResponse(
                f"/loyalty?tab=overview&settings={settings_key}", status_code=303
            )
        if page_tab not in {"overview", "transactions"}:
            page_tab = "overview"

        from app.services.users import SETTING_GROUPS, TAB_SETTING_GROUPS, get_all_settings

        values = await get_all_settings(session, reseller_id=scope)
        can_edit_referral_text = staff.get("role") == "admin" or (
            "shop_settings" in (staff.get("permissions") or [])
        )
        ref_names = (TAB_SETTING_GROUPS.get("loyalty") or []) if can_edit_referral_text else []
        settings_q = (request.query_params.get("settings") or "").strip()
        settings_tabs = {"1", "true", "yes", "club", "referral", "rules", "rewards", "tiers"}
        open_settings = settings_q in settings_tabs
        if settings_q in {"rules", "rewards", "tiers"}:
            loyalty_settings_tab = settings_q
        elif settings_q == "referral" and can_edit_referral_text:
            loyalty_settings_tab = "referral"
        else:
            loyalty_settings_tab = "club"
        next_referral = quote(f"/loyalty?tab={page_tab}&settings=referral")
        if staff.get("role") == "admin":
            referral_text_action = f"/settings?tab=loyalty&next={next_referral}"
        elif can_edit_referral_text:
            referral_text_action = f"/shop-settings?tab=loyalty&next={next_referral}"
        else:
            referral_text_action = ""

        flash_ok = None
        if request.query_params.get("saved"):
            flash_ok = request.query_params.get("msg") or "ذخیره شد."
        elif request.query_params.get("ok"):
            flash_ok = request.query_params.get("ok")

        return render(
            request,
            "loyalty.html",
            {
                "staff": staff,
                "tab": page_tab,
                "metrics": metrics,
                "rules": rules,
                "rewards": rewards,
                "tiers": tiers,
                "txs": txs,
                "event_labels": EVENT_LABELS,
                "reward_type_labels": REWARD_TYPE_LABELS,
                "loyalty_enabled": loyalty_enabled,
                "wallet_rate": wallet_rate,
                "is_platform_admin": staff.get("role") == "admin",
                "flash_ok": flash_ok,
                "flash_err": request.query_params.get("err"),
                "flash_msg": request.query_params.get("msg"),
                "open_loyalty_settings": open_settings,
                "loyalty_settings_tab": loyalty_settings_tab,
                "values": values,
                "referral_tab_groups": ref_names,
                "referral_groups": {
                    n: SETTING_GROUPS[n] for n in ref_names if n in SETTING_GROUPS
                },
                "referral_text_action": referral_text_action,
            },
        )

    @app.post("/loyalty/settings")
    async def loyalty_settings_save(
        request: Request,
        staff: dict = Depends(require_loyalty),
        session: AsyncSession = Depends(get_db),
        loyalty_enabled: str = Form("0"),
        points_to_wallet_rate: str = Form("100"),
        next_tab: str = Form("overview"),
    ):
        try:
            scope = _shop_scope(staff)
        except ValueError:
            return RedirectResponse("/home", status_code=303)
        page_tab = str(next_tab or "overview").strip()
        if page_tab not in {"overview", "transactions"}:
            page_tab = "overview"
        enabled = "1" if str(loyalty_enabled) in {"1", "on", "true", "yes"} else "0"
        try:
            rate = int(str(points_to_wallet_rate).replace(",", "").strip() or "0")
            if rate < 0:
                raise ValueError("نرخ نامعتبر")
        except ValueError:
            return RedirectResponse(
                f"/loyalty?tab={page_tab}&settings=1&err={quote('نرخ تبدیل نامعتبر است')}",
                status_code=303,
            )
        await set_setting(session, "loyalty_enabled", enabled, reseller_id=scope)
        await set_setting(session, "points_to_wallet_rate", str(rate), reseller_id=scope)
        return RedirectResponse(f"/loyalty?tab={page_tab}&settings=1&saved=1", status_code=303)

    @app.post("/loyalty/rules/{rule_id}/save")
    async def loyalty_rule_save(
        rule_id: int,
        staff: dict = Depends(require_loyalty),
        session: AsyncSession = Depends(get_db),
        name: str = Form(...),
        amount: int = Form(0),
        amount_mode: str = Form("fixed"),
        enabled: str = Form("0"),
        first_time_only: str = Form("0"),
        min_purchase_toman: int = Form(0),
        min_purchase_gb: int = Form(0),
        max_reward: str = Form(""),
        cooldown_hours: int = Form(0),
    ):
        try:
            scope = _shop_scope(staff)
        except ValueError:
            return RedirectResponse("/home", status_code=303)
        rule = await session.get(PointsRule, rule_id)
        if not rule or not _rule_in_scope(rule, scope):
            return RedirectResponse(
                f"/loyalty?tab=overview&settings=rules&err={quote('قانون پیدا نشد')}", status_code=303
            )
        rule.name = (name or rule.name).strip()[:128]
        rule.amount = max(0, int(amount))
        rule.amount_mode = amount_mode if amount_mode in {"fixed", "per_gb"} else "fixed"
        rule.enabled = str(enabled) in {"1", "on", "true", "yes"}
        rule.first_time_only = str(first_time_only) in {"1", "on", "true", "yes"}
        rule.min_purchase_toman = max(0, int(min_purchase_toman))
        rule.min_purchase_gb = max(0, int(min_purchase_gb))
        rule.cooldown_hours = max(0, int(cooldown_hours))
        mr = str(max_reward or "").strip()
        rule.max_reward = int(mr) if mr.isdigit() else None
        await session.commit()
        return RedirectResponse("/loyalty?tab=overview&settings=rules&saved=1", status_code=303)

    @app.post("/loyalty/rules/{rule_id}/toggle")
    async def loyalty_rule_toggle(
        rule_id: int,
        staff: dict = Depends(require_loyalty),
        session: AsyncSession = Depends(get_db),
    ):
        try:
            scope = _shop_scope(staff)
        except ValueError:
            return RedirectResponse("/home", status_code=303)
        rule = await session.get(PointsRule, rule_id)
        if rule and _rule_in_scope(rule, scope):
            rule.enabled = not bool(rule.enabled)
            await session.commit()
        return RedirectResponse("/loyalty?tab=overview&settings=rules&saved=1", status_code=303)

    @app.post("/loyalty/rewards/create")
    async def loyalty_reward_create(
        staff: dict = Depends(require_loyalty),
        session: AsyncSession = Depends(get_db),
        name: str = Form(...),
        description: str = Form(""),
        reward_type: str = Form(...),
        reward_value: int = Form(...),
        points_cost: int = Form(...),
        min_purchase_toman: int = Form(0),
        max_discount_toman: str = Form(""),
        expires_days: str = Form(""),
    ):
        try:
            scope = _shop_scope(staff)
        except ValueError:
            return RedirectResponse("/home", status_code=303)
        if reward_type not in REWARD_TYPE_LABELS:
            return RedirectResponse(
                f"/loyalty?tab=overview&settings=rewards&err={quote('نوع جایزه نامعتبر')}", status_code=303
            )
        if int(reward_value) <= 0 or int(points_cost) <= 0:
            return RedirectResponse(
                f"/loyalty?tab=overview&settings=rewards&err={quote('مقدار و هزینه باید مثبت باشند')}",
                status_code=303,
            )
        if reward_type == "discount_percent" and int(reward_value) > 100:
            return RedirectResponse(
                f"/loyalty?tab=overview&settings=rewards&err={quote('درصد تخفیف حداکثر ۱۰۰ است')}",
                status_code=303,
            )
        mx = str(max_discount_toman or "").strip()
        ex = str(expires_days or "").strip()
        session.add(
            LoyaltyReward(
                name=(name or "").strip()[:128] or "جایزه",
                description=(description or "").strip() or None,
                reward_type=reward_type,
                reward_value=int(reward_value),
                points_cost=int(points_cost),
                enabled=True,
                archived=False,
                sort_order=100,
                reseller_id=scope,
                min_purchase_toman=max(0, int(min_purchase_toman or 0))
                if reward_type == "discount_percent"
                else 0,
                max_discount_toman=int(mx) if mx.isdigit() and reward_type == "discount_percent" else None,
                expires_days=int(ex) if ex.isdigit() and reward_type == "discount_percent" else None,
            )
        )
        await session.commit()
        return RedirectResponse("/loyalty?tab=overview&settings=rewards&saved=1", status_code=303)

    @app.post("/loyalty/rewards/{reward_id}/save")
    async def loyalty_reward_save(
        reward_id: int,
        staff: dict = Depends(require_loyalty),
        session: AsyncSession = Depends(get_db),
        name: str = Form(...),
        description: str = Form(""),
        reward_value: int = Form(...),
        points_cost: int = Form(...),
        enabled: str = Form("0"),
        max_redemptions_global: str = Form(""),
        max_redemptions_per_user: str = Form(""),
        min_purchase_toman: int = Form(0),
        max_discount_toman: str = Form(""),
        expires_days: str = Form(""),
    ):
        try:
            scope = _shop_scope(staff)
        except ValueError:
            return RedirectResponse("/home", status_code=303)
        reward = await session.get(LoyaltyReward, reward_id)
        if not reward or not _reward_in_scope(reward, scope):
            return RedirectResponse(
                f"/loyalty?tab=overview&settings=rewards&err={quote('جایزه پیدا نشد')}", status_code=303
            )
        reward.name = (name or reward.name).strip()[:128]
        reward.description = (description or "").strip() or None
        reward.reward_value = max(1, int(reward_value))
        if reward.reward_type == "discount_percent":
            reward.reward_value = min(100, reward.reward_value)
        reward.points_cost = max(1, int(points_cost))
        reward.enabled = str(enabled) in {"1", "on", "true", "yes"}
        g = str(max_redemptions_global or "").strip()
        u = str(max_redemptions_per_user or "").strip()
        reward.max_redemptions_global = int(g) if g.isdigit() else None
        reward.max_redemptions_per_user = int(u) if u.isdigit() else None
        if reward.reward_type == "discount_percent":
            reward.min_purchase_toman = max(0, int(min_purchase_toman or 0))
            mx = str(max_discount_toman or "").strip()
            ex = str(expires_days or "").strip()
            reward.max_discount_toman = int(mx) if mx.isdigit() else None
            reward.expires_days = int(ex) if ex.isdigit() else None
        await session.commit()
        return RedirectResponse("/loyalty?tab=overview&settings=rewards&saved=1", status_code=303)

    @app.post("/loyalty/rewards/{reward_id}/archive")
    async def loyalty_reward_archive(
        reward_id: int,
        staff: dict = Depends(require_loyalty),
        session: AsyncSession = Depends(get_db),
    ):
        try:
            scope = _shop_scope(staff)
        except ValueError:
            return RedirectResponse("/home", status_code=303)
        reward = await session.get(LoyaltyReward, reward_id)
        if reward and _reward_in_scope(reward, scope):
            reward.archived = True
            reward.enabled = False
            await session.commit()
        return RedirectResponse("/loyalty?tab=overview&settings=rewards&saved=1", status_code=303)

    @app.post("/loyalty/tiers/{tier_id}/save")
    async def loyalty_tier_save(
        tier_id: int,
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
        name: str = Form(...),
        min_points: int = Form(0),
        max_points: str = Form(""),
        multiplier_bps: int = Form(10000),
        enabled: str = Form("0"),
    ):
        # Tiers are platform-global — admin only (no reseller mutation).
        tier = await session.get(LoyaltyTier, tier_id)
        if not tier:
            return RedirectResponse(
                f"/loyalty?tab=overview&settings=tiers&err={quote('سطح پیدا نشد')}", status_code=303
            )
        tier.name = (name or tier.name).strip()[:64]
        tier.min_points = max(0, int(min_points))
        mx = str(max_points or "").strip()
        tier.max_points = int(mx) if mx.isdigit() else None
        tier.multiplier_bps = max(0, int(multiplier_bps))
        tier.enabled = str(enabled) in {"1", "on", "true", "yes"}
        await session.commit()
        return RedirectResponse("/loyalty?tab=overview&settings=tiers&saved=1", status_code=303)

    @app.post("/loyalty/adjust")
    async def loyalty_adjust(
        staff: dict = Depends(require_admin),
        session: AsyncSession = Depends(get_db),
        user_id: int = Form(...),
        delta: int = Form(...),
        reason: str = Form(...),
    ):
        user = await session.get(BotUser, int(user_id))
        if not user:
            return RedirectResponse(
                f"/loyalty?tab=transactions&err={quote('کاربر پیدا نشد')}", status_code=303
            )
        try:
            assert_bot_user_in_scope(staff, user)
        except ShopScopeError as e:
            return RedirectResponse(
                f"/loyalty?tab=transactions&err={quote(e.message)}", status_code=303
            )
        admin_id = str(staff.get("username") or staff.get("telegram_id") or staff.get("id") or "admin")
        try:
            await admin_adjust_points(
                session,
                user,
                int(delta),
                reason=reason,
                admin_identity=admin_id,
            )
        except ValueError as e:
            return RedirectResponse(
                f"/loyalty?tab=transactions&err={quote(str(e)[:200])}", status_code=303
            )
        return RedirectResponse(
            f"/loyalty?tab=transactions&saved=1&msg={quote('تعدیل ثبت شد')}",
            status_code=303,
        )
