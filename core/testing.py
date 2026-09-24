"""
Small, explicit factories shared by the branch-access tests.

Deliberately *not* named ``test*.py`` so the test runner treats it as a
plain module. ``supervisor/tests.py`` predates this file and keeps its
own copies of these helpers; nothing there is changed by this module.

Every helper takes what it needs as an argument -- nothing is hidden in
class-level defaults -- so a test body can be audited against its
assertions without looking anything up.
"""

import jdatetime
from django.contrib.auth import get_user_model

from school.models import AcademicYear, Branch, ClassSubject, Grade, SchoolClass, Subject
from staff.models import BranchAccess, Staff, TeacherAssignment, TeacherProfile
from student.models.student_enrollment import StudentEnrollment
from student.models.student_profile import StudentProfile
from supervisor.models.supervisor_profile import SupervisorProfile

User = get_user_model()

_counter = 0


def unique(prefix):
    global _counter
    _counter += 1
    return f"{prefix}{_counter}"


def make_user(role, is_staff=False, is_superuser=False, password="test-pass-123"):
    username = unique("user")
    return User.objects.create_user(
        username=username,
        password=password,
        first_name=username,
        last_name=role or "super",
        role=role,
        phone_number="09120000000",
        is_staff=is_staff,
        is_superuser=is_superuser,
    )


def make_superuser(password="test-pass-123"):
    return make_user(
        User.Roles.ADMIN,
        is_staff=True,
        is_superuser=True,
        password=password,
    )


def make_branch(name=None, is_active=True, order=1):
    code = name or unique("branch")
    return Branch.objects.create(
        name=code, code=code, is_active=is_active, order=order
    )


def make_grade(level=None):
    if level is None:
        global _counter
        _counter += 1
        level = _counter
    return Grade.objects.create(name=f"پایه {level}", level=level)


def make_subject():
    slug = unique("subject")
    return Subject.objects.create(name=slug, slug=slug)


def make_academic_year(start_date=None, end_date=None, is_current=True, is_active=True):
    if start_date is None:
        start_date = jdatetime.date(1403, 7, 1)
    if end_date is None:
        end_date = start_date.replace(year=start_date.year + 1)

    return AcademicYear.objects.create(
        title=unique("year"),
        start_date=start_date,
        end_date=end_date,
        is_current=is_current,
        is_active=is_active,
    )


def make_staff(role=User.Roles.TEACHER, is_staff=False, password="test-pass-123", user=None):
    """
    User -> Staff. Returns the Staff row (``staff.user`` is the login).

    Pass ``user`` to attach a Staff row to somebody who already exists
    (e.g. a supervisor who is also on the payroll).
    """

    if user is None:
        user = make_user(role, is_staff=is_staff, password=password)

    return Staff.objects.create(
        user=user,
        personnel_code=unique("pc"),
        national_code=unique("nc")[:10],
        gender=Staff.Gender.MALE,
        hire_date=jdatetime.date(1400, 1, 1),
    )


def make_teacher_profile(staff=None, is_staff=False):
    if staff is None:
        staff = make_staff(is_staff=is_staff)

    return TeacherProfile.objects.create(staff=staff)


def make_assignment(
    teacher,
    branch,
    academic_year,
    status=TeacherAssignment.AssignmentStatus.ACTIVE,
    hire_date=None,
    end_date=None,
):
    return TeacherAssignment.objects.create(
        teacher=teacher,
        branch=branch,
        academic_year=academic_year,
        hire_date=hire_date or jdatetime.date(1400, 1, 1),
        end_date=end_date,
        status=status,
    )


def make_branch_access(staff, branch, is_default=False):
    return BranchAccess.objects.create(
        staff=staff, branch=branch, is_default=is_default
    )


def make_supervisor(branch, grade, is_staff=False, password="test-pass-123"):
    user = make_user(User.Roles.SUPERVISOR, is_staff=is_staff, password=password)

    return SupervisorProfile.objects.create(user=user, branch=branch, grade=grade)


def make_school_class(branch, grade, year, is_active=True):
    return SchoolClass.objects.create(
        year=year,
        grade=grade,
        branch=branch,
        section=unique("section"),
        is_active=is_active,
    )


def make_class_subject(
    school_class, subject, teacher_assignment, start_date=None, end_date=None
):
    return ClassSubject.objects.create(
        school_class=school_class,
        subject=subject,
        teacher_assignment=teacher_assignment,
        start_date=start_date or jdatetime.date(1403, 7, 1),
        end_date=end_date or jdatetime.date(1404, 3, 31),
    )


def make_student(is_staff=False):
    user = make_user(User.Roles.STUDENT, is_staff=is_staff)

    return StudentProfile.objects.create(user=user, student_code=unique("std"))


def make_enrollment(
    student,
    school_class,
    status=StudentEnrollment.EnrollmentStatus.ACTIVE,
    enrollment_date=None,
):
    return StudentEnrollment.objects.create(
        student=student,
        school_class=school_class,
        enrollment_date=enrollment_date or jdatetime.date(1403, 7, 1),
        status=status,
    )


def grant_all_model_permissions(user):
    """
    Gives ``user`` every model permission, so an admin test exercises
    *branch* scoping rather than Django's permission framework.
    """

    from django.contrib.auth.models import Permission

    user.user_permissions.set(Permission.objects.all())
    user.save()

    return user
