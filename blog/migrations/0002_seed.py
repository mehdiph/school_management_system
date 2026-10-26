"""
Seed the blog (D15): the «صفحه وبلاگ» row with its default texts (the
privacy reminder, acknowledgement and review checklist of D16), and the
two sections «پرورشی» and «مشاوره». Create only: existing rows are not
touched. No categories, authors or posts are seeded.

The reverse removes only the seeded sections that no post uses.
"""

from django.db import migrations

SECTIONS = [
    {
        "slug": "پرورشی",
        "title": "پرورشی",
        "description": "جشن‌ها، اردوها، هنر و فعالیت‌های بیرون از کلاس.",
        "paper": "tomato",
        "order": 1,
    },
    {
        "slug": "مشاوره",
        "title": "مشاوره",
        "description": "راهنمایی مشاور مدرسه برای خانواده‌ها: درس خواندن، احساسات و رشد بچه‌ها.",
        "paper": "sky",
        "order": 2,
    },
]


def seed(apps, schema_editor):
    apps.get_model("blog", "BlogPage").objects.get_or_create(pk=1)
    Section = apps.get_model("blog", "Section")
    for values in SECTIONS:
        Section.objects.get_or_create(slug=values["slug"], defaults=values)


def unseed(apps, schema_editor):
    Section = apps.get_model("blog", "Section")
    Section.objects.filter(slug__in=[s["slug"] for s in SECTIONS], posts__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
