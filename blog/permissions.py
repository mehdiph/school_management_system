"""
Who may do what in the blog (D3, D4, §6 of the plan, ADR-026).

A person **can write** when all of these hold:
- they have a ``BlogAuthor`` row and it is active;
- their account is active;
- their role is in ``BLOG_AUTHOR_ROLES`` (this module is the only reader);
- if they have a ``Staff`` row, it is active (someone who left can't write);
- and, for a section, it is granted to them and active.

Editors are staff with ``blog.publish_post``; they work in the admin.
Nothing else in the project decides these rules: the admin, the services
and the authoring views all ask here.
"""

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from .models import BlogAuthor, Post, Section


def author_for(user):
    """
    The user's ``BlogAuthor`` row (active or not), or None: one query,
    with the account and its staff record, cached on the user object.
    """

    if not getattr(user, "is_authenticated", False):
        return None
    if not hasattr(user, "_blog_author"):
        user._blog_author = BlogAuthor.objects.select_related("user__staff_profile").filter(user=user).first()
    return user._blog_author


def _staff_is_active(user):
    try:
        return user.staff_profile.is_active
    except ObjectDoesNotExist:
        return True


def write_block_reason(author):
    """
    Why this author can't write right now, in Persian, or "" when they can
    (sections aside). Shown in the admin as «وضعیت نویسندگی».
    """

    user = author.user
    if not author.is_active:
        return "اجازه نوشتن این نویسنده خاموش است."
    if not user.is_active:
        return "حساب کاربری غیرفعال است."
    if user.role not in settings.BLOG_AUTHOR_ROLES:
        return f"نقش «{user.get_role_display() or '—'}» اجازه نویسندگی ندارد."
    if not _staff_is_active(user):
        return "پرونده پرسنلی این شخص غیرفعال است."
    return ""


def can_write(user):
    """True when the user may use the authoring area at all (any section aside)."""

    author = author_for(user)
    return author is not None and not write_block_reason(author)


def writable_sections(user):
    """The active sections granted to ``user``, or none when they can't write."""

    if not can_write(user):
        return Section.objects.none()
    return Section.objects.filter(is_active=True, grants__author=author_for(user)).order_by("order", "id")


def can_write_in(user, section):
    return section is not None and writable_sections(user).filter(pk=section.pk).exists()


def author_posts(user):
    """The posts every authoring view starts from: the user's own, or none."""

    if not can_write(user):
        return Post.objects.none()
    return Post.objects.filter(author=author_for(user))


def can_edit_as_author(user, post):
    """An author edits only their own drafts, in a section they may still write in (D8, D9)."""

    return (
        post.status == Post.Status.DRAFT
        and author_for(user) is not None
        and post.author_id == author_for(user).pk
        and can_write_in(user, post.section)
    )


def is_editor(user):
    """Staff with ``blog.publish_post`` (directly, through a group, or as a superuser)."""

    return bool(user.is_active and user.is_staff and user.has_perm("blog.publish_post"))


def can_publish(user):
    return is_editor(user)


def can_edit_in_admin(user):
    return bool(user.is_active and user.is_staff and user.has_perm("blog.change_post"))


def can_preview(user, post):
    """The post's own author (while they can write) and editors; nobody else, not even other staff."""

    if is_editor(user):
        return True
    author = author_for(user)
    return author is not None and post.author_id == author.pk and can_write(user)
