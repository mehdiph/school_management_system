"""
Keep the permissions granted on the old ``Attendance`` model.

``0003`` renamed the model to ``SessionAttendance`` (and Django renamed its
content type), but permission codenames are not renamed with it: groups
and users holding ``attendance.change_attendance`` would silently lose it
when the app starts asking for ``attendance.*_sessionattendance``. This
renames the four existing permission rows in place, so every grant
follows. Only ``auth_permission`` rows change; no attendance row is
touched. On a fresh database there are no rows yet (``post_migrate``
creates the new ones), so it does nothing.
"""

from django.db import migrations

ACTIONS = ("add", "change", "delete", "view")


def _rename(apps, old_model, new_model, verbose_name):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")

    content_type = ContentType.objects.filter(app_label="attendance", model="sessionattendance").first()
    if content_type is None:
        return
    for action in ACTIONS:
        permission = Permission.objects.filter(
            content_type=content_type, codename=f"{action}_{old_model}"
        ).first()
        if permission is None or Permission.objects.filter(
            content_type=content_type, codename=f"{action}_{new_model}"
        ).exists():
            continue
        permission.codename = f"{action}_{new_model}"
        permission.name = f"Can {action} {verbose_name}"
        permission.save(update_fields=["codename", "name"])


def forwards(apps, schema_editor):
    _rename(apps, "attendance", "sessionattendance", "حضور و غیاب جلسه (بایگانی)")


def backwards(apps, schema_editor):
    _rename(apps, "sessionattendance", "attendance", "حضور و غیاب")


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0004_daily_attendance"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
