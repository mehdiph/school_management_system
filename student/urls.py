from django.urls import path
from . import views

app_name = 'student'

urlpatterns = [
    path('dashboard/', views.student_dashboard, name='dashboard'),
    path('sessions/', views.sessions_list, name='sessions'),
    path('api/sessions/<slug:subject>', views.session_list_json, name='session_list_json')
]