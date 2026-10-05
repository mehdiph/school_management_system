from django.apps import AppConfig


class AcademicCalendarConfig(AppConfig):
    name = 'academic_calendar'
    verbose_name = 'تقویم آموزشی'

    def ready(self):
        # Re-syncs holiday sessions when the timetable changes.
        from . import signals  # noqa: F401
