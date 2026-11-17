"""
Allowed domains and invisible marks in links (2026-11 allowed-domains fix).

The reported case: ``https://skyroom.online/ch/nasle_ghalam/sheshom1-1``
copied from a messenger with an RLM after the host was refused on a platform
allowing ``skyroom.online``. Links are now cleaned before they are checked,
and every path stores the cleaned link.
"""

from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from core.moments import format_jalali_datetime
from core.spreadsheet import FileRejected
from core.testing import make_superuser
from online_classes import importer, services
from online_classes.models import Announcement, OnlineEvent, OnlineEventAccess, OnlinePlatform
from online_classes.testing import NOW, SchoolMixin, make_access, make_announcement, make_event, make_platform
from online_classes.validators import (
    clean_url, normalise_domains, safe_button_url, safe_https_url, split_domains, tidy_domains,
    validate_button_url, validate_domains, validate_https_url,
)

from .test_importer import cells, xlsx

LRM, RLM, ZWNJ, ZWSP, BOM, ALM = "‎", "‏", "‌", "​", "﻿", "؜"
REPORTED = "https://skyroom.online/ch/nasle_ghalam/sheshom1-1"
#: The reported link as it arrives from a Persian messenger: an RLM right after the host.
PASTED = "https://skyroom.online" + RLM + "/ch/nasle_ghalam/sheshom1-1"
PERSONAL = OnlineEvent.AccessMode.PERSONAL
NOT_ALLOWED = "جزو دامنه‌های مجاز این پلتفرم نیست"


class CleanUrlTests(SimpleTestCase):
    def test_bidi_and_zero_width_are_removed_everywhere(self):
        for mark in (LRM, RLM, ZWSP, BOM, ALM, "‪", "‫", "‬", "‭", "‮",
                     "⁦", "⁧", "⁨", "⁩"):
            with self.subTest(hex(ord(mark))):
                dirty = f"{mark}https://{mark}skyroom{mark}.online{mark}/ch/{mark}x?y={mark}1#{mark}f{mark}"
                self.assertEqual(clean_url(dirty), "https://skyroom.online/ch/x?y=1#f")

    def test_zwnj_leaves_the_scheme_and_host_but_stays_in_the_path(self):
        dirty = f"{ZWNJ}https://sky{ZWNJ}room.online{ZWNJ}/کلاس{ZWNJ}ها?q=a{ZWNJ}b#c{ZWNJ}d"
        self.assertEqual(clean_url(dirty), f"https://skyroom.online/کلاس{ZWNJ}ها?q=a{ZWNJ}b#c{ZWNJ}d")

    def test_surrounding_whitespace_is_trimmed(self):
        self.assertEqual(clean_url(f"  {RLM}\n{REPORTED}\n "), REPORTED)

    def test_empty(self):
        self.assertEqual(clean_url(""), "")
        self.assertEqual(clean_url(None), "")
        self.assertEqual(clean_url(RLM + LRM), "")

    def test_internal_paths(self):
        self.assertEqual(clean_url(f"{RLM}/student/online/{LRM}"), "/student/online/")


class LinkValidationTests(SimpleTestCase):
    def assertRefused(self, link, message, domains=None):
        with self.assertRaises(ValidationError) as caught:
            validate_https_url(link, domains)
        self.assertIn(message, caught.exception.messages[0])

    def test_the_reported_link_passes(self):
        for link in (REPORTED, PASTED, RLM + REPORTED + LRM, REPORTED.replace("https://", "https://" + RLM),
                     REPORTED.replace(".online", ZWNJ + ".online")):
            with self.subTest(ascii(link)):
                validate_https_url(link, "skyroom.online")
                self.assertEqual(safe_https_url(link), REPORTED)

    def test_trailing_dot_and_port_are_the_same_host(self):
        validate_https_url("https://skyroom.online./ch/x", "skyroom.online")
        validate_https_url("https://class.skyroom.online.:443/ch/x", "skyroom.online")

    def test_a_host_still_not_ascii_is_refused(self):
        for link in ("https://اسکای.ir/x", "https://skyroom.آنلاین/x", "https://skyрoom.online/x"):
            with self.subTest(link):
                self.assertRefused(link, "دامنه‌ی لینک باید با حروف انگلیسی باشد")
            self.assertEqual(safe_https_url(link), "")

    def test_marks_never_hide_a_user_at_host(self):
        for link in (f"https://skyroom.online{RLM}@evil.com/", f"https://skyroom.online@{RLM}evil.com/"):
            with self.subTest(ascii(link)), self.assertRaises(ValidationError):
                validate_https_url(link, "skyroom.online")

    def test_spaces_and_controls_inside_are_still_refused(self):
        for link in ("https://example.com/a\nb", "https://example.com/a b", "https://exa mple.com/"):
            with self.subTest(ascii(link)), self.assertRaises(ValidationError):
                validate_https_url(link)

    def test_the_domain_error_lists_the_host_and_the_allowed_domains(self):
        with self.assertRaises(ValidationError) as caught:
            validate_https_url("https://example.com/x", "skyroom.online\nwww.monta.ir")
        message = caught.exception.messages[0]
        self.assertIn("(example.com)", message)
        self.assertIn("دامنه‌های مجاز: skyroom.online، monta.ir (و زیردامنه‌هایشان)", message)

    def test_lookalikes_stay_refused(self):
        for link in ("https://evilskyroom.online/", "https://skyroom.online.evil.com/", "https://example.com/?u=skyroom.online"):
            with self.subTest(link):
                self.assertRefused(link, NOT_ALLOWED, "skyroom.online")

    def test_button_links(self):
        validate_button_url(f"{RLM}/student/online/")
        validate_button_url(PASTED)
        self.assertEqual(safe_button_url(PASTED), REPORTED)
        self.assertEqual(safe_button_url(f"{RLM}/student/online/"), "/student/online/")
        for value in (f"{RLM}//evil.com", "https://اسکای.ir/x"):
            with self.subTest(ascii(value)), self.assertRaises(ValidationError):
                validate_button_url(value)


class DomainNormalisationTests(SimpleTestCase):
    def assertNormalised(self, text, expected):
        domains, errors = normalise_domains(text)
        self.assertEqual(errors, [], ascii(text))
        self.assertEqual(domains, expected, ascii(text))

    def test_each_case(self):
        cases = {
            "skyroom.online": "skyroom.online",
            "  skyroom.online  ": "skyroom.online",
            "https://skyroom.online": "skyroom.online",
            "HTTPS://SkyRoom.Online/": "skyroom.online",
            "http://skyroom.online/ch/x?y=1#z": "skyroom.online",
            "//skyroom.online/x": "skyroom.online",
            "skyroom.online/": "skyroom.online",
            "skyroom.online.": "skyroom.online",
            "skyroom.online:443": "skyroom.online",
            "https://user@skyroom.online:8443/x": "skyroom.online",
            "*.skyroom.online": "skyroom.online",
            "www.skyroom.online": "skyroom.online",
            "https://www.skyroom.online/": "skyroom.online",
            "class.skyroom.online": "class.skyroom.online",
            f"{RLM}skyroom.online{LRM}": "skyroom.online",
            f"{BOM}skyroom{ZWNJ}.online{ZWSP}": "skyroom.online",
            "skyroom۔online": "skyroom.online",
            "skyroom٫online": "skyroom.online",
            "monta۱۲.ir": "monta12.ir",
            "monta٣.ir": "monta3.ir",
            "www.com": "www.com",
        }
        for text, expected in cases.items():
            with self.subTest(ascii(text)):
                self.assertNormalised(text, [expected])

    def test_separators_duplicates_and_empty_lines(self):
        text = f"skyroom.online\n\nmonta.ir, www.skyroom.online; a-b.co ، x.ir؛ y.ir\r\n{RLM}\n"
        self.assertNormalised(text, ["skyroom.online", "monta.ir", "a-b.co", "x.ir", "y.ir"])
        self.assertEqual(tidy_domains(text), "skyroom.online\nmonta.ir\na-b.co\nx.ir\ny.ir")
        self.assertEqual(tidy_domains(""), "")

    def test_refusals_name_each_bad_line(self):
        domains, errors = normalise_domains(f"skyroom.online\nاسکای{ZWNJ}روم\nskyroom\n1.2.3.4\nhttps://\nexample.com/a b")
        self.assertEqual(domains, ["skyroom.online", "example.com"])
        self.assertEqual(errors, [
            f"«اسکای{ZWNJ}روم»: نام دامنه باید با حروف انگلیسی باشد، مثل skyroom.online",
            "«skyroom» دامنه‌ی معتبری نیست؛ فقط نام دامنه را بنویسید، مثل skyroom.online",
            "«1.2.3.4» دامنه‌ی معتبری نیست؛ فقط نام دامنه را بنویسید، مثل skyroom.online",
            "«https://» دامنه‌ی معتبری نیست؛ فقط نام دامنه را بنویسید، مثل skyroom.online",
            "«b» دامنه‌ی معتبری نیست؛ فقط نام دامنه را بنویسید، مثل skyroom.online",
        ])
        with self.assertRaises(ValidationError) as caught:
            validate_domains("skyroom\nاسکای.ir")
        self.assertEqual(len(caught.exception.messages), 2)

    def test_an_unusable_text_is_kept_as_typed(self):
        self.assertEqual(tidy_domains("skyroom\nmonta.ir"), "skyroom\nmonta.ir")

    def test_www_either_way_accepts_both(self):
        for stored in ("www.example.com", "example.com"):
            for link in ("https://example.com/x", "https://www.example.com/x", "https://class.example.com/x"):
                with self.subTest(stored=stored, link=link):
                    validate_https_url(link, stored)

    def test_reading_old_text_normalises_without_a_save(self):
        """A row stored before the fix (``www.``, a bad line) still matches its usable domains."""
        self.assertEqual(split_domains("www.skyroom.online\nskyroom"), ["skyroom.online"])
        validate_https_url(REPORTED, "www.skyroom.online")


class PlatformTests(TestCase):
    def setUp(self):
        self.client.force_login(make_superuser())

    def post(self, **fields):
        return self.client.post(reverse("admin:online_classes_onlineplatform_add"), {"name": "اسکای‌روم", "is_active": "on", **fields})

    def test_admin_stores_the_normalised_domains(self):
        response = self.post(allowed_domains=f"https://www.SkyRoom.online/ch/{RLM}\n{RLM}monta.ir:443\nskyroom.online")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OnlinePlatform.objects.get().allowed_domains, "skyroom.online\nmonta.ir")

    def test_admin_refuses_a_bad_line_with_its_name(self):
        response = self.post(allowed_domains="skyroom.online\nاسکای‌روم")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "«اسکای‌روم»: نام دامنه باید با حروف انگلیسی باشد")
        self.assertFalse(OnlinePlatform.objects.exists())

    def test_admin_stores_the_cleaned_support_url(self):
        response = self.post(support_url=f"{RLM}https://skyroom.online{RLM}/help")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OnlinePlatform.objects.get().support_url, "https://skyroom.online/help")

    def test_full_clean_normalises_too(self):
        platform = OnlinePlatform(name="x", allowed_domains="https://www.skyroom.online/", support_url=PASTED)
        platform.full_clean()
        self.assertEqual((platform.allowed_domains, platform.support_url), ("skyroom.online", REPORTED))

    def test_old_support_url_renders_cleaned(self):
        platform = make_platform()
        OnlinePlatform.objects.filter(pk=platform.pk).update(support_url=PASTED)
        platform.refresh_from_db()
        self.assertEqual(platform.safe_support_url, REPORTED)
        OnlinePlatform.objects.filter(pk=platform.pk).update(support_url="javascript:alert(1)")
        platform.refresh_from_db()
        self.assertEqual(platform.safe_support_url, "")


class AdminLinkPathsTests(SchoolMixin, TestCase):
    """The event admin, the access rows and announcements store the cleaned link."""

    def setUp(self):
        self.make_school()
        self.client.force_login(make_superuser())
        self.platform = make_platform(allowed_domains="skyroom.online")
        clock = patch("django.utils.timezone.now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def event_data(self, **overrides):
        start = NOW + timedelta(hours=1)
        return {
            "title": "کلاس",
            "event_type": "class",
            "platform": self.platform.pk,
            "start_at": format_jalali_datetime(start),
            "end_at": format_jalali_datetime(start + timedelta(hours=1)),
            "status": "scheduled",
            "access_mode": "shared",
            "join_url": PASTED,
            "credentials_lead_hours": 0,
            "is_active": "on",
            "is_whole_school": "on",
            "access_rows-TOTAL_FORMS": 0,
            "access_rows-INITIAL_FORMS": 0,
            **overrides,
        }

    def test_event_stores_the_cleaned_link(self):
        response = self.client.post(reverse("admin:online_classes_onlineevent_add"), self.event_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OnlineEvent.objects.get().join_url, REPORTED)

    def test_event_error_lists_the_allowed_domains(self):
        response = self.client.post(reverse("admin:online_classes_onlineevent_add"), self.event_data(join_url="https://example.com/x"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دامنه‌ی این لینک (example.com) جزو دامنه‌های مجاز این پلتفرم نیست")
        self.assertContains(response, "دامنه‌های مجاز: skyroom.online (و زیردامنه‌هایشان)")

    def test_event_with_a_www_platform_accepts_the_bare_link(self):
        OnlinePlatform.objects.filter(pk=self.platform.pk).update(allowed_domains="www.skyroom.online")
        response = self.client.post(reverse("admin:online_classes_onlineevent_add"), self.event_data(join_url=REPORTED))
        self.assertEqual(response.status_code, 302)

    def test_access_row_stores_the_cleaned_link(self):
        event = make_event(access_mode=PERSONAL, platform=self.platform)
        data = self.event_data(access_mode="personal", join_url="", **{
            "access_rows-TOTAL_FORMS": 1,
            "access_rows-0-student": self.student_a1.pk,
            "access_rows-0-event": event.pk,
            "access_rows-0-url": PASTED,
        })
        response = self.client.post(reverse("admin:online_classes_onlineevent_change", args=[event.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OnlineEventAccess.objects.get().read_secrets()["url"], REPORTED)

    def test_access_row_error_lists_the_allowed_domains(self):
        event = make_event(access_mode=PERSONAL, platform=self.platform)
        data = self.event_data(access_mode="personal", join_url="", **{
            "access_rows-TOTAL_FORMS": 1,
            "access_rows-0-student": self.student_a1.pk,
            "access_rows-0-event": event.pk,
            "access_rows-0-url": "https://example.com/x",
        })
        response = self.client.post(reverse("admin:online_classes_onlineevent_change", args=[event.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "دامنه‌های مجاز: skyroom.online")
        self.assertFalse(OnlineEventAccess.objects.exists())

    def test_announcement_button_stores_the_cleaned_link(self):
        data = {
            "title": "الف",
            "level": "info",
            "visible_from": format_jalali_datetime(NOW),
            "visible_until": format_jalali_datetime(NOW + timedelta(days=1)),
            "priority": 0,
            "is_active": "on",
            "is_whole_school": "on",
            "button_label": "ورود",
            "button_url": PASTED,
        }
        response = self.client.post(reverse("admin:online_classes_announcement_add"), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Announcement.objects.get().button_url, REPORTED)

    def test_old_announcement_button_renders_cleaned_and_external(self):
        item = make_announcement(button_label="برو", button_url="/x/")
        Announcement.objects.filter(pk=item.pk).update(button_url=PASTED)
        item.refresh_from_db()
        self.assertEqual(item.safe_button_url, REPORTED)
        self.assertTrue(item.button_is_external)


class ImportLinkTests(SchoolMixin, TestCase):
    def setUp(self):
        self.make_school()
        self.admin = make_superuser()
        platform = make_platform(allowed_domains="skyroom.online")
        self.event = make_event({"classes": [self.class_a1]}, access_mode=PERSONAL, platform=platform)

    def test_cleaned_on_validate_and_save(self):
        plan = importer.validate([cells(self.student_a1, url=PASTED)], self.event, self.admin)
        self.assertTrue(plan.is_valid, plan.rows[0].errors)
        self.assertEqual(plan.rows[0].url, REPORTED)
        services.save_access_import(plan, user=self.admin)
        self.assertEqual(OnlineEventAccess.objects.get().read_secrets()["url"], REPORTED)

    def test_a_cell_of_only_marks_is_empty(self):
        plan = importer.validate([cells(self.student_a1, url=RLM + LRM, password="pw")], self.event, self.admin)
        self.assertTrue(plan.is_valid, plan.rows[0].errors)
        self.assertEqual(plan.rows[0].url, "")
        with self.assertRaises(FileRejected):  # nothing but marks: the row has no way in
            importer.validate([cells(self.student_a1, url=RLM + LRM)], self.event, self.admin)

    def test_row_error_lists_the_allowed_domains(self):
        plan = importer.validate([cells(self.student_a1, url="https://example.com/x")], self.event, self.admin)
        self.assertFalse(plan.is_valid)
        self.assertIn("دامنه‌های مجاز: skyroom.online", plan.rows[0].errors[0])

    def test_import_page_end_to_end(self):
        self.client.force_login(self.admin)
        url = reverse("admin:online_classes_onlineevent_access_import", args=[self.event.pk])
        response = self.client.post(url, {"file": xlsx([cells(self.student_a1, url=PASTED, password="pw")])})
        self.assertEqual(response.status_code, 200)
        self.client.post(url, {"confirm": "1"})
        self.assertEqual(OnlineEventAccess.objects.get().read_secrets()["url"], REPORTED)


class StudentPageTests(SchoolMixin, TestCase):
    """Rows written before the fix (or another way) render the cleaned link."""

    def setUp(self):
        self.make_school()
        self.client.force_login(self.student_a1.user)
        clock = patch("django.utils.timezone.now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def test_shared_link_and_support_link(self):
        platform = make_platform(support_url="https://example.com/help")
        event = make_event(platform=platform, start_at=NOW - timedelta(minutes=5))
        OnlineEvent.objects.filter(pk=event.pk).update(join_url=PASTED)
        OnlinePlatform.objects.filter(pk=platform.pk).update(support_url=RLM + "https://example.com/help" + LRM)
        response = self.client.get(reverse("online_classes:online"), {"tab": "today"})
        self.assertContains(response, f'href="{REPORTED}"')
        self.assertContains(response, 'href="https://example.com/help"')
        self.assertNotContains(response, RLM)

    def test_personal_link(self):
        event = make_event(access_mode=PERSONAL, start_at=NOW - timedelta(minutes=5))
        make_access(event, self.student_a1, url=PASTED)
        response = self.client.get(reverse("online_classes:online"), {"tab": "today"})
        self.assertContains(response, f'href="{REPORTED}"')
