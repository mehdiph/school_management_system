from django.contrib import admin
from django_jalali.admin.filters import JDateFieldListFilter
import django_jalali.admin as jadmin
from .models import SchoolSession, SessionContent


@admin.register(SchoolSession)
class SchoolSessionAdmin(admin.ModelAdmin):
    list_display = ('get_session_name', 'class_subject', 'date', 'session_number', 'status', 'created_at')
    list_filter = (
        ('date', JDateFieldListFilter),
        'status',
        'class_subject__subject',
        'class_subject__school_class__grade'
    )
    search_fields = (
        'class_subject__subject__name',
        'class_subject__school_class__section',
        'class_subject__teacher__username',
        'class_subject__teacher__first_name',
        'class_subject__teacher__last_name',
        'session_number'
    )
    list_editable = ('status',)
    ordering = ('-date', '-session_number')
    date_hierarchy = 'date'
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('class_subject', 'date', 'session_number')
        }),
        ('وضعیت', {
            'fields': ('status',)
        }),
    )
    
    def get_session_name(self, obj):
        return f"{obj.class_subject.school_class} - {obj.class_subject.subject.name} - جلسه {obj.session_number}"
    get_session_name.short_description = 'جلسه'


@admin.register(SessionContent)
class SessionContentAdmin(admin.ModelAdmin):
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
