import importlib
import shutil
import tempfile
from datetime import timedelta

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import Client, RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.testing import make_branch

from .forms import form_token
from .models import (
    ContactChannel,
    ContactLocation,
    ContactMessage,
    ContactPage,
    ContactTopic,
    FooterLink,
    NavMenuItem,
)
from .services import client_ip, client_ip_hash
from .tests import PIXEL

User = get_user_model()
URL = "/contact/"


def valid_data(**overrides):
    topic = ContactTopic.objects.first()
    data = {
        "name": "مریم محمدی",
        "mobile": "09141234567",
        "topic": str(topic.pk) if topic else "",
        "message": "سلام، برای ثبت‌نام کلاس اول سوال دارم.",
        "website": "",
        # Rendered 10 s ago: past the time trap.
        "started": form_token(timezone.now() - timedelta(seconds=10)),
    }
    data.update(overrides)
    return data


class ContactFixture(TestCase):
    """The seeded page (topics) plus two branches with locations and channels."""

    @classmethod
    def setUpTestData(cls):
        cls.page = ContactPage.load()
        cls.ammar = make_branch(name="شعبه مرکزی (عمار)", order=1)
        cls.ammar.address = "ارومیه، خیابان عمار"
        cls.ammar.phone_number = "044-33445566"
        cls.ammar.save()
        cls.afshar = make_branch(name="شعبه ۲ (منصور افشار)", order=2)
        cls.loc_ammar = ContactLocation.objects.create(
            page=cls.page, branch=cls.ammar, order=1, hours="شنبه تا چهارشنبه", neshan_url="https://neshan.org/x"
        )
        cls.loc_afshar = ContactLocation.objects.create(
            page=cls.page, branch=cls.afshar, order=2, address_override="بلوار منصور افشار"
        )
        cls.office = ContactChannel.objects.create(
            page=cls.page, label="دفتر مدرسه", kind="phone", value="۰۴۴-۳۳۱۱۲۲۳۳", order=1
        )
        ContactChannel.objects.create(page=cls.page, label="ایمیل", kind="email", value="info@example.com", order=2)
        ContactChannel.objects.create(
            page=cls.page, location=cls.loc_afshar, label="دفتر شعبه", kind="mobile", value="0914 000 1122"
        )

    def post(self, ip="5.6.7.8", **overrides):
        return self.client.post(URL, valid_data(**overrides), REMOTE_ADDR=ip, HTTP_X_REAL_IP=ip)


# ----------------------------------------------------------------------- view


class ContactViewTests(ContactFixture):
    def test_url_name(self):
        self.assertEqual(reverse("website:contact"), URL)

    def test_page_renders_content(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        for text in (
            "با دفتر مدرسه در تماس باشید",   # hero default
            "شعبه مرکزی (عمار)",             # branch name fallback
            "ارومیه، خیابان عمار",           # branch address fallback
            "بلوار منصور افشار",             # override
            "شنبه تا چهارشنبه",
            "info@example.com",
            "ثبت‌نام",                        # seeded topic
        ):
            self.assertContains(response, text)
        self.assertContains(response, 'href="https://neshan.org/x"')

    def test_phone_links_use_ascii_digits_and_show_persian(self):
        response = self.client.get(URL)
        self.assertContains(response, 'href="tel:04433112233"')
        self.assertContains(response, "۰۴۴-۳۳۱۱۲۲۳۳")
        self.assertContains(response, 'href="tel:09140001122"')
        self.assertContains(response, 'href="mailto:info@example.com"')

    def test_branch_phone_shows_only_without_a_phone_channel(self):
        response = self.client.get(URL)
        # Ammar has no phone channel: the branch's number is shown.
        self.assertContains(response, 'href="tel:04433445566"')
        ContactChannel.objects.create(
            page=self.page, location=self.loc_ammar, label="عمار", kind="phone", value="044-11112222"
        )
        response = self.client.get(URL)
        self.assertNotContains(response, 'href="tel:04433445566"')

    def test_hero_and_bar_call_the_first_school_wide_phone(self):
        response = self.client.get(URL)
        self.assertEqual(response.context["call"]["href"], "tel:04433112233")
        self.assertContains(response, 'class="ct-bar"')
        self.assertEqual(response.context["directions_url"], "https://neshan.org/x")

    def test_no_bar_without_phone_or_map(self):
        ContactChannel.objects.all().delete()
        ContactLocation.objects.all().delete()
        response = self.client.get(URL)
        self.assertIsNone(response.context["call"])
        self.assertNotContains(response, 'class="ct-bar"')
        self.assertNotContains(response, "has-ct-bar")

    def test_switches_and_inactive_items(self):
        self.page.show_channels = False
        self.page.show_locations = False
        self.page.show_form = False
        self.page.save()
        response = self.client.get(URL)
        self.assertNotContains(response, "ct-channels")
        self.assertNotContains(response, "ct-locations")
        self.assertNotContains(response, 'id="contact-form"')

    def test_inactive_location_and_inactive_branch_are_hidden(self):
        self.loc_afshar.is_active = False
        self.loc_afshar.save()
        self.ammar.is_active = False
        self.ammar.save()
        response = self.client.get(URL)
        self.assertNotContains(response, "بلوار منصور افشار")
        self.assertNotContains(response, "ارومیه، خیابان عمار")

    def test_faq_teaser_is_off_by_default(self):
        self.assertNotContains(self.client.get(URL), 'class="ct-faq"')
        self.page.show_faq = True
        self.page.save()
        self.assertContains(self.client.get(URL), 'class="ct-faq"')

    def test_social_chips_skip_placeholder_links(self):
        FooterLink.objects.filter(title="اینستاگرام").update(url="https://instagram.com/school")
        response = self.client.get(URL)
        self.assertContains(response, 'class="ct-social__link" target="_blank"')
        html = response.content.decode()
        social = html[html.index('class="ct-social"'):html.index("</ul>", html.index('class="ct-social"'))]
        self.assertIn("اینستاگرام", social)
        self.assertNotIn("تلگرام", social)  # still "#"

    def test_user_text_is_escaped(self):
        self.office.note = "<script>alert(1)</script>"
        self.office.save()
        response = self.client.get(URL)
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, "&lt;script&gt;")

    def test_nav_item_points_here_and_is_current(self):
        response = self.client.get(URL)
        self.assertContains(response, 'href="/contact/" class="public-nav__link is-active"')

    def test_only_get_and_post(self):
        self.assertEqual(self.client.put(URL).status_code, 405)

    def test_query_count_does_not_grow_with_items(self):
        def count_queries():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(URL)
            return len(ctx.captured_queries)

        before = count_queries()
        for i in range(4):
            branch = make_branch(name=f"شعبه {i}", order=10 + i)
            location = ContactLocation.objects.create(page=self.page, branch=branch, order=10 + i)
            ContactChannel.objects.create(page=self.page, location=location, label="x", value=f"0441234{i}")
            ContactChannel.objects.create(page=self.page, label="y", value=f"0449876{i}")
            ContactTopic.objects.create(page=self.page, title=f"موضوع {i}")
        self.assertEqual(count_queries(), before)


# ----------------------------------------------------------------------- form


class ContactFormTests(ContactFixture):
    def test_success_saves_and_redirects(self):
        response = self.post(mobile="۰۹۱۴ ۱۲۳ ۴۵۶۷", location=str(self.loc_afshar.pk))
        self.assertRedirects(response, URL + "#contact-form", fetch_redirect_response=False)
        message = ContactMessage.objects.get()
        self.assertEqual(message.mobile, "09141234567")
        self.assertEqual(message.topic, "ثبت‌نام")
        self.assertEqual(message.location, "شعبه ۲ (منصور افشار)")
        self.assertFalse(message.is_handled)

        page = self.client.get(URL)
        self.assertContains(page, 'class="ct-success" role="status"')
        self.assertContains(page, "۰۹۱۴۱۲۳۴۵۶۷")

    def test_mobile_variants(self):
        for ok in ("+98 914 123 4567", "00989141234567", "9141234567", "۰۹۱۴-۱۲۳-۴۵۶۷"):
            ContactMessage.objects.all().delete()
            self.assertEqual(self.post(mobile=ok).status_code, 302, ok)
            self.assertEqual(ContactMessage.objects.get().mobile, "09141234567")
        for bad in ("0912", "02133445566", "۰۹۱۲۳۴۵۶۷۸۹۰", "abc"):
            response = self.post(mobile=bad)
            self.assertEqual(response.status_code, 200, bad)
            self.assertContains(response, "شماره موبایل باید ۱۱ رقم باشد")

    def test_required_fields_and_lengths(self):
        response = self.post(name="", mobile="", topic="", message="")
        for text in ("نام و نام خانوادگی را وارد کنید.", "شماره موبایل را وارد کنید.",
                     "موضوع پیام را انتخاب کنید.", "متن پیام را بنویسید."):
            self.assertContains(response, text)
        response = self.post(name="م", message="کوتاه")
        self.assertContains(response, "نام باید دست‌کم ۲ حرف باشد.")
        self.assertContains(response, "متن پیام باید دست‌کم ۱۰ حرف باشد.")
        response = self.post(message="الف" * 2001)
        self.assertContains(response, "متن پیام حداکثر ۲۰۰۰ حرف است.")
        self.assertFalse(ContactMessage.objects.exists())

    def test_errors_are_linked_to_their_inputs(self):
        response = self.post(name="")
        self.assertContains(response, 'id="ct-errors" role="alert"')
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'aria-describedby="id_name_error"')
        self.assertContains(response, 'id="id_name_error"')
        self.assertContains(response, 'aria-describedby="id_mobile_helptext"')
        self.assertContains(response, 'id="id_mobile_helptext"')
        self.assertContains(response, 'value="09141234567"')  # what was typed is kept

    def test_unknown_topic_or_location_is_refused(self):
        response = self.post(topic="99999")
        self.assertContains(response, "گزینه‌ی انتخاب‌شده معتبر نیست.")
        response = self.post(location="99999")
        self.assertContains(response, "گزینه‌ی انتخاب‌شده معتبر نیست.")
        self.assertFalse(ContactMessage.objects.exists())

    def test_location_field_needs_two_locations(self):
        self.assertContains(self.client.get(URL), 'name="location"')
        self.loc_afshar.delete()
        self.assertNotContains(self.client.get(URL), 'name="location"')
        # And a submission without it still works.
        self.assertEqual(self.post().status_code, 302)

    def test_topic_field_hidden_without_topics(self):
        ContactTopic.objects.all().delete()
        self.assertNotContains(self.client.get(URL), 'name="topic"')
        self.assertEqual(self.post(topic="").status_code, 302)
        self.assertEqual(ContactMessage.objects.get().topic, "")

    def test_post_ignored_when_form_is_off(self):
        self.page.show_form = False
        self.page.save()
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContactMessage.objects.exists())

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(URL, valid_data()).status_code, 403)
        self.assertFalse(ContactMessage.objects.exists())


# ----------------------------------------------------------------------- spam


class ContactSpamTests(ContactFixture):
    def test_honeypot_pretends_success_and_saves_nothing(self):
        response = self.post(website="http://spam.example")
        self.assertRedirects(response, URL + "#contact-form", fetch_redirect_response=False)
        self.assertFalse(ContactMessage.objects.exists())
        self.assertContains(self.client.get(URL), 'class="ct-success"')

    def test_honeypot_is_hidden_from_people(self):
        self.assertContains(self.client.get(URL), '<div class="ct-hp" aria-hidden="true">')

    def test_time_trap(self):
        response = self.post(started=form_token())
        self.assertContains(response, "فرم خیلی سریع ارسال شد")
        response = self.post(started=form_token(timezone.now() - timedelta(hours=3)))
        self.assertContains(response, "فرم منقضی شده است")
        response = self.post(started="forged")
        self.assertContains(response, "فرم معتبر نیست")
        self.assertFalse(ContactMessage.objects.exists())

    def test_fourth_message_from_one_ip_within_ten_minutes_is_refused(self):
        for i in range(3):
            self.assertEqual(self.post(mobile=f"0914000000{i}").status_code, 302)
        response = self.post(mobile="09140000009")
        self.assertEqual(response.status_code, 429)
        self.assertContains(response, "پیام‌های زیادی ثبت شده است", status_code=429)
        self.assertContains(response, "سلام، برای ثبت‌نام", status_code=429)  # text kept
        self.assertEqual(ContactMessage.objects.count(), 3)

    def test_one_mobile_is_limited_across_ips(self):
        for i in range(3):
            self.assertEqual(self.post(ip=f"10.0.0.{i}").status_code, 302)
        self.assertEqual(self.post(ip="10.0.0.99").status_code, 429)

    def test_shared_ip_with_different_mobiles_after_the_window(self):
        """CGNAT: many parents behind one IP are only held to the daily cap."""
        for i in range(3):
            self.assertEqual(self.post(mobile=f"0914000000{i}").status_code, 302)
        ContactMessage.objects.update(created_at=timezone.now() - timedelta(minutes=11))
        for i in range(3, 6):
            self.assertEqual(self.post(mobile=f"0914000000{i}").status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 6)

    @override_settings(CONTACT_DAILY_LIMIT=5)
    def test_daily_cap_per_ip(self):
        for i in range(5):
            ContactMessage.objects.create(
                name="x", mobile=f"0914000001{i}", message="x" * 10, ip_hash=self._hash("5.6.7.8")
            )
        ContactMessage.objects.update(created_at=timezone.now() - timedelta(hours=2))
        self.assertEqual(self.post(mobile="09140000020").status_code, 429)
        # Older than 24 hours no longer counts.
        ContactMessage.objects.update(created_at=timezone.now() - timedelta(hours=25))
        self.assertEqual(self.post(mobile="09140000020").status_code, 302)

    def test_other_ip_and_mobile_are_not_limited(self):
        for i in range(3):
            self.post(mobile=f"0914000000{i}")
        self.assertEqual(self.post(ip="9.9.9.9", mobile="09145555555").status_code, 302)

    def test_only_the_ip_hash_is_stored(self):
        self.post(ip="5.6.7.8")
        message = ContactMessage.objects.get()
        self.assertEqual(message.ip_hash, self._hash("5.6.7.8"))
        self.assertEqual(len(message.ip_hash), 64)
        self.assertNotIn("5.6.7.8", str(ContactMessage.objects.values().get()))

    def _hash(self, ip):
        return client_ip_hash(RequestFactory().get(URL, REMOTE_ADDR=ip, HTTP_X_REAL_IP=ip))


class ClientIpTests(TestCase):
    def request(self, **meta):
        return RequestFactory().get(URL, **meta)

    def test_configured_header_wins(self):
        with override_settings(CLIENT_IP_HEADER="CF-Connecting-IP"):
            request = self.request(REMOTE_ADDR="172.18.0.5", HTTP_CF_CONNECTING_IP="5.6.7.8", HTTP_X_REAL_IP="1.1.1.1")
            self.assertEqual(client_ip(request), "5.6.7.8")
        with override_settings(CLIENT_IP_HEADER="HTTP_AR_REAL_IP"):
            self.assertEqual(client_ip(self.request(HTTP_AR_REAL_IP="2a01:5ec0::1")), "2a01:5ec0::1")

    def test_default_is_nginx_x_real_ip(self):
        self.assertEqual(client_ip(self.request(REMOTE_ADDR="172.18.0.5", HTTP_X_REAL_IP="5.6.7.8")), "5.6.7.8")

    def test_first_entry_of_a_list_and_fallbacks(self):
        with override_settings(CLIENT_IP_HEADER="X-Forwarded-For"):
            self.assertEqual(client_ip(self.request(HTTP_X_FORWARDED_FOR="5.6.7.8, 10.0.0.1")), "5.6.7.8")
            # Missing or malformed header -> REMOTE_ADDR.
            self.assertEqual(client_ip(self.request(REMOTE_ADDR="9.9.9.9")), "9.9.9.9")
            self.assertEqual(client_ip(self.request(REMOTE_ADDR="9.9.9.9", HTTP_X_FORWARDED_FOR="evil")), "9.9.9.9")
        with override_settings(CLIENT_IP_HEADER=""):
            self.assertEqual(client_ip(self.request(REMOTE_ADDR="9.9.9.9", HTTP_X_REAL_IP="5.6.7.8")), "9.9.9.9")


# ---------------------------------------------------------------------- models


class ContactModelTests(ContactFixture):
    def test_channel_validation(self):
        for kind, value in (("email", "not-an-email"), ("mobile", "0912"), ("phone", "12")):
            with self.assertRaises(ValidationError, msg=value) as ctx:
                ContactChannel(page=self.page, label="x", kind=kind, value=value).full_clean()
            self.assertIn("value", ctx.exception.message_dict)
        for kind, value in (("email", "a@b.ir"), ("mobile", "۰۹۱۲ ۳۴۵ ۶۷۸۹"), ("phone", "+98 44 3344 5566")):
            ContactChannel(page=self.page, label="x", kind=kind, value=value).full_clean()

    def test_channel_href(self):
        self.assertEqual(ContactChannel(kind="phone", value="+98 (44) 3344-5566").href, "tel:+984433445566")
        self.assertEqual(ContactChannel(kind="mobile", value="+98 912 345 6789").href, "tel:09123456789")

    def test_location_needs_branch_or_title(self):
        with self.assertRaises(ValidationError):
            ContactLocation(page=self.page).clean()
        ContactLocation(page=self.page, title_override="دفتر پذیرش").clean()

    def test_map_links_only_filled_ones(self):
        location = ContactLocation(page=self.page, balad_url="https://balad.ir/x")
        self.assertEqual(location.map_links, [("بلد", "https://balad.ir/x")])

    def test_map_links_must_be_safe(self):
        location = ContactLocation(page=self.page, title_override="x", neshan_url="javascript:alert(1)")
        with self.assertRaises(ValidationError):
            location.full_clean()

    def test_success_text(self):
        self.assertIn("۰۹۱۴۱۲۳۴۵۶۷", self.page.success_text("09141234567"))

    def test_map_image_is_removed_when_replaced(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        with override_settings(MEDIA_ROOT=media):
            self.loc_ammar.map_image = SimpleUploadedFile("one.png", PIXEL, content_type="image/png")
            self.loc_ammar.save()
            old = self.loc_ammar.map_image.name
            storage = self.loc_ammar.map_image.storage
            with self.captureOnCommitCallbacks(execute=True):
                self.loc_ammar.map_image = SimpleUploadedFile("two.png", PIXEL, content_type="image/png")
                self.loc_ammar.save()
            self.assertFalse(storage.exists(old))


# ----------------------------------------------------------------------- admin


class ContactAdminTests(ContactFixture):
    def setUp(self):
        self.message = ContactMessage.objects.create(
            name="مریم", mobile="09141234567", topic="ثبت‌نام", message="سلام سلام سلام", ip_hash="h"
        )

    def staff(self, *codenames):
        user = User.objects.create_user(f"office{User.objects.count()}", password="x", is_staff=True)
        user.user_permissions.set(Permission.objects.filter(content_type__app_label="website", codename__in=codenames))
        self.client.force_login(user)
        return user

    def test_page_admin_is_a_singleton_with_inlines(self):
        self.client.force_login(User.objects.create_superuser("admin", "a@example.com", "x"))
        response = self.client.get(reverse("admin:website_contactpage_changelist"))
        self.assertRedirects(response, reverse("admin:website_contactpage_change", args=[1]))
        response = self.client.get(reverse("admin:website_contactpage_change", args=[1]))
        self.assertEqual(response.status_code, 200)
        for prefix in ("locations", "channels", "topics"):
            self.assertContains(response, f'name="{prefix}-TOTAL_FORMS"')

    def test_message_list_and_persian_digit_search(self):
        self.staff("view_contactmessage")
        url = reverse("admin:website_contactmessage_changelist")
        response = self.client.get(url, {"q": "۰۹۱۴۱۲۳"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "مریم")

    def test_view_only_staff_cannot_change(self):
        self.staff("view_contactmessage")
        url = reverse("admin:website_contactmessage_change", args=[self.message.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {"is_handled": "on"})
        self.message.refresh_from_db()
        self.assertFalse(self.message.is_handled)

    def test_change_staff_can_only_tick_handled(self):
        self.staff("view_contactmessage", "change_contactmessage")
        url = reverse("admin:website_contactmessage_change", args=[self.message.pk])
        response = self.client.post(url, {"is_handled": "on", "name": "دستکاری", "message": "دستکاری شده"})
        self.assertEqual(response.status_code, 302)
        self.message.refresh_from_db()
        self.assertTrue(self.message.is_handled)
        self.assertEqual(self.message.name, "مریم")
        self.assertEqual(self.message.message, "سلام سلام سلام")

    def test_add_forbidden_and_delete_superuser_only(self):
        self.staff("view_contactmessage", "change_contactmessage", "delete_contactmessage")
        self.assertEqual(self.client.get(reverse("admin:website_contactmessage_add")).status_code, 403)
        delete_url = reverse("admin:website_contactmessage_delete", args=[self.message.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 403)

        self.client.force_login(User.objects.create_superuser("root", "r@example.com", "x"))
        self.assertEqual(self.client.get(reverse("admin:website_contactmessage_add")).status_code, 403)
        self.assertEqual(self.client.get(delete_url).status_code, 200)

    def test_ip_hash_is_not_shown(self):
        self.staff("view_contactmessage")
        response = self.client.get(reverse("admin:website_contactmessage_change", args=[self.message.pk]))
        self.assertNotContains(response, "شناسه دستگاه")


# ------------------------------------------------------------------ migrations


class ContactMigrationTests(TestCase):
    """The data migrations' functions, run against the current models."""

    seed = importlib.import_module("website.migrations.0004_seed_contact")
    link = importlib.import_module("website.migrations.0005_link_contact_menu")

    def test_seed_creates_topics_and_one_location_per_active_branch(self):
        ContactLocation.objects.all().delete()
        ContactTopic.objects.all().delete()
        first = make_branch(name="الف", order=2)
        second = make_branch(name="ب", order=1)
        make_branch(name="غیرفعال", is_active=False, order=3)

        self.seed.seed(django_apps, None)
        self.assertEqual(ContactTopic.objects.count(), 5)
        self.assertEqual(list(ContactLocation.objects.values_list("branch", flat=True)), [second.pk, first.pk])

        # Re-running never duplicates.
        self.seed.seed(django_apps, None)
        self.assertEqual(ContactLocation.objects.count(), 2)
        self.assertEqual(ContactTopic.objects.count(), 5)

    def test_link_changes_only_rows_still_at_hash_and_reverses(self):
        # The test database already ran 0005: start from the seed's state.
        NavMenuItem.objects.filter(title="تماس با ما").update(url="#")
        FooterLink.objects.filter(title="تماس با ما").update(url="/edited/")
        other = NavMenuItem.objects.exclude(title="تماس با ما").first()

        self.link.link(django_apps, None)
        self.assertEqual(NavMenuItem.objects.get(title="تماس با ما").url, "/contact/")
        self.assertEqual(FooterLink.objects.get(title="تماس با ما").url, "/edited/")  # admin-edited: untouched
        other.refresh_from_db()
        self.assertEqual(other.url, "#")

        self.link.unlink(django_apps, None)
        self.assertEqual(NavMenuItem.objects.get(title="تماس با ما").url, "#")
        self.assertEqual(FooterLink.objects.get(title="تماس با ما").url, "/edited/")
