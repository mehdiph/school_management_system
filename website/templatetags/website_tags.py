from django import template

register = template.Library()


@register.filter
def social_only(links):
    """The footer's social links that point somewhere (seeded rows are '#')."""
    return [link for link in links if link.kind == "social" and link.url.strip() not in ("", "#")]
