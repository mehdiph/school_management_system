"""
Base settings for teachlog project, shared by every environment.

See development.py and production.py for the environment-specific
overrides that get layered on top of this file.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# BASE_DIR points at the repository root (teachlog/config/settings/base.py -> repo root).
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Load a .env file from the repo root if one is present. Real environments
# (Docker/VPS) are expected to provide environment variables directly, so a
# missing .env file here is not an error.
load_dotenv(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
# Falls back to the project's original development key so local setups that
# don't define SECRET_KEY keep working unchanged.
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-^=6ex(k-vm!swl&9=@rs)(@nx0t81(mi!h55m02rvq$58m537#',
)

ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('ALLOWED_HOSTS', '').split(',')
    if host.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]

AUTH_USER_MODEL = 'accounts.User'

# Header holding the real client IP when a reverse proxy we control sets
# it (accounts.sessions.client_ip). None: use REMOTE_ADDR. Never point this
# at X-Forwarded-For -- clients can forge it. production.py sets it.
CLIENT_IP_HEADER = None

# Where @login_required sends logged-out users. Django's default
# (/accounts/login/) does not exist here: the login page is /auth/login/.
LOGIN_URL = 'accounts:login'

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_jalali',
    'school',
    'teaching',
    'core',
    'report',
    'accounts',
    'website',
    'scheduling',
    'staff',
    'student',
    'attendance',
    'supervisor',
    'academic_calendar',
    'analytics',
    'director',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.branch.BranchMiddleware',
    'accounts.middleware.ForcePasswordChangeMiddleware',
]

ROOT_URLCONF = 'teachlog.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'template'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'student.context_processors.student_info',
                'core.context_processors.branch.branch_context',
                'core.context_processors.teacher_info.teacher_info_context',
                'core.context_processors.topbar.topbar_context',
                'website.context_processors.site_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'teachlog.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
#
# Defaults to the project's original SQLite database. If POSTGRES_DB is set
# in the environment, PostgreSQL is used instead (this is how production.py
# is expected to be configured, via Docker Compose environment variables).

if os.environ.get('POSTGRES_DB'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ['POSTGRES_DB'],
            'USER': os.environ.get('POSTGRES_USER', ''),
            'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
            'HOST': os.environ.get('POSTGRES_HOST', 'localhost'),
            'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    {
        'NAME': 'accounts.validators.NotNationalCodePasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'fa-ir'

TIME_ZONE = 'Asia/Tehran'

USE_I18N = True

USE_TZ = True


# Weekly schedule (see scheduling/utils.py)
#
# Days the school holds classes, as ClassSchedule.DayChoices values:
# 0=شنبه 1=یکشنبه 2=دوشنبه 3=سه‌شنبه 4=چهارشنبه. Thursday and Friday are
# never working days (academic_calendar.services.is_working_day) and no
# new timetable slot may be put on Thursday.
SCHOOL_WORKING_DAYS = [0, 1, 2, 3, 4]

# "هفته اول" / "هفته دوم" is derived from AcademicYear.start_date alone
# (scheduling.utils.get_week_cycle); there is no setting for it.


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Where `collectstatic` gathers files for production serving.
STATIC_ROOT = BASE_DIR / 'staticfiles'

# media settings
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Let Django itself serve MEDIA_URL even when DEBUG is False. Intended for
# local/container testing only, before Nginx exists to serve the media volume
# directly. Kept opt-in via env var so it stays off in real production.
SERVE_MEDIA = os.environ.get('SERVE_MEDIA', 'False') == 'True'


# Logging
# Simple, container-friendly logging: everything goes to the console so it
# can be collected by `docker logs` / systemd / the VPS's process manager.
# Errors always show; day-to-day request noise is trimmed unless DEBUG.

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
        # WeasyPrint subsets the font on every PDF and fontTools logs a
        # dozen INFO lines each time (weekly schedule / reports).
        'fontTools': {
            'level': 'WARNING',
        },
    },
}
