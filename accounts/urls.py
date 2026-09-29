from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_form, name='login'),
    path('logout/', views.auth_logout, name='logout'),
    path('password/change/', views.password_change, name='password_change'),
    path('profile/', views.profile, name='profile'),
]