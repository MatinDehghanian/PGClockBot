from __future__ import annotations

from sqlalchemy import select, update
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
    with session.no_autoflush:
        result = await session.execute(
            update(BotUser)
            .where(BotUser.id == user.id)
            .values(wallet_balance=BotUser.wallet_balance + int(amount))
            .execution_options(synchronize_session=False)
        )
    if result.rowcount != 1:
        raise ValueError("کاربر یافت نشد")
    await session.refresh(user)
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
    with session.no_autoflush:
        result = await session.execute(
            update(BotUser)
            .where(
                BotUser.id == user.id,
                BotUser.wallet_balance >= int(amount),
            )
            .values(wallet_balance=BotUser.wallet_balance - int(amount))
            .execution_options(synchronize_session=False)
        )
    if result.rowcount != 1:
        raise ValueError("موجودی کافی نیست")
    await session.refresh(user)
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
