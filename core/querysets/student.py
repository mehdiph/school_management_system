from django.db.models import Subquery

from school.models.academic_year import AcademicYear

from .base import BaseQuerySet


class StudentEnrollmentQuerySet(BaseQuerySet):
    def active(self):
        return self.filter(
            status="active"
        )

    def for_branch(self, branch):
        return self.filter(
            school_class__branch=branch
        )

    def current(self):
        """
        Enrolments that make someone a student of the school right now:
        active, in the current year (the newest one if two are flagged, as
        ``core.selectors.current_academic_year``), in an active class of an
        active branch. A student has at most one, because a student has one
        row per year.
        """

        return self.active().filter(
            academic_year=Subquery(
                AcademicYear.objects.filter(is_current=True).order_by("-start_date", "-pk").values("pk")[:1]
            ),
            school_class__is_active=True,
            school_class__branch__is_active=True,
        )
