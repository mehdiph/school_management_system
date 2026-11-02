from django.urls import path

from . import views

app_name = 'online_classes'

urlpatterns = [
    path('online/', views.online_page, name='online'),
    path('announcements/<int:pk>/dismiss/', views.dismiss_announcement, name='dismiss_announcement'),
]
