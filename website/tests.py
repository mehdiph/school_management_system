import shutil
import tempfile

import jdatetime
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from staff.models import Staff, TeacherProfile

from .models import (
    FeatureCard,
    FooterLink,
    HeroSlide,
    LandingPage,
    LandingTeacher,
    LearningPoint,
    NavMenuItem,
    SiteSettings,
)
from .validators import validate_link

User = get_user_model()

# Smallest valid GIF, renamed .png: Pillow only checks it is an image.
PIXEL = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def clear_content():
    """Undo the seed migration so a test starts from an empty database."""
    for model in (NavMenuItem, FooterLink, HeroSlide, FeatureCard, LearningPoint, LandingTeacher):
        model.objects.all().delete()
    SiteSettings.objects.all().delete()
    LandingPage.objects.all().delete()


def make_teacher(first_name="سارا", last_name="احمدی", avatar=None, field_of_study="ریاضی"):
    user = User.objects.create_user(
        username=f"t-{User.objects.count()}",
        password="x",
        first_name=first_name,
        last_name=last_name,
        role=User.Roles.TEACHER,
        avatar=avatar,
    )
    staff = Staff.objects.create(
        user=user,
        personnel_code=f"p{user.pk}",
        national_code=f"{user.pk:010d}",
        gender=Staff.Gender.FEMALE,
        hire_date=jdatetime.date(1400, 1, 1),
    )
    return TeacherProfile.objects.create(staff=staff, field_of_study=field_of_study)


class SingletonTests(TestCase):
    def setUp(self):
        clear_content()

    def test_load_creates_the_row_once(self):
        first = SiteSettings.load()
        second = SiteSettings.load()
        self.assertEqual(first.pk, 1)
        self.assertEqual(second.pk, 1)
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_saving_a_new_instance_overwrites_the_single_row(self):
        SiteSettings.load()
        SiteSettings(site_name="نام دیگر").save()
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(SiteSettings.load().site_name, "نام دیگر")

    def test_delete_is_a_no_op(self):
        page = LandingPage.load()
        page.delete()
        self.assertTrue(LandingPage.objects.filter(pk=1).exists())


class SingletonAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "a@example.com", "pass", role=User.Roles.ADMIN)
        self.client.force_login(self.admin)

    def test_changelist_redirects_to_the_single_record(self):
        for model in (SiteSettings, LandingPage):
            name = model._meta.model_name
            response = self.client.get(reverse(f"admin:website_{name}_changelist"))
            self.assertRedirects(response, reverse(f"admin:website_{name}_change", args=[1]))

    def test_add_and_delete_are_forbidden(self):
        SiteSettings.load()
        self.assertEqual(self.client.get(reverse("admin:website_sitesettings_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:website_sitesettings_delete", args=[1])).status_code, 403)

    def test_change_pages_render(self):
        for model in (SiteSettings, LandingPage):
            name = model._meta.model_name
            response = self.client.get(reverse(f"admin:website_{name}_change", args=[1]))
            self.assertEqual(response.status_code, 200)


class LandingPageViewTests(TestCase):
    url = "/"

    def test_seeded_page_shows_original_content(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for text in (
            "کلاس‌های رباتیک و کدنویسی نسل قلم",
            "رباتیک و برنامه نویسی",
            "برنامه های خلاقانه",
            "علی رضایی",
            "تماس با ما",
            "Made with 💗 in Urmia",
        ):
            self.assertContains(response, text)
        self.assertContains(response, "website/images/robatic-slider.jpeg")

    def test_empty_database_renders_without_sections(self):
        clear_content()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="main-slider"')
        self.assertNotContains(response, 'class="features"')
        self.assertNotContains(response, 'class="learning-section"')
        self.assertNotContains(response, 'class="instructors-section"')
        # Intro has no list, so its default texts and static image still render.
        self.assertContains(response, "website/images/happy_young_boy.png")

    def test_disabled_section_and_inactive_items_are_hidden(self):
        page = LandingPage.load()
        page.show_features = False
        page.save()
        HeroSlide.objects.filter(title__contains="هنر").update(is_active=False)

        response = self.client.get(self.url)
        self.assertNotContains(response, 'class="features"')
        self.assertNotContains(response, "پرورش خلاقیت در زنگ هنر و نقاشی")
        self.assertContains(response, "کلاس‌های رباتیک و کدنویسی نسل قلم")

    def test_only_first_slide_is_eager(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        self.assertEqual(html.count('fetchpriority="high"'), 1)
        self.assertEqual(html.count('class="main-slide__img"'), 3)

    def test_user_text_is_escaped(self):
        HeroSlide.objects.filter(order=1).update(description="<script>alert(1)</script>\nخط دوم")
        response = self.client.get(self.url)
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;<br>خط دوم")

    def test_query_count_does_not_grow_with_teachers(self):
        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(self.url)
            return len(ctx.captured_queries)

        before = count_queries()
        page = LandingPage.load()
        for i in range(5):
            LandingTeacher.objects.create(page=page, teacher=make_teacher(first_name=f"استاد{i}"), order=10 + i)
        self.assertEqual(count_queries(), before)


class LandingTeacherPropertyTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        self.page = LandingPage.load()

    def test_falls_back_to_linked_user(self):
        with override_settings(MEDIA_ROOT=self.media):
            profile = make_teacher(avatar=SimpleUploadedFile("a.png", PIXEL, content_type="image/png"))
            card = LandingTeacher(page=self.page, teacher=profile)
            self.assertEqual(card.display_name, "سارا احمدی")
            self.assertTrue(card.photo_url.startswith("/media/users/avatars/"))
            self.assertEqual(card.display_specialty, "ریاضی")

    def test_overrides_win(self):
        with override_settings(MEDIA_ROOT=self.media):
            card = LandingTeacher(
                page=self.page,
                teacher=make_teacher(),
                name_override="نام دلخواه",
                specialty_override="استاد علوم",
                photo_override=SimpleUploadedFile("b.png", PIXEL, content_type="image/png"),
            )
            card.save()
            self.assertEqual(card.display_name, "نام دلخواه")
            self.assertEqual(card.display_specialty, "استاد علوم")
            self.assertIn("/media/website/teachers/", card.photo_url)

    def test_without_teacher_or_photo(self):
        card = LandingTeacher(page=self.page, name_override="مهمان")
        self.assertEqual(card.display_name, "مهمان")
        self.assertEqual(card.photo_url, "")
        self.assertEqual(card.display_specialty, "")

    def test_clean_requires_teacher_or_name(self):
        with self.assertRaises(ValidationError):
            LandingTeacher(page=self.page).clean()


class ImageFileCleanupTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media)
        override.enable()
        self.addCleanup(override.disable)
        self.page = LandingPage.load()

    def upload(self, name):
        return SimpleUploadedFile(name, PIXEL, content_type="image/png")

    def test_replaced_and_deleted_files_are_removed(self):
        card = FeatureCard.objects.create(page=self.page, title="کارت", image=self.upload("one.png"))
        old = card.image.name
        storage = card.image.storage

        with self.captureOnCommitCallbacks(execute=True):
            card.image = self.upload("two.png")
            card.save()
        self.assertFalse(storage.exists(old))
        self.assertTrue(storage.exists(card.image.name))

        new = card.image.name
        with self.captureOnCommitCallbacks(execute=True):
            card.delete()
        self.assertFalse(storage.exists(new))


class ValidatorTests(TestCase):
    def test_links(self):
        for ok in ("/auth/login/", "#contact", "https://instagram.com/x", "tel:0441", "mailto:a@b.c"):
            validate_link(ok)
        for bad in ("javascript:alert(1)", "data:text/html,x", "instagram.com"):
            with self.assertRaises(ValidationError):
                validate_link(bad)

    def test_image_size_and_extension(self):
        big = SimpleUploadedFile("big.png", b"0" * (2 * 1024 * 1024 + 1))
        card = FeatureCard(page=LandingPage.load(), title="x", image=big)
        with self.assertRaises(ValidationError) as ctx:
            card.full_clean()
        self.assertIn("image", ctx.exception.message_dict)

        card.image = SimpleUploadedFile("vector.svg", b"<svg/>")
        with self.assertRaises(ValidationError):
            card.full_clean()
