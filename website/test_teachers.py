import importlib

import jdatetime
from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.testing import make_academic_year, make_assignment, make_branch

from .models import LandingPage, LandingTeacher, NavMenuItem, TeacherGroup, TeachersPage
from .test_about import TempMediaMixin, upload
from .tests import assert_reencoded, make_teacher, phone_photo

User = get_user_model()
URL = "/teachers/"


def published(**fields):
    """A teacher card ticked onto the teachers page."""
    fields.setdefault("on_teachers_page", True)
    if "teacher" not in fields:
        fields.setdefault("name_override", "سارا احمدی")
    return LandingTeacher.objects.create(**fields)


class TeachersFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.page = TeachersPage.load()

    def get(self, url=URL):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response

    def set(self, **fields):
        TeachersPage.objects.filter(pk=1).update(**fields)

    def group(self, title, order=0, **fields):
        return TeacherGroup.objects.create(page=self.page, title=title, order=order, **fields)


# ----------------------------------------------------------------------- view


class TeachersViewTests(TeachersFixture):
    def test_url_name_and_methods(self):
        self.assertEqual(reverse("website:teachers"), URL)
        self.assertEqual(self.client.head(URL).status_code, 200)
        self.assertEqual(self.client.post(URL).status_code, 405)

    def test_deploy_day_shows_the_empty_state(self):
        response = self.get()
        self.assertContains(response, "معلمان نسل قلم")
        self.assertContains(response, "فهرست معلمان به‌زودی در این صفحه منتشر می‌شود.")
        self.assertContains(response, 'href="/contact/" class="tc-btn tc-btn--primary"')
        # The seeded (and since 0013 inactive) landing teachers are not here.
        self.assertNotContains(response, "علی رضایی")
        self.assertNotContains(response, 'class="tc-teacher"')

    def test_exactly_one_h1_even_without_the_intro(self):
        published()
        self.assertContains(self.get(), "<h1", count=1)
        self.set(show_intro=False)
        response = self.get()
        self.assertContains(response, "<h1", count=1)
        self.assertContains(response, '<h1 class="visually-hidden">معلمان نسل قلم</h1>')
        self.assertNotContains(response, "با معلمانی آشنا شوید")

    def test_published_teacher(self):
        published(
            specialty_override="آموزگار پایه دوم",
            experience="۱۲ سال",
            education="کارشناسی ارشد آموزش ابتدایی",
            bio="معرفی کوتاه معلم",
            quote="هر بچه راه خودش را دارد.",
        )
        response = self.get()
        for text in (
            "سارا احمدی",
            "آموزگار پایه دوم",
            "<dt>سابقه تدریس</dt><dd>۱۲ سال</dd>",
            "هر بچه راه خودش را دارد.",
            "درباره سارا احمدی",
            "معرفی کوتاه معلم",
            "<dt>تحصیلات</dt><dd>کارشناسی ارشد آموزش ابتدایی</dd>",
        ):
            self.assertContains(response, text)
        self.assertContains(response, 'class="tc-note"')
        self.assertNotContains(response, "فهرست معلمان به‌زودی")

    def test_note_and_details_only_when_filled(self):
        published()
        response = self.get()
        self.assertNotContains(response, 'class="tc-note"')
        self.assertNotContains(response, "<details")

    def test_only_published_teachers(self):
        published(name_override="منتشرشده")
        published(name_override="فقط صفحه اصلی", on_teachers_page=False, on_home=True)
        published(name_override="غیرفعال", is_active=False)
        response = self.get()
        self.assertContains(response, "منتشرشده")
        self.assertNotContains(response, "فقط صفحه اصلی")
        self.assertNotContains(response, "غیرفعال")

    def test_teacher_who_left_is_hidden(self):
        teacher = make_teacher(first_name="رفته")
        published(teacher=teacher)
        published(name_override="مانده")
        teacher.staff.is_active = False
        teacher.staff.save()
        response = self.get()
        self.assertNotContains(response, "رفته")
        self.assertContains(response, "مانده")

    def test_switches(self):
        published()
        self.set(show_cta=False)
        self.assertNotContains(self.get(), 'class="tc-cta"')

    def test_cta_second_button_needs_text_and_link(self):
        self.set(cta_secondary_text="ثبت‌نام")
        self.assertNotContains(self.get(), "tc-btn--outline")
        self.set(cta_secondary_text="ثبت‌نام", cta_secondary_url="/register/")
        self.assertContains(self.get(), 'href="/register/" class="tc-btn tc-btn--outline">ثبت‌نام</a>')

    def test_user_text_is_escaped(self):
        published(name_override="<script>x</script>", quote="<script>q</script>", bio="<script>b</script>\nخط دوم")
        response = self.get()
        self.assertNotContains(response, "<script>x")
        self.assertNotContains(response, "<script>q")
        self.assertContains(response, "&lt;script&gt;q&lt;/script&gt;")
        self.assertContains(response, "&lt;script&gt;b&lt;/script&gt;<br>خط دوم")

    def test_links_must_be_safe(self):
        page = TeachersPage.load()
        page.cta_primary_url = "javascript:alert(1)"
        with self.assertRaises(ValidationError):
            page.full_clean()
        landing = LandingPage.load()
        landing.teachers_link_url = "javascript:alert(1)"
        with self.assertRaises(ValidationError):
            landing.full_clean()

    def test_nav_points_here_also_when_filtering(self):
        for url in (URL, URL + "?group=1"):
            response = self.get(url)
            self.assertContains(response, 'href="/teachers/" class="public-nav__link is-active"')
            self.assertContains(response, 'aria-current="page"')

    def test_query_count_is_flat(self):
        def count_queries(url=URL):
            with CaptureQueriesContext(connection) as ctx:
                self.get(url)
            return len(ctx.captured_queries)

        # Page row + teachers (with their groups) + navbar/footer (3).
        self.assertEqual(count_queries(), 5)

        groups = [self.group(f"گروه {i}", order=i) for i in range(4)]
        for i in range(12):
            published(teacher=make_teacher(first_name=f"معلم{i}"), group=groups[i % 4], quote="جمله", bio="معرفی")
        published(name_override="بی‌گروه")
        # With teachers, + the blog author pages linked to their cards (one query, D21 of the blog plan).
        self.assertEqual(count_queries(), 6)
        self.assertEqual(count_queries(f"{URL}?group={groups[1].pk}"), 6)
        # The fragment: page row + teachers + blog author pages.
        self.assertEqual(count_queries(f"{URL}?group={groups[1].pk}&partial=1"), 3)


# ------------------------------------------------------------ groups, filter


class TeachersFilterTests(TeachersFixture):
    def setUp(self):
        self.base = self.group("آموزگاران پایه", order=1)
        self.english = self.group("زبان انگلیسی", order=2)
        published(name_override="معلم پایه", group=self.base)
        published(name_override="معلم زبان", group=self.english)
        published(name_override="معلم بی‌گروه")

    def test_all_shows_one_section_per_group_then_the_rest(self):
        content = self.get().content.decode()
        positions = [content.index(text) for text in ("آموزگاران پایه</h2>", "زبان انگلیسی</h2>", "سایر معلمان</h2>")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('<a class="tc-chip" href="/teachers/#tc-list" aria-current="true">همه</a>', content)
        self.assertIn(f'href="/teachers/?group={self.english.pk}#tc-list">زبان انگلیسی</a>', content)

    def test_group_order_is_the_admins(self):
        TeacherGroup.objects.filter(pk=self.english.pk).update(order=0)
        content = self.get().content.decode()
        self.assertLess(content.index("زبان انگلیسی</h2>"), content.index("آموزگاران پایه</h2>"))

    def test_filter_shows_one_group(self):
        response = self.get(f"{URL}?group={self.english.pk}")
        self.assertContains(response, "معلم زبان")
        self.assertNotContains(response, "معلم پایه")
        self.assertNotContains(response, "معلم بی‌گروه")
        self.assertContains(response, f'href="/teachers/?group={self.english.pk}#tc-list" aria-current="true"')
        self.assertContains(response, 'data-tc-count="۱ معلم"')

    def test_unusable_filters_show_everyone(self):
        empty = self.group("هنر")
        hidden = self.group("ورزش", is_active=False)
        for value in ("999", "abc", "", str(empty.pk), str(hidden.pk)):
            response = self.get(f"{URL}?group={value}")
            for name in ("معلم پایه", "معلم زبان", "معلم بی‌گروه"):
                self.assertContains(response, name)
            self.assertContains(response, 'href="/teachers/#tc-list" aria-current="true"')

    def test_teachers_of_an_inactive_group_are_hidden(self):
        TeacherGroup.objects.filter(pk=self.english.pk).update(is_active=False)
        response = self.get()
        self.assertNotContains(response, "معلم زبان")
        # One group left in use: no chips.
        self.assertNotContains(response, 'class="tc-chip"')

    def test_chips_need_two_groups_and_the_switch(self):
        self.set(show_filter=False)
        self.assertNotContains(self.get(), 'class="tc-chip"')

        self.set(show_filter=True)
        LandingTeacher.objects.filter(group=self.english).update(group=self.base)
        response = self.get()
        self.assertNotContains(response, 'class="tc-chip"')
        self.assertContains(response, "آموزگاران پایه</h2>")

    def test_without_groups_one_flat_list(self):
        LandingTeacher.objects.update(group=None)
        response = self.get()
        self.assertContains(response, '<h2 class="tc-group__title visually-hidden" id="tc-group-other">فهرست معلمان</h2>')
        self.assertNotContains(response, "سایر معلمان")
        self.assertNotContains(response, 'class="tc-chip"')

    def test_partial_is_only_the_filter_and_the_list(self):
        response = self.get(f"{URL}?group={self.base.pk}&partial=1")
        content = response.content.decode()
        self.assertNotIn("<html", content)
        self.assertNotIn("public-nav", content)
        self.assertNotIn("<h1", content)
        self.assertIn('data-tc-swap="filter"', content)
        self.assertIn('data-tc-swap="list"', content)
        self.assertIn("معلم پایه", content)
        self.assertNotIn("معلم زبان", content)


# ------------------------------------------------- fallbacks, slug, privacy


class TeacherCardTests(TempMediaMixin, TeachersFixture):
    def test_name_and_specialty_fall_back_photo_does_not(self):
        teacher = make_teacher(first_name="مریم", last_name="نوری", field_of_study="علوم تربیتی", avatar=upload("a.png"))
        card = published(teacher=teacher)
        self.assertEqual(card.display_name, "مریم نوری")
        self.assertEqual(card.display_specialty, "علوم تربیتی")
        self.assertEqual(card.photo_url, "")

        response = self.get()
        self.assertNotContains(response, teacher.staff.user.avatar.name)
        self.assertContains(response, '<span class="tc-portrait__initial">م</span>')

    def test_overrides_win(self):
        card = published(
            teacher=make_teacher(),
            name_override="نام دلخواه",
            specialty_override="معلم زبان انگلیسی",
            photo_override=upload("p.png"),
        )
        response = self.get()
        self.assertContains(response, "نام دلخواه")
        self.assertContains(response, "معلم زبان انگلیسی")
        self.assertContains(response, f'src="{card.photo_url}"')
        self.assertNotContains(response, "tc-portrait__initial")

    def test_slug(self):
        first = published(name_override="سارا احمدی")
        second = published(name_override="سارا احمدی")
        self.assertEqual(first.slug, "سارا-احمدی")
        self.assertEqual(second.slug, "سارا-احمدی-2")

        # Not regenerated when the name changes; an edited slug is kept.
        first.name_override = "سارا احمدی‌نژاد"
        first.save()
        first.refresh_from_db()
        self.assertEqual(first.slug, "سارا-احمدی")
        second.slug = "sara"
        second.save()
        second.refresh_from_db()
        self.assertEqual(second.slug, "sara")

        response = self.get()
        self.assertContains(response, 'id="سارا-احمدی" aria-labelledby="سارا-احمدی-name"')
        self.assertContains(response, 'id="sara"')

    def test_slug_without_a_usable_name(self):
        self.assertEqual(published(name_override="؟؟").slug, "teacher")

    def test_personal_data_is_never_rendered(self):
        teacher = make_teacher(first_name="ریحانه", last_name="محمدی", field_of_study="ریاضی", avatar=upload("secret.png"))
        user = teacher.staff.user
        user.username = "zz-login-marker"
        user.national_code = "9876543210"
        user.phone_number = "09121112233"
        user.email = "secret.teacher@example.com"
        user.save()
        staff = teacher.staff
        staff.personnel_code = "PCODE-7788"
        staff.birth_date = jdatetime.date(1361, 5, 17)
        staff.address = "نشانی-محرمانه-خانه"
        staff.emergency_phone = "09350001122"
        staff.save()
        teacher.education = "مدرک-محرمانه-پرونده"
        teacher.teaching_experience = 4321
        teacher.save()
        make_assignment(teacher, make_branch(name="شعبه-محرمانه"), make_academic_year())
        published(teacher=teacher, on_home=True)

        markers = [
            "zz-login-marker", "9876543210", "۹۸۷۶۵۴۳۲۱۰", "09121112233", "۰۹۱۲۱۱۱۲۲۳۳",
            "secret.teacher@example.com", "PCODE-7788", "1361", "۱۳۶۱", "نشانی-محرمانه-خانه",
            "09350001122", "۰۹۳۵۰۰۰۱۱۲۲", "مدرک-محرمانه-پرونده", "4321", "۴۳۲۱", "شعبه-محرمانه",
            "users/avatars", user.avatar.name,
        ]
        for url in (URL, URL + "?partial=1", "/"):
            response = self.get(url)
            self.assertContains(response, "ریحانه محمدی")
            for marker in markers:
                self.assertNotContains(response, marker, msg_prefix=f"{url}: {marker}")

    def test_new_photo_is_reencoded_and_the_old_file_removed(self):
        with self.captureOnCommitCallbacks(execute=True):
            card = published(photo_override=phone_photo())
        assert_reencoded(self, card.photo_override)
        old = card.photo_override.name
        storage = card.photo_override.storage
        self.assertTrue(storage.exists(old))

        # A save without a new upload leaves the stored file alone.
        card.bio = "معرفی"
        with self.captureOnCommitCallbacks(execute=True):
            card.save()
        self.assertEqual(card.photo_override.name, old)

        with self.captureOnCommitCallbacks(execute=True):
            card.photo_override = phone_photo("second.jpg")
            card.save()
        self.assertNotEqual(card.photo_override.name, old)
        self.assertFalse(storage.exists(old))

    def test_transparent_png_is_flattened(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGBA", (40, 60), (0, 0, 0, 0)).save(buffer, "PNG")
        card = published(photo_override=SimpleUploadedFile("t.png", buffer.getvalue(), content_type="image/png"))
        with card.photo_override.open("rb") as stored, Image.open(stored) as image:
            self.assertEqual((image.format, image.mode, image.size), ("JPEG", "RGB", (40, 60)))
            self.assertEqual(image.getpixel((5, 5)), (255, 255, 255))


# ------------------------------------------------------------- landing page


class LandingTeachersTests(TempMediaMixin, TestCase):
    def test_only_active_on_home_teachers_who_have_not_left(self):
        LandingTeacher.objects.create(name_override="روی صفحه اصلی", on_home=True)
        LandingTeacher.objects.create(name_override="فقط صفحه معلمان", on_teachers_page=True)
        LandingTeacher.objects.create(name_override="خاموش", on_home=True, is_active=False)
        left = make_teacher(first_name="رفته")
        LandingTeacher.objects.create(teacher=left, on_home=True)
        left.staff.is_active = False
        left.staff.save()

        response = self.client.get("/")
        self.assertContains(response, "روی صفحه اصلی")
        for name in ("فقط صفحه معلمان", "خاموش", "رفته"):
            self.assertNotContains(response, name)

    def test_section_is_hidden_without_an_active_on_home_teacher(self):
        LandingTeacher.objects.create(name_override="فقط صفحه معلمان", on_teachers_page=True)
        LandingTeacher.objects.create(name_override="خاموش", on_home=True, is_active=False)
        self.assertNotContains(self.client.get("/"), 'class="instructors-section"')

    def test_initial_instead_of_the_avatar_and_the_link_to_the_page(self):
        teacher = make_teacher(first_name="مریم", avatar=upload("a.png"))
        LandingTeacher.objects.create(teacher=teacher, on_home=True)
        response = self.client.get("/")
        self.assertNotContains(response, teacher.staff.user.avatar.name)
        self.assertContains(response, '<span class="instructor-initial" aria-hidden="true">م</span>')
        self.assertContains(response, '<p class="instructors-more"><a href="/teachers/">آشنایی با همه معلمان</a></p>')

        LandingPage.objects.filter(pk=1).update(teachers_link_text="")
        self.assertNotContains(self.client.get("/"), "instructors-more")


# ---------------------------------------------------------------------- admin


class TeachersAdminTests(TempMediaMixin, TeachersFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(User.objects.create_superuser("admin", "a@example.com", "x"))

    def test_teachers_page_is_a_singleton_with_groups(self):
        response = self.client.get(reverse("admin:website_teacherspage_changelist"))
        self.assertRedirects(response, reverse("admin:website_teacherspage_change", args=[1]))
        response = self.client.get(reverse("admin:website_teacherspage_change", args=[1]))
        self.assertContains(response, 'name="groups-TOTAL_FORMS"')
        self.assertContains(response, f'href="{reverse("admin:website_landingteacher_changelist")}"')
        self.assertEqual(self.client.get(reverse("admin:website_teacherspage_add")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:website_teacherspage_delete", args=[1])).status_code, 403)

    def test_teacher_list_search_and_filters(self):
        group = self.group("زبان انگلیسی")
        published(name_override="مریم نوری", group=group)
        published(teacher=make_teacher(first_name="الهام", last_name="کاظمی"))
        changelist = reverse("admin:website_landingteacher_changelist")

        response = self.client.get(changelist)
        self.assertContains(response, "مریم نوری")
        self.assertContains(response, "الهام کاظمی")
        self.assertContains(response, 'name="form-0-on_teachers_page"')
        self.assertContains(response, 'name="form-0-on_home"')

        response = self.client.get(changelist, {"q": "کاظمی"})
        self.assertContains(response, "الهام کاظمی")
        self.assertNotContains(response, "مریم نوری")

        response = self.client.get(changelist, {"group__id__exact": group.pk})
        self.assertContains(response, "مریم نوری")
        self.assertNotContains(response, "الهام کاظمی")

    def test_add_a_teacher_with_a_photo(self):
        response = self.client.get(reverse("admin:website_landingteacher_add"))
        self.assertContains(response, "admin-autocomplete")
        self.assertContains(response, "اطلاعات همراه عکس (مثل موقعیت مکانی گوشی) هنگام ذخیره حذف می‌شود.")

        response = self.client.post(
            reverse("admin:website_landingteacher_add"),
            {
                "name_override": "سمیه کاظمی",
                "specialty_override": "آموزگار پایه سوم",
                "is_active": "on",
                "on_teachers_page": "on",
                "order": "1",
                "photo_override": phone_photo(),
                "slug": "",
            },
        )
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].errors)
        card = LandingTeacher.objects.get(name_override="سمیه کاظمی")
        self.assertEqual(card.slug, "سمیه-کاظمی")
        self.assertFalse(card.on_home)
        assert_reencoded(self, card.photo_override)

    def test_add_requires_a_name(self):
        response = self.client.post(reverse("admin:website_landingteacher_add"), {"order": "0", "is_active": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "یک معلم دارای نام انتخاب کنید یا نام نمایشی را وارد کنید.")

    def test_landing_page_admin_has_no_teacher_inline(self):
        response = self.client.get(reverse("admin:website_landingpage_change", args=[LandingPage.load().pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="teachers-TOTAL_FORMS"')
        self.assertContains(response, 'name="teachers_link_url"')
        self.assertContains(response, f'href="{reverse("admin:website_landingteacher_changelist")}"')

    def test_staff_without_permission_is_refused(self):
        self.client.force_login(User.objects.create_user("office", password="x", is_staff=True, role=User.Roles.TEACHER))
        self.assertEqual(self.client.get(reverse("admin:website_landingteacher_changelist")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:website_teacherspage_change", args=[1])).status_code, 403)


# ----------------------------------------------------------------- migrations


class TeachersMigrationTests(TestCase):
    """The data migrations' functions, run against the current models."""

    seed = importlib.import_module("website.migrations.0010_seed_teachers")
    menu = importlib.import_module("website.migrations.0012_teachers_menu")
    hide = importlib.import_module("website.migrations.0013_hide_seed_teachers")

    def test_seed_creates_the_page_once_and_fills_missing_slugs(self):
        TeachersPage.objects.all().delete()
        taken = LandingTeacher.objects.create(name_override="سارا احمدی")
        self.assertEqual(taken.slug, "سارا-احمدی")
        card = LandingTeacher.objects.create(teacher=make_teacher(first_name="سارا", last_name="احمدی"))
        LandingTeacher.objects.filter(pk=card.pk).update(slug="")

        self.seed.seed(django_apps, None)
        self.seed.seed(django_apps, None)
        self.assertEqual(TeachersPage.objects.count(), 1)
        card.refresh_from_db()
        taken.refresh_from_db()
        self.assertEqual(taken.slug, "سارا-احمدی")
        self.assertEqual(card.slug, "سارا-احمدی-2")
        self.assertFalse(TeacherGroup.objects.exists())

    def test_menu_row_still_at_hash_is_linked_and_reversed(self):
        NavMenuItem.objects.filter(title="معلمان").update(url="#")
        NavMenuItem.objects.filter(title="وبلاگ").update(url="#")  # the seed's state; 0014 links it
        others = dict(NavMenuItem.objects.exclude(title="معلمان").values_list("title", "url"))

        self.menu.link_teachers(django_apps, None)
        self.assertEqual(NavMenuItem.objects.get(title="معلمان").url, "/teachers/")
        self.assertEqual(dict(NavMenuItem.objects.exclude(title="معلمان").values_list("title", "url")), others)
        self.assertEqual(others["وبلاگ"], "#")

        self.menu.unlink_teachers(django_apps, None)
        self.assertEqual(NavMenuItem.objects.get(title="معلمان").url, "#")

    def test_an_edited_menu_row_is_left_alone(self):
        NavMenuItem.objects.filter(title="معلمان").update(url="/our-teachers/")
        self.menu.link_teachers(django_apps, None)
        self.menu.unlink_teachers(django_apps, None)
        self.assertEqual(NavMenuItem.objects.get(title="معلمان").url, "/our-teachers/")

    def seed_rows(self):
        return LandingTeacher.objects.filter(name_override__in=[name for name, _ in self.hide.SEED_TEACHERS])

    def test_untouched_seed_teachers_are_hidden_and_reversed(self):
        # The test database already ran 0013: start from the seed's state.
        self.seed_rows().update(is_active=True)
        self.assertEqual(self.seed_rows().count(), 4)
        self.assertEqual(self.client.get("/").content.decode().count('class="instructor-card"'), 4)

        self.hide.hide(django_apps, None)
        self.assertFalse(self.seed_rows().filter(is_active=True).exists())
        self.assertNotContains(self.client.get("/"), 'class="instructors-section"')

        self.hide.show(django_apps, None)
        self.assertEqual(self.seed_rows().filter(is_active=True).count(), 4)

    def test_edited_seed_teachers_are_left_alone(self):
        self.seed_rows().update(is_active=True)
        ali, saeed, maria, neda = (self.seed_rows().get(name_override=name) for name, _ in self.hide.SEED_TEACHERS)
        LandingTeacher.objects.filter(pk=ali.pk).update(specialty_override="معلم ریاضی")
        LandingTeacher.objects.filter(pk=saeed.pk).update(teacher=make_teacher())
        LandingTeacher.objects.filter(pk=maria.pk).update(photo_override="website/teachers/real.jpg")

        self.hide.hide(django_apps, None)
        active = set(self.seed_rows().filter(is_active=True).values_list("pk", flat=True))
        self.assertEqual(active, {ali.pk, saeed.pk, maria.pk})

        # The reverse only re-activates the untouched rows.
        LandingTeacher.objects.filter(pk=ali.pk).update(is_active=False)
        self.hide.show(django_apps, None)
        active = set(self.seed_rows().filter(is_active=True).values_list("pk", flat=True))
        self.assertEqual(active, {saeed.pk, maria.pk, neda.pk})
