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
from .base import SECRET_KEY, ALLOWED_HOSTS, DATABASES, MIDDLEWARE

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

# Static files.
#
# With DEBUG=False Django serves nothing under STATIC_URL, and there is no
# Nginx in front of the app yet, so CSS/JS/fonts would 404. WhiteNoise serves
# the collected STATIC_ROOT directory straight from Gunicorn, which makes the
# site fully testable before Nginx exists. It stays harmless afterwards:
# Nginx answers /static/ first, so those requests never reach Django.
#
# WhiteNoise requires its middleware immediately after SecurityMiddleware.
# Looking the position up (rather than hardcoding index 1) means this fails
# loudly if base.py's MIDDLEWARE is ever reordered.
_SECURITY_MIDDLEWARE = 'django.middleware.security.SecurityMiddleware'
MIDDLEWARE = list(MIDDLEWARE)
MIDDLEWARE.insert(
    MIDDLEWARE.index(_SECURITY_MIDDLEWARE) + 1,
    'whitenoise.middleware.WhiteNoiseMiddleware',
)

# CompressedStaticFilesStorage (not the *Manifest* variant) on purpose: the
# manifest version raises at render time when a template references a static
# file that doesn't exist. Hashed/manifest filenames are a later upgrade.
# brotli is already a dependency (via WeasyPrint), so WhiteNoise writes .br
# alongside .gz automatically.
STORAGES = {
    # Media files — Django's default, left unchanged.
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

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


# Nginx terminates TLS and passes the original scheme in X-Forwarded-Proto.
# Trusting this header is only safe because the app has no published port:
# nothing but Nginx can reach it. Needed before SECURE_SSL_REDIRECT is turned
# on, otherwise Django never sees a request as secure and redirects forever.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')