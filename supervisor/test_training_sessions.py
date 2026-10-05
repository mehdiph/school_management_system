"""
Tests for the supervisor's "training sessions" (جلسات آموزشی) and
"supervised teachers" (معلمان من) pages: access, scoping, counts,
filters, partial/full rendering and query counts.

Helpers come from supervisor/tests.py (functions only -- importing its
TestCase classes here would run them twice).
"""

from datetime import date, time
from unittest.mock import patch

import jdatetime
from django.test import TestCase
from django.urls import reverse

from scheduling.models.class_schedule import ClassSchedule
from scheduling.utils import count_scheduled_occurrences
from teaching.models import SchoolSession, SessionContent

from .tests import (
    User,
    assign_class,
    make_academic_year,
    make_attendance,
    make_bell,
    make_branch,
    make_class_subject,
    make_enrollment,
    make_grade,
    make_schedule,
    make_school_class,
    make_session,
    make_student,
    make_subject,
    make_supervisor,
    make_teacher,
    make_user,
)

#: Monday 13 Mehr 1405: academic week 2 of a year starting 1 Mehr 1405
#: (see scheduling.utils -- 1..10 Mehr is week 1).
TODAY = date(2026, 10, 5)
YEAR_START = jdatetime.date(1405, 7, 1)
YEAR_END = jdatetime.date(1406, 6, 31)
J = jdatetime.date


def add_content(session, title="عنوان", content="محتوا", homework="تمرین ۱", activity="", notes=""):
    return SessionContent.objects.create(
        session=session,
        title=title,
        content=content,
        homework=homework,
        activity=activity,
        notes=notes,
    )


class SupervisorPagesTestCase(TestCase):
    """
    Two supervisors in the same branch and grade, each with their own
    class -- so only ``SupervisorClass`` separates them:

    * supervisor A -> class_a (current year) and old_class (last year)
    * supervisor B -> class_b

    ``teacher`` teaches ``subject`` in class_a (the main fixture) and also
    ``other_subject`` in class_b (outside A's scope); ``other_teacher``
    only teaches in class_b.
    """

    def setUp(self):
        patcher = patch("supervisor.selectors.timezone.localdate", return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.branch = make_branch()
        self.grade = make_grade()
        self.old_year = make_academic_year(J(1404, 7, 1), J(1405, 6, 31), is_current=False)
        self.year = make_academic_year(YEAR_START, YEAR_END)

        self.supervisor = make_supervisor(self.branch, self.grade)
        self.other_supervisor = make_supervisor(self.branch, self.grade)

        self.class_a = make_school_class(self.branch, self.grade, self.year)
        self.class_b = make_school_class(self.branch, self.grade, self.year)
        self.old_class = make_school_class(self.branch, self.grade, self.old_year)
        assign_class(self.supervisor, self.class_a)
        assign_class(self.supervisor, self.old_class)
        assign_class(self.other_supervisor, self.class_b)

        self.teacher, self.assignment = make_teacher(self.branch, self.year)
        self.other_teacher, self.other_assignment = make_teacher(self.branch, self.year)

        self.subject = make_subject()
        self.other_subject = make_subject()

        self.class_subject = make_class_subject(
            self.class_a, self.subject, self.assignment, YEAR_START, YEAR_END
        )
        # Same teacher, but in supervisor B's class.
        self.foreign_class_subject = make_class_subject(
            self.class_b, self.other_subject, self.assignment, YEAR_START, YEAR_END
        )
        self.other_class_subject = make_class_subject(
            self.class_b, self.subject, self.other_assignment, YEAR_START, YEAR_END
        )

        # In scope: 4 sessions -- 2 with content, 1 held without content,
        # 1 cancelled without content (not counted as "no content").
        self.s1 = make_session(self.class_subject, J(1405, 7, 1))
        add_content(self.s1, title="فصل ۱", activity="کار گروهی")
        self.s2 = make_session(self.class_subject, J(1405, 7, 5))
        add_content(self.s2, title="فصل ۲", homework="")
        self.s3 = make_session(self.class_subject, J(1405, 7, 8))
        self.s4 = make_session(self.class_subject, J(1405, 7, 12), status=SchoolSession.Status.CANCELED)

        # Out of scope.
        self.foreign_session = make_session(self.foreign_class_subject, J(1405, 7, 6))
        make_session(self.foreign_class_subject, J(1405, 7, 7))
        self.other_session = make_session(self.other_class_subject, J(1405, 7, 6))

        self.client.force_login(self.supervisor.user)

    def timeline_url(self, class_subject):
        return reverse("supervisor:class_subject_timeline", args=[class_subject.pk])

    def detail_url(self, session):
        return reverse("supervisor:session_detail", args=[session.pk])


# ----------------------------------------------------------------------
# Access
# ----------------------------------------------------------------------


class AccessTests(SupervisorPagesTestCase):

    def urls(self):
        return [
            reverse("supervisor:sessions"),
            reverse("supervisor:teachers"),
            self.timeline_url(self.class_subject),
            self.detail_url(self.s1),
        ]

    def test_anonymous_users_are_sent_to_login(self):
        self.client.logout()
        for url in self.urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(
                    response,
                    f"{reverse('accounts:login')}?next={url}",
                    fetch_redirect_response=False,
                )

    def test_non_supervisors_are_forbidden(self):
        self.client.force_login(make_user(User.Roles.TEACHER))
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_sidebar_links_to_the_new_pages_and_marks_the_active_one(self):
        response = self.client.get(self.timeline_url(self.class_subject))

        self.assertContains(
            response,
            f'<a href="{reverse("supervisor:sessions")}" class="sidebar-nav__item is-active">',
            html=False,
        )
        self.assertContains(response, f'href="{reverse("supervisor:teachers")}"')


# ----------------------------------------------------------------------
# Scoping
# ----------------------------------------------------------------------


class ScopingTests(SupervisorPagesTestCase):

    def test_summary_only_lists_the_supervisors_class_subjects(self):
        response = self.client.get(reverse("supervisor:sessions"))

        self.assertEqual([row.pk for row in response.context["rows"]], [self.class_subject.pk])
        self.assertEqual(response.context["kpis"]["session_count"], 4)

    def test_filter_options_only_come_from_the_scope(self):
        form = self.client.get(reverse("supervisor:sessions")).context["form"]

        self.assertEqual(list(form.fields["teacher"].objects.values()), [self.teacher])
        self.assertEqual(list(form.fields["subject"].objects.values()), [self.subject])
        self.assertEqual(list(form.fields["school_class"].objects.values()), [self.class_a])
        self.assertEqual(
            set(form.fields["academic_year"].objects.values()), {self.year, self.old_year}
        )

    def test_out_of_scope_teacher_id_is_rejected_not_applied(self):
        response = self.client.get(
            reverse("supervisor:sessions"), {"teacher": self.other_teacher.pk}
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("teacher", response.context["form"].errors)
        self.assertIsNone(response.context["filters"].teacher)
        self.assertNotContains(response, self.other_teacher.staff.user.get_full_name())

    def test_out_of_scope_timeline_and_detail_are_404(self):
        for url in [
            self.timeline_url(self.foreign_class_subject),
            self.timeline_url(self.other_class_subject),
            self.detail_url(self.foreign_session),
            self.detail_url(self.other_session),
        ]:
            for query in ({}, {"partial": "1"}):
                with self.subTest(url=url, query=query):
                    self.assertEqual(self.client.get(url, query).status_code, 404)

    def test_other_supervisor_sees_their_own_data_only(self):
        self.client.force_login(self.other_supervisor.user)

        rows = self.client.get(reverse("supervisor:sessions")).context["rows"]
        self.assertEqual(
            {row.pk for row in rows},
            {self.foreign_class_subject.pk, self.other_class_subject.pk},
        )
        self.assertEqual(self.client.get(self.detail_url(self.s1)).status_code, 404)
        self.assertEqual(self.client.get(self.timeline_url(self.class_subject)).status_code, 404)

    def test_inactive_class_subject_and_class_are_out_of_scope(self):
        self.class_subject.is_active = False
        self.class_subject.save()

        self.assertEqual(list(self.client.get(reverse("supervisor:sessions")).context["rows"]), [])
        self.assertEqual(self.client.get(self.timeline_url(self.class_subject)).status_code, 404)
        self.assertEqual(self.client.get(self.detail_url(self.s1)).status_code, 404)

        self.class_subject.is_active = True
        self.class_subject.save()
        self.class_a.is_active = False
        self.class_a.save()

        self.assertEqual(list(self.client.get(reverse("supervisor:sessions")).context["rows"]), [])
        self.assertEqual(self.client.get(self.timeline_url(self.class_subject)).status_code, 404)

    def test_teachers_page_lists_only_teachers_of_own_classes(self):
        response = self.client.get(reverse("supervisor:teachers"))

        self.assertEqual([t.pk for t in response.context["teachers"]], [self.teacher.pk])
        self.assertEqual(
            list(response.context["form"].fields["subject"].objects.values()), [self.subject]
        )

    def test_empty_state_without_classes(self):
        lonely = make_supervisor(self.branch, self.grade)
        self.client.force_login(lonely.user)

        sessions = self.client.get(reverse("supervisor:sessions"))
        teachers = self.client.get(reverse("supervisor:teachers"))

        self.assertContains(sessions, "هنوز کلاسی")
        self.assertContains(teachers, "هنوز کلاسی")


# ----------------------------------------------------------------------
# Counts
# ----------------------------------------------------------------------


class CountTests(SupervisorPagesTestCase):

    def test_summary_row_counts_and_dates(self):
        row = self.client.get(reverse("supervisor:sessions")).context["rows"][0]

        self.assertEqual(row.session_count, 4)
        self.assertEqual(row.empty_count, 1)  # s3; the cancelled s4 does not count
        self.assertEqual(row.delivered_count, 3)
        self.assertEqual(row.first_date, J(1405, 7, 1))
        self.assertEqual(row.last_date, J(1405, 7, 12))

    def test_kpis(self):
        kpis = self.client.get(reverse("supervisor:sessions")).context["kpis"]

        self.assertEqual(kpis["session_count"], 4)
        self.assertEqual(kpis["empty_count"], 1)
        self.assertEqual(kpis["teacher_count"], 1)
        self.assertEqual(kpis["last_date"], J(1405, 7, 12))

    def test_class_subject_without_sessions_is_still_listed(self):
        empty = make_class_subject(
            self.class_a, make_subject(), self.assignment, YEAR_START, YEAR_END
        )

        rows = {row.pk: row for row in self.client.get(reverse("supervisor:sessions")).context["rows"]}

        self.assertEqual(rows[empty.pk].session_count, 0)
        self.assertIsNone(rows[empty.pk].last_date)

    def test_teacher_stats_only_count_in_scope_sessions(self):
        teacher = self.client.get(reverse("supervisor:teachers")).context["teachers"][0]

        # 2 more sessions of the same teacher in class_b are not counted.
        self.assertEqual(teacher.session_count, 4)
        self.assertEqual(teacher.empty_count, 1)
        self.assertEqual(teacher.last_session_date, J(1405, 7, 12))
        self.assertEqual(teacher.subject_chips, [self.subject.name])
        self.assertEqual(teacher.class_chips, [f"{self.grade.name} {self.class_a.section}"])

    def test_teacher_stats_with_two_class_subjects(self):
        second = make_class_subject(
            self.class_a, make_subject(), self.assignment, YEAR_START, YEAR_END
        )
        make_session(second, J(1405, 7, 13))

        teacher = self.client.get(reverse("supervisor:teachers")).context["teachers"][0]

        self.assertEqual(teacher.session_count, 5)
        self.assertEqual(teacher.empty_count, 2)
        self.assertEqual(teacher.last_session_date, J(1405, 7, 13))
        self.assertEqual(len(teacher.subject_chips), 2)

    def test_inactivity_marker(self):
        # last session 12 Mehr, today 13 Mehr: active.
        teacher = self.client.get(reverse("supervisor:teachers")).context["teachers"][0]
        self.assertEqual(teacher.days_since_last_session, 1)
        self.assertFalse(teacher.is_inactive)

        SchoolSession.objects.filter(pk=self.s4.pk).delete()
        SchoolSession.objects.filter(pk=self.s3.pk).delete()
        # last session now 5 Mehr: 8 days > 7.
        response = self.client.get(reverse("supervisor:teachers"))
        teacher = response.context["teachers"][0]
        self.assertTrue(teacher.is_inactive)
        self.assertContains(response, "sv-activity--stale")
        self.assertContains(response, "۱ هفته پیش")

    def test_coverage_against_the_timetable(self):
        # Saturdays every week + Mondays of week 2 only. From 1 Mehr
        # (Wed 23 Sep) to today (Mon 5 Oct): Sat 26 Sep, Sat 3 Oct and
        # Mon 5 Oct (week 2) -- Mon 28 Sep is week 1.
        make_schedule(self.class_subject, ClassSchedule.DayChoices.SATURDAY, make_bell(time(8), time(9)))
        make_schedule(
            self.class_subject,
            ClassSchedule.DayChoices.MONDAY,
            make_bell(time(10), time(11)),
            week_type=ClassSchedule.WeekTypeChoices.WEEK_TWO,
        )

        row = self.client.get(reverse("supervisor:sessions")).context["rows"][0]

        self.assertEqual(row.expected_count, 3)
        self.assertEqual(row.coverage, 100)  # 3 delivered (s4 was cancelled)
        self.assertEqual(row.coverage_level, "ok")

    def test_no_timetable_means_no_coverage(self):
        row = self.client.get(reverse("supervisor:sessions")).context["rows"][0]

        self.assertIsNone(row.expected_count)
        self.assertIsNone(row.coverage)

    def test_count_scheduled_occurrences(self):
        slots = [
            (ClassSchedule.DayChoices.SATURDAY, ClassSchedule.WeekTypeChoices.WEEK_ONE),
            (ClassSchedule.DayChoices.SATURDAY, ClassSchedule.WeekTypeChoices.BOTH),
        ]
        # 1..20 Mehr: Saturdays 4 Mehr (week 1), 11 Mehr (week 2), 18 Mehr (week 3).
        self.assertEqual(
            count_scheduled_occurrences(slots, J(1405, 7, 1), J(1405, 7, 20), self.year), 5
        )
        self.assertEqual(count_scheduled_occurrences([], YEAR_START, YEAR_END, self.year), 0)


# ----------------------------------------------------------------------
# Filters, sorting, paging
# ----------------------------------------------------------------------


class FilterTests(SupervisorPagesTestCase):

    def get_rows(self, **query):
        return self.client.get(reverse("supervisor:sessions"), query).context

    def test_date_range(self):
        context = self.get_rows(date_from="1405/07/05", date_to="1405-07-08")
        row = context["rows"][0]

        self.assertEqual(row.session_count, 2)
        self.assertEqual(row.first_date, J(1405, 7, 5))
        self.assertEqual(context["kpis"]["session_count"], 2)

    def test_persian_digits_are_accepted(self):
        row = self.get_rows(date_from="۱۴۰۵/۰۷/۰۸")["rows"][0]

        self.assertEqual(row.session_count, 2)

    def test_invalid_dates_show_an_error_instead_of_crashing(self):
        response = self.client.get(reverse("supervisor:sessions"), {"date_from": "1405/13/40"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("date_from", response.context["form"].errors)
        self.assertContains(response, "تاریخ معتبر نیست")
        self.assertEqual(response.context["rows"][0].session_count, 4)

    def test_reversed_range_is_an_error(self):
        response = self.client.get(
            reverse("supervisor:sessions"), {"date_from": "1405/07/10", "date_to": "1405/07/01"}
        )

        self.assertContains(response, "تاریخ پایان نباید قبل از تاریخ شروع باشد")
        self.assertIsNone(response.context["filters"].date_to)

    def test_status_filter(self):
        row = self.get_rows(status=SchoolSession.Status.CANCELED)["rows"][0]

        self.assertEqual(row.session_count, 1)
        self.assertEqual(row.empty_count, 0)

    def test_range_shortcut_this_week(self):
        # Week of Mon 5 Oct 2026: Sat 3 Oct (11 Mehr) .. Fri 9 Oct (17 Mehr).
        context = self.get_rows(range="week")

        self.assertEqual(context["filters"].date_from, J(1405, 7, 11))
        self.assertEqual(context["filters"].date_to, J(1405, 7, 17))
        self.assertEqual(context["rows"][0].session_count, 1)  # s4 on 12 Mehr
        self.assertEqual(context["form"].active_range, "week")

    def test_range_shortcut_this_month(self):
        filters = self.get_rows(range="month")["filters"]

        self.assertEqual((filters.date_from, filters.date_to), (J(1405, 7, 1), J(1405, 7, 30)))

    def test_academic_year_defaults_to_current_and_can_be_switched(self):
        old_teacher, old_assignment = make_teacher(self.branch, self.old_year)
        old_class_subject = make_class_subject(
            self.old_class, self.subject, old_assignment, J(1404, 7, 1), J(1405, 6, 31)
        )
        make_session(old_class_subject, J(1404, 8, 1))

        current = self.get_rows()
        self.assertEqual(current["filters"].academic_year, self.year)
        self.assertEqual([row.pk for row in current["rows"]], [self.class_subject.pk])

        old = self.get_rows(academic_year=self.old_year.pk)
        self.assertEqual([row.pk for row in old["rows"]], [old_class_subject.pk])
        self.assertEqual(list(old["form"].fields["teacher"].objects.values()), [old_teacher])

        teachers = self.client.get(reverse("supervisor:teachers"), {"academic_year": self.old_year.pk})
        self.assertEqual([t.pk for t in teachers.context["teachers"]], [old_teacher.pk])

    def test_foreign_academic_year_falls_back_to_current(self):
        stranger_year = make_academic_year(J(1300, 1, 1), is_current=False)

        response = self.client.get(reverse("supervisor:sessions"), {"academic_year": stranger_year.pk})

        self.assertIn("academic_year", response.context["form"].errors)
        self.assertEqual(response.context["filters"].academic_year, self.year)

    def test_teacher_query_param_prefills_the_teacher_filter(self):
        second_teacher, second_assignment = make_teacher(self.branch, self.year)
        make_class_subject(self.class_a, make_subject(), second_assignment, YEAR_START, YEAR_END)

        response = self.client.get(reverse("supervisor:sessions"), {"teacher": self.teacher.pk})

        self.assertEqual(response.context["filters"].teacher, self.teacher)
        self.assertEqual([row.pk for row in response.context["rows"]], [self.class_subject.pk])
        self.assertContains(response, f'<option value="{self.teacher.pk}" selected>', html=False)

    def test_sorting(self):
        busy = make_class_subject(self.class_a, make_subject(), self.assignment, YEAR_START, YEAR_END)
        for day in range(1, 7):
            make_session(busy, J(1405, 7, day))

        rows = self.get_rows(sort="-sessions")["rows"]
        self.assertEqual([row.pk for row in rows], [busy.pk, self.class_subject.pk])

        rows = self.get_rows(sort="sessions")["rows"]
        self.assertEqual([row.pk for row in rows], [self.class_subject.pk, busy.pk])

        # unknown sort -> default, no crash
        self.assertEqual(self.client.get(reverse("supervisor:sessions"), {"sort": "evil"}).status_code, 200)

    def test_pagination_keeps_the_filters(self):
        for _ in range(21):
            make_class_subject(self.class_a, make_subject(), self.assignment, YEAR_START, YEAR_END)

        response = self.client.get(reverse("supervisor:sessions"), {"teacher": self.teacher.pk, "page": 2})

        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(len(response.context["rows"]), 2)
        self.assertContains(response, f"?teacher={self.teacher.pk}&amp;page=1")

    def test_timeline_links_carry_the_period(self):
        response = self.client.get(
            reverse("supervisor:sessions"), {"date_from": "1405/07/05", "status": "HD"}
        )

        self.assertContains(
            response,
            f'{self.timeline_url(self.class_subject)}?date_from=1405-07-05&amp;status=HD',
        )

    def test_teacher_search_and_view_toggle(self):
        code = self.teacher.staff.personnel_code

        found = self.client.get(reverse("supervisor:teachers"), {"q": code})
        missing = self.client.get(reverse("supervisor:teachers"), {"q": "no-such-teacher"})
        table = self.client.get(reverse("supervisor:teachers"), {"view": "table"})

        self.assertEqual(len(found.context["teachers"]), 1)
        self.assertEqual(len(missing.context["teachers"]), 0)
        self.assertContains(missing, "معلمی با این مشخصات پیدا نشد")
        self.assertContains(table, "sv-teachers-table")
        self.assertNotContains(found, "sv-teachers-table")

    def test_view_sessions_link(self):
        response = self.client.get(reverse("supervisor:teachers"))

        self.assertContains(
            response,
            f'{reverse("supervisor:sessions")}?teacher={self.teacher.pk}&amp;academic_year={self.year.pk}',
        )

    def test_teacher_sorting(self):
        busy_teacher, busy_assignment = make_teacher(self.branch, self.year)
        busy = make_class_subject(self.class_a, make_subject(), busy_assignment, YEAR_START, YEAR_END)
        for day in range(1, 9):
            make_session(busy, J(1405, 7, day))

        teachers = self.client.get(reverse("supervisor:teachers"), {"sort": "-sessions"}).context["teachers"]

        self.assertEqual([t.pk for t in teachers], [busy_teacher.pk, self.teacher.pk])


# ----------------------------------------------------------------------
# Timeline / detail: partial vs full page
# ----------------------------------------------------------------------


class PartialRenderingTests(SupervisorPagesTestCase):

    def test_timeline_partial_and_full_page(self):
        partial = self.client.get(self.timeline_url(self.class_subject), {"partial": "1"})
        full = self.client.get(self.timeline_url(self.class_subject))

        self.assertTemplateUsed(partial, "supervisor/partials/_session_timeline.html")
        self.assertTemplateNotUsed(partial, "base.html")
        self.assertTemplateUsed(full, "supervisor/session_timeline.html")
        self.assertTemplateUsed(full, "supervisor/partials/_session_timeline.html")
        self.assertTemplateUsed(full, "base.html")

    def test_timeline_content(self):
        response = self.client.get(self.timeline_url(self.class_subject), {"partial": "1"})
        sessions = response.context["sessions"]

        self.assertEqual([s.pk for s in sessions], [self.s1.pk, self.s2.pk, self.s3.pk, self.s4.pk])
        self.assertEqual([s.gap_days for s in sessions], [None, 4, 3, 4])
        self.assertEqual(sessions[0].title, "فصل ۱")
        self.assertTrue(sessions[0].has_activity)
        self.assertTrue(sessions[0].has_homework)
        self.assertFalse(sessions[1].has_homework)
        self.assertTrue(sessions[2].is_missing_content)
        self.assertFalse(sessions[3].is_missing_content)  # cancelled
        self.assertContains(response, "محتوایی برای این جلسه ثبت نشده است")
        self.assertContains(response, self.detail_url(self.s1))

    def test_timeline_respects_the_period_and_marks_long_gaps(self):
        later = make_session(self.class_subject, J(1405, 8, 1))

        response = self.client.get(
            self.timeline_url(self.class_subject),
            {"partial": "1", "date_from": "1405/07/08"},
        )
        sessions = response.context["sessions"]

        self.assertEqual([s.pk for s in sessions], [self.s3.pk, self.s4.pk, later.pk])
        self.assertTrue(sessions[2].is_long_gap)  # 12 Mehr -> 1 Aban: 19 days
        self.assertContains(response, "فاصله‌ی طولانی")

    def test_timeline_does_not_load_full_texts(self):
        long_text = "الف" * 1000
        content = self.s1.session_contents
        content.content = long_text
        content.save()

        sessions = self.client.get(
            self.timeline_url(self.class_subject), {"partial": "1"}
        ).context["sessions"]

        self.assertEqual(len(sessions[0].excerpt), 240)

    def test_detail_partial_and_full_page(self):
        student = make_student()
        enrollment = make_enrollment(student, self.class_a)
        make_attendance(self.s1, enrollment, status="absent")

        partial = self.client.get(self.detail_url(self.s1), {"partial": "1"})
        full = self.client.get(self.detail_url(self.s1))

        self.assertTemplateUsed(partial, "supervisor/partials/_session_detail.html")
        self.assertTemplateNotUsed(partial, "base.html")
        self.assertTemplateUsed(full, "supervisor/session_detail.html")
        self.assertTemplateUsed(full, "base.html")
        self.assertEqual(
            partial.context["attendance"], {"total": 1, "present": 0, "absent": 1, "late": 0}
        )
        self.assertContains(partial, "کار گروهی")

    def test_detail_without_content(self):
        response = self.client.get(self.detail_url(self.s3), {"partial": "1"})

        self.assertIsNone(response.context["content"])
        self.assertContains(response, "محتوایی برای این جلسه ثبت نشده است")


# ----------------------------------------------------------------------
# Query counts (no N+1)
# ----------------------------------------------------------------------


class QueryCountTests(SupervisorPagesTestCase):
    """
    No N+1: a page's query count must not grow with its rows, and the
    exact numbers are locked. Every request starts with 9 queries that
    are not these pages' own (session, user, staff/supervisor profile,
    branch middleware + access check, sidebar/topbar context); a full
    page adds 2 more for the footer's site settings. Page-specific:

    * sessions: years, teacher / subject / class options, page count,
      KPIs, rows, timetable slots of the page                      -> 8
    * teachers: years, subject options, page count, rows, chips    -> 5
    * timeline (partial): class subject, sessions                  -> 2
    * detail (partial): session (+ content + chain), attendance    -> 2
    """

    OVERHEAD = 9
    FOOTER = 2

    def add_rows(self, count):
        for _ in range(count):
            teacher, assignment = make_teacher(self.branch, self.year)
            class_subject = make_class_subject(
                self.class_a, make_subject(), assignment, YEAR_START, YEAR_END
            )
            make_schedule(
                class_subject,
                ClassSchedule.DayChoices.SATURDAY,
                make_bell(time(7, 0), time(7, 30)),
            )
            session = make_session(class_subject, J(1405, 7, 5))
            add_content(session)

    def get(self, url, query=None):
        response = self.client.get(url, query or {})
        self.assertEqual(response.status_code, 200)
        return response

    def test_sessions_page(self):
        url = reverse("supervisor:sessions")
        expected = self.OVERHEAD + self.FOOTER + 8
        self.get(url)  # warm up per-process caches (content types, ...)

        with self.assertNumQueries(expected):
            self.get(url)

        self.add_rows(6)
        with self.assertNumQueries(expected):
            self.get(url)
        with self.assertNumQueries(expected):
            self.get(url, {
                "teacher": self.teacher.pk,
                "subject": self.subject.pk,
                "date_from": "1405/07/01",
                "status": "HD",
                "sort": "-last_date",
            })

    def test_teachers_page(self):
        url = reverse("supervisor:teachers")
        expected = self.OVERHEAD + self.FOOTER + 5
        self.get(url)

        with self.assertNumQueries(expected):
            self.get(url)

        self.add_rows(6)
        with self.assertNumQueries(expected):
            self.get(url)
        with self.assertNumQueries(expected):
            self.get(url, {"view": "table", "q": "user", "sort": "-last_activity"})

    def test_timeline_partial(self):
        url = self.timeline_url(self.class_subject)
        self.get(url, {"partial": "1"})

        for day in range(13, 25):
            add_content(make_session(self.class_subject, J(1405, 7, day)))

        with self.assertNumQueries(self.OVERHEAD + 2):
            self.get(url, {"partial": "1"})

    def test_detail_partial(self):
        url = self.detail_url(self.s1)
        self.get(url, {"partial": "1"})

        with self.assertNumQueries(self.OVERHEAD + 2):
            self.get(url, {"partial": "1"})
