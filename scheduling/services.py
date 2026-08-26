# scheduling/services.py

from .models.class_schedule import ClassSchedule
from .models.bell import Bell


def get_class_weekly_schedule(school_class):
    bells = (
        Bell.objects
        .all()
        .order_by('start_time')
    )

    schedules = (
        ClassSchedule.objects
        .filter(
            class_subject__school_class=school_class
        )
        .select_related(
            'class_subject',
            'class_subject__subject',
            'class_subject__teacher_assignment__teacher',
            'bell',
        )
    )

    # ساخت lookup برای دسترسی سریع به برنامه هر روز و هر زنگ
    schedule_map = {
        (schedule.day_of_week, schedule.bell_id): schedule
        for schedule in schedules
    }

    week_schedule = {
        0: [],
        1: [],
        2: [],
        3: [],
        4: [],
        5: [],
    }

    for day in week_schedule:
        for bell in bells:
            schedule = schedule_map.get((day, bell.id))

            week_schedule[day].append({
                'bell': bell,
                'schedule': schedule,
            })

    return week_schedule