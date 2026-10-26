from django.utils.functional import SimpleLazyObject

from . import permissions


def authoring(request):
    """
    ``blog_can_write``: may the user open «نوشته‌های من»? The panels'
    sidebars show the item by it. It is lazy, so its one query runs only
    on a page whose template actually asks (a panel sidebar), never on the
    public pages (change 1 of the plan's approval).
    """

    user = getattr(request, "user", None)
    return {"blog_can_write": SimpleLazyObject(lambda: permissions.can_write(user))}
