"""
URL configuration for teachlog project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import re

from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('website.urls')),
    path('teaching/', include('teaching.urls')),
    path('school/', include('school.urls')),
    path('report/', include('report.urls')),
    path('dashboard/', include('core.urls')),
    path('auth/', include('accounts.urls')),
    path('student/', include('student.urls')),
    path('scheduling/', include('scheduling.urls')),
    path('attendance/', include('attendance.urls')),
    path('supervisor/', include('supervisor.urls')),
]

# Serve user uploads (MEDIA_URL) from MEDIA_ROOT through Django.
#
# django.conf.urls.static.static() can't be used here: it returns an empty
# list whenever DEBUG is False, which is exactly the case we need to cover.
#
# FOR LOCAL / CONTAINER TESTING ONLY. Serving media through Django is slow
# and not hardened for untrusted files. In real production Nginx serves
# MEDIA_URL directly from the media volume and SERVE_MEDIA must stay False.
if settings.DEBUG or settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(
            r'^%s(?P<path>.*)$' % re.escape(settings.MEDIA_URL.lstrip('/')),
            serve,
            {'document_root': settings.MEDIA_ROOT},
        ),
    ]