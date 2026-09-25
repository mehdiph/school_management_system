import jdatetime
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.testing import (
    make_academic_year,
    make_assignment,
    make_branch,
    make_class_subject,
    make_grade,
    make_school_class,
    make_staff,
    make_subject,
    make_superuser,
    make_teacher_profile,
    make_user,
)
from school.models import SchoolClass
from staff.models import TeacherAssignment
from teaching.models import SchoolSession, SessionContent

from .selectors import (
    NO_ASSIGNMENT_MESSAGE,
    NO_TEACHER_PROFILE_MESSAGE,
    ReportScope,
    build_class_report,
    build_grade_report,
)

URL = reverse("report:reports_page")
OPTIONS_URL = reverse("report:report_options")


def make_session(class_subject, day, title="عنوان", content="محتوا"):
    session = SchoolSession.objects.create(
        class_subject=class_subject,
        date=jdatetime.date(1403, 8, day),
    )
    SessionContent.objects.create(
        session=session,
        title=title,
        content=content,
        activity="-",
        homework="-",
        notes="-",
    )
    return session


class ReportTestData(TestCase):
    """
    Two teachers in one branch and year:

      * ``teacher`` teaches two subjects in ``class_a`` (grade_1) and
        one in ``class_b`` (grade_2); a deactivated subject in
        ``class_inactive_cs`` (grade_3); and has an ended assignment in
        another branch (``class_ended``, grade_3).
      * ``other`` teaches in ``class_other`` (grade_3) and also one
        subject in ``class_a``.
    """

    @classmethod
    def setUpTestData(cls):
        cls.year = make_academic_year()
        cls.branch = make_branch()
        cls.other_branch = make_branch()
        cls.grade_1 = make_grade()
        cls.grade_2 = make_grade()
        cls.grade_3 = make_grade()

        cls.teacher = make_teacher_profile()
        cls.teacher_user = cls.teacher.staff.user
        cls.other = make_teacher_profile()

        assignment = make_assignment(cls.teacher, cls.branch, cls.year)
        other_assignment = make_assignment(cls.other, cls.branch, cls.year)
        ended_assignment = make_assignment(
            cls.teacher,
            cls.other_branch,
            cls.year,
            status=TeacherAssignment.AssignmentStatus.TERMINATED,
        )

        cls.class_a = make_school_class(cls.branch, cls.grade_1, cls.year)
        cls.class_b = make_school_class(cls.branch, cls.grade_2, cls.year)
        cls.class_inactive_cs = make_school_class(cls.branch, cls.grade_3, cls.year)
        cls.class_other = make_school_class(cls.branch, cls.grade_3, cls.year)
        cls.class_ended = make_school_class(cls.other_branch, cls.grade_3, cls.year)

        cls.math = make_class_subject(cls.class_a, make_subject(), assignment)
        cls.science = make_class_subject(cls.class_a, make_subject(), assignment)
        cls.art = make_class_subject(cls.class_b, make_subject(), assignment)
        inactive = make_class_subject(cls.class_inactive_cs, make_subject(), assignment)
        inactive.is_active = False
        inactive.save()
        make_class_subject(cls.class_ended, make_subject(), ended_assignment)

        cls.foreign_in_class_a = make_class_subject(
            cls.class_a, make_subject(), other_assignment
        )
        cls.foreign = make_class_subject(cls.class_other, make_subject(), other_assignment)

        make_session(cls.math, 1, content="جلسه ریاضی")
        make_session(cls.art, 2, content="جلسه هنر")
        make_session(cls.foreign_in_class_a, 3, content="محتوای معلم دیگر")
        make_session(cls.foreign, 4, content="محتوای کلاس دیگر")

    def setUp(self):
        self.client.force_login(self.teacher_user)

    def get(self, **params):
        return self.client.get(URL, params)


class TeacherFilterScopeTests(ReportTestData):
    def test_filter_offers_only_own_grades_and_classes(self):
        response = self.get()

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(
            list(form.fields["grade"].queryset), [self.grade_1, self.grade_2]
        )
        # class_a appears once although the teacher has two subjects there.
        self.assertEqual(
            list(form.fields["class_id"].queryset), [self.class_a, self.class_b]
        )
        self.assertEqual(list(form.fields["year"].queryset), [self.year])
        self.assertNotContains(response, f'value="{self.class_other.pk}"')

    def test_options_endpoint_is_scoped(self):
        response = self.client.get(OPTIONS_URL, {"year": self.year.pk})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(
            [grade["id"] for grade in data["grades"]],
            [self.grade_1.pk, self.grade_2.pk],
        )
        self.assertEqual(
            [(c["id"], c["grade_id"]) for c in data["classes"]],
            [(self.class_a.pk, self.grade_1.pk), (self.class_b.pk, self.grade_2.pk)],
        )

    def test_options_endpoint_rejects_year_without_assignment(self):
        past_year = make_academic_year(
            start_date=jdatetime.date(1402, 7, 1), is_current=False
        )

        response = self.client.get(OPTIONS_URL, {"year": past_year.pk})

        self.assertEqual(response.status_code, 404)


class TeacherTamperingTests(ReportTestData):
    def assertRejected(self, response, field):
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_report"])
        self.assertIn(field, response.context["form"].errors)
        self.assertNotContains(response, "محتوای کلاس دیگر")
        self.assertNotContains(response, "محتوای معلم دیگر")

    def test_other_teachers_class_is_rejected(self):
        response = self.get(
            report_type="class", year=self.year.pk, class_id=self.class_other.pk
        )

        self.assertRejected(response, "class_id")

    def test_class_with_only_inactive_subject_is_rejected(self):
        response = self.get(
            report_type="class", year=self.year.pk, class_id=self.class_inactive_cs.pk
        )

        self.assertRejected(response, "class_id")

    def test_class_of_ended_assignment_is_rejected(self):
        response = self.get(
            report_type="class", year=self.year.pk, class_id=self.class_ended.pk
        )

        self.assertRejected(response, "class_id")

    def test_other_grade_is_rejected(self):
        response = self.get(report_type="grade", year=self.year.pk, grade=self.grade_3.pk)

        self.assertRejected(response, "grade")

    def test_pdf_of_rejected_class_is_not_generated(self):
        response = self.get(
            report_type="class",
            year=self.year.pk,
            class_id=self.class_other.pk,
            format="pdf",
        )

        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertRejected(response, "class_id")

    def test_malformed_ids_are_form_errors_not_500(self):
        response = self.get(report_type="class", year="abc", class_id="x")

        self.assertEqual(response.status_code, 200)
        self.assertIn("year", response.context["form"].errors)
        self.assertIn("class_id", response.context["form"].errors)


class TeacherReportContentTests(ReportTestData):
    def test_class_report_contains_only_own_subjects(self):
        response = self.get(report_type="class", year=self.year.pk, class_id=self.class_a.pk)

        self.assertTrue(response.context["has_report"])
        subjects = response.context["subjects"]
        self.assertEqual(
            sorted(s["name"] for s in subjects),
            sorted([self.math.subject.name, self.science.subject.name]),
        )
        self.assertEqual(
            {s["teacher_name"] for s in subjects},
            {self.teacher_user.get_full_name()},
        )
        self.assertContains(response, "جلسه ریاضی")
        self.assertNotContains(response, "محتوای معلم دیگر")

    def test_grade_report_contains_only_own_classes_and_sessions(self):
        response = self.get(report_type="grade", year=self.year.pk)

        self.assertTrue(response.context["has_report"])
        grades = response.context["grades_data"]
        self.assertEqual(
            [(g["grade_name"], [c["class_name"] for c in g["classes"]]) for g in grades],
            [
                (self.grade_1.name, [self.class_a.section]),
                (self.grade_2.name, [self.class_b.section]),
            ],
        )
        self.assertContains(response, "جلسه ریاضی")
        self.assertContains(response, "جلسه هنر")
        self.assertNotContains(response, "محتوای معلم دیگر")
        self.assertNotContains(response, "محتوای کلاس دیگر")

    def test_grade_report_filtered_by_grade(self):
        response = self.get(report_type="grade", year=self.year.pk, grade=self.grade_2.pk)

        grades = response.context["grades_data"]
        self.assertEqual([g["grade_name"] for g in grades], [self.grade_2.name])


class OtherRolesTests(ReportTestData):
    def test_anonymous_is_sent_to_login(self):
        self.client.logout()

        response = self.get()

        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={URL}",
            fetch_redirect_response=False,
        )

    def test_superuser_is_not_restricted(self):
        self.client.force_login(make_superuser())

        response = self.get(report_type="class", year=self.year.pk, class_id=self.class_a.pk)

        self.assertTrue(response.context["has_report"])
        self.assertEqual(len(response.context["subjects"]), 3)
        self.assertContains(response, "محتوای معلم دیگر")

        response = self.get(report_type="class", year=self.year.pk, class_id=self.class_other.pk)
        self.assertTrue(response.context["has_report"])


class TeacherEdgeCaseTests(TestCase):
    def assertScopeMessage(self, user, message):
        self.client.force_login(user)

        for params in ({}, {"report_type": "class", "year": 1, "class_id": 1, "format": "pdf"}):
            response = self.client.get(URL, params)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context["has_report"])
            self.assertContains(response, message)

    def test_teacher_user_without_staff(self):
        self.assertScopeMessage(make_user("teacher"), NO_TEACHER_PROFILE_MESSAGE)

    def test_staff_without_teacher_profile(self):
        self.assertScopeMessage(make_staff().user, NO_TEACHER_PROFILE_MESSAGE)

    def test_teacher_without_any_assignment(self):
        make_academic_year()
        teacher = make_teacher_profile()

        self.assertScopeMessage(teacher.staff.user, NO_ASSIGNMENT_MESSAGE)

    def test_options_endpoint_for_teacher_without_profile(self):
        self.client.force_login(make_user("teacher"))

        response = self.client.get(OPTIONS_URL, {"year": 1})

        self.assertEqual(response.status_code, 404)

    def test_teacher_with_only_a_past_year_gets_that_year(self):
        make_academic_year()  # current, no assignment in it
        past_year = make_academic_year(
            start_date=jdatetime.date(1402, 7, 1), is_current=False
        )
        teacher = make_teacher_profile()
        make_assignment(teacher, make_branch(), past_year)
        self.client.force_login(teacher.staff.user)

        response = self.client.get(URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].selected_year, past_year)
        self.assertIn("scope_notice", response.context)


class QueryCountTests(ReportTestData):
    def scope(self):
        return ReportScope(self.teacher_user)

    def test_class_report_query_count_is_fixed(self):
        school_class = SchoolClass.objects.select_related("grade", "year").get(
            pk=self.class_a.pk
        )
        scope = self.scope()

        # class subjects (with subject/teacher joined) + their sessions
        # (with content joined), however many subjects and sessions.
        with self.assertNumQueries(2):
            build_class_report(scope, school_class)

    def test_grade_report_query_count_is_fixed(self):
        scope = self.scope()

        # classes + sessions, instead of one query per grade and class.
        with self.assertNumQueries(2):
            build_grade_report(scope, self.year)

    def count_queries(self, params):
        with CaptureQueriesContext(connection) as queries:
            response = self.get(**params)
        self.assertTrue(response.context["has_report"])
        return len(queries)

    def test_page_query_count_does_not_grow_with_data(self):
        class_params = {
            "report_type": "class", "year": self.year.pk, "class_id": self.class_a.pk,
        }
        grade_params = {"report_type": "grade", "year": self.year.pk}
        # The first request of a session also stores the default branch
        # (BranchMiddleware); keep that one-off write out of the count.
        self.get()
        before = (self.count_queries(class_params), self.count_queries(grade_params))

        assignment = self.math.teacher_assignment
        for day in range(10, 20):
            make_session(self.math, day)
            make_session(self.science, day)
        extra_class = make_school_class(self.branch, self.grade_1, self.year)
        for _ in range(3):
            make_session(make_class_subject(extra_class, make_subject(), assignment), 5)

        after = (self.count_queries(class_params), self.count_queries(grade_params))

        self.assertEqual(before, after)

