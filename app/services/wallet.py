from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BotUser, WalletTransaction


async def credit_wallet(
    session: AsyncSession,
    user: BotUser,
    amount: int,
    reason: str,
) -> BotUser:
    if amount <= 0:
        raise ValueError("amount must be positive")
    user.wallet_balance += amount
    session.add(
        WalletTransaction(
            user_id=user.id,
            amount=amount,
            balance_after=user.wallet_balance,
            reason=reason,
        )
    )
    await session.commit()
    await session.refresh(user)
    return user


async def debit_wallet(
    session: AsyncSession,
    user: BotUser,
    amount: int,
    reason: str,
) -> BotUser:
    if amount <= 0:
        raise ValueError("amount must be positive")
    if user.wallet_balance < amount:
        raise ValueError("موجودی کافی نیست")
    user.wallet_balance -= amount
    session.add(
        WalletTransaction(
            user_id=user.id,
            amount=-amount,
            balance_after=user.wallet_balance,
            reason=reason,
        )
    )
    await session.commit()
    await session.refresh(user)
    return user


async def list_transactions(session: AsyncSession, user_id: int, limit: int = 20):
    result = await session.execute(
        select(WalletTransaction)
        .where(WalletTransaction.user_id == user_id)
        .order_by(WalletTransaction.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
