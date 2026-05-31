from django.contrib import admin
from .models import StudentProfile

# Register your models here.

@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['get_full_name', 'school_class', 'enrollment_date', 'status']


    def get_full_name(self, obj):
        return f"{obj.user.get_full_name()}"
    get_full_name.short_description = 'نام و نام خانوادگی'