from django.urls import path

from . import views

app_name = "director"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("execution/", views.execution, name="execution"),
    path("attendance/", views.attendance, name="attendance"),
]
