from django.urls import path
from . import views


app_name = 'website'

urlpatterns = [
    path('', views.website, name='website'),
    path('contact/', views.contact, name='contact'),
    path('about/', views.about, name='about'),
    path('teachers/', views.teachers, name='teachers'),
    path('robots.txt', views.robots_txt, name='robots'),
]
