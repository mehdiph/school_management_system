"""
Seed the «معلمان» page's row (model defaults hold the texts) and give
every existing teacher card its slug. No teachers and no groups are
created: who is published, and how they are grouped, is the school's
choice. Only creates the page row and fills the new, empty slug column.

The reverse points the cards back at the landing page's row (0011's
reverse re-adds that column empty) and deletes the teachers page row and
its groups.
"""

from django.db import migrations
from django.db.models import Q
from django.utils.text import slugify


def _name(card):
    # LandingTeacher.display_name, without the model's methods (historical model).
    if card.name_override.strip():
        return card.name_override.strip()
    if card.teacher_id:
        user = card.teacher.staff.user
        return f"{user.first_name} {user.last_name}".strip()
    return ""


def seed(apps, schema_editor):
    TeachersPage = apps.get_model("website", "TeachersPage")
    LandingTeacher = apps.get_model("website", "LandingTeacher")

    TeachersPage.objects.get_or_create(pk=1)

    without_slug = Q(slug__isnull=True) | Q(slug="")
    taken = set(LandingTeacher.objects.exclude(without_slug).values_list("slug", flat=True))
    for card in LandingTeacher.objects.filter(without_slug).select_related("teacher__staff__user").order_by("order", "id"):
        base = slugify(_name(card), allow_unicode=True)[:70].strip("-") or "teacher"
        slug, n = base, 2
        while slug in taken:
            slug, n = f"{base}-{n}", n + 1
        taken.add(slug)
        LandingTeacher.objects.filter(pk=card.pk).update(slug=slug)


def unseed(apps, schema_editor):
    LandingPage = apps.get_model("website", "LandingPage")
    LandingTeacher = apps.get_model("website", "LandingTeacher")
    TeachersPage = apps.get_model("website", "TeachersPage")

    orphans = LandingTeacher.objects.filter(page__isnull=True)
    if orphans.exists():
        landing, _ = LandingPage.objects.get_or_create(pk=1)
        orphans.update(page=landing)
    TeachersPage.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("website", "0009_teachers"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
