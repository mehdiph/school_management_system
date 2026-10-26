from django import template

register = template.Library()


@register.filter
def social_only(links):
    """The footer's social links that point somewhere (seeded rows are '#')."""
    return [link for link in links if link.kind == "social" and link.url.strip() not in ("", "#")]


@register.filter
def nav_state(url, path):
    """
    How a navbar item relates to the current page: "page" on its own URL,
    "section" on a page under it (/blog/post/…/ under /blog/), else "".
    Only site paths other than "/" count as sections.
    """

    url = (url or "").strip()
    if url == path:
        return "page"
    if url.startswith("/") and url != "/" and url.endswith("/") and path.startswith(url):
        return "section"
    return ""
