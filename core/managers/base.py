from django.db import models
from core.querysets.base import BaseQuerySet, BranchQuerySet


class BranchManager(models.Manager.from_queryset(BranchQuerySet)):
    pass