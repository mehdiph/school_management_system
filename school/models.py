from django.db import models
from django.contrib.auth.models import User

# Create your models here.

class AcademicYear(models.Model):
    title = models.CharField(max_length=50)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)

class Grade(models.Model):
    name = models.CharField(max_length=255)
    level = models.IntegerField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

class Subject(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    


class SchoolClass(models.Model):
    year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE)
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE)
    Subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    section = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    
class ClassSubject(models.Model):
    school_class = models.ForeignKey(SchoolClass, on_delete=models.DO_NOTHING)
    subject = models.ForeignKey(Subject, on_delete=models.DO_NOTHING)
    teacher = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    is_active = models.BooleanField(default=True)
