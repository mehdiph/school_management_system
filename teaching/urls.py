from django.urls import path
from . import views

app_name = 'teaching'

urlpatterns = [
    path('session/', views.school_session_form, name='session_form'),
    path('sessions/', views.session_list, name='session_list'),
]