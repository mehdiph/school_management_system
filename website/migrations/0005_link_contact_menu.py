"""
Point the seeded «تماس با ما» menu and footer rows at the new contact
page. Only rows still at the seed's "#" change, so a link an admin has
already edited is left alone; the reverse only resets rows still at
/contact/.
"""

from django.db import migrations

TITLE = "تماس با ما"
CONTACT_URL = "/contact/"


def _set_url(apps, old, new):
    for name in ("NavMenuItem", "FooterLink"):
        apps.get_model("website", name).objects.filter(title=TITLE, url=old).update(url=new)


def link(apps, schema_editor):
    _set_url(apps, "#", CONTACT_URL)


def unlink(apps, schema_editor):
    _set_url(apps, CONTACT_URL, "#")


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0004_seed_contact"),
    ]

    operations = [
        migrations.RunPython(link, unlink),
    ]
