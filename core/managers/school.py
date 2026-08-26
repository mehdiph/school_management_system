from django.db import models
from core.querysets.school import ClassSubjectQuerySet, SchoolClassQuerySet


class ClassSubjectManager(models.Manager.from_queryset(ClassSubjectQuerySet)):
    pass

class SchoolClassManager(models.Manager.from_queryset(SchoolClassQuerySet)):
    pass