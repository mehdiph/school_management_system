from django.urls import path
from . import views

app_name = 'attendance'

urlpatterns = [
    path('<int:session_id>/', views.manage_attendance, name='attendance_form')
]