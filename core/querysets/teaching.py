from .base import BaseQuerySet

class SchoolSessionQuerySet(BaseQuerySet):
    def for_branch(self, branch):
        return self.filter(
            class_subject__school_class__branch=branch
        )
    

class AttendanceQuerySet(BaseQuerySet):
    def for_branch(self, branch):
        return self.filter(
            student_enrollment__school_class__branch=branch
        )
    
class TeacherAssignmentQuerySet(BaseQuerySet):
    def for_branch(self, branch):
        return self.filter(branch=branch)