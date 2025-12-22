from django.db import models
from school.models import SchoolClass

# Create your models here.

class SchoolSession(models.Model):
    class Status(models.TextChoices):
        COMPENSATORY = 'JB', 'جبرانی'
        CANCELED = 'CD', 'کنسل شده'
        HELD = 'HD', 'برگزار شده'

    school_class = models.ForeignKey(SchoolClass, on_delete=models.DO_NOTHING)
    date = models.DateTimeField(auto_now_add=True)
    session_number = models.IntegerField()
    status = models.CharField(
        max_length=2,
        choices=Status,
        default=Status.HELD
    )
    created_at = models.DateTimeField(auto_now_add=True)

class SessionContent(models.Model):
    session = models.OneToOneField(SchoolSession, on_delete=models.DO_NOTHING)
    title = models.CharField(max_length=255)
    content = models.TextField()
    activity = models.TextField()
    homework = models.TextField()
    notes = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)