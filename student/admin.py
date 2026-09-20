from django.contrib import admin
from .models.student_profile import StudentProfile
from .models.student_enrollment import StudentEnrollment

# Register your models here.

@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['get_full_name']


    def get_full_name(self, obj):
        return f"{obj.user.get_full_name()}"
    get_full_name.short_description = 'نام و نام خانوادگی'


@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'school_class', 'status', 'enrollment_date', 'academic_year']
    search_fields = [
        'student__user__first_name',
        'student__user__last_name',
        'student__student_code',
    ]
