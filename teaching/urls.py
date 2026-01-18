from django.urls import path
from . import views

app_name = 'teaching'

urlpatterns = [
    path('session/<int:class_id>', views.school_session_form, name='session_form'),
    path('sessions/<int:class_id>', views.session_list, name='session_list'),
    path('update_session/<int:session_id>/', views.update_session, name='update_session'),
]