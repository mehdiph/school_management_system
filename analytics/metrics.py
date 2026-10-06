"""
The metrics, defined once: a ``Breakdown`` adds up slot outcomes and
sessions, and its properties are the rates every panel shows. Pages
group an ``EngineResult`` with :func:`breakdowns` by any key (branch,
grade, class, class subject, teacher, day) and over any date window, so a
number on one page always equals the same number on another.

Counts
------
expected       open expected slots (``engine``)
held           expected slots with an HD session -- or a JB one
cancelled      expected slots with a CD session (cancelled by the teacher)
unregistered   expected slots without any session
lost_to_closures  HL sessions (each is one slot an event closed)
compensatory   JB sessions that fill no expected slot (made up elsewhere)
outside_timetable HD / CD sessions that fill no slot (legacy data)
conflicts      non-holiday sessions in closed slots
delivered      HD + JB sessions (whatever slot they are in)

Rates (percentages; None when the denominator is 0)
-----
execution_rate           held / expected
makeup_coverage          compensatory / (lost_to_closures + cancelled)
content_rate             delivered with content / delivered
attendance_recorded_rate delivered with >= 1 attendance record / delivered
attendance_rate          (records - absent) / records, on delivered sessions
late_rate                late records / records, on delivered sessions
"""

from collections import defaultdict
from dataclasses import dataclass, fields

from .definitions import (
    CANCELLED,
    COMPENSATORY,
    DELIVERED_STATUSES,
    HELD,
    HOLIDAY,
    attendance_rate,
    rate,
)
from .engine import CANCELLED_SLOT, CONFLICT, HELD_SLOT, UNREGISTERED_SLOT


@dataclass
class Breakdown:
    expected: int = 0
    held: int = 0
    cancelled: int = 0
    unregistered: int = 0
    lost_to_closures: int = 0
    compensatory: int = 0
    outside_timetable: int = 0
    conflicts: int = 0
    delivered: int = 0
    with_content: int = 0
    with_attendance: int = 0
    attendance_total: int = 0
    absent: int = 0
    late: int = 0

    def add_outcome(self, outcome):
        self.expected += 1
        if outcome.outcome == HELD_SLOT:
            self.held += 1
        elif outcome.outcome == CANCELLED_SLOT:
            self.cancelled += 1
        elif outcome.outcome == UNREGISTERED_SLOT:
            self.unregistered += 1

    def add_session(self, row):
        if row.status == HOLIDAY:
            self.lost_to_closures += 1
            return

        if row.role == CONFLICT:
            self.conflicts += 1
        elif not row.role:
            if row.status == COMPENSATORY:
                self.compensatory += 1
            elif row.status in (HELD, CANCELLED):
                self.outside_timetable += 1

        if row.status in DELIVERED_STATUSES:
            self.delivered += 1
            self.with_content += row.has_content
            self.with_attendance += row.attendance_total > 0
            self.attendance_total += row.attendance_total
            self.absent += row.absent
            self.late += row.late

    def __add__(self, other):
        return Breakdown(**{
            f.name: getattr(self, f.name) + getattr(other, f.name) for f in fields(self)
        })

    # -- rates -------------------------------------------------------------

    @property
    def execution_rate(self):
        return rate(self.held, self.expected)

    @property
    def makeup_coverage(self):
        return rate(self.compensatory, self.lost_to_closures + self.cancelled)

    @property
    def content_rate(self):
        return rate(self.with_content, self.delivered)

    @property
    def attendance_recorded_rate(self):
        return rate(self.with_attendance, self.delivered)

    @property
    def attendance_rate(self):
        return attendance_rate(self.attendance_total, self.absent)

    @property
    def late_rate(self):
        return rate(self.late, self.attendance_total)

    @property
    def attended(self):
        return self.attendance_total - self.absent

    @property
    def is_empty(self):
        """Nothing expected and nothing recorded."""

        return not (self.expected or self.delivered or self.lost_to_closures
                    or self.cancelled or self.outside_timetable or self.conflicts)


# -- grouping keys: (class subject, Gregorian date) -> group --------------

def by_school(cs, day):
    return None


def by_branch(cs, day):
    return cs.school_class.branch_id


def by_grade(cs, day):
    return cs.school_class.grade_id


def by_class(cs, day):
    return cs.school_class_id


def by_class_subject(cs, day):
    return cs.pk


def by_teacher(cs, day):
    return cs.teacher_assignment.teacher_id


def by_day(cs, day):
    return day


def breakdowns(result, key, *, start=None, end=None, where=None):
    """
    ``{group: Breakdown}`` of ``result``, grouped by ``key(cs, day)``,
    only for days in ``start``..``end`` (Gregorian, inclusive; None = the
    whole result) and class subjects ``where(cs)`` accepts.
    """

    groups = defaultdict(Breakdown)
    class_subjects = result.class_subjects

    def accepted(day, cs):
        if start is not None and day < start:
            return False
        if end is not None and day > end:
            return False
        return where is None or where(cs)

    for outcome in result.outcomes:
        cs = class_subjects[outcome.class_subject_id]
        if accepted(outcome.date, cs):
            groups[key(cs, outcome.date)].add_outcome(outcome)
    for row in result.sessions:
        cs = class_subjects[row.class_subject_id]
        if accepted(row.date, cs):
            groups[key(cs, row.date)].add_session(row)
    return dict(groups)


def total(result, **kwargs):
    """The ``Breakdown`` of everything :func:`breakdowns` would keep."""

    return breakdowns(result, by_school, **kwargs).get(None, Breakdown())
