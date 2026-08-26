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