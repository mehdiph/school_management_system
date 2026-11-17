"""
The one place that decides whether a link may be stored or shown (D13).

A link that reaches a student is https, with a host and no ``user@host``
form, so ``https://skyroom.online@evil.com`` can't pass for the platform. If
the platform lists allowed domains, the host must be one of them or a
subdomain of one. Models, forms and the importer call these; the student page
checks again when it renders, so a row written any other way can't produce a
dangerous link.
"""

import re
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

MAX_URL_LENGTH = 2000

_HTTPS_ONLY = URLValidator(schemes=["https"])
_DOMAIN = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_SPACE_OR_CONTROL = re.compile(r"[\s\x00-\x1f\x7f\\]")
_DOMAIN_SEPARATORS = re.compile(r"[\s,،;؛]+")


def split_domains(text):
    """The platform's «دامنه‌های مجاز» text -> lower-case domains."""

    return [part.lower() for part in _DOMAIN_SEPARATORS.split(text or "") if part]


def validate_domains(text):
    for domain in split_domains(text):
        if not _DOMAIN.match(domain):
            raise ValidationError(f"«{domain}» دامنه‌ی معتبری نیست؛ فقط نام دامنه را بنویسید، مثل skyroom.online")


def validate_https_url(value, allowed_domains=None):
    """``allowed_domains``: the platform's text, or ``None`` / empty for any domain."""

    if len(value) > MAX_URL_LENGTH:
        raise ValidationError("لینک خیلی طولانی است.")
    if _SPACE_OR_CONTROL.search(value):
        raise ValidationError("لینک نباید فاصله یا نویسه‌ی نامعتبر داشته باشد.")
    if not value.lower().startswith("https://"):
        raise ValidationError("لینک باید با https:// شروع شود.")
    try:
        _HTTPS_ONLY(value)
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
    except (ValidationError, ValueError):
        raise ValidationError("لینک معتبر نیست.") from None
    if not host:
        raise ValidationError("لینک معتبر نیست.")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise ValidationError("لینک نباید نام کاربری یا @ در نشانی داشته باشد.")

    domains = split_domains(allowed_domains)
    if domains and not any(host == domain or host.endswith(f".{domain}") for domain in domains):
        raise ValidationError("دامنه‌ی این لینک جزو دامنه‌های مجاز این پلتفرم نیست.")


def validate_button_url(value):
    """An announcement's button: an https link, or a path inside this site."""

    if value.startswith("/"):
        if value.startswith("//") or _SPACE_OR_CONTROL.search(value) or len(value) > MAX_URL_LENGTH:
            raise ValidationError("مسیر داخلی معتبر نیست.")
        return
    validate_https_url(value)


def _passes(validator, value, *args):
    try:
        validator(value, *args)
    except ValidationError:
        return False
    return True


def safe_https_url(value):
    """``value`` if it may be rendered as a link, else "" (the check on the way out)."""

    return value if value and _passes(validate_https_url, value) else ""


def safe_button_url(value):
    return value if value and _passes(validate_button_url, value) else ""
