"""Factories for the blog's tests (the project's shared ones are in ``core/testing.py``)."""

from datetime import timedelta

from django.contrib.auth.models import Permission
from django.utils import timezone

from accounts.models import User
from core.testing import make_user, unique

from .models import AuthorSection, BlogAuthor, Category, Post, Section, Tag


def make_section(title=None, is_active=True, **fields):
    return Section.objects.create(title=title or unique("بخش"), is_active=is_active, **fields)


def make_category(section, title=None, **fields):
    return Category.objects.create(section=section, title=title or unique("دسته"), **fields)


def make_author(user=None, sections=(), role=User.Roles.TEACHER, **fields):
    """An author (and, without ``user``, a fresh user of ``role``) granted ``sections``."""

    user = user or make_user(role)
    author = BlogAuthor.objects.create(user=user, **fields)
    for section in sections:
        AuthorSection.objects.create(author=author, section=section)
    return author


def make_post(author, section=None, status=Post.Status.DRAFT, published_at=None, **fields):
    section = section or author.sections.first() or make_section()
    fields.setdefault("title", unique("نوشته"))
    fields.setdefault("body", "<p>متن نوشته برای آزمون.</p>")
    if status == Post.Status.PUBLISHED and published_at is None:
        published_at = timezone.now() - timedelta(days=1)
    return Post.objects.create(author=author, section=section, status=status, published_at=published_at, **fields)


def make_tag(name=None, **fields):
    return Tag.objects.create(name=name or unique("برچسب"), **fields)


def make_editor(is_superuser=False):
    """Staff with every blog permission, ``publish_post`` included: a «ویراستار وبلاگ»."""

    user = make_user(User.Roles.ADMIN, is_staff=True, is_superuser=is_superuser)
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label="blog"))
    return User.objects.get(pk=user.pk)  # drop the permission cache


def grant(user, *codenames):
    user.user_permissions.add(*Permission.objects.filter(content_type__app_label="blog", codename__in=codenames))
    return User.objects.get(pk=user.pk)
