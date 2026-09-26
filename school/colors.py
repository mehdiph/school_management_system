"""
Subject colours.

A subject's colour is picked in the admin and ends up in ``style``
attributes (``--subject-color``) and in the PDF, so it is only ever
stored as a strict ``#rrggbb`` string (``hex_color_validator``) and
re-checked with ``safe_hex`` right before rendering -- a bad value in
the database can never turn into arbitrary CSS.
"""

import re

from django.core.validators import RegexValidator

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}\Z")  # \Z: "$" would accept a trailing newline

hex_color_validator = RegexValidator(
    regex=HEX_COLOR_RE.pattern,
    message="رنگ باید یک کد هگز شش‌رقمی مثل ‎#2563eb‎ باشد.",
    code="invalid_hex_color",
)

DEFAULT_SUBJECT_COLOR = "#d96a30"  # the app's --primary

#: Curated palette: saturated mid/dark tones that stay distinguishable
#: from each other, keep >= 3:1 contrast against white (non-text UI),
#: and still read as a tint when mixed ~12% into a white cell in print.
SUBJECT_PALETTE = (
    ("#2563eb", "آبی"),
    ("#15803d", "سبز"),
    ("#c2410c", "نارنجی"),
    ("#7c3aed", "بنفش"),
    ("#db2777", "صورتی"),
    ("#0f766e", "فیروزه‌ای"),
    ("#a16207", "خردلی"),
    ("#dc2626", "قرمز"),
    ("#0e7490", "آبی آسمانی"),
    ("#4f46e5", "نیلی"),
    ("#4d7c0f", "سبز زیتونی"),
    ("#b45309", "قهوه‌ای"),
    ("#9333ea", "ارغوانی"),
    ("#475569", "خاکستری"),
)

DARK_TEXT = "#1f2937"
LIGHT_TEXT = "#ffffff"


def is_hex_color(value):
    return isinstance(value, str) and bool(HEX_COLOR_RE.match(value))


def safe_hex(value, fallback=DEFAULT_SUBJECT_COLOR):
    """``value`` lower-cased if it is a strict ``#rrggbb``, else ``fallback``."""

    return value.lower() if is_hex_color(value) else fallback


def _rgb(hex_color):
    hex_color = safe_hex(hex_color)
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))


def relative_luminance(hex_color):
    """WCAG 2.x relative luminance, 0 (black) .. 1 (white)."""

    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in _rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(color_a, color_b):
    la, lb = sorted((relative_luminance(color_a), relative_luminance(color_b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def readable_text_color(background):
    """Whichever of dark / white text contrasts more with ``background``."""

    if contrast_ratio(background, DARK_TEXT) >= contrast_ratio(background, LIGHT_TEXT):
        return DARK_TEXT
    return LIGHT_TEXT


def tint(hex_color, amount, base="#ffffff"):
    """
    ``hex_color`` mixed ``amount`` (0..1) into ``base`` -- the server-side
    twin of CSS ``color-mix(in srgb, color amount, base)``, for WeasyPrint,
    which does not support ``color-mix()``.
    """

    mixed = (
        round(c * amount + b * (1 - amount))
        for c, b in zip(_rgb(hex_color), _rgb(base))
    )
    return "#" + "".join(f"{c:02x}" for c in mixed)
