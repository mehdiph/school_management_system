from django.shortcuts import render
from .services import get_class_weekly_schedule
from .models.bell import Bell

# Create your views here.

def weekly_schedule(request):
    student = request.user.student_profile
    school_class = student.school_class

    weekly_schedule = get_class_weekly_schedule(school_class)
    bells = Bell.objects.all()

    context = {
        'weekly_schedule': weekly_schedule,
        'bells': bells
    }

    return render(request, 'scheduling/weekly-schedule.html', context)