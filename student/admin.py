from django.contrib import admin

from core.admin import BranchScopedAdminMixin
from core.services import access

from .models.student_profile import StudentProfile
from .models.student_enrollment import StudentEnrollment

# Register your models here.

@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['get_full_name']
    # For the student pickers of online events and announcements.
    search_fields = ['user__first_name', 'user__last_name', 'student_code', 'user__national_code']

    def get_full_name(self, obj):
        return f"{obj.user.get_full_name()}"
    get_full_name.short_description = 'نام و نام خانوادگی'

    def get_search_results(self, request, queryset, search_term):
        queryset, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        queryset = queryset.select_related('user')
        # A branch-scoped admin picking an audience only finds students of
        # their own branches; this admin's own pages stay as they were.
        if request.GET.get('app_label') == 'online_classes' and not request.user.is_superuser:
            allowed = access.get_accessible_branch_ids(request.user, request=request)
            queryset = queryset.filter(pk__in=(
                StudentEnrollment.objects.current()
                .filter(school_class__branch__in=allowed)
                .values('student_id')
            ))
        return queryset, may_have_duplicates


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
