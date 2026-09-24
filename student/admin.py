from django.contrib import admin

from core.admin import BranchScopedAdminMixin

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
class StudentEnrollmentAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    branch_lookup = "school_class__branch"

    related_branch_lookups = {
        "school_class": "branch",
    }

    list_display = ['student', 'school_class', 'branch', 'status', 'enrollment_date', 'academic_year']
    list_filter = ['status', 'school_class__branch', 'academic_year']
    search_fields = [
        'student__user__first_name',
        'student__user__last_name',
        'student__student_code',
    ]

    list_select_related = [
        'student',
        'student__user',
        'school_class',
        'school_class__branch',
        'academic_year',
    ]

    @admin.display(description='شعبه')
    def branch(self, obj):
        return obj.school_class.branch
