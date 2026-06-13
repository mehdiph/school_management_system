from django.contrib import admin
from .models.class_schedule import ClassSchedule
from .models.bell import Bell

# Register your models here.
@admin.register(ClassSchedule)
class ClassScheduleAdmin(admin.ModelAdmin):
    list_display = ('class_room', 'day_of_week', 'week_type', 'bell')
    list_filter = ('day_of_week', 'week_type')
    search_fields = ('class_room__school_class__section', 'class_room__subject__name')
    # ordering = ('bell')

@admin.register(Bell)
class BellAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_time', 'end_time')