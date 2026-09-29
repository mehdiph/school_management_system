"""
Sign-in history and "sign out of other devices".

Every successful login is recorded as a ``LoginActivity`` (accounts.signals)
together with its session key. That key is what lets us end a user's
*other* sessions later without scanning the whole session table: each one
is deleted through the configured session engine's own ``SessionStore``,
so it works for the database and cache backends alike. Only the
signed-cookie backend keeps sessions in the browser, where the server
cannot delete them (``can_end_sessions`` is False then).

Keep the stored key in step whenever a session key changes under a
logged-in user (``update_session_auth_hash`` cycles it): use
``update_session_auth_hash_tracked`` instead of calling Django's directly.
"""

import ipaddress
import re
from importlib import import_module

from django.conf import settings
from django.contrib.auth import update_session_auth_hash

from .models import LoginActivity

#: Rows kept per user; older ones are pruned on each new login.
KEEP_PER_USER = 50

RECENT_LIMIT = 10


# ----------------------------------------------------------------------
# Request details
# ----------------------------------------------------------------------

def client_ip(request):
    """
    The client's IP, or None.

    ``REMOTE_ADDR`` unless ``settings.CLIENT_IP_HEADER`` names a header set
    by our own reverse proxy (production: Nginx's ``X-Real-IP``, which it
    overwrites with ``$remote_addr``; see production.py). X-Forwarded-For
    is never trusted: a client can put anything in it.
    """

    header = getattr(settings, 'CLIENT_IP_HEADER', None)
    value = request.META.get(header) if header else None
    value = (value or request.META.get('REMOTE_ADDR') or '').strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


# (label, pattern) -- first match wins, so the more specific ones go first
# (Edge and Opera also say "Chrome"; Chrome also says "Safari").
_BROWSERS = (
    ('Edge', re.compile(r'Edg(?:e|A|iOS)?/([\d]+)')),
    ('Opera', re.compile(r'(?:OPR|Opera)/([\d]+)')),
    ('Samsung Internet', re.compile(r'SamsungBrowser/([\d]+)')),
    ('Firefox', re.compile(r'(?:Firefox|FxiOS)/([\d]+)')),
    ('Chrome', re.compile(r'(?:Chrome|CriOS)/([\d]+)')),
    ('Safari', re.compile(r'Version/([\d]+)[\d.]* .*Safari/')),
)

_SYSTEMS = (
    ('iOS', re.compile(r'iPhone|iPad|iPod')),
    ('Android', re.compile(r'Android')),
    ('Windows', re.compile(r'Windows')),
    ('macOS', re.compile(r'Mac OS X|Macintosh')),
    ('ChromeOS', re.compile(r'CrOS')),
    ('Linux', re.compile(r'Linux')),
)


def describe_user_agent(user_agent):
    """
    ``(browser, os)`` in plain words, e.g. ``("Chrome 128", "Android")``;
    empty strings for what cannot be told. Deliberately small: enough to
    recognise one's own devices, no dependency for it.
    """

    user_agent = user_agent or ''
    browser = ''
    for name, pattern in _BROWSERS:
        match = pattern.search(user_agent)
        if match:
            browser = f'{name} {match.group(1)}'
            break

    system = next((name for name, pattern in _SYSTEMS if pattern.search(user_agent)), '')
    return browser, system


# ----------------------------------------------------------------------
# Recording
# ----------------------------------------------------------------------

def record_login(request, user):
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:512]
    browser, system = describe_user_agent(user_agent)
    session = getattr(request, 'session', None)

    LoginActivity.objects.create(
        user=user,
        ip_address=client_ip(request),
        user_agent=user_agent,
        browser=browser,
        os=system,
        session_key=getattr(session, 'session_key', None),
    )

    stale = LoginActivity.objects.filter(user=user).values_list('pk', flat=True)[KEEP_PER_USER:]
    LoginActivity.objects.filter(pk__in=list(stale)).delete()


def forget_session(session_key):
    """The session is over (logout): it can no longer be ended from elsewhere."""

    if session_key:
        LoginActivity.objects.filter(session_key=session_key).update(session_key=None)


def update_session_auth_hash_tracked(request, user):
    """``update_session_auth_hash`` + keep the tracked key of this session current."""

    old_key = request.session.session_key
    update_session_auth_hash(request, user)
    new_key = request.session.session_key
    if old_key and new_key and old_key != new_key:
        LoginActivity.objects.filter(user=user, session_key=old_key).update(session_key=new_key)


# ----------------------------------------------------------------------
# Ending sessions
# ----------------------------------------------------------------------

def can_end_sessions():
    return settings.SESSION_ENGINE != 'django.contrib.sessions.backends.signed_cookies'


def end_other_sessions(request):
    """
    Deletes every tracked session of ``request.user`` except this one.
    Returns how many were ended.
    """

    store = import_module(settings.SESSION_ENGINE).SessionStore
    current = request.session.session_key

    others = (
        LoginActivity.objects
        .filter(user=request.user, session_key__isnull=False)
        .exclude(session_key=current)
    )
    keys = set(others.values_list('session_key', flat=True))
    for key in keys:
        store(session_key=key).delete()
    others.update(session_key=None)
    return len(keys)


def recent_logins(user, limit=RECENT_LIMIT):
    return list(LoginActivity.objects.filter(user=user)[:limit])
