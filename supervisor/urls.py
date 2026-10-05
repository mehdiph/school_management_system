from django.urls import path

from . import views

app_name = "supervisor"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("attention/", views.attention_list, name="attention_list"),
    path("attendance/", views.attendance, name="attendance"),
    path("sessions/", views.training_sessions, name="sessions"),
    path(
        "sessions/class-subject/<int:pk>/timeline/",
        views.class_subject_timeline,
        name="class_subject_timeline",
    ),
    path("sessions/<int:pk>/", views.session_detail, name="session_detail"),
    path("teachers/", views.supervised_teachers, name="teachers"),
]
