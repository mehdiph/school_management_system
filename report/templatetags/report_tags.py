from django import template

register = template.Library()

@register.filter(name='to_persian')
def to_persian(value):
    """Converts English digits to Persian digits."""
    if value is None:
        return ""
    value = str(value)
    translation = value.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return value.translate(translation)
