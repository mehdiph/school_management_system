from .base import BaseQuerySet

class SchoolClassQuerySet(BaseQuerySet):

    def for_branch(self, branch):
        return self.filter(branch=branch)
    
class ClassSubjectQuerySet(BaseQuerySet):
    def for_branch(self, branch):
        return self.filter(
            school_class__branch=branch
        )
    
    def for_teacher(self, teacher):
        return self.filter(
            teacher_assignment__teacher=teacher
        )