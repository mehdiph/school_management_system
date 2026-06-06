from django.urls import path
from . import views

app_name = 'student'

urlpatterns = [
    path('dashboard/', views.student_dashboard, name='dashboard'),
    path('sessions/<slug:subject>', views.sessions_list, name='sessions')
]