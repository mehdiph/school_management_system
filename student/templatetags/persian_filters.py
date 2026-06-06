import jdatetime
from django import template

register = template.Library()

# ---------- Ordinal conversion ----------
# Simple mapping for 1–19. For larger numbers you can extend the logic.
_ORDINALS = {
    1: 'اول', 2: 'دوم', 3: 'سوم', 4: 'چهارم', 5: 'پنجم',
    6: 'ششم', 7: 'هفتم', 8: 'هشتم', 9: 'نهم', 10: 'دهم',
    11: 'یازدهم', 12: 'دوازدهم', 13: 'سیزدهم', 14: 'چهاردهم',
    15: 'پانزدهم', 16: 'شانزدهم', 17: 'هفدهم', 18: 'هجدهم',
    19: 'نوزدهم',
}
# Compound numbers like 20 (بیستم), 30 (سی‌ام), 21 (بیست و یکم)
_TENS = {
    20: 'بیستم', 30: 'سی‌ام', 40: 'چهلم', 50: 'پنجاهم',
    60: 'شصتم', 70: 'هفتادم', 80: 'هشتادم', 90: 'نودم',
    100: 'صدم',
}
_JOIN = ' و '  # "بیست و یکم"

@register.filter
def persian_ordinal(value):
    """Convert an integer to Persian ordinal word (e.g., 1 → اول)."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return value

    if n in _ORDINALS:
        return _ORDINALS[n]

    # Handle 20, 30, ..., 100 exactly
    if n in _TENS:
        return _TENS[n]

    # For numbers like 21, 34, 99
    tens = (n // 10) * 10
    ones = n % 10
    if tens >= 20 and ones > 0:
        return _ORDINALS[ones] + _JOIN + _TENS[tens]
    
    # Fallback – just show number as string
    return str(n)


# ---------- Jalali date formatting ----------
_PERSIAN_MONTHS = [
    'فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
    'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند'
]

@register.filter
def persian_date(jdate):
    """
    Convert a Jalali date string 'YYYY-MM-DD' to 'day monthName'
    Example: '1405-03-10' → '10 خرداد'
    """
    try:
        return f'{jdate.day} {_PERSIAN_MONTHS[jdate.month - 1]} {jdate.year}'
    except Exception:
        return jdate  # fail silently, show original