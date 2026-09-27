"""
Iranian national code (کد ملی): normalisation + checksum, and a password
validator that refuses the national code as a password.

Used by ``User.national_code``, the Excel user import and
``AUTH_PASSWORD_VALIDATORS``.
"""

import re

from django.core.exceptions import ValidationError

_TO_ASCII_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_national_code(value):
    """
    Whatever a spreadsheet or a form hands us -> a 10-character digit
    string, or "" when there is nothing.

    * Excel gives numbers back as int, or float (``12345678.0``);
    * Persian/Arabic digits become ASCII, anything else non-digit is dropped;
    * leading zeros lost by Excel are restored (``zfill(10)``).

    Does not validate: an 11-digit input stays 11 digits so the checksum
    rejects it instead of it being silently truncated.
    """

    if value is None:
        return ""
    if isinstance(value, bool):
        value = str(value)
    elif isinstance(value, float):
        value = str(int(value)) if value.is_integer() else str(value)
    elif isinstance(value, int):
        value = str(value)

    digits = re.sub(r"\D", "", str(value).translate(_TO_ASCII_DIGITS))
    return digits.zfill(10) if digits else ""


def is_valid_national_code(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{10}", value):
        return False
    if len(set(value)) == 1:  # 0000000000, 1111111111, ... pass the checksum but are not real
        return False

    check = int(value[9])
    remainder = sum(int(value[i]) * (10 - i) for i in range(9)) % 11
    return check == remainder if remainder < 2 else check == 11 - remainder


def validate_national_code(value):
    if not is_valid_national_code(value):
        raise ValidationError("کد ملی نامعتبر است.", code="invalid_national_code")


class NotNationalCodePasswordValidator:
    """The national code is the first-login password of imported users; it may not be kept."""

    def validate(self, password, user=None):
        national_code = getattr(user, "national_code", None)
        candidate = (password or "").strip().translate(_TO_ASCII_DIGITS)
        # Also the code typed without its leading zeros (0012345678 -> 12345678).
        if national_code and candidate.isdigit() and candidate.zfill(10) == national_code:
            raise ValidationError(
                "رمز عبور نباید با کد ملی یکسان باشد.",
                code="password_is_national_code",
            )

    def get_help_text(self):
        return "رمز عبور نباید با کد ملی شما یکسان باشد."
