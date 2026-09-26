from django.urls import path
from . import views

app_name = 'scheduling'

urlpatterns = [
    path('weekly-schedule/', views.weekly_schedule, name='weekly-schedule'),
    path('weekly-schedule/pdf/', views.weekly_schedule_pdf, name='weekly-schedule-pdf'),
]
