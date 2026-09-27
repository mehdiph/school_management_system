"""
Moves national codes onto ``User.national_code`` before 0005 drops
``Staff.national_code``.

1. Every ``Staff.national_code`` is copied to its user -- it was entered
   explicitly, so it wins. Codes failing the checksum are still copied
   (dropping them would lose data) and reported.
2. Users with no staff row whose ``username`` is a valid national code
   get it too, unless a staff member already claimed that code.

Nothing is overwritten silently: every conflict or oddity is printed
during ``migrate``. The checksum is copied here on purpose so this
migration keeps doing the same thing if accounts/validators.py changes.

Reverse copies ``User.national_code`` back onto staff rows.
"""

import re

from django.db import migrations


def _is_valid(code):
    if not re.fullmatch(r"\d{10}", code or "") or len(set(code)) == 1:
        return False
    check = int(code[9])
    remainder = sum(int(code[i]) * (10 - i) for i in range(9)) % 11
    return check == remainder if remainder < 2 else check == 11 - remainder


def copy_to_user(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Staff = apps.get_model("staff", "Staff")

    report = []
    assigned = {}  # national code -> user id

    staff_rows = list(
        Staff.objects.select_related("user")
        .exclude(national_code__isnull=True)
        .exclude(national_code="")
        .order_by("id")
    )

    for staff in staff_rows:
        code = staff.national_code.strip()
        user = staff.user
        if not _is_valid(code):
            report.append(
                f"کد ملی پرسنل «{user.username}» ({code}) نامعتبر است؛ همان مقدار منتقل شد، اصلاح کنید."
            )
        if user.username != code and _is_valid(user.username):
            report.append(
                f"نام کاربری «{user.username}» شبیه کد ملی است ولی کد ملی پرسنلی او {code} است؛ "
                f"{code} ثبت شد."
            )
        user.national_code = code
        user.save(update_fields=["national_code"])
        assigned[code] = user.pk

    staff_user_ids = {staff.user_id for staff in staff_rows}
    candidates = (
        User.objects.filter(national_code__isnull=True)
        .exclude(pk__in=staff_user_ids)
        .order_by("id")
    )
    for user in candidates:
        code = user.username
        if not _is_valid(code):
            continue
        if code in assigned:
            owner = User.objects.get(pk=assigned[code])
            report.append(
                f"تعارض: نام کاربری «{user.username}» همان کد ملی ثبت‌شده برای پرسنل "
                f"«{owner.username}» است؛ برای «{user.username}» کد ملی ثبت نشد، دستی بررسی کنید."
            )
            continue
        user.national_code = code
        user.save(update_fields=["national_code"])
        assigned[code] = user.pk

    if report:
        print("\n  [staff.0004] انتقال کد ملی به کاربران:")
        for line in report:
            print(f"    - {line}")


def copy_back_to_staff(apps, schema_editor):
    Staff = apps.get_model("staff", "Staff")
    for staff in Staff.objects.select_related("user").exclude(user__national_code__isnull=True):
        staff.national_code = staff.user.national_code
        staff.save(update_fields=["national_code"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_national_code_and_must_change_password"),
        ("staff", "0003_optional_staff_fields"),
    ]

    operations = [
        migrations.RunPython(copy_to_user, copy_back_to_staff),
    ]
