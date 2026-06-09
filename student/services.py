from scheduling.models.class_schedule import ClassSchedule
from scheduling.utils import get_today_schedule_day

def get_classes_for_day(school_class, targed_date):
    classes = ClassSchedule.objects.filter(
        class_room__school_class=school_class,
        day_of_week=get_today_schedule_day(targed_date)
    ).select_related(
        'class_room',
        'class_room__subject',
        'class_room__teacher'
    ).order_by(
        'start_time'
    )

    return classes