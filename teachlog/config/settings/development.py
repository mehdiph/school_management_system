"""
Development settings.

Used automatically by manage.py / wsgi.py / asgi.py unless
DJANGO_SETTINGS_MODULE is overridden (e.g. by Docker Compose in production).
"""

from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS

DEBUG = True

# Dev-only tooling: shell_plus/runserver_plus (django-extensions) and the ERD
# generator management command. Not needed, and not installed, in production.
INSTALLED_APPS = INSTALLED_APPS + [
    'django_extensions',
    'django_erd_generator',
]

# Keep the project runnable out of the box with no .env / env vars at all.
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']
