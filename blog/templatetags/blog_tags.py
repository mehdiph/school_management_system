"""
Template helpers of the blog (public pages and «نوشته‌های من»).

    {% load blog_tags %}
    {{ post.published_dt|iso }}        ->  2026-11-03T09:30:00+03:30
    {{ post.body|body }}               ->  the body, sanitized again (ADR-026)
    {{ block|ld_json }}                ->  <script type="application/ld+json">…</script>
    {% page_url posts 2 %}             ->  ?page=2 (keeps ?q= on the search page)
    {{ post|post_state }}              ->  draft / submitted / scheduled / published / archived
"""

import json

from django import template
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.safestring import mark_safe

from blog import content

register = template.Library()

BACKSLASH = chr(92)
# Characters that could end the data block or start markup inside it, as
# JSON escapes (the same set as Django's json_script).
_JSON_ESCAPES = {ord(c): f"{BACKSLASH}u{ord(c):04X}" for c in "<>&"}


@register.filter
def iso(value):
    """An aware datetime in Tehran time, ISO 8601: for ``<time datetime>`` and meta tags."""

    if not value:
        return ""
    return timezone.localtime(value).isoformat(timespec="seconds")


@register.filter
def body(html):
    """A post's stored body, run through the allow-list once more on the way out."""

    return mark_safe(content.sanitize(html))


@register.filter
def ld_json(data):
    """A JSON-LD data block. It is not a script, so the CSP doesn't block it (D19)."""

    text = json.dumps(data, ensure_ascii=False).translate(_JSON_ESCAPES)
    return format_html('<script type="application/ld+json">{}</script>', mark_safe(text))


@register.filter
def page_numbers(posts):
    """The page numbers to link, with "…" for long runs: 1 … 4 5 6 … 12."""

    return posts.paginator.get_elided_page_range(posts.number, on_each_side=1, on_ends=1)


@register.simple_tag(takes_context=True)
def page_url(context, number):
    """The URL of page ``number`` of the current list, keeping the search query."""

    params = {}
    query = context.get("listing") and context["listing"].query
    if query:
        params["q"] = query
    if number > 1:
        params["page"] = number
    path = context["request"].path
    return f"{path}?{urlencode(params)}" if params else path


@register.filter
def post_state(post):
    """The state a badge shows: the status, or "scheduled" for a published post whose time hasn't come."""

    return "scheduled" if post.is_scheduled else post.status
