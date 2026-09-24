from django.contrib import admin
from django_jalali.admin.filters import JDateFieldListFilter
import django_jalali.admin as jadmin

from core.admin import BranchScopedAdminMixin

from .models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    branch_lookup = "session__class_subject__school_class__branch"

    related_branch_lookups = {
        "session": "class_subject__school_class__branch",
        "student_enrollment": "school_class__branch",
    }

    list_display = (
        "get_student_name",
        "session",
        "status",
        "created_at",
    )

    list_filter = (
        "status",
        ("session__date", JDateFieldListFilter),
        "session__class_subject__school_class",
    )

    search_fields = (
        "student_enrollment__student__user__first_name",
        "student_enrollment__student__user__last_name",
        "session__class_subject__subject__name",
    )

    list_editable = ("status",)

    autocomplete_fields = (
        "session",
        "student_enrollment",
    )

    list_select_related = (
        "session",
        "session__class_subject",
        "student_enrollment",
        "student_enrollment__student",
        "student_enrollment__student__user",
    )

    ordering = (
        "-session__date",
        "student_enrollment__student__user__last_name",
    )

    fieldsets = (
        ("اطلاعات اصلی", {
            "fields": ("session", "student_enrollment", "status")
        }),
        ("توضیحات", {
            "fields": ("description",)
        }),
    )

    def get_student_name(self, obj):
        return obj.student_enrollment.student.user.get_full_name()

    get_student_name.short_description = "دانش‌آموز"
    get_student_name.admin_order_field = (
        "student_enrollment__student__user__last_name"
    )
