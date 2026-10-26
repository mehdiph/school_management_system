"""
Plain-text helpers of the blog: Persian normalisation, search keys,
slugs and reading time. No HTML here (that is ``blog.content``).

Persian text arrives in several spellings of "the same" thing: Arabic
ي/ك/ى from some keyboards, Persian or Arabic-Indic digits, ZWNJ
(نیم‌فاصله) or a space or nothing between the halves of a word.
``normalize`` fixes what a reader would call a typo (the letters and the
spaces) and keeps ZWNJ, for text that is displayed; ``search_key`` folds
everything that should match into one string, for searching.
"""

import math
import re

from django.conf import settings
from django.utils.text import slugify

ZWNJ = "\u200c"

# Arabic letters typed for their Persian twins, and tatweel (کشیده).
_LETTERS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "\u0640": None})
# Spellings a search should not tell apart, though they are kept on display.
_LOOSE_LETTERS = str.maketrans({"ئ": "ی", "ۀ": "ه", "ة": "ه", "أ": "ا", "إ": "ا", "آ": "ا", "ؤ": "و"})
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_MARKS = re.compile("[\u064b-\u065f\u0670]")  # harakat, tanwin, hamza above, superscript alef
_ZW_RUNS = re.compile("[\u200c\u200d\u200e\u200f\ufeff]+")  # ZWNJ, ZWJ, direction marks, BOM
_SPACES = re.compile(r"\s+")


def normalize(text):
    """
    Display text with the Persian letters and single spaces: ي→ی, ك→ک,
    no tatweel, one ZWNJ at most between two letters, trimmed. Digits and
    ZWNJ are kept as typed.
    """

    text = (text or "").translate(_LETTERS)
    text = _ZW_RUNS.sub(lambda m: ZWNJ if ZWNJ in m.group() else "", text)
    text = _SPACES.sub(" ", text).strip()
    # A ZWNJ next to a space is a typing slip, never meant.
    return text.replace(f" {ZWNJ}", " ").replace(f"{ZWNJ} ", " ")


def search_key(text):
    """
    ``text`` folded for matching: normalised letters (also ئ→ی, ۀ→ه,
    أ/إ/آ→ا), ASCII digits, no diacritics, lower case, and **no ZWNJ and no spaces**, so «کتاب‌خوانی»,
    «کتاب خوانی» and «کتابخوانی» are the same key. A query matches a post
    when its key is contained in the post's key.
    """

    text = normalize(text).translate(_DIGITS).translate(_LOOSE_LETTERS)
    text = _MARKS.sub("", text).lower()
    return text.replace(ZWNJ, "").replace(" ", "")


def word_count(text):
    return len(normalize(text).split())


def reading_minutes(text):
    """Minutes to read ``text`` at ``BLOG_WORDS_PER_MINUTE``, at least 1."""

    return max(1, math.ceil(word_count(text) / settings.BLOG_WORDS_PER_MINUTE))


def summary(text, limit=200):
    """The first ``limit`` characters of ``text``, cut at a word, with «…» when cut."""

    text = normalize(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip("،؛,.:!؟?-–")
    return f"{cut}…"


def unique_slug(instance, text, *, field="slug", max_length=80, fallback="item", reserved=(), **scope):
    """
    A Unicode slug from ``text`` that no other row of ``instance``'s model
    (limited to ``scope``, e.g. ``section=...``) uses and that isn't in
    ``reserved``: «جشن-پاییز», «جشن-پاییز-2»… The shape of
    ``LandingTeacher._unique_slug``.
    """

    base = slugify(normalize(text), allow_unicode=True)[: max_length - 4].strip("-") or fallback
    others = type(instance)._default_manager.filter(**scope).exclude(pk=instance.pk)
    slug, n = base, 2
    while slug in reserved or others.filter(**{field: slug}).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug
