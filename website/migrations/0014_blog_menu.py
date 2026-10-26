"""
Point the seeded «وبلاگ» menu row at /blog/ and hide the seeded «مقاله»
row, which the blog replaces (D20 of the blog plan). Only rows still in
the seed's state change: «وبلاگ» at "#", «مقاله» active at "#". The
reverse resets only a «وبلاگ» row still at /blog/ and re-activates only
an inactive «مقاله» row still at "#". Rows an admin has renamed or
linked are left alone; the «مقاله» row is never deleted.
"""

from django.db import migrations

BLOG = "وبلاگ"
ARTICLE = "مقاله"
URL = "/blog/"


def _items(apps):
    return apps.get_model("website", "NavMenuItem").objects


def link_blog(apps, schema_editor):
    _items(apps).filter(title=BLOG, url="#").update(url=URL)
    _items(apps).filter(title=ARTICLE, url="#", is_active=True).update(is_active=False)


def unlink_blog(apps, schema_editor):
    _items(apps).filter(title=BLOG, url=URL).update(url="#")
    _items(apps).filter(title=ARTICLE, url="#", is_active=False).update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0013_hide_seed_teachers"),
    ]

    operations = [
        migrations.RunPython(link_blog, unlink_blog),
    ]
