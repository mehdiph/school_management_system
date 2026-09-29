"""
Teacher dashboard: access, today's lessons (timetable-based), the KPIs,
the "now / next" badges, and that the removed «کلاس‌های من» section
stays gone. Calendar as in scheduling/tests.py: NOW is Saturday
2026-10-03 09:10 (rotation week 2).
"""

from datetime import datetime, time
from unittest import mock

import jdatetime
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.testing import make_student, make_user
from scheduling.models.bell import Bell
from scheduling.tests import FAST_HASHER, NOW, TEHRAN, WEEK_ONE, Day, ScheduleFixtureMixin
from teaching.models import SchoolSession, SessionContent

from .selectors import build_teacher_dashboard


class DashboardDataTests(ScheduleFixtureMixin, TestCase):

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.bell_4 = Bell.objects.create(title="چهارم", order=4, start_time=time(11), end_time=time(11, 45))
        cls.bell_5 = Bell.objects.create(title="پنجم", order=5, start_time=time(12), end_time=time(12, 45))

    def build(self, now=NOW):
        return build_teacher_dashboard(self.teacher, now=now)

    def test_lessons_come_from_todays_timetable(self):
        today = self.class_subject("ریاضی")
        self.slot(today, Day.SATURDAY, self.bell_1)
        self.slot(self.class_subject("فردا"), Day.SUNDAY, self.bell_1)
        self.slot(self.class_subject("هفته دیگر"), Day.SATURDAY, self.bell_2, WEEK_ONE)

        data = self.build()

        self.assertEqual([lesson.subject for lesson in data["today_lessons"]], ["ریاضی"])
        self.assertEqual(data["today_lessons_count"], 1)

    def test_consecutive_bells_are_one_row_and_a_later_one_another(self):
        math = self.class_subject("ریاضی")
        for bell in (self.bell_1, self.bell_2, self.bell_5):
            self.slot(math, Day.SATURDAY, bell)

        rows = self.build()["today_lessons"]

        self.assertEqual([row.bell_orders for row in rows], [[1, 2], [5]])
        self.assertEqual((rows[0].start_time, rows[0].end_time), (time(8), time(9, 45)))

    def test_now_and_next_badges_and_the_single_focus_row(self):
        self.slot(self.class_subject("اول"), Day.SATURDAY, self.bell_1)
        self.slot(self.class_subject("دوم"), Day.SATURDAY, self.bell_2)
        self.slot(self.class_subject("چهارم"), Day.SATURDAY, self.bell_4)

        rows = self.build()["today_lessons"]  # 09:10: in the second bell

        self.assertEqual([row.state for row in rows], [None, "now", "next"])
        self.assertEqual([row.is_focus for row in rows], [False, True, False])

    def test_focus_moves_to_the_next_lesson_between_bells(self):
        self.slot(self.class_subject("دوم"), Day.SATURDAY, self.bell_2)
        rows = self.build(now=datetime(2026, 10, 3, 8, 50, tzinfo=TEHRAN))["today_lessons"]
        self.assertEqual([(row.state, row.is_focus) for row in rows], [("next", True)])

    def test_recorded_today_and_pending_count(self):
        recorded = self.class_subject("ثبت‌شده")
        self.slot(recorded, Day.SATURDAY, self.bell_1)
        self.slot(self.class_subject("مانده"), Day.SATURDAY, self.bell_2)
        session = SchoolSession.objects.create(
            class_subject=recorded, date=jdatetime.date.fromgregorian(date=NOW.date())
        )

        data = self.build()

        self.assertEqual(data["today_lessons"][0].recorded_session_id, session.pk)
        self.assertEqual(data["pending_today_count"], 1)

    def test_last_session_number_and_summary(self):
        math = self.class_subject("ریاضی")
        self.slot(math, Day.SATURDAY, self.bell_1)
        for day, text in ((1, "اول"), (5, "دوم")):
            session = SchoolSession.objects.create(class_subject=math, date=jdatetime.date(1405, 7, day))
            SessionContent.objects.create(session=session, title=text, content=f"محتوای {text}", homework="-")

        row = self.build()["today_lessons"][0]

        self.assertEqual((row.last_session_number, row.last_summary), (2, "محتوای دوم"))

    def test_active_classes_counts_classes_not_subjects_or_today(self):
        self.class_subject("ریاضی")
        self.class_subject("علوم")  # same class, second subject
        self.class_subject("فارسی", school_class=self.other_class)

        self.assertEqual(self.build()["active_classes_count"], 2)

    def test_query_count_does_not_grow_with_lessons(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                self.build()
            return len(queries)

        first = self.class_subject("یک")
        self.slot(first, Day.SATURDAY, self.bell_1)
        SchoolSession.objects.create(class_subject=first, date=jdatetime.date(1405, 7, 1))
        few = count()

        for bell in (self.bell_2, self.bell_4, self.bell_5):
            cs = self.class_subject(f"درس {bell.order}", school_class=self.other_class)
            self.slot(cs, Day.SATURDAY, bell)
            SchoolSession.objects.create(class_subject=cs, date=jdatetime.date(1405, 7, 1))

        self.assertEqual(count(), few)


@FAST_HASHER
class DashboardViewTests(ScheduleFixtureMixin, TestCase):
    url = reverse("core:dashboard")

    def setUp(self):
        patcher = mock.patch("django.utils.timezone.now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_anonymous_is_sent_to_login(self):
        self.assertRedirects(
            self.client.get(self.url), f"{reverse('accounts:login')}?next={self.url}", fetch_redirect_response=False
        )

    def test_student_is_sent_to_their_own_dashboard(self):
        self.client.force_login(make_student().user)
        self.assertRedirects(self.client.get(self.url), reverse("student:dashboard"), fetch_redirect_response=False)

    def test_teacher_role_without_profile_is_forbidden_not_a_500(self):
        self.client.force_login(make_user("teacher"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_teacher_sees_the_new_dashboard_without_my_classes(self):
        self.slot(self.class_subject("ریاضی"), Day.SATURDAY, self.bell_1)
        self.client.force_login(self.teacher.staff.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "teacher/base.html")
        self.assertContains(response, "برنامه امروز")
        self.assertContains(response, reverse("scheduling:teacher-schedule"))
        self.assertContains(response, "شنبه ۱۱ مهر ۱۴۰۵")  # Persian digits + Jalali
        for gone in ("کلاس‌های من", "کلاس های من", "بر اساس پایه", "بر اساس درس", "toggleView"):
            self.assertNotContains(response, gone)
        self.assertNotIn("class_subjects_summary", response.context)

    def test_shared_pages_use_the_teacher_shell_only_for_teachers(self):
        self.client.force_login(self.teacher.staff.user)
        self.assertTemplateUsed(self.client.get(reverse("school:class_list")), "teacher/base.html")

        admin = make_user("admin", is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        response = self.client.get(reverse("report:reports_page"))
        self.assertTemplateNotUsed(response, "teacher/base.html")
