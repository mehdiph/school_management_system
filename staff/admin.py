from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from core.admin import BranchScopedAdminMixin, EffectiveBranchesMixin
from core.services import access

from .models import BranchAccess, Staff, TeacherAssignment, TeacherProfile


class TeacherAssignmentInline(admin.TabularInline):
    """
    Assigning a teacher to a branch is a single step: it happens here,
    on the teacher's own page. No separate ``BranchAccess`` row is
    needed -- access follows the assignment (see
    ``core.services.access``).
    """

    model = TeacherAssignment
    extra = 1

    fields = (
        "branch",
        "academic_year",
        "hire_date",
        "end_date",
        "status",
    )

    autocomplete_fields = ("branch",)

    verbose_name = "انتساب به شعبه"
    verbose_name_plural = "انتساب به شعبه‌ها (دسترسی به شعبه از همین‌جا داده می‌شود)"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "branch" and not request.user.is_superuser:
            kwargs["queryset"] = access.get_accessible_branches(
                request.user, request=request
            )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class BranchAccessInline(admin.TabularInline):
    model = BranchAccess
    extra = 0

    fields = ("branch", "is_default")
    autocomplete_fields = ("branch",)

    verbose_name = "دسترسی مستقیم به شعبه"
    verbose_name_plural = "دسترسی‌های مستقیم به شعبه (اضافه بر تدریس)"

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "branch" and not request.user.is_superuser:
            kwargs["queryset"] = access.get_accessible_branches(
                request.user, request=request
            )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Staff)
class StaffAdmin(EffectiveBranchesMixin, admin.ModelAdmin):
    list_display = [
        'user',
        'personnel_code',
        'national_code',
        'emergency_phone',
    ]

    search_fields = [
        'user__first_name',
        'user__last_name',
        'user__username',
        'personnel_code',
        'national_code',
    ]

    list_select_related = ['user']

    readonly_fields = ['effective_branches']

    inlines = [BranchAccessInline]

    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('user', 'personnel_code', 'national_code', 'gender')
        }),
        ('اطلاعات تماس و استخدام', {
            'fields': ('birth_date', 'hire_date', 'address', 'emergency_phone')
        }),
        ('دسترسی', {
            'fields': ('effective_branches',),
            'description': (
                "شعبه‌های مؤثر از مجموع دسترسی‌های مستقیم، انتساب‌های فعال "
                "تدریس در سال تحصیلی جاری و پروفایل پشتیبانی محاسبه می‌شود."
            ),
        }),
        ('وضعیت', {
            'fields': ('is_active',)
        }),
    )

    def get_user_for_branch_access(self, obj):
        return obj.user


@admin.register(TeacherProfile)
class TeacherProfileAdmin(EffectiveBranchesMixin, admin.ModelAdmin):
    list_display = [
        'staff',
        'education',
        'teaching_experience',
    ]

    search_fields = [
        'staff__user__first_name',
        'staff__user__last_name',
        'staff__personnel_code',
    ]

    list_select_related = ['staff', 'staff__user']

    autocomplete_fields = ['staff']

    readonly_fields = ['effective_branches']

    inlines = [TeacherAssignmentInline]

    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('staff', 'education', 'field_of_study', 'teaching_experience')
        }),
        ('دسترسی', {
            'fields': ('effective_branches',),
            'description': (
                "معلم به شعبه‌ی هر انتساب فعال خود در سال تحصیلی جاری "
                "دسترسی دارد؛ ثبت جداگانه‌ی «دسترسی به شعبه» لازم نیست."
            ),
        }),
    )

    def get_user_for_branch_access(self, obj):
        return obj.staff.user


@admin.register(TeacherAssignment)
class TeacherAssignmentAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    branch_lookup = "branch"

    related_branch_lookups = {
        "branch": "",
    }

    list_display = [
        'teacher',
        'teacher_link',
        'branch',
        'academic_year',
        'hire_date',
        'end_date',
        'status',
        'grants_access',
    ]

    list_filter = ['status', 'branch', 'academic_year']

    search_fields = [
        'teacher__staff__user__first_name',
        'teacher__staff__user__last_name',
        'teacher__staff__personnel_code',
    ]

    list_select_related = [
        'teacher',
        'teacher__staff',
        'teacher__staff__user',
        'branch',
        'academic_year',
    ]

    autocomplete_fields = ['teacher', 'branch']

    @admin.display(description="پروفایل معلم")
    def teacher_link(self, obj):
        url = reverse(
            "admin:staff_teacherprofile_change",
            args=[obj.teacher_id],
        )

        return format_html('<a href="{}">مشاهده / انتساب‌ها</a>', url)

    @admin.display(description="دسترسی به شعبه", boolean=True)
    def grants_access(self, obj):
        """
        Whether this row currently grants its teacher access to its
        branch -- the same "active assignment" rule the access service
        applies, evaluated in Python so the list page stays at one
        query (``academic_year`` is already select_related).
        """

        if obj.status != TeacherAssignment.AssignmentStatus.ACTIVE:
            return False

        if not obj.academic_year.is_current:
            return False

        return obj.end_date is None or obj.end_date >= access.today_jalali()


@admin.register(BranchAccess)
class BranchAccessesAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    branch_lookup = "branch"

    related_branch_lookups = {
        "branch": "",
    }

    list_display = ['staff', 'branch', 'is_default']
    list_filter = ['branch', 'is_default']

    search_fields = [
        'staff__user__first_name',
        'staff__user__last_name',
        'staff__personnel_code',
    ]

    list_select_related = ['staff', 'staff__user', 'branch']

    autocomplete_fields = ['staff', 'branch']

    fieldsets = (
        (None, {
            'fields': ('staff', 'branch', 'is_default'),
            'description': (
                "این جدول فقط برای دسترسی «مستقیم و اضافی» است — معمولاً "
                "برای پرسنل غیرمدرس (حسابدار، انفورماتیک، خدمات و ...) یا "
                "برای دادن دسترسی اضافه به یک معلم. "
                "معلمان به‌صورت خودکار به شعبه‌ی انتساب‌های فعال خود در سال "
                "تحصیلی جاری دسترسی دارند و نیازی به ثبت رکورد در این "
                "جدول ندارند."
            ),
        }),
    )
