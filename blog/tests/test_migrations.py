import importlib

from django.apps import apps as django_apps
from django.test import TestCase

from blog.models import BlogPage, Section
from blog.testing import make_author, make_post

seed = importlib.import_module("blog.migrations.0002_seed")


class SeedMigrationTests(TestCase):
    """The data migration's functions, run against the current models."""

    def test_seed_creates_the_page_and_two_sections_once(self):
        BlogPage.objects.all().delete()
        Section.objects.all().delete()
        seed.seed(django_apps, None)
        seed.seed(django_apps, None)
        self.assertEqual(BlogPage.objects.count(), 1)
        self.assertEqual(
            list(Section.objects.values_list("title", "paper", "is_active")),
            [("پرورشی", "tomato", True), ("مشاوره", "sky", True)],
        )
        page = BlogPage.load()
        self.assertEqual(len(page.checklist_items()), 4)
        self.assertIn("بدون رضایت کتبی ولی", page.author_reminder)
        self.assertFalse(Section.objects.filter(categories__isnull=False).exists())

    def test_seed_leaves_edited_rows_alone(self):
        Section.objects.filter(slug="مشاوره").update(title="مشاوره خانواده", paper="grape")
        seed.seed(django_apps, None)
        self.assertEqual(Section.objects.get(slug="مشاوره").title, "مشاوره خانواده")

    def test_reverse_removes_only_seeded_sections_without_posts(self):
        used = Section.objects.get(slug="مشاوره")
        make_post(make_author(sections=[used]), section=used)
        Section.objects.create(title="هنر")
        seed.unseed(django_apps, None)
        self.assertEqual(set(Section.objects.values_list("slug", flat=True)), {"مشاوره", "هنر"})
