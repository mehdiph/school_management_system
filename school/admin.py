from django.contrib import admin
from django_jalali.admin.filters import JDateFieldListFilter
import django_jalali.admin as jadmin
from .models import AcademicYear, Grade, Subject, SchoolClass, ClassSubject


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
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ('get_class_name', 'year', 'grade', 'section', 'is_active', 'created_at')
    list_filter = ('year', 'grade', 'is_active')
    search_fields = ('section', 'grade__name', 'year__title')
    list_editable = ('is_active',)
    ordering = ('-created_at',)
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('year', 'grade', 'section')
        }),
        ('وضعیت', {
            'fields': ('is_active',)
        }),
    )
    
    def get_class_name(self, obj):
        return f"{obj.grade.name} - {obj.section}"
    get_class_name.short_description = 'کلاس'


@admin.register(ClassSubject)
class ClassSubjectAdmin(admin.ModelAdmin):
    list_display = ('get_class_subject_name', 'school_class', 'subject', 'teacher', 'start_date', 'end_date', 'is_active')
    list_filter = ('subject', 'is_active', 'school_class__grade')
    search_fields = ('school_class__section', 'subject__name', 'teacher__username', 'teacher__first_name', 'teacher__last_name')
    list_editable = ('is_active',)
    ordering = ('-created_at',)
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('school_class', 'subject', 'teacher')
        }),
        ('دوره تدریس', {
            'fields': (('start_date', 'end_date'),)
        }),
        ('وضعیت', {
            'fields': ('is_active',)
        }),
    )
    
    def get_class_subject_name(self, obj):
        return f"{obj.school_class.grade.name} {obj.school_class.section} - {obj.subject.name}"
    get_class_subject_name.short_description = 'کلاس و درس'


