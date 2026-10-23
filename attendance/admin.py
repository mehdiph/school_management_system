from django.contrib import admin
from django_jalali.admin.filters import JDateFieldListFilter
import django_jalali.admin as jadmin

from core.admin import BranchScopedAdminMixin

from .models import DailyAttendance, DailyAttendanceSheet, SessionAttendance


@admin.register(SessionAttendance)
class SessionAttendanceAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    """
    The archive of per-session attendance: view only. Nothing may be added,
    changed or deleted, here or anywhere in the app (daily attendance
    replaced it; see ``attendance.services``).
    """

    branch_lookup = "session__class_subject__school_class__branch"

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

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_student_name(self, obj):
        return obj.student_enrollment.student.user.get_full_name()

    get_student_name.short_description = "دانش‌آموز"
    get_student_name.admin_order_field = (
        "student_enrollment__student__user__last_name"
    )


class DailyAttendanceInline(admin.TabularInline):
    model = DailyAttendance
    extra = 0
    fields = ("student_enrollment", "status", "description", "updated_by", "updated_at")
    readonly_fields = ("updated_by", "updated_at")
    autocomplete_fields = ("student_enrollment",)


@admin.register(DailyAttendanceSheet)
class DailyAttendanceSheetAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    """
    Corrections to the supporters' daily sheets. The normal way to take
    attendance is the sheet page (``attendance:daily_sheet``), which lists
    every student of the class; a sheet added here has only the records
    added to it.
    """

    branch_lookup = "school_class__branch"

    related_branch_lookups = {
        "school_class": "branch",
    }

    inlines = (DailyAttendanceInline,)

    list_display = ("school_class", "date", "taken_by", "created_at")
    list_filter = (("date", JDateFieldListFilter), "school_class__branch", "school_class__grade")
    search_fields = ("school_class__section", "school_class__grade__name")
    list_select_related = ("school_class__grade", "school_class__branch", "taken_by")
    autocomplete_fields = ("school_class",)
    readonly_fields = ("taken_by", "created_at")
    fields = ("school_class", "date", "taken_by", "created_at")
    ordering = ("-date",)

    def get_readonly_fields(self, request, obj=None):
        # the class and day of an existing sheet never change
        if obj is not None:
            return ("school_class", "date", *self.readonly_fields)
        return self.readonly_fields

    def save_model(self, request, obj, form, change):
        if not change:
            obj.taken_by = request.user
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        records = formset.save(commit=False)
        for record in records:
            # a record changed after the sheet was taken
            if change or record.pk:
                record.updated_by = request.user
            record.save()
        for record in formset.deleted_objects:
            record.delete()
        formset.save_m2m()
