"""
Point the seeded «معلمان» menu row at /teachers/. Only rows still at the
seed's "#" change; the reverse only resets rows still at /teachers/. Rows
an admin has renamed or linked are left alone. There is no «معلمان»
footer row in the seed.
"""

from django.db import migrations

TITLE = "معلمان"
URL = "/teachers/"


def _set_url(apps, old, new):
    apps.get_model("website", "NavMenuItem").objects.filter(title=TITLE, url=old).update(url=new)


def link_teachers(apps, schema_editor):
    _set_url(apps, "#", URL)


def unlink_teachers(apps, schema_editor):
    _set_url(apps, URL, "#")


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0011_teacher_slug"),
    ]

    operations = [
        migrations.RunPython(link_teachers, unlink_teachers),
    ]
