"""
The teacher's dated week (scheduling.services.build_teacher_week and the
/scheduling/teacher/ page): concrete dates, prev/next navigation, and the
state of each slot -- open, future, registered, holiday.

Calendar as in scheduling/tests.py: NOW is Saturday 2026-10-03 09:10
(1405/07/11, rotation week 2); Sunday 10-04 is in the future.
"""

from unittest import mock

import jdatetime
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.testing import make_calendar_event
from teaching.models import SchoolSession

from .services import (
    FUTURE_TOOLTIP,
    SLOT_FUTURE,
    SLOT_HOLIDAY,
    SLOT_OPEN,
    SLOT_REGISTERED,
    build_teacher_week,
)
from .tests import FAST_HASHER, NOW, WEEK_ONE, WEEK_TWO, Day, ScheduleFixtureMixin

J = jdatetime.date
SATURDAY = J(1405, 7, 11)


def states(week):
    return {
        (day.value, cell.bell.order, lesson.entry.subject): lesson.state
        for day in week.days
        for cell in day.cells
        for lesson in cell.lessons
    }


class TeacherWeekTests(ScheduleFixtureMixin, TestCase):

    def build(self, week_of=None, now=NOW):
        return build_teacher_week(self.teacher, self.year, week_of=week_of, now=now)

    def setUp(self):
        self.math = self.class_subject("ریاضی")
        # the same subject twice on Saturday, and on Sunday
        self.slot(self.math, Day.SATURDAY, self.bell_1)
        self.slot(self.math, Day.SATURDAY, self.bell_2)
        self.slot(self.math, Day.SUNDAY, self.bell_1)

    def test_days_have_dates_and_the_week_its_rotation(self):
        week = self.build()

        self.assertEqual(str(week.start), "2026-10-03")
        self.assertEqual([d.value for d in week.days], [0, 1, 2, 3, 4])
        self.assertEqual(week.days[1].jalali, "1405-07-12")
        self.assertEqual(week.week_type, WEEK_TWO)
        self.assertTrue(week.is_current)
        self.assertEqual(week.next_query, "1405-07-18")
        self.assertEqual(week.previous_query, "1405-07-04")

    def test_slot_states(self):
        SchoolSession.objects.create(class_subject=self.math, date=SATURDAY, bell=self.bell_1)

        self.assertEqual(states(self.build()), {
            (Day.SATURDAY, 1, "ریاضی"): SLOT_REGISTERED,
            # registering bell 1 does not block bell 2 of the same day
            (Day.SATURDAY, 2, "ریاضی"): SLOT_OPEN,
            (Day.SUNDAY, 1, "ریاضی"): SLOT_FUTURE,
        })

    def test_closed_slots_show_the_event(self):
        make_calendar_event(self.year, SATURDAY, title="برف", bells=[self.bell_2])

        week = self.build()

        self.assertEqual(states(week)[(Day.SATURDAY, 2, "ریاضی")], SLOT_HOLIDAY)
        lesson = week.days[0].cells[1].lessons[0]
        self.assertEqual(lesson.event_title, "برف")
        self.assertFalse(lesson.is_link)

    def test_legacy_session_without_bell_takes_the_first_slot(self):
        SchoolSession.objects.create(class_subject=self.math, date=SATURDAY)

        result = states(self.build())

        self.assertEqual(result[(Day.SATURDAY, 1, "ریاضی")], SLOT_REGISTERED)
        self.assertEqual(result[(Day.SATURDAY, 2, "ریاضی")], SLOT_OPEN)

    def test_other_weeks_follow_their_rotation(self):
        self.slot(self.class_subject("هفته اول"), Day.MONDAY, self.bell_1, WEEK_ONE)

        this_week = states(self.build())
        next_week = self.build(week_of=J(1405, 7, 20).togregorian())

        self.assertNotIn((Day.MONDAY, 1, "هفته اول"), this_week)
        self.assertEqual(next_week.week_type, WEEK_ONE)
        self.assertEqual(states(next_week)[(Day.MONDAY, 1, "هفته اول")], SLOT_FUTURE)

    def test_weeks_are_clamped_to_the_academic_year(self):
        week = self.build(week_of=J(1404, 1, 1).togregorian())

        self.assertEqual(week.start, self.build(week_of=self.year.start_date.togregorian()).start)
        self.assertIsNone(week.previous_start)

    def test_query_count_does_not_grow_with_lessons(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                self.build()
            return len(queries)

        # one event already: its scope is prefetched once, however many
        make_calendar_event(self.year, J(1405, 7, 15), bells=[self.bell_1])
        few = count()
        for day in (Day.MONDAY, Day.TUESDAY, Day.WEDNESDAY):
            cs = self.class_subject(f"درس {day}", school_class=self.other_class)
            self.slot(cs, day, self.bell_1)
            SchoolSession.objects.create(class_subject=cs, date=SATURDAY)
        make_calendar_event(self.year, SATURDAY, bells=[self.bell_2])

        self.assertEqual(count(), few)


@FAST_HASHER
class TeacherWeekPageTests(ScheduleFixtureMixin, TestCase):
    url = reverse("scheduling:teacher-schedule")

    def setUp(self):
        self.math = self.class_subject("ریاضی")
        self.slot(self.math, Day.SATURDAY, self.bell_1)
        self.slot(self.math, Day.SATURDAY, self.bell_2)
        self.slot(self.math, Day.SUNDAY, self.bell_1)
        self.client.force_login(self.teacher.staff.user)
        patcher = mock.patch("django.utils.timezone.now", return_value=NOW)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_cells_are_real_links_with_their_state(self):
        session = SchoolSession.objects.create(class_subject=self.math, date=SATURDAY, bell=self.bell_1)
        make_calendar_event(self.year, J(1405, 7, 13), title="عید غدیر")
        self.slot(self.math, Day.MONDAY, self.bell_1)

        html = self.client.get(self.url).content.decode()

        form = reverse("teaching:session_form", args=[self.math.pk])
        # open: Saturday bell 2, a link with the slot prefilled
        self.assertIn(f'href="{form}?date=1405-07-11&amp;bell={self.bell_2.pk}&amp;next=', html)
        # registered: still a link (the server answers with the error), marked for JS
        self.assertIn(f'href="{form}?date=1405-07-11&amp;bell={self.bell_1.pk}', html)
        self.assertIn(
            f'data-session-url="{reverse("teaching:update_session", args=[session.pk])}"', html
        )
        # future: not a link, with the tooltip
        self.assertIn(f'title="{FUTURE_TOOLTIP}" aria-disabled="true"', html)
        self.assertNotIn(f"{form}?date=1405-07-12", html)
        # holiday: the event's title, not a link
        self.assertIn("تعطیل: عید غدیر", html)
        self.assertNotIn(f"{form}?date=1405-07-13", html)

    def test_week_navigation_links(self):
        response = self.client.get(self.url)

        self.assertContains(response, 'href="?week=1405-07-18" rel="next"')
        self.assertContains(response, 'href="?week=1405-07-04" rel="prev"')
