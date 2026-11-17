"""
Encrypting personal passwords, access codes and links at rest (D14).

``settings.ONLINE_ACCESS_KEYS`` is a list of Fernet keys: the first encrypts,
all decrypt, so a key can be rotated (``reencrypt_online_access``,
``docs/apps/online_classes.md``). This module is the only reader of that
setting. It never logs a value.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class DecryptionFailed(Exception):
    """No configured key opens this value, or it has expired."""


@lru_cache(maxsize=4)
def _build(keys):
    if not keys:
        raise ImproperlyConfigured("ONLINE_ACCESS_KEYS is empty; see docs/apps/online_classes.md.")
    return MultiFernet([Fernet(key) for key in keys]), Fernet(keys[0])


def _fernets():
    return _build(tuple(settings.ONLINE_ACCESS_KEYS))


def encrypt(text):
    """Text -> token; empty stays empty, so "nothing stored" is visible without a key."""

    return _fernets()[0].encrypt(text.encode()).decode() if text else ""


def decrypt(token, ttl=None):
    """Token -> text, or ``DecryptionFailed``. ``ttl`` in seconds refuses an older token."""

    if not token:
        return ""
    try:
        return _fernets()[0].decrypt(token.encode(), ttl=ttl).decode()
    except InvalidToken:
        raise DecryptionFailed from None


def uses_newest_key(token):
    """True when the newest key alone opens ``token`` (nothing to re-encrypt)."""

    if not token:
        return True
    try:
        _fernets()[1].decrypt(token.encode())
    except InvalidToken:
        return False
    return True


def reencrypt(token):
    """The same text under the newest key, or ``DecryptionFailed``."""

    if not token:
        return ""
    try:
        return _fernets()[0].rotate(token.encode()).decode()
    except InvalidToken:
        raise DecryptionFailed from None
