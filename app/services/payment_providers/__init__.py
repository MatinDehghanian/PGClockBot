"""Provider registry."""

from __future__ import annotations

from app.services.payment_providers.base import PspAdapter
from app.services.payment_providers.mock_psp import MockPspAdapter
from app.services.payment_providers.zarinpal import ZarinpalAdapter


def get_psp_adapter(provider: str, *, ui: dict, public_base_url: str) -> PspAdapter:
    name = (provider or "mock").strip().lower()
    if name in {"", "mock"}:
        return MockPspAdapter(public_base_url=public_base_url)
    if name == "zarinpal":
        return ZarinpalAdapter(
            merchant_id=str(ui.get("psp_merchant_id") or ""),
            sandbox=str(ui.get("psp_sandbox") or "1") in {"1", "true", "yes", "on"},
        )
    raise ValueError(f"unknown psp provider: {name}")
