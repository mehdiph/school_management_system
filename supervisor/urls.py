from django.urls import path

from . import views

app_name = "supervisor"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("attention/", views.attention_list, name="attention_list"),
    path("attendance/", views.attendance, name="attendance"),
]
