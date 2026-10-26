ROLE_DASHBOARDS = {
    'teacher': 'core:dashboard',
    'student': 'student:dashboard',
    'supervisor': 'supervisor:dashboard',
    'director': 'director:dashboard',
}


def role_dashboard(user):
    """
    Where to send ``user`` after login. Always returns a URL name:
    roles without a dashboard of their own (admin, accountant, ...) used
    to get ``None`` here, which made ``redirect()`` raise a TypeError.
    Those go to the admin when they are staff, to «نوشته‌های من» when
    they can write in the blog, and to the public site otherwise.
    """

    if user.role in ROLE_DASHBOARDS:
        return ROLE_DASHBOARDS[user.role]

    if user.is_staff:
        return 'admin:index'

    # A blog author without a panel (a counselor, say) lands in
    # «نوشته‌های من» instead of the public home page (blog plan D7).
    from blog.permissions import can_write

    if can_write(user):
        return 'blog:write'

    return 'website:website'
