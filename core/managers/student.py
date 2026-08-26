from django.db import models
from core.querysets.student import StudentEnrollmentQuerySet

class StudentEnrollmentManager(models.Manager.from_queryset(StudentEnrollmentQuerySet)):
    pass

