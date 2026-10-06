"""
What one analytics computation looks at: an academic year, a date range,
optionally a branch, a grade or an explicit set of class subjects, and
the moment it is computed "as of".

Every metric only ever looks at dates up to today: the range is clamped
to the academic year and to ``as_of``'s date when the scope is built, so
no caller can ask about the future by accident.
"""

from dataclasses import dataclass, replace
from datetime import date, datetime, time

from django.utils import timezone

from academic_calendar.services import to_gregorian


def as_of_for(today=None):
    """
    The moment to compute metrics as of: now -- or, when the caller is
    about another day (a selector built for a fixed date, a test), the
    end of that day, which has then fully passed.
    """

    now = timezone.localtime()
    if today is None or today == now.date():
        return now
    return timezone.make_aware(
        datetime.combine(today, time.max), timezone.get_default_timezone()
    )


@dataclass(frozen=True)
class AnalyticsScope:
    """
    Build it with :meth:`build`, which clamps the range; ``start`` /
    ``end`` are Gregorian dates, both inclusive. ``start > end`` (a range
    entirely in the future or outside the year) is an empty scope.

    ``class_subject_ids`` restricts the scope to those class subjects
    (the supervisor's rows); None means every class subject of the year
    in the branch / grade.
    """

    year: object
    start: date
    end: date
    as_of: datetime
    branch: object = None
    grade: object = None
    class_subject_ids: frozenset = None

    @classmethod
    def build(cls, year, start=None, end=None, *, as_of=None, branch=None, grade=None,
              class_subjects=None):
        as_of = timezone.localtime(as_of) if as_of is not None else timezone.localtime()
        first, last = to_gregorian(year.start_date), to_gregorian(year.end_date)
        start = max(to_gregorian(start), first) if start else first
        end = min(to_gregorian(end) if end else last, last, as_of.date())
        ids = None
        if class_subjects is not None:
            ids = frozenset(getattr(cs, "pk", cs) for cs in class_subjects)
        return cls(year=year, start=start, end=end, as_of=as_of, branch=branch, grade=grade,
                   class_subject_ids=ids)

    @property
    def today(self):
        return self.as_of.date()

    @property
    def is_empty(self):
        return self.start > self.end

    def with_range(self, start, end):
        """The same scope over another range (clamped again)."""

        return type(self).build(
            self.year, start, end, as_of=self.as_of, branch=self.branch, grade=self.grade,
            class_subjects=self.class_subject_ids,
        )

    def without_branch(self):
        return replace(self, branch=None)

    def class_subject_filter(self, prefix=""):
        """
        The scope as ``ClassSubject`` lookups, prefixed for a related
        model (``"class_subject__"`` for sessions and timetable slots).
        """

        lookups = {f"{prefix}school_class__year": self.year}
        if self.branch is not None:
            lookups[f"{prefix}school_class__branch"] = self.branch
        if self.grade is not None:
            lookups[f"{prefix}school_class__grade"] = self.grade
        if self.class_subject_ids is not None:
            lookups[f"{prefix}pk__in"] = sorted(self.class_subject_ids)
        return lookups
