"""
Deactivate the four invented teachers that 0002 seeded on the landing
page: a public page must not present made-up people as the school's
teachers (ADR-025).

Only untouched seed rows change: the exact seed name and specialty, no
linked teacher and no uploaded photo, still active. Rows an admin has
edited in any of those ways are left alone. They are deactivated, not
deleted; the reverse re-activates only inactive rows matching the same
conditions. (If an admin had deactivated one by hand before this
migration, a rollback turns it back on.)
"""

from django.db import migrations

SEED_TEACHERS = [
    ("علی رضایی", "استاد ریاضی"),
    ("سعید محمدی", "استاد علوم"),
    ("ماریا کریمی", "استاد زبان"),
    ("ندا حسینی", "استاد هنر"),
]


def _untouched_seed_rows(apps):
    LandingTeacher = apps.get_model("website", "LandingTeacher")
    pks = []
    for name, specialty in SEED_TEACHERS:
        pks += LandingTeacher.objects.filter(
            name_override=name,
            specialty_override=specialty,
            teacher__isnull=True,
            photo_override="",
        ).values_list("pk", flat=True)
    return LandingTeacher.objects.filter(pk__in=pks)


def hide(apps, schema_editor):
    _untouched_seed_rows(apps).filter(is_active=True).update(is_active=False)


def show(apps, schema_editor):
    _untouched_seed_rows(apps).filter(is_active=False).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0012_teachers_menu"),
    ]

    operations = [
        migrations.RunPython(hide, show),
    ]
