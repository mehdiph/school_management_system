import importlib
import shutil
import tempfile

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.testing import make_branch

from .models import (
    AboutFact,
    AboutHighlight,
    AboutMilestone,
    AboutPage,
    AboutPerson,
    AboutPhoto,
    AboutValue,
    ContactLocation,
    ContactPage,
    FooterLink,
    NavMenuItem,
)
from .tests import PIXEL, assert_reencoded, make_teacher, phone_photo

User = get_user_model()
URL = "/about/"


def upload(name="photo.png"):
    return SimpleUploadedFile(name, PIXEL, content_type="image/png")


class TempMediaMixin:
    def setUp(self):
        super().setUp()
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)


class AboutFixture(TestCase):
    """The seeded page plus one branch with a location on the contact page."""

    @classmethod
    def setUpTestData(cls):
        cls.page = AboutPage.load()
        cls.branch = make_branch(name="شعبه مرکزی (عمار)")
        cls.branch.address = "ارومیه، خیابان عمار"
        cls.branch.save()
        ContactLocation.objects.all().delete()
        cls.location = ContactLocation.objects.create(page=ContactPage.load(), branch=cls.branch, order=1)

    def get(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        return response

    def set(self, **fields):
        AboutPage.objects.filter(pk=1).update(**fields)


# ----------------------------------------------------------------------- view


class AboutViewTests(TempMediaMixin, AboutFixture):
    def test_url_name(self):
        self.assertEqual(reverse("website:about"), URL)

    def test_seeded_page(self):
        response = self.get()
        self.assertTemplateUsed(response, "website/about.html")
        for text in (
            "مدرسه‌ای که بچه‌ها در آن با شوق یاد می‌گیرند",
            "هماهنگی بازدید از مدرسه",
            "داستان ما",
            "مأموریت ما",
            "احترام به هر کودک",
            "ربات می‌سازند و کد می‌نویسند",
            "website/images/robotic.jpg",
            "website/images/happy_young_boy.png",
            "از نزدیک با مدرسه آشنا شوید",
        ):
            self.assertContains(response, text)
        # Inactive examples, the quote (off by default) and the empty
        # people and photo lists are not published.
        for text in ("تأسیس مدرسه", "سال تجربه", "از روز اول", 'id="team"', "گوشه‌ای از مدرسه"):
            self.assertNotContains(response, text)

    def test_exactly_one_h1(self):
        self.assertEqual(self.get().content.decode().count("<h1"), 1)

    def test_only_safe_methods(self):
        self.assertEqual(self.client.head(URL).status_code, 200)
        self.assertEqual(self.client.post(URL).status_code, 405)

    def test_active_milestones_facts_people_and_photos(self):
        AboutMilestone.objects.filter(title="تأسیس مدرسه").update(year="۱۳۹۲", is_active=True)
        AboutFact.objects.filter(label="دانش‌آموز").update(value="۴۰۰+", is_active=True)
        AboutPerson.objects.create(page=self.page, name_override="مریم احمدی", role="مدیر مدرسه")
        AboutPhoto.objects.create(page=self.page, image=upload(), caption="زنگ هنر")
        response = self.get()
        for text in ("۱۳۹۲", "تأسیس مدرسه", "۴۰۰+", "دانش‌آموز", "مریم احمدی", "مدیر مدرسه", "زنگ هنر"):
            self.assertContains(response, text)
        self.assertNotContains(response, "افتتاح شعبه دوم")  # still inactive

    def test_each_switch_hides_its_section(self):
        AboutMilestone.objects.update(is_active=True)
        AboutFact.objects.update(is_active=True)
        AboutPerson.objects.create(page=self.page, name_override="مریم احمدی", role="مدیر مدرسه")
        self.set(show_quote=True)
        on = self.get()
        for marker in ("ab-story", "ab-quote", "ab-values-title", "ab-highlights-title", "ab-facts-title",
                       "ab-team-title", "ab-branches-title", "ab-cta-title"):
            self.assertContains(on, marker)

        self.set(
            show_story=False, show_timeline=False, show_quote=False, show_values=False, show_highlights=False,
            show_facts=False, show_team=False, show_gallery=False, show_branches=False, show_cta=False,
        )
        off = self.get()
        for marker in ("ab-story", "ab-quote", "ab-values-title", "ab-highlights-title", "ab-facts-title",
                       "ab-team-title", "ab-branches-title", "ab-cta-title"):
            self.assertNotContains(off, marker)
        self.assertContains(off, 'id="ab-hero-title"')  # the hero is always there

    def test_story_shows_with_only_text_or_only_milestones(self):
        self.assertContains(self.get(), "ab-story")
        self.set(story_text="")
        self.assertNotContains(self.get(), "ab-story")
        AboutMilestone.objects.filter(order=1).update(is_active=True)
        response = self.get()
        self.assertContains(response, "ab-story")
        self.assertContains(response, "ab-timeline")

    def test_sections_without_content_are_not_rendered(self):
        AboutValue.objects.all().delete()
        self.set(mission_text="", vision_text="")
        AboutHighlight.objects.update(is_active=False)
        response = self.get()
        self.assertNotContains(response, "باورهای ما")
        self.assertNotContains(response, "در نسل قلم، بچه‌ها…")

    def test_inactive_items_are_hidden(self):
        AboutValue.objects.filter(title="امنیت و آرامش").update(is_active=False)
        response = self.get()
        self.assertNotContains(response, "امنیت و آرامش")
        self.assertContains(response, "احترام به هر کودک")

    def test_quote(self):
        self.set(show_quote=True, quote_name="مریم احمدی")
        response = self.get()
        self.assertContains(response, "<blockquote")
        self.assertContains(response, "مریم احمدی")
        self.assertContains(response, 'aria-labelledby="ab-quote-by"')
        self.set(quote_text="")
        self.assertNotContains(self.get(), "<blockquote")

    def test_cta_buttons(self):
        response = self.get()
        self.assertContains(response, 'href="/contact/" class="ab-btn ab-btn--primary">تماس با مدرسه</a>', html=False)
        self.assertNotContains(response, "ab-btn--outline")

        self.set(cta_secondary_text="ثبت‌نام")  # no URL yet: still hidden
        self.assertNotContains(self.get(), "ab-btn--outline")

        self.set(cta_secondary_url="/register/")
        self.assertContains(self.get(), 'href="/register/" class="ab-btn ab-btn--outline">ثبت‌نام</a>', html=False)

    def test_user_text_is_escaped(self):
        self.set(show_quote=True, hero_title="<script>alert(1)</script>", quote_text="<b>سلام</b>")
        AboutHighlight.objects.filter(order=1).update(title="<img src=x onerror=alert(1)>")
        response = self.get()
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertNotContains(response, "<img src=x")
        self.assertNotContains(response, "<b>سلام</b>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertContains(response, "&lt;b&gt;سلام&lt;/b&gt;")

    def test_links_must_be_safe(self):
        page = AboutPage.load()
        for field in ("hero_button_url", "cta_primary_url", "cta_secondary_url", "branches_link_url"):
            setattr(page, field, "javascript:alert(1)")
            with self.assertRaises(ValidationError) as ctx:
                page.full_clean()
            self.assertIn(field, ctx.exception.message_dict)
            setattr(page, field, "/contact/")

    def test_nav_points_here_and_classes_item_is_gone(self):
        response = self.get()
        self.assertContains(response, 'href="/about/" class="public-nav__link is-active"')
        self.assertContains(response, 'aria-current="page"')
        self.assertNotContains(response, ">کلاس ها</a>")

    def test_query_count_does_not_grow_with_items(self):
        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                self.get()
            return len(ctx.captured_queries)

        AboutPage.objects.filter(pk=1).update(show_quote=True)
        before = count_queries()
        # Page row + six section lists + locations + navbar/footer (3).
        self.assertEqual(before, 11)

        for i in range(5):
            AboutMilestone.objects.create(page=self.page, year=f"۱۴۰{i}", title=f"رویداد {i}")
            AboutValue.objects.create(page=self.page, title=f"ارزش {i}")
            AboutHighlight.objects.create(page=self.page, title=f"ویژگی {i}")
            AboutFact.objects.create(page=self.page, value=str(i), label=f"عدد {i}")
            AboutPerson.objects.create(page=self.page, staff=make_teacher(first_name=f"همکار{i}").staff, role="معاون")
            AboutPhoto.objects.create(page=self.page, image=upload(f"p{i}.png"))
        for i in range(3):
            branch = make_branch(name=f"شعبه {i}", order=10 + i)
            ContactLocation.objects.create(page=ContactPage.load(), branch=branch, order=10 + i)
        self.assertEqual(count_queries(), before)


class AboutBranchesTests(AboutFixture):
    def test_shows_the_contact_page_locations(self):
        response = self.get()
        self.assertContains(response, "شعبه مرکزی (عمار)")
        self.assertContains(response, "ارومیه، خیابان عمار")
        self.assertContains(response, 'href="/contact/" class="ab-link">مسیریابی و تلفن')

    def test_overrides_win(self):
        ContactLocation.objects.filter(pk=self.location.pk).update(title_override="دفتر ثبت‌نام", address_override="نشانی دیگر")
        response = self.get()
        self.assertContains(response, "دفتر ثبت‌نام")
        self.assertContains(response, "نشانی دیگر")
        self.assertNotContains(response, "ارومیه، خیابان عمار")

    def test_inactive_location_or_branch_is_hidden(self):
        ContactLocation.objects.filter(pk=self.location.pk).update(is_active=False)
        self.assertNotContains(self.get(), "ab-branches-title")

        ContactLocation.objects.filter(pk=self.location.pk).update(is_active=True)
        type(self.branch).objects.filter(pk=self.branch.pk).update(is_active=False)
        self.assertNotContains(self.get(), "ab-branches-title")


# ---------------------------------------------------------------------- people


class AboutPersonTests(TempMediaMixin, AboutFixture):
    def test_name_falls_back_to_the_linked_account_never_the_username(self):
        staff = make_teacher(first_name="سارا", last_name="احمدی").staff
        person = AboutPerson.objects.create(page=self.page, staff=staff, role="مسئول دفتر")
        self.assertEqual(person.display_name, "سارا احمدی")
        self.assertEqual(person.initial, "س")

        staff.user.first_name = staff.user.last_name = ""
        staff.user.save()
        person.refresh_from_db()
        self.assertEqual(person.display_name, "")
        self.assertNotIn(staff.user.username, str(person))

    def test_account_avatar_is_never_published(self):
        staff = make_teacher(first_name="سارا", last_name="احمدی", avatar=upload("avatar.png")).staff
        self.assertTrue(staff.user.avatar_url)
        person = AboutPerson.objects.create(page=self.page, staff=staff, role="مسئول دفتر")
        self.assertEqual(person.photo_url, "")

        response = self.get()
        self.assertNotContains(response, staff.user.avatar.name)
        self.assertContains(response, '<span class="ab-person__photo ab-person__initial" aria-hidden="true">س</span>', html=False)

    def test_uploaded_photo_is_reencoded_without_metadata(self):
        with self.captureOnCommitCallbacks(execute=True):
            person = AboutPerson.objects.create(page=self.page, name_override="مریم", role="مدیر", photo_override=phone_photo())
        assert_reencoded(self, person.photo_override)
        self.assertIn("website/about/people/", person.photo_override.name)

    def test_uploaded_photo_and_name_override_win(self):
        staff = make_teacher(first_name="سارا", last_name="احمدی").staff
        person = AboutPerson.objects.create(
            page=self.page, staff=staff, name_override="خانم احمدی", role="مدیر", photo_override=upload()
        )
        response = self.get()
        self.assertContains(response, person.photo_override.url)
        self.assertContains(response, "خانم احمدی")
        self.assertNotContains(response, "ab-person__initial")

    def test_inactive_staff_and_inactive_rows_are_hidden(self):
        staff = make_teacher(first_name="رضا", last_name="نوری").staff
        AboutPerson.objects.create(page=self.page, staff=staff, role="معاون")
        AboutPerson.objects.create(page=self.page, name_override="علی کریمی", role="معاون", is_active=False)
        self.assertContains(self.get(), "رضا نوری")

        type(staff).objects.filter(pk=staff.pk).update(is_active=False)
        response = self.get()
        self.assertNotContains(response, "رضا نوری")
        self.assertNotContains(response, "علی کریمی")
        self.assertNotContains(response, 'id="team"')

    def test_clean_requires_a_name(self):
        with self.assertRaises(ValidationError):
            AboutPerson(page=self.page, role="مدیر").clean()
        nameless = make_teacher(first_name="", last_name="").staff
        with self.assertRaises(ValidationError):
            AboutPerson(page=self.page, staff=nameless, role="مدیر").clean()
        AboutPerson(page=self.page, staff=nameless, name_override="مریم", role="مدیر").clean()
        AboutPerson(page=self.page, staff=make_teacher().staff, role="مدیر").clean()


# ----------------------------------------------------------------- admin, files


class AboutAdminTests(AboutFixture):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("admin", "a@example.com", "x"))

    def test_singleton_with_all_inlines(self):
        response = self.client.get(reverse("admin:website_aboutpage_changelist"))
        self.assertRedirects(response, reverse("admin:website_aboutpage_change", args=[1]))

        response = self.client.get(reverse("admin:website_aboutpage_change", args=[1]))
        self.assertEqual(response.status_code, 200)
        for prefix in ("milestones", "belief_values", "highlights", "facts", "people", "photos"):
            self.assertContains(response, f'name="{prefix}-TOTAL_FORMS"')
        # Staff are picked with autocomplete, and the admin is told photos are public
        # and that teachers belong on their own page.
        self.assertContains(response, "admin-autocomplete")
        self.assertContains(response, "این عکس در سایت عمومی نمایش داده می‌شود")
        self.assertContains(response, "معلمان در صفحه جداگانه معلمان معرفی می‌شوند")

    def test_add_and_delete_are_forbidden(self):
        self.assertEqual(self.client.get(reverse("admin:website_aboutpage_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:website_aboutpage_delete", args=[1])).status_code, 403)


class AboutImageCleanupTests(TempMediaMixin, TestCase):
    def test_replaced_hero_and_deleted_photo_are_removed(self):
        page = AboutPage.load()
        with self.captureOnCommitCallbacks(execute=True):
            page.hero_image = upload("one.png")
            page.save()
        old = page.hero_image.name
        storage = page.hero_image.storage

        with self.captureOnCommitCallbacks(execute=True):
            page.hero_image = upload("two.png")
            page.save()
        self.assertFalse(storage.exists(old))
        self.assertTrue(storage.exists(page.hero_image.name))

        photo = AboutPhoto.objects.create(page=page, image=upload("gallery.png"))
        name = photo.image.name
        with self.captureOnCommitCallbacks(execute=True):
            photo.delete()
        self.assertFalse(storage.exists(name))

    def test_hero_falls_back_to_the_bundled_image(self):
        page = AboutPage.load()
        self.assertTrue(page.hero_image_url.endswith("website/images/happy_young_boy.png"))
        highlight = AboutHighlight.objects.filter(static_fallback="website/images/robotic.jpg").get()
        self.assertTrue(highlight.image_url.endswith("website/images/robotic.jpg"))
        highlight.image = upload()
        highlight.save()
        self.assertIn("website/about/highlights/", highlight.image_url)


# ------------------------------------------------------------------ migrations


class AboutMigrationTests(TestCase):
    """The data migrations' functions, run against the current models."""

    seed = importlib.import_module("website.migrations.0007_seed_about")
    menu = importlib.import_module("website.migrations.0008_about_menu")

    def test_seed_creates_rows_once_and_reverses(self):
        self.seed.unseed(django_apps, None)
        self.assertFalse(AboutPage.objects.exists())

        self.seed.seed(django_apps, None)
        self.assertEqual(AboutPage.objects.count(), 1)
        self.assertEqual(AboutValue.objects.filter(is_active=True).count(), 4)
        self.assertEqual(AboutHighlight.objects.filter(is_active=True).count(), 4)
        # Nothing that reads as a fact about the school is published.
        self.assertEqual(AboutMilestone.objects.count(), 3)
        self.assertFalse(AboutMilestone.objects.filter(is_active=True).exists())
        self.assertEqual(AboutFact.objects.count(), 4)
        self.assertFalse(AboutFact.objects.filter(is_active=True).exists())
        self.assertFalse(AboutPerson.objects.exists())
        self.assertFalse(AboutPhoto.objects.exists())
        self.assertFalse(AboutPage.objects.get().show_quote)

        # Re-running never duplicates.
        self.seed.seed(django_apps, None)
        self.assertEqual(AboutValue.objects.count(), 4)
        self.assertEqual(AboutHighlight.objects.count(), 4)
        self.assertEqual(AboutMilestone.objects.count(), 3)
        self.assertEqual(AboutFact.objects.count(), 4)

    def reset_menu(self):
        """The seed's state (the test database already ran 0008)."""
        NavMenuItem.objects.filter(title="درباره ما").update(url="#")
        FooterLink.objects.filter(title="درباره ما").update(url="#")
        NavMenuItem.objects.filter(title="کلاس ها").update(url="#", is_active=True)
        NavMenuItem.objects.filter(title="معلمان").update(url="#")  # 0012 links it
        NavMenuItem.objects.filter(title="وبلاگ").update(url="#")  # 0014 links it

    def test_about_rows_still_at_hash_are_linked_and_reversed(self):
        self.reset_menu()
        FooterLink.objects.filter(title="درباره ما").update(url="/edited/")
        others = dict(NavMenuItem.objects.exclude(title__in=["درباره ما", "کلاس ها"]).values_list("title", "url"))

        self.menu.link_about(django_apps, None)
        self.assertEqual(NavMenuItem.objects.get(title="درباره ما").url, "/about/")
        self.assertEqual(FooterLink.objects.get(title="درباره ما").url, "/edited/")  # admin-edited: untouched
        self.assertEqual(
            dict(NavMenuItem.objects.exclude(title__in=["درباره ما", "کلاس ها"]).values_list("title", "url")), others
        )
        self.assertEqual(others["معلمان"], "#")
        self.assertEqual(others["وبلاگ"], "#")

        self.menu.unlink_about(django_apps, None)
        self.assertEqual(NavMenuItem.objects.get(title="درباره ما").url, "#")
        self.assertEqual(FooterLink.objects.get(title="درباره ما").url, "/edited/")

    def test_classes_item_is_deactivated_not_deleted_and_reversed(self):
        self.reset_menu()
        active_before = set(NavMenuItem.objects.filter(is_active=True).values_list("title", flat=True))

        self.menu.hide_classes(django_apps, None)
        classes = NavMenuItem.objects.get(title="کلاس ها")
        self.assertFalse(classes.is_active)
        self.assertEqual(
            set(NavMenuItem.objects.filter(is_active=True).values_list("title", flat=True)), active_before - {"کلاس ها"}
        )

        self.menu.show_classes(django_apps, None)
        classes.refresh_from_db()
        self.assertTrue(classes.is_active)

    def test_a_linked_or_renamed_classes_item_is_left_alone(self):
        self.reset_menu()
        NavMenuItem.objects.filter(title="کلاس ها").update(url="/classes/")
        self.menu.hide_classes(django_apps, None)
        self.assertTrue(NavMenuItem.objects.get(title="کلاس ها").is_active)

        NavMenuItem.objects.filter(title="کلاس ها").update(url="#", title="کلاس‌های ما")
        self.menu.hide_classes(django_apps, None)
        self.assertTrue(NavMenuItem.objects.get(title="کلاس‌های ما").is_active)

        # The reverse only re-activates an inactive «کلاس ها» still at "#".
        NavMenuItem.objects.filter(title="کلاس‌های ما").update(title="کلاس ها", url="/classes/", is_active=False)
        self.menu.show_classes(django_apps, None)
        self.assertFalse(NavMenuItem.objects.get(title="کلاس ها").is_active)
