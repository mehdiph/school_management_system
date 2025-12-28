from django.urls import path
from . import views

app_name = 'school'

urlpatterns = [
    path('class/create/', views.class_create, name='class_create'),
    path('class/<int:pk>/update/', views.class_update, name='class_update'),
    path('classes/', views.class_list, name='class_list'),
]