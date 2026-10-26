"""The public site's ties to the blog: the menu row (0014), the navbar's section highlight and the teachers page link."""

import importlib
from datetime import timedelta

from django.apps import apps as django_apps
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from blog.models import BlogAuthor, Post
from blog.testing import make_author, make_post, make_section

from .models import LandingTeacher, NavMenuItem
from .templatetags.website_tags import nav_state
from .tests import make_teacher


class NavStateTests(SimpleTestCase):
    def test_page_section_or_nothing(self):
        self.assertEqual(nav_state("/blog/", "/blog/"), "page")
        self.assertEqual(nav_state("/blog/", "/blog/post/x/"), "section")
        self.assertEqual(nav_state("/teachers/", "/teachers/"), "page")
        self.assertEqual(nav_state("/", "/"), "page")
        for url, path in (
            ("/", "/blog/"),  # the home page is never a section
            ("#", "/blog/"),
            ("", "/blog/"),
            ("https://example.com/blog/", "/blog/"),
            ("/blog/", "/blogger/"),
            ("/blog", "/blog/post/"),  # without the slash it would match /blogger/ too
            ("/teachers/", "/blog/"),
        ):
            with self.subTest(url=url, path=path):
                self.assertEqual(nav_state(url, path), "")


class BlogMenuMigrationTests(TestCase):
    """website.0014: the seeded «وبلاگ» row → /blog/, the seeded «مقاله» row hidden (D20)."""

    menu = importlib.import_module("website.migrations.0014_blog_menu")

    def rows(self):
        return {item.title: (item.url, item.is_active) for item in NavMenuItem.objects.filter(title__in=["وبلاگ", "مقاله"])}

    def seed_state(self):
        # The test database already ran 0014: start from the seed's state.
        NavMenuItem.objects.filter(title="وبلاگ").update(url="#", is_active=True)
        NavMenuItem.objects.filter(title="مقاله").update(url="#", is_active=True)

    def test_the_test_database_ran_it(self):
        self.assertEqual(self.rows(), {"وبلاگ": ("/blog/", True), "مقاله": ("#", False)})

    def test_seed_rows_are_changed_and_reversed(self):
        self.seed_state()
        others = dict(NavMenuItem.objects.exclude(title__in=["وبلاگ", "مقاله"]).values_list("title", "url"))

        self.menu.link_blog(django_apps, None)
        self.assertEqual(self.rows(), {"وبلاگ": ("/blog/", True), "مقاله": ("#", False)})
        self.assertTrue(NavMenuItem.objects.filter(title="مقاله").exists())  # hidden, never deleted
        self.assertEqual(dict(NavMenuItem.objects.exclude(title__in=["وبلاگ", "مقاله"]).values_list("title", "url")), others)

        self.menu.unlink_blog(django_apps, None)
        self.assertEqual(self.rows(), {"وبلاگ": ("#", True), "مقاله": ("#", True)})

    def test_rows_an_admin_edited_are_left_alone(self):
        NavMenuItem.objects.filter(title="وبلاگ").update(url="/news/")
        NavMenuItem.objects.filter(title="مقاله").update(url="/articles/", is_active=True)
        self.menu.link_blog(django_apps, None)
        self.menu.unlink_blog(django_apps, None)
        self.assertEqual(self.rows(), {"وبلاگ": ("/news/", True), "مقاله": ("/articles/", True)})

    def test_the_reverse_spares_a_relinked_or_reactivated_row(self):
        self.seed_state()
        self.menu.link_blog(django_apps, None)
        NavMenuItem.objects.filter(title="وبلاگ").update(url="/blog/news/")
        NavMenuItem.objects.filter(title="مقاله").update(url="/articles/")
        self.menu.unlink_blog(django_apps, None)
        self.assertEqual(self.rows(), {"وبلاگ": ("/blog/news/", True), "مقاله": ("/articles/", False)})


class TeachersPageBlogLinkTests(TestCase):
    """D21: a card links to its author's page while that page exists."""

    def setUp(self):
        self.teacher = make_teacher(first_name="سارا", last_name="کریمی")
        self.card = LandingTeacher.objects.create(teacher=self.teacher, on_teachers_page=True)
        section = make_section()
        self.author = make_author(user=self.teacher.staff.user, sections=[section], teacher_card=self.card)
        self.link = f'<a href="{self.author.get_absolute_url()}">نوشته‌های سارا کریمی در وبلاگ</a>'

    def content(self):
        return self.client.get("/teachers/").content.decode()

    def test_linked_once_the_author_has_a_public_post(self):
        self.assertNotIn(self.link, self.content())  # no posts yet
        draft = make_post(self.author)
        self.assertNotIn(self.link, self.content())
        Post.objects.filter(pk=draft.pk).update(status=Post.Status.PUBLISHED, published_at=timezone.now() - timedelta(hours=1))
        content = self.content()
        self.assertIn(self.link, content)
        self.assertIn('<details class="tc-more">', content)  # shown though the card has no bio
        self.assertIn(self.link, self.client.get("/teachers/?partial=1").content.decode())

    def test_no_link_without_an_author_page(self):
        make_post(self.author, status=Post.Status.PUBLISHED)
        BlogAuthor.objects.filter(pk=self.author.pk).update(show_profile=False)
        content = self.content()
        self.assertNotIn(self.author.get_absolute_url(), content)
        self.assertNotIn('<details class="tc-more">', content)

    def test_the_landing_page_has_no_link(self):
        LandingTeacher.objects.filter(pk=self.card.pk).update(on_home=True)
        make_post(self.author, status=Post.Status.PUBLISHED)
        self.assertNotIn(self.author.get_absolute_url(), self.client.get("/").content.decode())
