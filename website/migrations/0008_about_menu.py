"""
Menu changes for the «درباره ما» page.

* The seeded «درباره ما» menu and footer rows point at /about/. Only rows
  still at the seed's "#" change; the reverse only resets rows still at
  /about/.
* The seeded «کلاس ها» menu item is deactivated (not deleted: one tick in
  «تنظیمات سایت» brings it back). Only the row still at "#" changes; the
  reverse re-activates only an inactive «کلاس ها» row still at "#".

Rows an admin has already renamed or linked are left alone.
"""

from django.db import migrations

ABOUT_TITLE = "درباره ما"
ABOUT_URL = "/about/"
CLASSES_TITLE = "کلاس ها"


def _set_about_url(apps, old, new):
    for name in ("NavMenuItem", "FooterLink"):
        apps.get_model("website", name).objects.filter(title=ABOUT_TITLE, url=old).update(url=new)


def link_about(apps, schema_editor):
    _set_about_url(apps, "#", ABOUT_URL)


def unlink_about(apps, schema_editor):
    _set_about_url(apps, ABOUT_URL, "#")


def _set_classes_active(apps, was, now):
    NavMenuItem = apps.get_model("website", "NavMenuItem")
    NavMenuItem.objects.filter(title=CLASSES_TITLE, url="#", is_active=was).update(is_active=now)


def hide_classes(apps, schema_editor):
    _set_classes_active(apps, True, False)


def show_classes(apps, schema_editor):
    _set_classes_active(apps, False, True)


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0007_seed_about"),
    ]

    operations = [
        migrations.RunPython(link_about, unlink_about),
        migrations.RunPython(hide_classes, show_classes),
    ]
