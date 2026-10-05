"""
The supervisor panel and the academic calendar: closed slots are never
"missing", two bells of one subject are two expected sessions, coverage
leaves holidays out, and holiday sessions are shown (not counted) on the
timeline and in the per-class-subject holiday column.

NOW is Sunday 1405/07/12 (2026-10-04) 12:00, Tehran: both morning bells
are over (with the grace period).
"""

from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import jdatetime

from academic_calendar import services
from academic_calendar.tests import CalendarTestCase, Day
from core.testing import make_calendar_event, make_schedule, make_supervisor
from supervisor.models import SupervisorClass
from supervisor.selectors import (
    SessionFilters,
    SupervisorDashboardSelector,
    SupervisorSessionsSelector,
)
from teaching.models import SchoolSession

J = jdatetime.date
NOW = datetime(2026, 10, 4, 12, 0, tzinfo=ZoneInfo("Asia/Tehran"))
SUNDAY = J(1405, 7, 12)


@mock.patch("django.utils.timezone.now", lambda: NOW)
class SupervisorCalendarTests(CalendarTestCase):

    def setUp(self):
        super().setUp()
        make_schedule(self.math, Day.SUNDAY, self.bell_1)
        make_schedule(self.math, Day.SUNDAY, self.bell_2)
        self.supervisor = make_supervisor(self.branch, self.grade)
        SupervisorClass.objects.create(supervisor=self.supervisor, school_class=self.school_class)

    def missing(self):
        items = SupervisorDashboardSelector(self.supervisor).attention_items()
        return [item["bell"].order for item in items]

    def test_each_bell_is_an_expected_session(self):
        self.assertEqual(self.missing(), [1, 2])

        SchoolSession.objects.create(class_subject=self.math, date=SUNDAY, bell=self.bell_1)

        # bell 1 is recorded: only bell 2 is missing (not "one of two")
        self.assertEqual(self.missing(), [2])

    def test_a_legacy_session_without_bell_covers_the_first_bell(self):
        SchoolSession.objects.create(class_subject=self.math, date=SUNDAY)

        self.assertEqual(self.missing(), [2])

    def test_closed_slots_are_never_missing_nor_scheduled(self):
        make_calendar_event(self.year, SUNDAY, bells=[self.bell_2])

        self.assertEqual(self.missing(), [1])
        self.assertEqual(SupervisorDashboardSelector(self.supervisor).today_schedule_count(), 1)

    def test_coverage_leaves_holidays_out(self):
        # 07/05 and 07/12 are the Sundays up to today: 2 x 2 bells
        selector = SupervisorSessionsSelector(self.supervisor, today=NOW.date())
        filters = SessionFilters(academic_year=self.year)

        row = selector.attach_coverage(selector.summary_rows(filters), filters)[0]
        self.assertEqual(row.expected_count, 4)

        event = make_calendar_event(self.year, SUNDAY)
        services.sync_cancelled_sessions(SUNDAY, SUNDAY)

        row = selector.attach_coverage(selector.summary_rows(filters), filters)[0]
        self.assertEqual((row.expected_count, row.holiday_count, row.session_count), (2, 2, 0))
        self.assertEqual(selector.kpis(filters)["holiday_count"], 2)
        self.assertTrue(event.sessions.exists())

    def test_timeline_shows_holidays_in_place_and_measures_gaps_without_them(self):
        SchoolSession.objects.create(class_subject=self.math, date=J(1405, 7, 5), bell=self.bell_1)
        make_calendar_event(self.year, SUNDAY, bells=[self.bell_1])
        services.sync_cancelled_sessions(SUNDAY, SUNDAY)
        SchoolSession.objects.create(class_subject=self.math, date=J(1405, 7, 19), bell=self.bell_1)

        selector = SupervisorSessionsSelector(self.supervisor, today=NOW.date())
        sessions = selector.timeline(self.math, SessionFilters())

        self.assertEqual(
            [(s.date, s.session_number, s.status) for s in sessions],
            [
                (J(1405, 7, 5), 1, SchoolSession.Status.HELD),
                (SUNDAY, None, SchoolSession.Status.HOLIDAY),
                (J(1405, 7, 19), 2, SchoolSession.Status.HELD),
            ],
        )
        self.assertEqual(sessions[2].gap_days, 14)
        self.assertFalse(sessions[1].is_missing_content)
