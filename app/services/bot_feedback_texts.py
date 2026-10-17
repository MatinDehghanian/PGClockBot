"""Short feedback texts that many bot handlers send (alerts, toasts and replies).

One definition per text keeps the wording identical everywhere it appears, so
a later rewording changes every screen at once and shows up in the bot UI
snapshots. These texts are fixed; admin-editable texts live in settings.
"""

from __future__ import annotations

NOT_ADMIN = "ادمین نیستید"
NOT_RESELLER = "نماینده نیستید"
RESELLERS_ONLY = "فقط نمایندگان"
NO_ACCESS = "دسترسی ندارید"
NO_ACCESS_REPLY = "دسترسی ندارید."
ACTION_NOT_ALLOWED = "اجازه این عمل را ندارید"
NOT_FOUND = "یافت نشد"
INVALID = "نامعتبر"
CANCELLED = "لغو شد."
SAVED = "ذخیره شد"
DELETED = "حذف شد"
ENTER_VALID_NUMBER = "عدد معتبر بفرستید."
