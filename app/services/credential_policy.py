"""Unified credential / password policy (Phase D1).

Source of truth: PasarGuard ``PasswordValidator.validate_password``
(``PasarGuard/panel`` ``app/models/validators.py``).

Do not invent stricter rules beyond PasarGuard + our placeholder ban.
"""

from __future__ import annotations

import re

# PasarGuard special-character class (must match panel PasswordValidator).
_PG_SPECIAL_RE = re.compile(r"[!@#$%^&*()\-_=+\[\]{}|;:,.<>?/~`]")
_PG_SPECIAL_CHARS = "!@#$%^&*()-_=+[]{}|;:,.<>?/~`"


def validate_password_strength(
    password: str,
    *,
    username: str | None = None,
) -> tuple[bool, str]:
    """Return ``(ok, persian_error)``. Empty error when ok.

    Mirrors PasarGuard admin password rules; optional username ban matches PG
    ``check_username`` behavior.
    """
    from app.services.security_policy import is_placeholder_password

    p = password or ""
    if not p:
        return False, "رمز عبور الزامی است."

    errors: list[str] = []
    encoded_len = len(p.encode("utf-8"))
    if encoded_len > 72:
        errors.append("رمز عبور حداکثر ۷۲ بایت باشد.")
    if len(p) < 12:
        errors.append("رمز عبور باید حداقل ۱۲ کاراکتر باشد.")
    if len(re.findall(r"\d", p)) < 2:
        errors.append("رمز عبور باید حداقل دو رقم داشته باشد.")
    if len(re.findall(r"[A-Z]", p)) < 2:
        errors.append("رمز عبور باید حداقل دو حرف بزرگ انگلیسی داشته باشد.")
    if len(re.findall(r"[a-z]", p)) < 2:
        errors.append("رمز عبور باید حداقل دو حرف کوچک انگلیسی داشته باشد.")
    if not _PG_SPECIAL_RE.search(p):
        errors.append("رمز عبور باید حداقل یک کاراکتر خاص مجاز داشته باشد.")
    if '"' in p:
        errors.append('رمز عبور نباید شامل کاراکتر " باشد.')
    if username and username.strip() and username.strip().lower() in p.lower():
        errors.append("رمز عبور نباید شامل نام کاربری باشد.")
    if is_placeholder_password(p):
        errors.append("این رمز عبور نمونه/ضعیف است؛ رمز قوی‌تری انتخاب کنید.")

    if errors:
        return False, errors[0]
    return True, ""


def password_policy_hint_fa() -> str:
    """Short Persian hint for forms (matches PasarGuard rules)."""
    return (
        "حداقل ۱۲ کاراکتر، شامل حداقل دو رقم، دو حرف بزرگ، دو حرف کوچک "
        "و یک کاراکتر خاص"
    )


def generate_compliant_password(length: int = 14) -> str:
    """Generate a password that always satisfies ``validate_password_strength``."""
    import secrets
    import string

    length = max(14, int(length))
    specials = _PG_SPECIAL_CHARS
    alphabet = string.ascii_letters + string.digits + specials
    for _ in range(32):
        required = (
            [secrets.choice(string.ascii_lowercase) for _ in range(2)]
            + [secrets.choice(string.ascii_uppercase) for _ in range(2)]
            + [secrets.choice(specials)]
            + [secrets.choice(string.digits) for _ in range(2)]
        )
        required += [secrets.choice(alphabet) for _ in range(length - len(required))]
        secrets.SystemRandom().shuffle(required)
        pwd = "".join(required)
        ok, _ = validate_password_strength(pwd)
        if ok:
            return pwd
    return "AaBb12!@#$xY" + secrets.token_hex(2)