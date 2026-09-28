from scheduling.models.class_schedule import ClassSchedule
from scheduling.utils import DateBeforeAcademicYearError, get_today_schedule_day, get_week_cycle

def get_classes_for_day(school_class, targed_date):
    try:
        week_type = get_week_cycle(targed_date, school_class.year)
    except DateBeforeAcademicYearError:
        # The academic year has not started yet: no classes that day.
        return ClassSchedule.objects.none()

    classes = ClassSchedule.objects.filter(
        class_subject__school_class=school_class,
        day_of_week=get_today_schedule_day(targed_date)
    ).for_week(
        week_type
    ).select_related(
        'class_subject',
        'class_subject__subject',
        'class_subject__teacher_assignment__teacher'
    ).order_by(
        'bell__start_time'
    )

    return classes
