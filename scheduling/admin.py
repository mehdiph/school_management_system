from django.contrib import admin

from core.admin import BranchScopedAdminMixin

from .models.class_schedule import ClassSchedule
from .models.bell import Bell

# Register your models here.
@admin.register(ClassSchedule)
class ClassScheduleAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    branch_lookup = "class_subject__school_class__branch"

    related_branch_lookups = {
        "class_subject": "school_class__branch",
    }

    list_display = ('class_subject', 'day_of_week', 'week_type', 'bell')
    list_filter = ('day_of_week', 'week_type')
    search_fields = ('class_subject__school_class__section', 'class_subject__subject__name')
    # ordering = ('bell')

@admin.register(Bell)
class BellAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_time', 'end_time')