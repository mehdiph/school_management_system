from django.urls import path
from .views import ReportOptionsView, ReportsView

app_name = 'report'

urlpatterns = [
    path('all/', ReportsView.as_view(), name='reports_page'),
    path('all/options/', ReportOptionsView.as_view(), name='report_options'),
]
