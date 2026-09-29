"""
The teacher's weekly schedule (/scheduling/teacher/) and its PDF: whose
lessons it shows, conflicts, and who may open it. Same fixed calendar as
scheduling/tests.py (NOW = Saturday of rotation week 2, 09:10).
"""

from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.testing import (
    make_assignment,
    make_branch,
    make_school_class,
    make_student,
    make_teacher_profile,
    make_user,
)

from .models.class_schedule import ClassSchedule
from .pdf import render_teacher_schedule_html
from .services import build_teacher_weekly_schedule, teacher_schedule_pdf_filename
from .tests import EVERY_WEEK, FAST_HASHER, NOW, WEEK_ONE, WEEK_TWO, Day, ScheduleFixtureMixin


def lessons(week):
    return [
        (day.value, slot.bell.order, entry.subject)
        for day in week.days
        for slot in day.slots
        for entry in slot.entries
    ]


class TeacherScheduleServiceTests(ScheduleFixtureMixin, TestCase):

    def build(self, now=NOW):
        return build_teacher_weekly_schedule(self.teacher, self.year, now=now)

    def test_only_the_teachers_own_lessons_across_classes_and_branches(self):
        other_branch = make_branch()
        other_branch_class = make_school_class(other_branch, self.grade, self.year)
        other_assignment = make_assignment(self.teacher, other_branch, self.year)
        mine = self.class_subject("ریاضی")
        self.slot(mine, Day.SATURDAY, self.bell_1)
        elsewhere = self.class_subject("علوم", school_class=other_branch_class)
        elsewhere.teacher_assignment = other_assignment
        elsewhere.save()
        self.slot(elsewhere, Day.SUNDAY, self.bell_2)

        colleague = make_teacher_profile()
        colleague_subject = self.class_subject("فارسی")
        colleague_subject.teacher_assignment = make_assignment(colleague, self.branch, self.year)
        colleague_subject.save()
        self.slot(colleague_subject, Day.SATURDAY, self.bell_2)

        schedule = self.build()

        for week in schedule.weeks:
            self.assertEqual(
                lessons(week),
                [(Day.SATURDAY, 1, "ریاضی"), (Day.SUNDAY, 2, "علوم")],
            )
        entry = schedule.weeks[0].days[1].slots[1].entries[0]
        self.assertEqual(entry.branch, other_branch.name)

    def test_rotation_weeks_and_today(self):
        self.slot(self.class_subject("هفته اول"), Day.SATURDAY, self.bell_1, WEEK_ONE)
        self.slot(self.class_subject("هفته دوم"), Day.SATURDAY, self.bell_1, WEEK_TWO)

        schedule = self.build()
        week_one, week_two = schedule.weeks

        self.assertEqual(lessons(week_one), [(Day.SATURDAY, 1, "هفته اول")])
        self.assertEqual(lessons(week_two), [(Day.SATURDAY, 1, "هفته دوم")])
        self.assertTrue(week_two.is_current)
        self.assertTrue(week_two.days[0].is_today)
        # 09:10 is in the second bell.
        self.assertEqual([slot.is_now for slot in week_two.days[0].slots], [False, True])
        self.assertTrue(schedule.weeks_differ)

    def test_a_clash_keeps_both_lessons_and_is_flagged(self):
        first = self.class_subject("ریاضی")
        second = self.class_subject("علوم", school_class=self.other_class)
        self.slot(first, Day.MONDAY, self.bell_1)
        # Legacy data that the conflict checks would refuse today.
        with mock.patch("scheduling.conflicts.check_slots"):
            ClassSchedule.objects.bulk_create([
                ClassSchedule(class_subject=second, day_of_week=Day.MONDAY, bell=self.bell_1, week_type=EVERY_WEEK)
            ])

        schedule = self.build()
        slot = schedule.weeks[0].days[2].slots[0]

        self.assertTrue(slot.has_conflict)
        self.assertEqual(sorted(entry.subject for entry in slot.entries), ["ریاضی", "علوم"])
        self.assertEqual(schedule.summary(schedule.weeks[0]).conflicts, 1)

    def test_summary_counts_periods_classes_and_subjects(self):
        math = self.class_subject("ریاضی")
        self.slot(math, Day.SATURDAY, self.bell_1)
        self.slot(math, Day.SUNDAY, self.bell_1)
        self.slot(self.class_subject("علوم", school_class=self.other_class), Day.SUNDAY, self.bell_2)

        schedule = self.build()
        summary = schedule.summary(schedule.weeks[0])

        self.assertEqual((summary.periods, summary.classes, summary.subjects, summary.conflicts), (3, 2, 2, 0))

    def test_combined_grid_lists_every_week_lessons_once_and_tags_the_others(self):
        self.slot(self.class_subject("هر هفته"), Day.SATURDAY, self.bell_1)
        self.slot(self.class_subject("فقط اول"), Day.SATURDAY, self.bell_2, WEEK_ONE)

        day, cells = self.build().combined_days[0]

        self.assertEqual(day.value, Day.SATURDAY)
        self.assertEqual([(e.subject, tag) for e, tag in cells[0].items], [("هر هفته", None)])
        self.assertEqual([(e.subject, tag) for e, tag in cells[1].items], [("فقط اول", "هفته اول")])

    def test_query_count_does_not_grow_with_lessons(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                self.build()
            return len(queries)

        self.slot(self.class_subject("یک"), Day.SATURDAY, self.bell_1)
        few = count()
        for day in (Day.SUNDAY, Day.MONDAY, Day.TUESDAY):
            self.slot(self.class_subject(f"درس {day}", school_class=self.other_class), day, self.bell_2)
        self.assertEqual(count(), few)

    def test_pdf_filename_and_html(self):
        self.slot(self.class_subject("ریاضی"), Day.SATURDAY, self.bell_1)
        schedule = self.build()

        self.assertEqual(teacher_schedule_pdf_filename(schedule), "weekly-schedule-1405-1406.pdf")
        html = render_teacher_schedule_html(schedule)
        self.assertIn("A4 landscape", html)
        self.assertIn("file://", html)  # local font, never a URL fetch
        self.assertIn("ریاضی", html)


@FAST_HASHER
class TeacherScheduleViewTests(ScheduleFixtureMixin, TestCase):
    url = reverse("scheduling:teacher-schedule")
    pdf_url = reverse("scheduling:teacher-schedule-pdf")

    def setUp(self):
        self.slot(self.class_subject("ریاضی"), Day.SATURDAY, self.bell_1)
        self.client.force_login(self.teacher.staff.user)
        patcher = mock.patch("django.utils.timezone.now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        for url in (self.url, self.pdf_url):
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url),
                    f"{reverse('accounts:login')}?next={url}",
                    fetch_redirect_response=False,
                )

    def test_student_is_sent_to_their_own_dashboard(self):
        self.client.force_login(make_student().user)
        for url in (self.url, self.pdf_url):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), reverse("student:dashboard"), fetch_redirect_response=False)

    def test_teacher_role_without_profile_is_forbidden(self):
        self.client.force_login(make_user("teacher"))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.pdf_url).status_code, 403)

    def test_page_shows_own_schedule_in_teacher_shell(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "teacher/base.html")
        self.assertContains(response, "ریاضی")
        self.assertContains(response, self.pdf_url)
        self.assertEqual(response.context["selected_week"].number, 2)  # the current one

    def test_week_query_parameter(self):
        response = self.client.get(self.url + "?week=1")
        self.assertEqual(response.context["selected_week"].number, 1)

    def test_empty_state_without_lessons(self):
        ClassSchedule.objects.all().delete()
        response = self.client.get(self.url)
        self.assertContains(response, "هنوز برنامه‌ای برای شما ثبت نشده است")
        self.assertEqual(self.client.get(self.pdf_url).status_code, 404)

    def test_pdf_download(self):
        response = self.client.get(self.pdf_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(
            response["Content-Disposition"], 'attachment; filename="weekly-schedule-1405-1406.pdf"'
        )
        self.assertTrue(response.content.startswith(b"%PDF"))
