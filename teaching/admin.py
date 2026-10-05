from django.contrib import admin
from django_jalali.admin.filters import JDateFieldListFilter

from core.admin import BranchScopedAdminMixin

from .models import SchoolSession, SessionContent


@admin.register(SchoolSession)
class SchoolSessionAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    branch_lookup = "class_subject__school_class__branch"

    related_branch_lookups = {
        "class_subject": "school_class__branch",
    }

    list_display = ('get_session_name', 'class_subject', 'date', 'bell', 'session_number', 'status', 'calendar_event', 'created_at')
    list_filter = (
        ('date', JDateFieldListFilter),
        'status',
        'is_auto_created',
        'bell',
        'class_subject__subject',
        'class_subject__school_class__grade'
    )
    search_fields = (
        'class_subject__subject__name',
        'class_subject__school_class__section',
        'class_subject__teacher_assignment__teacher__staff__user__first_name',
        'class_subject__teacher_assignment__teacher__staff__user__last_name',
        'session_number'
    )
    list_editable = ('status',)
    ordering = ('-date', '-session_number')
    date_hierarchy = 'date'
    # Holiday rows belong to the academic calendar: their event and the
    # auto-created flag are never edited by hand (SchoolSession.clean()
    # also refuses «تعطیل» without an event).
    readonly_fields = ('session_number', 'calendar_event', 'is_auto_created')
    list_select_related = ('class_subject__school_class__grade', 'class_subject__school_class__branch',
                           'class_subject__subject', 'class_subject__teacher_assignment__teacher__staff__user',
                           'bell', 'calendar_event')

    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('class_subject', 'date', 'bell', 'session_number')
        }),
        ('وضعیت', {
            'fields': ('status', 'calendar_event', 'is_auto_created')
        }),
    )
    
    def get_session_name(self, obj):
        number = 'تعطیل' if obj.is_holiday else f'جلسه {obj.session_number}'
        return f"{obj.class_subject.school_class} - {obj.class_subject.subject.name} - {number}"
    get_session_name.short_description = 'جلسه'


@admin.register(SessionContent)
class SessionContentAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    branch_lookup = "session__class_subject__school_class__branch"

    related_branch_lookups = {
        "session": "class_subject__school_class__branch",
    }

    list_display = ('get_content_title', 'session', 'title', 'created_at')
    list_filter = (
        ('created_at', JDateFieldListFilter),
        'session__status',
        'session__class_subject__subject'
    )
    search_fields = (
        'title',
        'content',
        'session__class_subject__subject__name',
        'session__class_subject__school_class__section'
    )
    ordering = ('-created_at',)
    
    fieldsets = (
        ('اطلاعات جلسه', {
            'fields': ('session', 'title')
        }),
        ('محتوای درسی', {
            'fields': ('content', 'activity')
        }),
        ('تکلیف و یادداشت', {
            'fields': ('homework', 'notes')
        }),
    )
    
    def get_content_title(self, obj):
        return f"{obj.session.class_subject.school_class} - {obj.title}"
    get_content_title.short_description = 'محتوا'
