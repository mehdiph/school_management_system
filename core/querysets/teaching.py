from .base import BaseQuerySet

#: SchoolSession.Status.HOLIDAY (not imported: the model imports this module).
HOLIDAY_STATUS = "HL"


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
    
class TeacherAssignmentQuerySet(BaseQuerySet):
    def for_branch(self, branch):
        return self.filter(branch=branch)
