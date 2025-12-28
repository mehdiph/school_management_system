from django.urls import path
from .views import ReportsView

app_name = 'report'

urlpatterns = [
    path('all/', ReportsView.as_view(), name='reports_page'),
]
