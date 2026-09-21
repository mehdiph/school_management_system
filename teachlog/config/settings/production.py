"""
Production settings.

Selected by setting DJANGO_SETTINGS_MODULE=teachlog.config.settings.production
in the environment (this is what the Docker Compose deployment, prepared in a
later phase, is expected to do).

Fails loudly at startup if required environment variables are missing,
rather than silently falling back to insecure development defaults.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, ALLOWED_HOSTS, DATABASES

DEBUG = False

if not SECRET_KEY or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured(
        'SECRET_KEY environment variable must be set to a unique, secret '
        'value in production.'
    )

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        'ALLOWED_HOSTS environment variable must be set in production '
        '(comma-separated list of hostnames).'
    )

if DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql':
    raise ImproperlyConfigured(
        'Production requires PostgreSQL. Set POSTGRES_DB, POSTGRES_USER, '
        'POSTGRES_PASSWORD, POSTGRES_HOST and POSTGRES_PORT environment '
        'variables.'
    )

# Security settings that depend on HTTPS being terminated in front of the
# app (Nginx + SSL, configured in a later deployment phase). Kept opt-in via
# env var so production can still be reached over plain HTTP until SSL is
# actually set up, without silently locking users out with secure-only
# cookies or a redirect loop.
SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False') == 'True'
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT

SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '0'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0

# Safe to enable unconditionally, independent of SSL status.
SECURE_CONTENT_TYPE_NOSNIFF = True
