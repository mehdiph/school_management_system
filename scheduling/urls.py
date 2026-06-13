from django.urls import path
from . import views

app_name = 'scheduling'

urlpatterns = [
    path('weekly-schedule/', views.weekly_schedule, name='weekly-schedule')
]