from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .sessions import forget_session, record_login


@receiver(user_logged_in, dispatch_uid='accounts.record_login')
def on_login(sender, request, user, **kwargs):
    # Every login path goes through here (site login, admin, tests'
    # client.login). ``request`` can be None for programmatic logins.
    if request is not None:
        record_login(request, user)


@receiver(user_logged_out, dispatch_uid='accounts.forget_session')
def on_logout(sender, request, user, **kwargs):
    session = getattr(request, 'session', None)
    if session is not None:
        forget_session(session.session_key)
