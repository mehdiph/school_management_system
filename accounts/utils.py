ROLE_DASHBOARDS = {
    'teacher': 'core:dashboard',
    'student': 'student:dashboard',
    'supervisor': 'supervisor:dashboard',
}


def role_dashboard(user):
    """
    Where to send ``user`` after login. Always returns a URL name:
    roles without a dashboard of their own (admin, accountant, ...) used
    to get ``None`` here, which made ``redirect()`` raise a TypeError.
    """

    if user.role in ROLE_DASHBOARDS:
        return ROLE_DASHBOARDS[user.role]

    if user.is_staff:
        return 'admin:index'

    return 'website:website'
