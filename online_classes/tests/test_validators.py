from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from online_classes.models import Announcement, OnlineEvent, OnlinePlatform
from online_classes.testing import NOW, make_platform
from online_classes.validators import (
    safe_button_url, safe_https_url, validate_button_url, validate_domains, validate_https_url,
)


class HttpsUrlTests(SimpleTestCase):
    def test_refused(self):
        for value in (
            "http://example.com",
            "javascript:alert(1)",
            "//example.com/x",
            "/local",
            "https://",
            "https:///path",
            "https://skyroom.online@evil.com/",
            "https://user:pass@example.com/",
            "https://exa mple.com/",
            "https://example.com/a b",
            "https://example.com\\@evil.com",
            "https://example.com/\n",
            "ftp://example.com",
            "https://example.com/" + "a" * 2000,
        ):
            with self.subTest(value), self.assertRaises(ValidationError):
                validate_https_url(value)
            self.assertEqual(safe_https_url(value), "", value)

    def test_accepted(self):
        for value in ("https://example.com", "HTTPS://EXAMPLE.com/room?id=1&x=2", "https://a.b.example.com:8443/p#f"):
            with self.subTest(value):
                validate_https_url(value)
                self.assertEqual(safe_https_url(value), value)

    def test_allowed_domains(self):
        domains = "skyroom.online\nmonta.ir"
        validate_https_url("https://skyroom.online/x", domains)
        validate_https_url("https://class.skyroom.online/x", domains)
        validate_https_url("https://MONTA.ir/x", domains)
        for value in (
            "https://evilskyroom.online/",
            "https://skyroom.online.evil.com/",
            "https://example.com/?u=skyroom.online",
        ):
            with self.subTest(value), self.assertRaises(ValidationError):
                validate_https_url(value, domains)

    def test_domain_list(self):
        validate_domains("skyroom.online\nclass.monta.ir, a-b.co")
        for value in ("https://skyroom.online", "skyroom", "skyroom.online/path", "*.example.com"):
            with self.subTest(value), self.assertRaises(ValidationError):
                validate_domains(value)


class ButtonUrlTests(SimpleTestCase):
    def test_refused(self):
        for value in ("//evil.com", "/\\evil.com", "/a b", "http://x.com", "javascript:alert(1)", "student/online", "#x"):
            with self.subTest(value), self.assertRaises(ValidationError):
                validate_button_url(value)
            self.assertEqual(safe_button_url(value), "")

    def test_accepted(self):
        for value in ("/student/online/", "/", "https://example.com/x"):
            validate_button_url(value)
            self.assertEqual(safe_button_url(value), value)


class EventRulesTests(TestCase):
    def _event(self, **fields):
        base = {"title": "الف", "start_at": NOW, "end_at": NOW.replace(hour=11), "platform": make_platform()}
        return OnlineEvent(**{**base, **fields})

    def _errors(self, event):
        with self.assertRaises(ValidationError) as caught:
            event.full_clean()
        return caught.exception.message_dict

    def test_valid(self):
        self._event(join_url="https://example.com/x").full_clean()

    def test_end_must_follow_start(self):
        self.assertIn("end_at", self._errors(self._event(end_at=NOW, join_url="https://example.com")))

    def test_shared_needs_a_link(self):
        self.assertIn("join_url", self._errors(self._event()))

    def test_only_info_may_have_no_platform(self):
        self.assertIn("platform", self._errors(self._event(platform=None, join_url="https://example.com")))
        self._event(platform=None, access_mode=OnlineEvent.AccessMode.INFO).full_clean()

    def test_info_has_no_link(self):
        errors = self._errors(self._event(access_mode=OnlineEvent.AccessMode.INFO, join_url="https://example.com"))
        self.assertIn("join_url", errors)

    def test_personal_link_is_optional(self):
        self._event(access_mode=OnlineEvent.AccessMode.PERSONAL).full_clean()

    def test_platform_domains_are_enforced(self):
        platform = make_platform(allowed_domains="skyroom.online")
        self.assertIn("join_url", self._errors(self._event(platform=platform, join_url="https://example.com/x")))
        self._event(platform=platform, join_url="https://skyroom.online/x").full_clean()

    def test_cancelled_and_postponed_need_a_note(self):
        for status in (OnlineEvent.Status.CANCELLED, OnlineEvent.Status.POSTPONED):
            with self.subTest(status):
                errors = self._errors(self._event(status=status, join_url="https://example.com"))
                self.assertIn("status_note", errors)

    def test_credentials_lead_is_only_for_personal(self):
        for mode, url in ((OnlineEvent.AccessMode.SHARED, "https://example.com"), (OnlineEvent.AccessMode.INFO, "")):
            with self.subTest(mode):
                errors = self._errors(self._event(access_mode=mode, join_url=url, credentials_lead_hours=2))
                self.assertIn("credentials_lead_hours", errors)
        self._event(access_mode=OnlineEvent.AccessMode.PERSONAL, credentials_lead_hours=2).full_clean()

    def test_platform_needs_a_valid_support_url(self):
        with self.assertRaises(ValidationError):
            OnlinePlatform(name="x", support_url="http://example.com").full_clean()


class AnnouncementRulesTests(TestCase):
    def _announcement(self, **fields):
        base = {"title": "الف", "visible_from": NOW, "visible_until": NOW.replace(hour=11)}
        return Announcement(**{**base, **fields})

    def test_button_needs_both_label_and_url(self):
        with self.assertRaises(ValidationError):
            self._announcement(button_label="برو").full_clean()
        with self.assertRaises(ValidationError):
            self._announcement(button_url="/student/online/").full_clean()
        self._announcement(button_label="برو", button_url="/student/online/").full_clean()

    def test_window_must_be_forward(self):
        with self.assertRaises(ValidationError):
            self._announcement(visible_until=NOW).full_clean()

    def test_urgent_is_never_dismissible(self):
        self.assertFalse(self._announcement(level="urgent", is_dismissible=True).can_be_dismissed)
        self.assertFalse(self._announcement(level="info", is_dismissible=False).can_be_dismissed)
        self.assertTrue(self._announcement(level="important", is_dismissible=True).can_be_dismissed)
