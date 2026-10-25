"""
Seed the contact page: its row (model defaults hold the texts), the
message topics, and one location per active branch, linked to it so the
branch's name, address and phone show until they are overridden.
Only creates rows; existing branches are not modified.
"""

from django.db import migrations

TOPICS = ["ثبت‌نام", "امور آموزشی", "شهریه و امور مالی", "پیشنهاد یا انتقاد", "سایر"]


def seed(apps, schema_editor):
    ContactPage = apps.get_model("website", "ContactPage")
    ContactTopic = apps.get_model("website", "ContactTopic")
    ContactLocation = apps.get_model("website", "ContactLocation")
    Branch = apps.get_model("school", "Branch")

    page, _ = ContactPage.objects.get_or_create(pk=1)

    # Only seed empty lists, so re-running never duplicates content.
    if not page.topics.exists():
        ContactTopic.objects.bulk_create(
            ContactTopic(page=page, title=title, order=i) for i, title in enumerate(TOPICS, start=1)
        )
    if not page.locations.exists():
        branches = Branch.objects.filter(is_active=True).order_by("order", "name")
        ContactLocation.objects.bulk_create(
            ContactLocation(page=page, branch=branch, order=i) for i, branch in enumerate(branches, start=1)
        )


def unseed(apps, schema_editor):
    for name in ("ContactTopic", "ContactLocation", "ContactPage"):
        apps.get_model("website", name).objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0003_contact"),
        ("school", "0006_assign_subject_colors"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
