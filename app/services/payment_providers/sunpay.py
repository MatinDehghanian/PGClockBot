"""SunPay PSP adapter — request → redirect → callback → verify (amounts in Toman).

Follows the SunPay merchant API:
  GET  {PAY_URL}/api/request   JSON body → token
  GET  {PAY_URL}/pay/{token}   browser checkout
  GET/POST {PAY_URL}/api/verified  JSON body → amount/reference (read-only)

Verify never cancels or refunds; callers must match amount and invoice_id locally.
Unknown / transport failures must leave the settlement open for retry.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Any
from urllib.parse import urlparse

import httpx

from app.services.payment_providers.base import CheckoutRequest, CheckoutResult, VerifyResult

logger = logging.getLogger(__name__)

MIN_AMOUNT_TOMAN = 1000
_HTTP_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
_PLACEHOLDER_KEYS = frozenset(
    {"", "changeme", "your-api-key", "YOUR_API_KEY", "your_api_key"}
)
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
    }
)

_client: httpx.AsyncClient | None = None


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
    return _client


async def close_client() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


def _is_success_flag(raw: Any) -> bool:
    """SunPay callback/API success: 1 / \"1\" / true."""
    if raw is True:
        return True
    if raw is False or raw is None:
        return False
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return int(raw) == 1
    text = str(raw).strip().lower()
    return text in {"1", "true", "yes", "ok", "success"}


def _host_is_blocked(host: str) -> bool:
    name = (host or "").strip().lower().rstrip(".")
    if not name:
        return True
    if name in _BLOCKED_HOSTS or name.endswith(".localhost"):
        return True
    # Strip brackets from IPv6 literals.
    if name.startswith("[") and name.endswith("]"):
        name = name[1:-1]
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        return False
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_sunpay_pay_url(value: str) -> str:
    """Normalize PAY_URL: https only, no localhost/private targets (SSRF / cleartext key)."""
    raw = (value or "").strip().rstrip("/")
    if not raw:
        raise ValueError("آدرس پایه سان‌پی (PAY_URL) تنظیم نشده")
    try:
        parts = urlparse(raw)
    except ValueError as exc:
        raise ValueError("آدرس پایه سان‌پی نامعتبر است") from exc
    if parts.scheme != "https" or not parts.netloc:
        raise ValueError("آدرس پایه سان‌پی باید با https و میزبان عمومی باشد")
    if parts.username or parts.password:
        raise ValueError("آدرس پایه سان‌پی نامعتبر است")
    host = (parts.hostname or "").strip().lower()
    if _host_is_blocked(host):
        raise ValueError("آدرس پایه سان‌پی به میزبان داخلی مجاز نیست")
    return raw


def _safe_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} نامعتبر است")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{field} باید عدد صحیح باشد")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} نامعتبر است") from exc
    return number


def _api_error_text(data: Any) -> str:
    if not isinstance(data, dict):
        return "پاسخ نامعتبر درگاه سان‌پی"
    err = data.get("error")
    if isinstance(err, dict):
        code = str(err.get("code") or "").strip()
        if code:
            return f"خطای درگاه سان‌پی ({code})"
    return "درخواست سان‌پی ناموفق بود"


def _parse_verified_payment(
    data: dict[str, Any],
    *,
    token: str,
    expected_amount: int,
) -> VerifyResult | tuple[dict[str, Any], int]:
    """Return paid (result, amount) or a failed VerifyResult."""
    if not _is_success_flag(data.get("success")):
        return VerifyResult(
            ok=False,
            external_ref=token,
            message=_api_error_text(data),
            raw=data,
        )
    result = data.get("data") if isinstance(data.get("data"), dict) else {}
    try:
        paid_amount = _safe_int((result or {}).get("amount"), field="مبلغ")
    except ValueError:
        return VerifyResult(
            ok=False,
            external_ref=token,
            message="مبلغ تأییدشده نامعتبر است",
            raw=data,
        )
    if paid_amount != expected_amount:
        logger.warning(
            "sunpay verify amount mismatch token=%s expected=%s paid=%s",
            token[:16],
            expected_amount,
            paid_amount,
        )
        return VerifyResult(
            ok=False,
            external_ref=token,
            amount=paid_amount,
            message="مبلغ تأییدشده با سفارش هم‌خوانی ندارد",
            raw=data,
        )
    return (result or {}), paid_amount


def _invoice_matches_settlement(
    result: dict[str, Any],
    *,
    token: str,
    paid_amount: int,
    data: dict[str, Any],
    expected_invoice_id: int | None,
) -> VerifyResult | None:
    """None when ok; otherwise a failed VerifyResult."""
    if expected_invoice_id is None:
        return None
    raw_invoice = result.get("invoice_id")
    if raw_invoice is None or str(raw_invoice).strip() == "":
        return VerifyResult(
            ok=False,
            external_ref=token,
            amount=paid_amount,
            message="شناسه فاکتور در پاسخ درگاه نیست",
            raw=data,
        )
    try:
        if _safe_int(raw_invoice, field="invoice_id") != int(expected_invoice_id):
            logger.warning(
                "sunpay verify invoice mismatch token=%s expected=%s got=%s",
                token[:16],
                expected_invoice_id,
                raw_invoice,
            )
            return VerifyResult(
                ok=False,
                external_ref=token,
                amount=paid_amount,
                message="شناسه فاکتور با تسویه هم‌خوانی ندارد",
                raw=data,
            )
    except ValueError as exc:
        return VerifyResult(
            ok=False,
            external_ref=token,
            amount=paid_amount,
            message=str(exc),
            raw=data,
        )
    return None


class SunPayAdapter:
    name = "sunpay"

    def __init__(self, *, api_key: str, pay_url: str):
        self.api_key = (api_key or "").strip()
        # Store raw; validate on use so create_checkout can mark FAILED inside its try.
        self.pay_url = (pay_url or "").strip().rstrip("/")

    def _require_config(self) -> None:
        if self.api_key in _PLACEHOLDER_KEYS:
            raise ValueError("کلید API سان‌پی تنظیم نشده")
        self.pay_url = validate_sunpay_pay_url(self.pay_url)

    def _request_url(self) -> str:
        return f"{self.pay_url}/api/request"

    def _verify_url(self) -> str:
        return f"{self.pay_url}/api/verified"

    def checkout_page_url(self, token: str) -> str:
        return f"{self.pay_url}/pay/{token}"

    async def create_checkout(self, req: CheckoutRequest) -> CheckoutResult:
        self._require_config()
        amount = _safe_int(req.amount, field="مبلغ")
        if amount < MIN_AMOUNT_TOMAN:
            raise ValueError(f"حداقل مبلغ سان‌پی {MIN_AMOUNT_TOMAN} تومان است")
        invoice_id = _safe_int(req.settlement_id, field="invoice_id")
        if invoice_id <= 0:
            raise ValueError("invoice_id باید بزرگ‌تر از صفر باشد")
        callback = (req.callback_url or "").strip()
        # Local/dev may use http://127.0.0.1 — allow non-https only for loopback callbacks
        # that never leave our process; production PUBLIC_BASE_URL is https.
        try:
            cb_parts = urlparse(callback)
        except ValueError as exc:
            raise ValueError("آدرس بازگشت سان‌پی نامعتبر است") from exc
        if cb_parts.scheme not in {"http", "https"} or not cb_parts.netloc:
            raise ValueError("آدرس بازگشت سان‌پی نامعتبر است")

        payload = {
            "api_key": self.api_key,
            "callback": callback,
            "amount": amount,
            "invoice_id": invoice_id,
        }
        try:
            resp = await _http().request(
                "GET",
                self._request_url(),
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            data = resp.json() if resp.content else {}
        except httpx.HTTPError as exc:
            logger.warning("sunpay request network error: %s", exc)
            raise ValueError("خطا در ارتباط با درگاه سان‌پی") from exc
        except ValueError as exc:
            logger.warning("sunpay request non-json response: %s", exc)
            raise ValueError("پاسخ نامعتبر درگاه سان‌پی") from exc

        if not isinstance(data, dict) or not _is_success_flag(data.get("success")):
            raise ValueError(_api_error_text(data))
        result = data.get("data") if isinstance(data.get("data"), dict) else {}
        token = str((result or {}).get("token") or "").strip()
        if not token:
            raise ValueError("توکن پرداخت سان‌پی دریافت نشد")
        return CheckoutResult(
            external_ref=token,
            checkout_url=self.checkout_page_url(token),
            raw=data,
        )

    async def verify(
        self,
        *,
        external_ref: str,
        amount: int,
        callback_params: dict[str, Any],
        expected_invoice_id: int | None = None,
    ) -> VerifyResult:
        token = str(external_ref or "").strip()
        cb_token = str(callback_params.get("token") or "").strip()
        if cb_token and token and cb_token.lower() != token.lower():
            return VerifyResult(
                ok=False,
                external_ref=token,
                message="توکن تراکنش با تسویه هم‌خوانی ندارد",
            )
        if cb_token and not token:
            token = cb_token
        if not token:
            return VerifyResult(ok=False, external_ref="", message="توکن تراکنش موجود نیست")

        # Docs §5.1: only look up / verify when callback success=1.
        if "success" not in callback_params or not _is_success_flag(
            callback_params.get("success")
        ):
            return VerifyResult(
                ok=False,
                external_ref=token,
                message="پرداخت توسط کاربر تکمیل نشد",
            )

        try:
            expected_amount = _safe_int(amount, field="مبلغ")
        except ValueError as exc:
            return VerifyResult(ok=False, external_ref=token, message=str(exc))

        try:
            self._require_config()
        except ValueError as exc:
            return VerifyResult(ok=False, external_ref=token, message=str(exc))

        payload = {"api_key": self.api_key, "token": token}
        try:
            # Docs allow GET or POST; POST keeps the JSON body reliable.
            resp = await _http().request(
                "POST",
                self._verify_url(),
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            data = resp.json() if resp.content else {}
        except httpx.HTTPError as exc:
            logger.warning("sunpay verify network error: %s", exc)
            return VerifyResult(
                ok=False,
                external_ref=token,
                message="خطا در ارتباط با درگاه سان‌پی",
            )
        except ValueError:
            logger.warning("sunpay verify non-json response")
            return VerifyResult(
                ok=False,
                external_ref=token,
                message="پاسخ نامعتبر درگاه سان‌پی",
            )

        if not isinstance(data, dict):
            return VerifyResult(
                ok=False,
                external_ref=token,
                message="پاسخ نامعتبر درگاه سان‌پی",
            )

        parsed = _parse_verified_payment(
            data, token=token, expected_amount=expected_amount
        )
        if isinstance(parsed, VerifyResult):
            return parsed
        result, paid_amount = parsed

        invoice_err = _invoice_matches_settlement(
            result,
            token=token,
            paid_amount=paid_amount,
            data=data,
            expected_invoice_id=expected_invoice_id,
        )
        if invoice_err is not None:
            return invoice_err

        reference = str(result.get("reference") or "").strip()
        return VerifyResult(
            ok=True,
            external_ref=token,
            amount=paid_amount,
            message=reference or "verified",
            raw=data,
        )
