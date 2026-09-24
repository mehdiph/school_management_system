"""
Tests for the derived branch-access service (``core.services.access``)
and for the admin scoping built on top of it.

The point of every test here is the same invariant: a branch appears in
somebody's accessible set *because* of a live reason (an explicit
BranchAccess row, an active assignment in the current year, a supervisor
profile, an active enrolment) -- never because a stale row was left
behind.
"""

import jdatetime
from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from core.services import access
from core.services.branch_service import BranchService
from core.testing import (
    grant_all_model_permissions,
    make_academic_year,
    make_assignment,
    make_branch,
    make_branch_access,
    make_class_subject,
    make_enrollment,
    make_grade,
    make_school_class,
    make_staff,
    make_student,
    make_subject,
    make_superuser,
    make_supervisor,
    make_teacher_profile,
    make_user,
)
from accounts.models import User
from staff.models import BranchAccess, TeacherAssignment


def today():
    return jdatetime.date.fromgregorian(date=timezone.localdate())


class AccessibleBranchesTests(TestCase):
    """``get_accessible_branches`` / ``get_accessible_branch_ids``."""

    def setUp(self):
        self.branch = make_branch()
        self.other_branch = make_branch()
        self.current_year = make_academic_year(is_current=True)
        self.old_year = make_academic_year(
            start_date=jdatetime.date(1402, 7, 1), is_current=False
        )

    def ids(self, user):
        return access.get_accessible_branch_ids(user)

    # -- teaching -----------------------------------------------------

    def test_active_assignment_grants_access_without_branch_access_row(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.current_year)

        self.assertFalse(
            BranchAccess.objects.filter(staff=teacher.staff).exists()
        )
        self.assertEqual(self.ids(teacher.staff.user), {self.branch.id})

    def test_ended_assignment_grants_no_access(self):
        teacher = make_teacher_profile()
        make_assignment(
            teacher,
            self.branch,
            self.current_year,
            end_date=today() - timedelta(days=1),
        )

        self.assertEqual(self.ids(teacher.staff.user), set())

    def test_assignment_ending_today_still_grants_access(self):
        teacher = make_teacher_profile()
        make_assignment(
            teacher, self.branch, self.current_year, end_date=today()
        )

        self.assertEqual(self.ids(teacher.staff.user), {self.branch.id})

    def test_assignment_in_non_current_year_grants_no_access(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.old_year)

        self.assertEqual(self.ids(teacher.staff.user), set())

    def test_inactive_status_grants_no_access(self):
        for status in (
            TeacherAssignment.AssignmentStatus.TERMINATED,
            TeacherAssignment.AssignmentStatus.TRANSFERRED,
            TeacherAssignment.AssignmentStatus.LEAVE,
        ):
            with self.subTest(status=status):
                teacher = make_teacher_profile()
                make_assignment(
                    teacher, self.branch, self.current_year, status=status
                )

                self.assertEqual(self.ids(teacher.staff.user), set())

    def test_inactive_branch_is_excluded(self):
        closed_branch = make_branch(is_active=False)
        teacher = make_teacher_profile()
        make_assignment(teacher, closed_branch, self.current_year)

        self.assertEqual(self.ids(teacher.staff.user), set())

    # -- explicit -----------------------------------------------------

    def test_non_teaching_staff_gets_its_branch_access_rows(self):
        staff = make_staff(role=User.Roles.ACCOUNTANT)
        make_branch_access(staff, self.branch)
        make_branch_access(staff, self.other_branch)

        self.assertEqual(
            self.ids(staff.user), {self.branch.id, self.other_branch.id}
        )

    # -- supervisor ---------------------------------------------------

    def test_supervisor_gets_profile_branch(self):
        supervisor = make_supervisor(self.branch, make_grade())

        self.assertEqual(self.ids(supervisor.user), {self.branch.id})

    # -- student ------------------------------------------------------

    def test_student_gets_branch_of_active_enrolment(self):
        student = make_student()
        school_class = make_school_class(
            self.branch, make_grade(), self.current_year
        )
        make_enrollment(student, school_class)

        self.assertEqual(self.ids(student.user), {self.branch.id})

    # -- union / dedup ------------------------------------------------

    def test_sources_are_unioned(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.current_year)
        make_branch_access(teacher.staff, self.other_branch)

        self.assertEqual(
            self.ids(teacher.staff.user),
            {self.branch.id, self.other_branch.id},
        )

    def test_same_branch_from_two_sources_is_deduplicated(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.current_year)
        make_branch_access(teacher.staff, self.branch)

        self.assertEqual(self.ids(teacher.staff.user), {self.branch.id})
        self.assertEqual(
            list(access.get_accessible_branches(teacher.staff.user)),
            [self.branch],
        )

        sources = access.get_branch_access_map(teacher.staff.user)
        self.assertEqual(
            sources[self.branch.id],
            {access.SOURCE_EXPLICIT, access.SOURCE_TEACHING},
        )

    def test_supervisor_with_extra_explicit_access_gets_both(self):
        supervisor = make_supervisor(self.branch, make_grade())
        staff = make_staff(user=supervisor.user)
        make_branch_access(staff, self.other_branch)

        self.assertEqual(
            self.ids(supervisor.user),
            {self.branch.id, self.other_branch.id},
        )

    # -- superuser / anonymous ----------------------------------------

    def test_superuser_gets_all_active_branches(self):
        closed = make_branch(is_active=False)
        superuser = make_superuser()

        ids = self.ids(superuser)

        self.assertEqual(ids, {self.branch.id, self.other_branch.id})
        self.assertNotIn(closed.id, ids)

    def test_anonymous_user_gets_nothing(self):
        self.assertEqual(access.get_accessible_branch_ids(AnonymousUser()), set())
        self.assertFalse(access.get_accessible_branches(AnonymousUser()).exists())

    def test_staff_without_any_source_gets_nothing(self):
        staff = make_staff(role=User.Roles.IT)

        self.assertEqual(self.ids(staff.user), set())

    # -- caching ------------------------------------------------------

    def test_request_cache_avoids_repeated_queries(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.current_year)

        request = RequestFactory().get("/")
        user = User.objects.get(pk=teacher.staff.user.pk)

        first = access.get_accessible_branch_ids(user, request=request)

        # Second call on the same request answers from the memo.
        with self.assertNumQueries(0):
            second = access.get_accessible_branch_ids(user, request=request)

        self.assertEqual(first, {self.branch.id})
        self.assertEqual(first, second)

    def test_request_cache_is_not_shared_between_users(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.branch, self.current_year)

        other_staff = make_staff(role=User.Roles.IT)
        make_branch_access(other_staff, self.other_branch)

        request = RequestFactory().get("/")

        self.assertEqual(
            access.get_accessible_branch_ids(
                teacher.staff.user, request=request
            ),
            {self.branch.id},
        )
        self.assertEqual(
            access.get_accessible_branch_ids(
                other_staff.user, request=request
            ),
            {self.other_branch.id},
        )


class DefaultBranchTests(TestCase):
    """``get_default_branch`` resolution order."""

    def setUp(self):
        self.first_branch = make_branch(order=1)
        self.second_branch = make_branch(order=2)
        self.third_branch = make_branch(order=3)
        self.current_year = make_academic_year(is_current=True)

    def test_explicit_default_wins(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.first_branch, self.current_year)
        make_branch_access(teacher.staff, self.second_branch, is_default=True)

        self.assertEqual(
            access.get_default_branch(teacher.staff.user), self.second_branch
        )

    def test_falls_back_to_most_recent_active_assignment(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.third_branch, self.current_year)
        # Explicit, but not flagged as the default one.
        make_branch_access(teacher.staff, self.first_branch)

        self.assertEqual(
            access.get_default_branch(teacher.staff.user), self.third_branch
        )

    def test_falls_back_to_first_accessible_branch(self):
        staff = make_staff(role=User.Roles.SERVICES)
        make_branch_access(staff, self.third_branch)
        make_branch_access(staff, self.second_branch)

        self.assertEqual(
            access.get_default_branch(staff.user), self.second_branch
        )

    def test_supervisor_default_is_their_own_branch(self):
        supervisor = make_supervisor(self.third_branch, make_grade())

        self.assertEqual(
            access.get_default_branch(supervisor.user), self.third_branch
        )

    def test_superuser_default_is_first_active_branch(self):
        superuser = make_superuser()

        self.assertEqual(
            access.get_default_branch(superuser), self.first_branch
        )

    def test_no_access_means_no_default(self):
        staff = make_staff(role=User.Roles.IT)

        self.assertIsNone(access.get_default_branch(staff.user))

    def test_branch_service_delegates_to_the_access_service(self):
        teacher = make_teacher_profile()
        make_assignment(teacher, self.second_branch, self.current_year)
        user = teacher.staff.user

        self.assertEqual(
            list(BranchService.get_available_branches(user)),
            [self.second_branch],
        )
        self.assertEqual(
            BranchService.get_user_default_branch(user), self.second_branch
        )
        self.assertTrue(BranchService.has_access(user, self.second_branch))
        self.assertFalse(BranchService.has_access(user, self.first_branch))


class AdminScopingTests(TestCase):
    """
    Branch-scoped admins must only ever list rows from the branches the
    logged-in user can reach -- exercised through the real admin views
    with the test client, not by calling ``get_queryset`` directly.
    """

    PASSWORD = "test-pass-123"

    def setUp(self):
        self.branch = make_branch(name="شعبه-الف", order=1)
        self.other_branch = make_branch(name="شعبه-ب", order=2)
        self.year = make_academic_year(is_current=True)
        self.grade = make_grade()
        self.subject = make_subject()

        self.own_class = make_school_class(self.branch, self.grade, self.year)
        self.foreign_class = make_school_class(
            self.other_branch, self.grade, self.year
        )

        # A teacher whose only access comes from an active assignment.
        self.teacher = make_teacher_profile(
            staff=make_staff(is_staff=True, password=self.PASSWORD)
        )
        self.teacher_assignment = make_assignment(
            self.teacher, self.branch, self.year
        )
        grant_all_model_permissions(self.teacher.staff.user)

        # A non-teaching staff member with only an explicit BranchAccess.
        self.office_staff = make_staff(
            role=User.Roles.ACCOUNTANT,
            is_staff=True,
            password=self.PASSWORD,
        )
        make_branch_access(self.office_staff, self.other_branch)
        grant_all_model_permissions(self.office_staff.user)

        self.superuser = make_superuser(password=self.PASSWORD)

    def login(self, user):
        self.assertTrue(
            self.client.login(
                username=user.username, password=self.PASSWORD
            )
        )

    def changelist_ids(self, url_name):
        response = self.client.get(reverse(url_name))
        self.assertEqual(response.status_code, 200)

        return {
            obj.pk
            for obj in response.context["cl"].queryset
        }

    def test_teacher_sees_only_their_branch_classes(self):
        self.login(self.teacher.staff.user)

        ids = self.changelist_ids("admin:school_schoolclass_changelist")

        self.assertIn(self.own_class.pk, ids)
        self.assertNotIn(self.foreign_class.pk, ids)

    def test_office_staff_sees_only_its_explicit_branch(self):
        self.login(self.office_staff.user)

        ids = self.changelist_ids("admin:school_schoolclass_changelist")

        self.assertIn(self.foreign_class.pk, ids)
        self.assertNotIn(self.own_class.pk, ids)

    def test_superuser_sees_every_branch(self):
        self.login(self.superuser)

        ids = self.changelist_ids("admin:school_schoolclass_changelist")

        self.assertIn(self.own_class.pk, ids)
        self.assertIn(self.foreign_class.pk, ids)

    def test_class_subject_admin_is_scoped(self):
        own_cs = make_class_subject(
            self.own_class, self.subject, self.teacher_assignment
        )

        foreign_teacher = make_teacher_profile()
        foreign_assignment = make_assignment(
            foreign_teacher, self.other_branch, self.year
        )
        foreign_cs = make_class_subject(
            self.foreign_class, self.subject, foreign_assignment
        )

        self.login(self.teacher.staff.user)

        ids = self.changelist_ids("admin:school_classsubject_changelist")

        self.assertIn(own_cs.pk, ids)
        self.assertNotIn(foreign_cs.pk, ids)

    def test_student_enrollment_admin_is_scoped(self):
        own_enrollment = make_enrollment(make_student(), self.own_class)
        foreign_enrollment = make_enrollment(make_student(), self.foreign_class)

        self.login(self.teacher.staff.user)

        ids = self.changelist_ids("admin:student_studentenrollment_changelist")

        self.assertIn(own_enrollment.pk, ids)
        self.assertNotIn(foreign_enrollment.pk, ids)

    def test_teacher_assignment_admin_is_scoped(self):
        foreign_assignment = make_assignment(
            make_teacher_profile(), self.other_branch, self.year
        )

        self.login(self.teacher.staff.user)

        ids = self.changelist_ids("admin:staff_teacherassignment_changelist")

        self.assertIn(self.teacher_assignment.pk, ids)
        self.assertNotIn(foreign_assignment.pk, ids)

    def test_branch_access_admin_is_scoped(self):
        own_access = make_branch_access(self.teacher.staff, self.branch)
        foreign_access = BranchAccess.objects.get(staff=self.office_staff)

        self.login(self.teacher.staff.user)

        ids = self.changelist_ids("admin:staff_branchaccess_changelist")

        self.assertIn(own_access.pk, ids)
        self.assertNotIn(foreign_access.pk, ids)

    def test_class_subject_teacher_dropdown_is_filtered_to_the_class(self):
        """
        On a change form the teacher dropdown offers only assignments of
        that class's branch *and* year -- the mismatching ones that
        ``ClassSubject.clean()`` would reject are never offered.
        """

        own_cs = make_class_subject(
            self.own_class, self.subject, self.teacher_assignment
        )
        foreign_assignment = make_assignment(
            make_teacher_profile(), self.other_branch, self.year
        )
        old_year = make_academic_year(
            start_date=jdatetime.date(1402, 7, 1), is_current=False
        )
        wrong_year_assignment = make_assignment(
            make_teacher_profile(), self.branch, old_year
        )

        self.login(self.superuser)

        response = self.client.get(
            reverse("admin:school_classsubject_change", args=[own_cs.pk])
        )
        self.assertEqual(response.status_code, 200)

        choices = set(
            response.context["adminform"].form
            .fields["teacher_assignment"].queryset
            .values_list("pk", flat=True)
        )

        self.assertIn(self.teacher_assignment.pk, choices)
        self.assertNotIn(foreign_assignment.pk, choices)
        self.assertNotIn(wrong_year_assignment.pk, choices)

    def test_effective_branches_names_every_source(self):
        make_branch_access(self.teacher.staff, self.other_branch)

        self.login(self.superuser)

        response = self.client.get(
            reverse(
                "admin:staff_teacherprofile_change", args=[self.teacher.pk]
            )
        )
        self.assertEqual(response.status_code, 200)

        content = response.content.decode()

        self.assertIn("شعبه-الف", content)
        self.assertIn(access.SOURCE_LABELS[access.SOURCE_TEACHING], content)
        self.assertIn("شعبه-ب", content)
        self.assertIn(access.SOURCE_LABELS[access.SOURCE_EXPLICIT], content)
