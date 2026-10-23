from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    # archived per-session attendance (read-only)
    path('<int:session_id>/', views.session_attendance, name='session_attendance'),
    # daily attendance of a class: ?date=<Jalali>, default today
    path('daily/<int:class_id>/', views.daily_sheet, name='daily_sheet'),
]
