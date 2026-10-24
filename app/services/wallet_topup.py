"""Platform wallet top-up rules shared by the bot and the Mini App."""

from __future__ import annotations

from app.db.models import PaymentMethod
from app.services.orders import MIN_TOPUP_AMOUNT

# key -> (enable flag, Payment.method)
TOPUP_METHODS: dict[str, tuple[str, str]] = {
    "card": ("pay_card_enabled", PaymentMethod.CARD.value),
    "gateway": ("pay_gateway_enabled", PaymentMethod.GATEWAY.value),
    "psp": ("pay_psp_enabled", PaymentMethod.PSP.value),
    "bbc": ("pay_bbc_enabled", PaymentMethod.BBC.value),
    "crypto": ("pay_crypto_enabled", PaymentMethod.CRYPTO.value),
}
DEFAULT_TOPUP_PRESETS: tuple[int, ...] = (50_000, 100_000, 200_000, 500_000)


def parse_topup_presets(ui: dict | None = None) -> list[int]:
    """CSV of toman amounts from ``wallet_topup_presets`` (falls back to defaults)."""
    raw = str((ui or {}).get("wallet_topup_presets") or "").strip()
    out: list[int] = []
    if raw:
        for part in raw.replace("،", ",").split(","):
            part = part.replace(",", "").replace("٬", "").strip()
            if not part:
                continue
            try:
                n = int(part)
            except ValueError:
                continue
            if n >= MIN_TOPUP_AMOUNT:
                out.append(n)
    return out or list(DEFAULT_TOPUP_PRESETS)
