import tempfile
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from cryptography.fernet import Fernet
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from core.testing import make_user
from online_classes import selectors
from online_classes.models import Announcement, AnnouncementDismissal, OnlineEvent
from online_classes.models.event import Tab
from online_classes.testing import NOW, SchoolMixin, make_access, make_announcement, make_event, make_platform
from student.models.student_enrollment import StudentEnrollment
from student.selectors import current_enrollment

PERSONAL = OnlineEvent.AccessMode.PERSONAL
INFO = OnlineEvent.AccessMode.INFO
MISSING = "لینک شما هنوز ثبت نشده؛ با مدرسه تماس بگیرید"
ONLINE = reverse("online_classes:online")
DASHBOARD = reverse("student:dashboard")


def png(name):
    buffer = BytesIO()
    Image.new("RGB", (40, 40), (200, 100, 50)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class ClockMixin(SchoolMixin):
    def setUp(self):
        self.make_school()
        self.student = self.student_a1
        self.enrollment = current_enrollment(self.student)
        self.client.force_login(self.student.user)
        self.at(NOW)
        self.addCleanup(patch.stopall)

    def at(self, moment):
        if getattr(self, "_clock", None):
            self._clock.stop()
        self._clock = patch("django.utils.timezone.now", return_value=moment)
        self._clock.start()

    def card(self, event, tab=Tab.TODAY):
        cards = {c.event.pk: c for c in selectors.event_cards(self.enrollment, tab)}
        return cards.get(event.pk)

    def page(self, tab="today"):
        return self.client.get(ONLINE, {"tab": tab})


class TabTests(ClockMixin, TestCase):
    def tabs_of(self, event):
        return [tab for tab in Tab.values if self.card(event, tab)]

    def test_today_upcoming_and_past_by_the_clock(self):
        event = make_event(start_at=NOW + timedelta(hours=1))
        self.assertEqual(self.tabs_of(event), ["today"])
        self.at(NOW + timedelta(hours=1, minutes=30))
        self.assertEqual(self.tabs_of(event), ["today"])
        self.at(NOW + timedelta(hours=2))
        self.assertEqual(self.tabs_of(event), ["past"], "exactly at the end it has ended")

    def test_tehran_midnight_splits_today_from_upcoming(self):
        last_of_today = timezone.make_aware(timezone.datetime(2026, 11, 3, 23, 59))
        first_of_tomorrow = timezone.make_aware(timezone.datetime(2026, 11, 4, 0, 0))
        self.assertEqual(self.tabs_of(make_event(start_at=last_of_today)), ["today"])
        self.assertEqual(self.tabs_of(make_event(start_at=first_of_tomorrow)), ["upcoming"])

    def test_a_long_event_from_yesterday_is_still_today(self):
        event = make_event(start_at=NOW - timedelta(days=1), end_at=NOW + timedelta(minutes=5))
        self.assertEqual(self.tabs_of(event), ["today"])

    def test_past_keeps_the_last_n_days(self):
        with override_settings(ONLINE_PAST_DAYS=14):
            recent = make_event(start_at=NOW - timedelta(days=14), end_at=NOW - timedelta(days=13, hours=23))
            old = make_event(start_at=NOW - timedelta(days=15), end_at=NOW - timedelta(days=14))
            self.assertEqual(self.tabs_of(recent), ["past"])
            self.assertEqual(self.tabs_of(old), [], "the boundary itself has gone")

    def test_a_cancelled_event_follows_the_clock(self):
        event = make_event(status=OnlineEvent.Status.CANCELLED, status_note="معلم بیمار است")
        self.assertEqual(self.tabs_of(event), ["today"])
        self.at(NOW + timedelta(days=1))
        self.assertEqual(self.tabs_of(event), ["past"])

    def test_inactive_is_hidden_everywhere(self):
        self.assertEqual(self.tabs_of(make_event(is_active=False)), [])

    def test_today_lists_live_first(self):
        later = make_event(title="بعدی", start_at=NOW + timedelta(hours=2))
        live = make_event(title="زنده", start_at=NOW + timedelta(hours=1))
        cancelled = make_event(
            title="لغو", start_at=NOW - timedelta(minutes=5), end_at=NOW + timedelta(hours=5),
            status=OnlineEvent.Status.CANCELLED, status_note="x",
        )
        self.at(NOW + timedelta(hours=1, minutes=1))
        order = [c.event.pk for c in selectors.event_cards(self.enrollment, Tab.TODAY)]
        self.assertEqual(order, [live.pk, cancelled.pk, later.pk])

    def test_past_lists_newest_first(self):
        older = make_event(start_at=NOW - timedelta(days=2), end_at=NOW - timedelta(days=2) + timedelta(hours=1))
        newer = make_event(start_at=NOW - timedelta(days=1), end_at=NOW - timedelta(days=1) + timedelta(hours=1))
        order = [c.event.pk for c in selectors.event_cards(self.enrollment, Tab.PAST)]
        self.assertEqual(order, [newer.pk, older.pk])

    def test_unknown_tab_is_a_404(self):
        self.assertEqual(self.page("nope").status_code, 404)

    def test_empty_states_are_plain(self):
        self.assertContains(self.page("today"), "امروز کلاس یا آزمون آنلاینی ندارید")
        self.assertContains(self.page("upcoming"), "فعلاً برنامه‌ی دیگری ثبت نشده است")
        self.assertContains(self.page("past"), "در این چند روز برنامه‌ی آنلاینی نبوده است")

    def test_no_current_enrolment_says_what_to_do(self):
        StudentEnrollment.objects.filter(student=self.student).update(status="withdrawn")
        make_event()
        response = self.page()
        self.assertContains(response, "با مدرسه تماس بگیرید")
        self.assertEqual(response.context["cards"], [])


class PostponedTests(ClockMixin, TestCase):
    def make(self, **fields):
        return make_event(status=OnlineEvent.Status.POSTPONED, status_note="تا هفته‌ی بعد", **fields)

    def test_stays_upcoming_long_after_its_old_end(self):
        event = self.make(start_at=NOW + timedelta(minutes=5))
        for later in (NOW, NOW + timedelta(hours=3), NOW + timedelta(days=60)):
            with self.subTest(later=later):
                self.at(later)
                self.assertIsNotNone(self.card(event, Tab.UPCOMING))
                self.assertIsNone(self.card(event, Tab.TODAY))
                self.assertIsNone(self.card(event, Tab.PAST))

    def test_says_a_new_time_is_coming_and_keeps_no_way_in(self):
        event = self.make()
        make_event(title="x")
        response = self.page("upcoming")
        self.assertContains(response, "زمان جدید اعلام می‌شود")
        self.assertContains(response, "تا هفته‌ی بعد")
        self.assertContains(response, "به تعویق افتاد")
        self.assertNotContains(response, event.join_url)
        self.assertNotContains(response, "data-countdown")

    def test_comes_after_dated_items(self):
        postponed = self.make(start_at=NOW - timedelta(days=30), end_at=NOW - timedelta(days=29))
        dated = make_event(start_at=NOW + timedelta(days=3))
        order = [c.event.pk for c in selectors.event_cards(self.enrollment, Tab.UPCOMING)]
        self.assertEqual(order, [dated.pk, postponed.pk])

    def test_on_the_dashboard_it_comes_last(self):
        postponed = self.make(start_at=NOW - timedelta(days=30), end_at=NOW - timedelta(days=29))
        dated = make_event(start_at=NOW + timedelta(days=3))
        order = [c.event.pk for c in selectors.dashboard_cards(self.enrollment)]
        self.assertEqual(order, [dated.pk, postponed.pk])

    def test_an_admin_edit_brings_it_back(self):
        event = self.make(start_at=NOW - timedelta(days=30), end_at=NOW - timedelta(days=29))
        event.status = OnlineEvent.Status.SCHEDULED
        event.status_note = ""
        event.start_at = NOW + timedelta(hours=1)
        event.end_at = NOW + timedelta(hours=2)
        event.save()
        self.assertIsNotNone(self.card(event, Tab.TODAY))
        self.assertIsNone(self.card(event, Tab.UPCOMING))


class JoinWindowTests(ClockMixin, TestCase):
    """Shared link. Default lead: 15 minutes (``ONLINE_JOIN_LEAD_MINUTES``)."""

    def test_the_link_appears_exactly_in_the_window(self):
        event = make_event(join_url="https://example.com/room-xyz")
        start, end = event.start, event.end

        self.at(start - timedelta(minutes=15, seconds=1))
        response = self.page()
        self.assertNotContains(response, "room-xyz")
        self.assertContains(response, "دکمه‌ی ورود از")
        self.assertContains(response, "data-countdown")

        self.at(start - timedelta(minutes=15))
        self.assertContains(self.page(), "room-xyz")

        self.at(end - timedelta(seconds=1))
        self.assertContains(self.page(), "room-xyz")

        self.at(end)
        self.assertNotContains(self.page("past"), "room-xyz")

    def test_links_open_in_a_new_tab_safely(self):
        make_event(start_at=NOW - timedelta(minutes=1), join_url="https://example.com/room-xyz")
        self.assertContains(
            self.page(),
            'href="https://example.com/room-xyz" target="_blank" rel="noopener noreferrer"',
        )

    def test_per_event_override(self):
        event = make_event(join_lead_minutes=60, join_url="https://example.com/room-xyz")
        self.at(event.start - timedelta(minutes=61))
        self.assertNotContains(self.page(), "room-xyz")
        self.at(event.start - timedelta(minutes=60))
        self.assertContains(self.page(), "room-xyz")

    def test_setting_moves_the_default(self):
        event = make_event(join_url="https://example.com/room-xyz")
        self.at(event.start - timedelta(minutes=20))
        with override_settings(ONLINE_JOIN_LEAD_MINUTES=30):
            self.assertContains(self.page(), "room-xyz")

    def test_cancelled_has_no_link_and_shows_why(self):
        make_event(
            start_at=NOW - timedelta(minutes=1), join_url="https://example.com/room-xyz",
            status=OnlineEvent.Status.CANCELLED, status_note="معلم بیمار است",
        )
        response = self.page()
        self.assertNotContains(response, "room-xyz")
        self.assertContains(response, "لغو شد")
        self.assertContains(response, "معلم بیمار است")

    def test_info_only_has_no_button(self):
        make_event(access_mode=INFO, title="آزمون حضوری", start_at=NOW + timedelta(minutes=1))
        response = self.page()
        self.assertContains(response, "آزمون حضوری")
        self.assertNotContains(response, "online-join")
        self.assertNotContains(response, MISSING)

    def test_a_bad_link_written_directly_is_not_rendered(self):
        OnlineEvent.objects.filter(pk=make_event(start_at=NOW - timedelta(minutes=1)).pk).update(
            join_url="javascript:alert(1)"
        )
        response = self.page()
        self.assertNotContains(response, "javascript:")
        self.assertNotContains(response, 'class="online-join"')

    def test_outside_the_audience_is_invisible(self):
        make_event({"classes": [self.class_b1]}, title="کلاس شعبه دیگر")
        self.assertNotContains(self.page(), "کلاس شعبه دیگر")

    def test_title_and_description_are_escaped(self):
        make_event(title="<script>alert(1)</script>", description="<b>x</b>")
        response = self.page()
        self.assertNotContains(response, "<script>alert(1)")
        self.assertNotContains(response, "<b>x</b>")

    def test_help_and_support_are_shown_on_the_page(self):
        platform = make_platform(join_help="روی لینک بزنید.", support_contact="021-1234", support_url="https://example.com/help")
        make_event(platform=platform)
        response = self.page()
        self.assertContains(response, "روی لینک بزنید.")
        self.assertContains(response, "021-1234")
        self.assertContains(response, 'href="https://example.com/help"')

    def test_personal_pages_are_never_cached(self):
        for url in (ONLINE, DASHBOARD):
            self.assertIn("no-store", self.client.get(url)["Cache-Control"])


class CredentialsTests(ClockMixin, TestCase):
    """Personal mode (D8, D11)."""

    def make(self, lead_hours=0, join_url="", **access):
        event = make_event(access_mode=PERSONAL, credentials_lead_hours=lead_hours, join_url=join_url)
        access = access or {"url": "https://example.com/personal-link", "username": "user-1", "password": "pw-secret"}
        make_access(event, self.student, **access)
        return event

    def assertHidden(self, response):
        for value in ("personal-link", "user-1", "pw-secret"):
            self.assertNotContains(response, value)

    def test_default_opens_with_the_join_window(self):
        event = self.make()
        self.at(event.start - timedelta(minutes=15, seconds=1))
        response = self.page()
        self.assertHidden(response)
        self.assertContains(response, "اطلاعات ورود شما ثبت شده است")

        self.at(event.start - timedelta(minutes=15))
        response = self.page()
        self.assertContains(response, "pw-secret")
        self.assertContains(response, 'class="online-join" href="https://example.com/personal-link"')

    def test_closed_after_the_end(self):
        event = self.make()
        self.at(event.end)
        self.assertHidden(self.page("past"))

    def test_closed_when_cancelled_or_postponed(self):
        event = self.make()
        self.at(event.start)
        for status, tab in ((OnlineEvent.Status.CANCELLED, "today"), (OnlineEvent.Status.POSTPONED, "upcoming")):
            with self.subTest(status):
                OnlineEvent.objects.filter(pk=event.pk).update(status=status, status_note="x")
                response = self.page(tab)
                self.assertContains(response, event.title)
                self.assertHidden(response)
                self.assertNotContains(response, MISSING)

    def test_early_credentials_open_hours_before_but_not_the_button(self):
        event = self.make(lead_hours=24)
        event_start = event.start

        self.at(event_start - timedelta(hours=24, seconds=1))
        self.assertHidden(self.page())

        self.at(event_start - timedelta(hours=24))
        card = self.card(event, Tab.TODAY) or self.card(event, Tab.UPCOMING)
        self.assertEqual(card.password, "pw-secret")
        self.assertEqual(card.test_url, "https://example.com/personal-link")
        self.assertEqual(card.join_url, "")
        self.assertFalse(card.can_join)

        response = self.page("upcoming")
        self.assertContains(response, "pw-secret")
        self.assertContains(response, "آزمایش ورود")
        self.assertContains(response, 'href="https://example.com/personal-link" target="_blank" rel="noopener noreferrer"')
        self.assertNotContains(response, 'class="online-join" href')
        self.assertContains(response, "دکمه‌ی ورود از")

        self.at(event_start - timedelta(minutes=15))
        response = self.page()
        self.assertContains(response, 'class="online-join" href="https://example.com/personal-link"')
        self.assertNotContains(response, "آزمایش ورود")

    def test_a_lead_shorter_than_the_join_lead_never_delays_them(self):
        event = make_event(access_mode=PERSONAL, credentials_lead_hours=1, join_lead_minutes=120)
        make_access(event, self.student, password="pw-secret", url="https://example.com/personal-link")
        self.assertEqual(event.credentials_open_at, event.join_opens_at)
        self.at(event.start - timedelta(minutes=120))
        self.assertEqual(self.card(event).join_url, "https://example.com/personal-link")

    def test_a_shared_link_ignores_the_credentials_rule(self):
        # The form refuses this; written directly, the shared link still waits for the join window.
        event = make_event(credentials_lead_hours=24, join_url="https://example.com/room-xyz")
        self.at(event.start - timedelta(hours=2))
        self.assertNotContains(self.page(), "room-xyz")

    def test_a_row_without_a_link_uses_the_event_link(self):
        event = self.make(lead_hours=24, join_url="https://example.com/event-link", username="user-1", password="pw-secret")
        self.at(event.start - timedelta(hours=2))
        self.assertEqual(self.card(event).test_url, "https://example.com/event-link")
        self.at(event.start - timedelta(minutes=1))
        self.assertEqual(self.card(event).join_url, "https://example.com/event-link")

    def test_credentials_with_no_link_anywhere_show_no_button(self):
        event = self.make(username="user-1", password="pw-secret")
        self.at(event.start - timedelta(hours=2))
        self.assertNotContains(self.page(), "online-join")
        self.at(event.start)
        response = self.page()
        self.assertContains(response, "pw-secret")
        self.assertNotContains(response, 'class="online-join"')

    def test_missing_row_is_told_at_all_times(self):
        event = make_event(access_mode=PERSONAL, join_url="https://example.com/event-link", start_at=NOW + timedelta(days=5))
        self.assertContains(self.page("upcoming"), MISSING)
        self.at(event.start)
        response = self.page()
        self.assertContains(response, MISSING)
        self.assertNotContains(response, "event-link", msg_prefix="no row: the event's link isn't handed out")
        self.at(event.end)
        self.assertNotContains(self.page("past"), MISSING)

    def test_other_students_row_is_never_used(self):
        event = make_event(access_mode=PERSONAL)
        make_access(event, self.student_a2, password="their-password", username="their-user")
        self.at(event.start)
        response = self.page()
        self.assertNotContains(response, "their-password")
        self.assertNotContains(response, "their-user")
        self.assertContains(response, MISSING)

    def test_masked_by_default_with_reveal_and_copy(self):
        event = self.make()
        self.at(event.start)
        response = self.page()
        self.assertContains(response, "<details")
        self.assertContains(response, "••••••")
        self.assertContains(response, 'data-copy="pw-secret"')

    def test_dashboard_shows_the_button_but_not_the_password(self):
        event = self.make()
        self.at(event.start)
        response = self.client.get(DASHBOARD)
        self.assertContains(response, 'class="online-join" href="https://example.com/personal-link"')
        self.assertNotContains(response, "pw-secret")
        self.assertContains(response, "دیدن نام کاربری و رمز")

    def test_a_row_no_key_opens_tells_the_family_and_never_fails(self):
        event = make_event(access_mode=PERSONAL, join_url="https://example.com/event-link")
        with override_settings(ONLINE_ACCESS_KEYS=[Fernet.generate_key().decode()]):
            make_access(event, self.student, password="lost")
        self.at(event.start)
        with self.assertLogs("online_classes.selectors", level="ERROR") as logs:
            response = self.page()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "اطلاعات ورود شما باز نشد؛ با مدرسه تماس بگیرید")
        self.assertNotContains(response, 'class="online-join"')
        self.assertNotIn("lost", " ".join(logs.output))

    def test_a_refresh_is_scheduled_for_the_next_change(self):
        event = self.make(lead_hours=2)
        self.at(event.start - timedelta(hours=3))
        self.assertEqual(self.page().context["refresh_seconds"], 3601)
        self.at(event.start - timedelta(minutes=30))
        self.assertEqual(self.page().context["refresh_seconds"], 901)

    def test_partial_returns_only_the_list(self):
        self.make()
        response = self.client.get(ONLINE, {"tab": "today", "partial": "1"})
        self.assertNotContains(response, "<html")
        self.assertContains(response, "online-list")
        response = self.client.get(DASHBOARD, {"partial": "1"})
        self.assertNotContains(response, "<html")
        self.assertContains(response, "online-block")


class AccessToPagesTests(ClockMixin, TestCase):
    def test_logged_out_goes_to_login(self):
        self.client.logout()
        response = self.client.get(ONLINE)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_other_roles_go_to_their_own_dashboard(self):
        for role in ("teacher", "supervisor", "director"):
            with self.subTest(role):
                self.client.force_login(make_user(role))
                self.assertEqual(self.client.get(ONLINE).status_code, 302)

    def test_student_without_profile_is_refused(self):
        self.client.force_login(make_user("student"))
        self.assertEqual(self.client.get(ONLINE).status_code, 403)

    def test_sidebar_links_to_the_page(self):
        self.assertContains(self.client.get(DASHBOARD), f'href="{ONLINE}"')


class AnnouncementTests(ClockMixin, TestCase):
    def shown(self):
        return [banner.announcement.pk for banner in selectors.banners(self.enrollment)]

    def dismiss(self, announcement, **extra):
        return self.client.post(reverse("online_classes:dismiss_announcement", args=[announcement.pk]), **extra)

    def test_display_window(self):
        item = make_announcement(visible_from=NOW, visible_until=NOW + timedelta(hours=1))
        self.at(NOW - timedelta(seconds=1))
        self.assertEqual(self.shown(), [])
        self.at(NOW)
        self.assertEqual(self.shown(), [item.pk])
        self.at(NOW + timedelta(hours=1))
        self.assertEqual(self.shown(), [])

    def test_audience_and_inactive(self):
        mine = make_announcement({"classes": [self.class_a1]})
        make_announcement({"classes": [self.class_b1]})
        make_announcement(is_active=False)
        self.assertEqual(self.shown(), [mine.pk])

    def test_order_urgent_then_pinned_then_priority_then_newest(self):
        newest = make_announcement(title="c", visible_from=NOW - timedelta(hours=1))
        older = make_announcement(title="d", visible_from=NOW - timedelta(hours=2))
        high = make_announcement(title="b", priority=5)
        pinned = make_announcement(title="p", is_pinned=True)
        urgent = make_announcement(title="u", level="urgent", priority=0)
        with override_settings(ANNOUNCEMENT_MAX_VISIBLE=10):
            self.assertEqual(self.shown(), [urgent.pk, pinned.pk, high.pk, newest.pk, older.pk])

    def test_cap(self):
        for index in range(5):
            make_announcement(title=str(index), priority=index)
        with override_settings(ANNOUNCEMENT_MAX_VISIBLE=3):
            self.assertEqual(len(self.shown()), 3)

    def test_three_pinned_can_not_hide_an_urgent_one(self):
        for index in range(3):
            make_announcement(title=str(index), is_pinned=True, priority=9)
        urgent = make_announcement(title="u", level="urgent")
        with override_settings(ANNOUNCEMENT_MAX_VISIBLE=3):
            self.assertEqual(self.shown()[0], urgent.pk)

    def test_each_level_says_its_level_in_words_and_looks_different(self):
        make_announcement(level="info")
        make_announcement(level="important")
        make_announcement(level="urgent")
        response = self.client.get(DASHBOARD)
        for css, word in (("info", "اطلاع‌رسانی"), ("important", "مهم"), ("urgent", "فوری")):
            self.assertContains(response, f"online-banner--{css}")
            self.assertContains(response, word)

    def test_body_is_plain_text_with_line_breaks(self):
        make_announcement(body="خط اول\nخط <b>دوم</b>")
        response = self.client.get(DASHBOARD)
        self.assertContains(response, "خط اول<br>")
        self.assertNotContains(response, "<b>دوم</b>")

    def test_button_internal_and_external(self):
        make_announcement(title="a", button_label="داخلی", button_url="/student/online/")
        make_announcement(title="b", button_label="بیرونی", button_url="https://example.com/x")
        response = self.client.get(DASHBOARD)
        self.assertContains(response, 'href="/student/online/">داخلی')
        self.assertContains(response, 'href="https://example.com/x" target="_blank" rel="noopener noreferrer">بیرونی')

    def test_a_bad_button_url_written_directly_is_not_rendered(self):
        item = make_announcement(button_label="برو", button_url="/ok/")
        Announcement.objects.filter(pk=item.pk).update(button_url="javascript:alert(1)")
        response = self.client.get(DASHBOARD)
        self.assertNotContains(response, "javascript:alert")
        self.assertNotContains(response, "online-banner__button")

    def test_picture_with_mobile_source(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        with override_settings(MEDIA_ROOT=media.name):
            item = make_announcement(image=png("d.png"), image_mobile=png("m.png"))
            response = self.client.get(DASHBOARD)
        self.assertContains(response, f'srcset="{item.image_mobile.url}"')
        self.assertContains(response, f'src="{item.image.url}"')

    def test_linked_event_shows_a_countdown_but_never_its_way_in(self):
        # The event is for another class: everything about it on this page comes from the banner.
        event = make_event(
            {"classes": [self.class_b1]}, start_at=NOW + timedelta(days=2), join_url="https://example.com/room-xyz"
        )
        make_announcement(event=event)
        banner = selectors.banners(self.enrollment)[0]
        self.assertEqual(banner.seconds_to_event, 2 * 86400)
        response = self.client.get(DASHBOARD)
        self.assertContains(response, "۲ روز دیگر")
        self.at(event.start)
        self.assertNotContains(self.client.get(DASHBOARD), "room-xyz")

    def test_linked_event_status_is_followed(self):
        event = make_event(status=OnlineEvent.Status.POSTPONED, status_note="x")
        make_announcement(event=event)
        self.assertIn("زمان جدید اعلام می‌شود", selectors.banners(self.enrollment)[0].event_note)
        OnlineEvent.objects.filter(pk=event.pk).update(status=OnlineEvent.Status.CANCELLED)
        self.assertIn("لغو شده", selectors.banners(self.enrollment)[0].event_note)
        OnlineEvent.objects.filter(pk=event.pk).update(is_active=False)
        self.assertEqual(selectors.banners(self.enrollment)[0].event_note, "")

    # -- dismissing

    def test_dismissal_is_remembered_per_student(self):
        item = make_announcement()
        self.assertRedirects(self.dismiss(item), DASHBOARD, fetch_redirect_response=False)
        self.assertEqual(self.shown(), [])
        other = current_enrollment(self.student_a2)
        self.assertEqual(len(selectors.banners(other)), 1)

    def test_dismissed_ones_do_not_use_up_the_cap(self):
        first = make_announcement(priority=9)
        second = make_announcement(priority=1)
        with override_settings(ANNOUNCEMENT_MAX_VISIBLE=1):
            self.assertEqual(self.shown(), [first.pk])
            self.dismiss(first)
            self.assertEqual(self.shown(), [second.pk])

    def test_a_repeat_changes_nothing(self):
        item = make_announcement()
        self.dismiss(item)
        self.dismiss(item)
        self.assertEqual(AnnouncementDismissal.objects.count(), 1)

    def test_get_is_refused(self):
        item = make_announcement()
        self.assertEqual(self.client.get(reverse("online_classes:dismiss_announcement", args=[item.pk])).status_code, 405)
        self.assertEqual(AnnouncementDismissal.objects.count(), 0)

    def test_urgent_and_non_dismissible_are_refused(self):
        for item in (make_announcement(level="urgent"), make_announcement(is_dismissible=False)):
            self.assertEqual(self.dismiss(item).status_code, 403)
        self.assertEqual(AnnouncementDismissal.objects.count(), 0)

    def test_outside_the_audience_or_window_is_a_404(self):
        for item in (
            make_announcement({"classes": [self.class_b1]}),
            make_announcement(visible_from=NOW + timedelta(hours=1), visible_until=NOW + timedelta(hours=2)),
            make_announcement(is_active=False),
        ):
            self.assertEqual(self.dismiss(item).status_code, 404)
        self.assertEqual(AnnouncementDismissal.objects.count(), 0)

    def test_someone_else_can_not_dismiss(self):
        item = make_announcement()
        self.client.force_login(make_user("teacher"))
        self.assertEqual(self.dismiss(item).status_code, 302)
        self.assertEqual(AnnouncementDismissal.objects.count(), 0)

    def test_raised_to_urgent_or_made_undismissible_shows_again(self):
        item = make_announcement()
        self.dismiss(item)
        self.assertEqual(self.shown(), [])
        Announcement.objects.filter(pk=item.pk).update(level="urgent")
        self.assertEqual(self.shown(), [item.pk])
        Announcement.objects.filter(pk=item.pk).update(level="info", is_dismissible=False)
        self.assertEqual(self.shown(), [item.pk])

    def test_close_button_only_when_it_may_be_closed(self):
        make_announcement(level="urgent")
        self.assertNotContains(self.client.get(DASHBOARD), "data-dismiss")
        make_announcement()
        self.assertContains(self.client.get(DASHBOARD), "data-dismiss")

    def test_partial_post_returns_no_content(self):
        item = make_announcement()
        url = reverse("online_classes:dismiss_announcement", args=[item.pk]) + "?partial=1"
        self.assertEqual(self.client.post(url).status_code, 204)


LOCKED_PAGE_QUERIES = 13


class QueryCountTests(ClockMixin, TestCase):
    """A fixed number of queries, whatever the number of events, audiences and access rows."""

    def _seed(self, count):
        platform = make_platform()
        for index in range(count):
            event = make_event(
                {"classes": [self.class_a1, self.class_a2], "branches": [self.branch_a], "grades": [self.grade_1]},
                is_whole_school=False,
                title=f"e{index}",
                platform=platform,
                access_mode=PERSONAL,
                start_at=NOW - timedelta(minutes=1),
            )
            make_access(event, self.student, username=f"u{index}", password="pw", url="https://example.com/p")
            make_access(event, self.student_a2, username=f"o{index}", password="pw")
            make_announcement(
                {"branches": [self.branch_a], "excluded_students": [self.student_b1]}, title=f"a{index}"
            )

    def _count(self, url, **params):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        return len(captured)

    def test_page_does_not_grow_with_the_data(self):
        self._seed(1)
        self.page()  # the first request also fills the site-wide caches
        small = self._count(ONLINE, tab="today")
        self._seed(30)
        self.assertEqual(self._count(ONLINE, tab="today"), small)

    def test_dashboard_does_not_grow_with_the_data(self):
        self._seed(1)
        self.client.get(DASHBOARD)  # the first request also fills the site-wide caches
        small = self._count(DASHBOARD)
        self._seed(30)
        self.assertEqual(self._count(DASHBOARD), small)

    def test_online_block_costs_four_queries(self):
        self._seed(10)
        # enrolment, events, the student's access rows, announcements
        with self.assertNumQueries(4):
            selectors.dashboard_block(self.student)

    def test_page_is_locked(self):
        self._seed(10)
        self.page()  # the first request also fills the site-wide caches
        with self.assertNumQueries(LOCKED_PAGE_QUERIES):
            self.page()
