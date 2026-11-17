"""Factories for the online classes tests; not named ``test*.py``, so the runner treats it as a plain module."""

from datetime import timedelta

import jdatetime
from django.test import override_settings
from django.utils import timezone

from core.testing import make_academic_year, make_branch, make_enrollment, make_grade, make_school_class, make_student

from .models import Announcement, OnlineEvent, OnlineEventAccess, OnlinePlatform

#: Tuesday 12 Aban 1405, 10:00 in Tehran. Tests mock the clock to this.
NOW = timezone.make_aware(timezone.datetime(2026, 11, 3, 10, 0))


def make_platform(**fields):
    fields.setdefault("name", f"platform-{OnlinePlatform.objects.count() + 1}")
    return OnlinePlatform.objects.create(**fields)


def make_event(targets=None, **fields):
    """A shared-link event starting an hour from ``NOW``, whole school unless ``targets`` says otherwise."""

    fields.setdefault("title", "کلاس ریاضی")
    fields.setdefault("start_at", NOW + timedelta(hours=1))
    fields.setdefault("end_at", fields["start_at"] + timedelta(hours=1))
    if fields.get("access_mode", OnlineEvent.AccessMode.SHARED) != OnlineEvent.AccessMode.INFO:
        fields.setdefault("platform", make_platform())
    if fields.get("access_mode", OnlineEvent.AccessMode.SHARED) == OnlineEvent.AccessMode.SHARED:
        fields.setdefault("join_url", "https://example.com/room")
    fields.setdefault("is_whole_school", targets is None)
    event = OnlineEvent.objects.create(**fields)
    set_targets(event, targets)
    return event


def make_announcement(targets=None, **fields):
    fields.setdefault("title", "اطلاعیه")
    fields.setdefault("visible_from", NOW - timedelta(days=1))
    fields.setdefault("visible_until", NOW + timedelta(days=1))
    fields.setdefault("is_whole_school", targets is None)
    announcement = Announcement.objects.create(**fields)
    set_targets(announcement, targets)
    return announcement


def set_targets(item, targets):
    for name, values in (targets or {}).items():
        getattr(item, name).set(values)


def make_access(event, student, *, url="", password="", access_code="", **fields):
    row = OnlineEventAccess(event=event, student=student, **fields)
    row.set_secrets(url=url, password=password, access_code=access_code)
    row.save()
    return row


class SchoolMixin:
    """Two branches, two grades, three classes of the current year, and one student in each class."""

    @classmethod
    def setUpClass(cls):
        # Every student is a user, and the default password hasher is slow on purpose.
        fast = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
        fast.enable()
        cls.addClassCleanup(fast.disable)
        super().setUpClass()

    def make_school(self):
        self.year = make_academic_year(start_date=jdatetime.date(1405, 7, 1), is_current=True)
        self.branch_a = make_branch("a")
        self.branch_b = make_branch("b")
        self.grade_1 = make_grade(1)
        self.grade_2 = make_grade(2)
        self.class_a1 = make_school_class(self.branch_a, self.grade_1, self.year)
        self.class_a2 = make_school_class(self.branch_a, self.grade_2, self.year)
        self.class_b1 = make_school_class(self.branch_b, self.grade_1, self.year)
        self.student_a1 = self.enrol(self.class_a1)
        self.student_a2 = self.enrol(self.class_a2)
        self.student_b1 = self.enrol(self.class_b1)

    def enrol(self, school_class):
        student = make_student()
        make_enrollment(student, school_class)
        return student
