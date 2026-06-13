# scheduling/services.py

from .models.class_schedule import ClassSchedule


def get_class_weekly_schedule(school_class):
    schedules = (
        ClassSchedule.objects
        .filter(
            class_room__school_class=school_class
        )
        .select_related(
            'class_room',
            'class_room__subject',
            'class_room__teacher'
        )
        .order_by(
            'day_of_week',
            'bell__start_time'
        )
    )

    week_schedule = {
        0: [],
        1: [],
        2: [],
        3: [],
        4: [],
        5: [],
    }

    for schedule in schedules:
        week_schedule[schedule.day_of_week].append(schedule)

    return week_schedule