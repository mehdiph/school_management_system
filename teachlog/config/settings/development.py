"""
Development settings.

Used automatically by manage.py / wsgi.py / asgi.py unless
DJANGO_SETTINGS_MODULE is overridden (e.g. by Docker Compose in production).
"""

from .base import *  # noqa: F401,F403

DEBUG = True

# Keep the project runnable out of the box with no .env / env vars at all.
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']
