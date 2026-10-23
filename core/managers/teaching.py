from django.db import models
from core.querysets.teaching import (
    AttendanceQuerySet,
    DailyAttendanceQuerySet,
    SchoolSessionQuerySet,
    TeacherAssignmentQuerySet,
)


class SchoolSessionManager(models.Manager.from_queryset(SchoolSessionQuerySet)):
    pass

class AttendanceManager(models.Manager.from_queryset(AttendanceQuerySet)):
    pass

class DailyAttendanceManager(models.Manager.from_queryset(DailyAttendanceQuerySet)):
    pass

class TeacherAssignmentManager(models.Manager.from_queryset(TeacherAssignmentQuerySet)):
    pass