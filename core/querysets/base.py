from django.db import models


class BaseQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)
    
    def inactive(self):
        return self.filter(is_active=False)
    
class BranchQuerySet(BaseQuerySet):
    def for_branch(self, branch):
        return self.filter(branch=branch)