from django.contrib import admin
from .models import ClassSchedule

# Register your models here.
@admin.register(ClassSchedule)
class ClassScheduleAdmin(admin.ModelAdmin):
    list_display = ('class_room', 'day_of_week', 'week_type', 'start_time', 'end_time')
    list_filter = ('day_of_week', 'week_type')
    search_fields = ('class_room__school_class__section', 'class_room__subject__name')
    ordering = ('day_of_week', 'start_time')