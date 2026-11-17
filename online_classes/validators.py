"""
The one place that decides whether a link may be stored or shown (D13).

A link that reaches a student is https, with a plain-ASCII host and no
``user@host`` form, so ``https://skyroom.online@evil.com`` can't pass for the
platform. If the platform lists allowed domains, the host must be one of them
or a subdomain of one. Models, forms and the importer call these; the student
page checks again when it renders, so a row written any other way can't
produce a dangerous link.

Staff copy links out of Persian messengers, which slip invisible direction
marks into the text. ``clean_url`` removes them before anything is checked,
and callers store the cleaned link (2026-11 allowed-domains fix).
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

ZWNJ = "‌"
#: Bidi controls and zero-width characters that are never part of a link:
#: ZWSP, LRM/RLM, the embeddings and overrides, the isolates, BOM, and the
#: Arabic letter mark.
INVISIBLE = "​‎‏‪-‮⁦-⁩﻿؜"
_INVISIBLE = re.compile(f"[{INVISIBLE}]")
#: In a domain nothing invisible is meaningful, ZWNJ and ZWJ included.
_INVISIBLE_IN_DOMAIN = re.compile(f"[{INVISIBLE}‌‍]")
#: Scheme and authority: everything before the path, query or fragment.
_SCHEME_AND_HOST = re.compile(r"^(?:[^:/?#]*:)?(?://[^/?#]*)?")

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_FULL_STOPS = str.maketrans({"۔": ".", "٫": ".", "。": ".", "．": "."})
_URL_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://")
_PORT = re.compile(r":\d*$")


# ----------------------------------------------------------------------
# Links
# ----------------------------------------------------------------------

def clean_url(value):
    """``value`` without invisible marks or surrounding whitespace; what callers store.

    Bidi controls and zero-width characters go everywhere; ZWNJ only from the
    scheme and host, since Persian slugs in a path use it.
    """

    value = _INVISIBLE.sub("", value or "").strip()
    head = _SCHEME_AND_HOST.match(value).group(0)
    return head.replace(ZWNJ, "") + value[len(head):]


def validate_https_url(value, allowed_domains=None):
    """``allowed_domains``: the platform's text, or ``None`` / empty for any domain.

    Checks ``clean_url(value)``, the link that will be stored.
    """

    value = clean_url(value)
    if len(value) > MAX_URL_LENGTH:
        raise ValidationError("لینک خیلی طولانی است.")
    if _SPACE_OR_CONTROL.search(value):
        raise ValidationError("لینک نباید فاصله یا نویسه‌ی نامعتبر داشته باشد.")
    if not value.lower().startswith("https://"):
        raise ValidationError("لینک باید با https:// شروع شود.")
    try:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
    except ValueError:
        raise ValidationError("لینک معتبر نیست.") from None
    if host and not host.isascii():
        raise ValidationError("دامنه‌ی لینک باید با حروف انگلیسی باشد.")
    try:
        _HTTPS_ONLY(value)
    except ValidationError:
        raise ValidationError("لینک معتبر نیست.") from None
    if not host:
        raise ValidationError("لینک معتبر نیست.")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise ValidationError("لینک نباید نام کاربری یا @ در نشانی داشته باشد.")

    host = host.rstrip(".")
    domains = split_domains(allowed_domains)
    if domains and not any(host == domain or host.endswith(f".{domain}") for domain in domains):
        raise ValidationError(
            f"دامنه‌ی این لینک ({host}) جزو دامنه‌های مجاز این پلتفرم نیست. "
            f"دامنه‌های مجاز: {'، '.join(domains)} (و زیردامنه‌هایشان)."
        )


def validate_button_url(value):
    """An announcement's button: an https link, or a path inside this site."""

    value = clean_url(value)
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
    """The cleaned ``value`` if it may be rendered as a link, else "" (the check on the way out)."""

    value = clean_url(value)
    return value if value and _passes(validate_https_url, value) else ""


def safe_button_url(value):
    value = clean_url(value)
    return value if value and _passes(validate_button_url, value) else ""


# ----------------------------------------------------------------------
# A platform's allowed domains
# ----------------------------------------------------------------------

def _normalise_domain(text):
    """One entry -> ``(domain, None)``, ``(None, error)``, or ``(None, None)`` when empty.

    Accepts what admins paste: a whole link, a port, ``*.``, ``www.``, a
    trailing dot, Persian digits and full stops. A leading ``www.`` is dropped
    because a domain always covers its subdomains (D1).
    """

    shown = _INVISIBLE.sub("", text).strip()  # quoted back in errors; keeps a Persian word's ZWNJ
    domain = _INVISIBLE_IN_DOMAIN.sub("", shown).strip().lower()
    if not domain:
        return None, None
    domain = domain.translate(_PERSIAN_DIGITS).translate(_FULL_STOPS)
    domain = _URL_SCHEME.sub("", domain).lstrip("/")
    domain = re.split(r"[/?#]", domain, maxsplit=1)[0]
    domain = _PORT.sub("", domain.rsplit("@", 1)[-1]).rstrip(".")
    domain = domain.removeprefix("*.")
    if domain.startswith("www.") and "." in domain[4:]:
        domain = domain[4:]
    if not domain.isascii():
        return None, f"«{shown}»: نام دامنه باید با حروف انگلیسی باشد، مثل skyroom.online"
    if not _DOMAIN.match(domain):
        return None, f"«{shown}» دامنه‌ی معتبری نیست؛ فقط نام دامنه را بنویسید، مثل skyroom.online"
    return domain, None


def normalise_domains(text):
    """The platform's «دامنه‌های مجاز» text -> ``(domains, errors)``, domains without duplicates."""

    domains, errors = [], []
    for part in _DOMAIN_SEPARATORS.split(text or ""):
        domain, error = _normalise_domain(part)
        if error:
            errors.append(error)
        elif domain and domain not in domains:
            domains.append(domain)
    return domains, errors


def tidy_domains(text):
    """What the platform stores: one normalised domain per line, or ``text`` unchanged if a line is unusable."""

    domains, errors = normalise_domains(text)
    return text if errors else "\n".join(domains)


def split_domains(text):
    """The usable domains in ``text``; unusable lines are ignored here and refused on save."""

    return normalise_domains(text)[0]


def validate_domains(text):
    errors = normalise_domains(text)[1]
    if errors:
        raise ValidationError(errors)
