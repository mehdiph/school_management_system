from django.db.models import Count, Q

from analytics.definitions import ABSENT, DELIVERED_STATUSES, LATE, PRESENT, attendance_rate, rounded
from analytics.definitions import HOLIDAY as HOLIDAY_STATUS

from .base import BaseQuerySet


class SchoolSessionQuerySet(BaseQuerySet):
    def for_branch(self, branch):
        return self.filter(
            class_subject__school_class__branch=branch
        )

    def counted(self):
        """
        Sessions that count: everything except the calendar's holiday
        rows. Every session count, number and "last session" must start
        here -- ``status != HL`` is the single exclusion rule.
        """

        return self.exclude(status=HOLIDAY_STATUS)

    def holidays(self):
        """Sessions the academic calendar cancelled (no number, never counted)."""

        return self.filter(status=HOLIDAY_STATUS)
    

class AttendanceQuerySet(BaseQuerySet):
    def for_branch(self, branch):
        return self.filter(
            student_enrollment__school_class__branch=branch
        )

    def delivered(self):
        """
        Records of held or compensatory sessions: the only ones an
        attendance rate is computed over (``analytics.definitions``).
        """

        return self.filter(session__status__in=DELIVERED_STATUSES)

    def status_counts(self):
        """
        ``total`` / ``present`` / ``absent`` / ``late`` records (one
        query) and ``rate``: the attendance rate of
        ``analytics.definitions.attendance_rate`` -- late counts as
        attended -- rounded, or None without records.
        """

        counts = self.aggregate(
            total=Count("id"),
            present=Count("id", filter=Q(status=PRESENT)),
            absent=Count("id", filter=Q(status=ABSENT)),
            late=Count("id", filter=Q(status=LATE)),
        )
        counts["rate"] = rounded(attendance_rate(counts["total"], counts["absent"]))
        return counts
    
class TeacherAssignmentQuerySet(BaseQuerySet):
    def for_branch(self, branch):
        return self.filter(branch=branch)
