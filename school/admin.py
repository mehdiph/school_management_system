from django.contrib import admin
from django_jalali.admin.filters import JDateFieldListFilter
import django_jalali.admin as jadmin

from core.admin import BranchScopedAdminMixin
from staff.models import TeacherAssignment

from .models import AcademicYear, Grade, Subject, SchoolClass, ClassSubject, Branch


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_date', 'end_date', 'is_current', 'is_active')
    list_filter = ('is_current', 'is_active')
    search_fields = ('title',)
    list_editable = ('is_current', 'is_active')
    ordering = ('-start_date',)
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('title', ('start_date', 'end_date'))
        }),
        ('وضعیت', {
            'fields': ('is_current', 'is_active')
        }),
    )

@admin.register(Branch)
class BranchAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    # A Branch *is* the branch, so the scoping lookup is the row itself.
    branch_lookup = "id"

    list_display = ['name', 'address', 'phone_number', 'is_active']
    search_fields = ['name', 'code']

@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('name', 'level', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    list_editable = ('is_active',)
    ordering = ('level',)
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('name', 'level')
        }),
        ('وضعیت', {
            'fields': ('is_active',)
        }),
    )


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active',)
    ordering = ('name',)


@admin.register(SchoolClass)
class SchoolClassAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    branch_lookup = "branch"

    related_branch_lookups = {
        "branch": "",
    }

    search_fields = ('section', 'grade__name', 'year__title')

    list_display = ('get_class_name', 'year', 'grade', 'section', 'branch', 'created_at')
    list_filter = ('year', 'grade', 'is_active', 'branch')
    search_fields = ('section', 'grade__name', 'year__title')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('year', 'grade', 'branch', 'section')
        }),
        ('وضعیت', {
            'fields': ('is_active',)
        }),
    )
    
    def get_class_name(self, obj):
        return f"{obj.grade.name} - {obj.section}"
    get_class_name.short_description = 'کلاس'


@admin.register(ClassSubject)
class ClassSubjectAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    branch_lookup = "school_class__branch"

    related_branch_lookups = {
        "school_class": "branch",
        "teacher_assignment": "branch",
    }

    list_display = ('get_class_subject_name', 'school_class', 'subject', 'get_teacher', 'start_date', 'end_date', 'is_active')
    list_filter = ('subject', 'is_active', 'school_class__grade', 'school_class__branch')
    search_fields = ('school_class__section', 'subject__name')

    list_select_related = (
        'school_class',
        'school_class__grade',
        'school_class__branch',
        'subject',
        'teacher_assignment',
        'teacher_assignment__teacher',
        'teacher_assignment__teacher__staff',
        'teacher_assignment__teacher__staff__user',
    )
    list_editable = ('is_active',)
    ordering = ('-created_at',)
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('school_class', 'subject', 'teacher_assignment')
        }),
        ('دوره تدریس', {
            'fields': (('start_date', 'end_date'),)
        }),
        ('وضعیت', {
            'fields': ('is_active',)
        }),
    )
    def get_form(self, request, obj=None, **kwargs):
        # formfield_for_foreignkey() gets no obj, but the teacher
        # dropdown has to know which class is being edited -- stash it
        # on the request (per-request, never global) for the callback
        # below to pick up.
        request._class_subject_obj = obj

        return super().get_form(request, obj=obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Narrows the teacher-assignment dropdown so a mismatching
        assignment can't be picked in the first place (``ClassSubject.
        clean()`` is still what guarantees it -- this only keeps the
        admin from offering choices that would be rejected).

        On the change form the class is known, so the list is exactly
        the assignments of that class's branch *and* academic year. On
        the add form there is no class yet, so it falls back to the
        current year within the branches the user may see.
        """

        if db_field.name == "teacher_assignment":
            queryset = kwargs.get("queryset")

            if queryset is None:
                queryset = TeacherAssignment.objects.all()

            obj = getattr(request, "_class_subject_obj", None)

            if obj is not None and obj.school_class_id:
                queryset = queryset.filter(
                    branch_id=obj.school_class.branch_id,
                    academic_year_id=obj.school_class.year_id,
                )
            else:
                queryset = queryset.filter(academic_year__is_current=True)

            kwargs["queryset"] = queryset.select_related(
                "teacher__staff__user", "branch", "academic_year"
            )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_teacher(self, obj):
        if obj:
            return obj.teacher_assignment.teacher.staff.user.get_full_name()

        return "-"


    get_teacher.short_description = "معلم"
    def get_class_subject_name(self, obj):
        return f"{obj.school_class.grade.name} {obj.school_class.section} - {obj.subject.name}"
    get_class_subject_name.short_description = 'کلاس و درس'


