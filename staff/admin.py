from django.contrib import admin
from .models import Staff, TeacherProfile

# Register your models here.

@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ['user', 'personnel_code', 'national_code', 'emergency_phone']

@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ['staff', 'education', 'teaching_experience']