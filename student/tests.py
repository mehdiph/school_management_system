"""
Student pages are only for students: nobody else gets a 500 there.
Logged-out users go to the login page, other roles to their own
dashboard (the same place login sends them).
"""

import jdatetime
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.testing import (
    make_academic_year,
    make_branch,
    make_enrollment,
    make_grade,
    make_school_class,
    make_student,
    make_user,
)
from student.context_processors import student_info
from student.models.student_enrollment import StudentEnrollment
from student.selectors import current_enrollment, panel_enrollment

STUDENT_PAGES = (
    reverse('student:dashboard'),
    reverse('student:sessions'),
    reverse('student:session_list_json', args=['math']),
)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class StudentPagesAccessTests(TestCase):

    def assertRedirectsEverywhere(self, target):
        for url in STUDENT_PAGES:
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), target, fetch_redirect_response=False)

    def test_logged_out_goes_to_login(self):
        for url in STUDENT_PAGES:
            with self.subTest(url=url):
                self.assertRedirects(
                    self.client.get(url),
                    f"{reverse('accounts:login')}?next={url}",
                    fetch_redirect_response=False,
                )

    def test_other_roles_go_to_their_own_dashboard(self):
        for role, target in (
            ('teacher', 'core:dashboard'),
            ('supervisor', 'supervisor:dashboard'),
            ('accountant', 'website:website'),
        ):
            with self.subTest(role=role):
                self.client.force_login(make_user(role))
                self.assertRedirectsEverywhere(reverse(target))

    def test_staff_without_role_goes_to_admin(self):
        self.client.force_login(make_user('', is_staff=True))
        self.assertRedirectsEverywhere(reverse('admin:index'))

    def test_student_role_without_profile_is_forbidden_not_a_loop(self):
        self.client.force_login(make_user('student'))
        for url in STUDENT_PAGES:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_student_sees_the_dashboard(self):
        year = make_academic_year(start_date=jdatetime.date(1405, 7, 1), is_current=True)
        school_class = make_school_class(make_branch(), make_grade(), year)
        student = make_student()
        make_enrollment(student, school_class)
        self.client.force_login(student.user)

        self.assertEqual(self.client.get(reverse('student:dashboard')).status_code, 200)



class StudentInfoContextTests(TestCase):
    """
    The context processor runs on every page: a student account with no
    StudentProfile row must not break pages outside the student panel.
    """

    def context_for(self, user):
        request = RequestFactory().get('/')
        request.user = user
        return student_info(request)

    def test_student_without_profile_gets_no_student_info(self):
        self.assertEqual(self.context_for(make_user('student')), {})

    def test_student_without_profile_can_open_the_public_site(self):
        self.client.force_login(make_user('student'))

        self.assertEqual(self.client.get(reverse('website:website')).status_code, 200)

    def test_student_with_profile_still_gets_the_class(self):
        year = make_academic_year(start_date=jdatetime.date(1405, 7, 1), is_current=True)
        school_class = make_school_class(make_branch(), make_grade(), year)
        student = make_student()
        make_enrollment(student, school_class)

        context = self.context_for(student.user)

        self.assertEqual(context['student'], student.user)
        self.assertEqual(context['school_class'], school_class)

class StudentSessionJsonCalendarTests(TestCase):
    """Holiday sessions in the student's session list: flagged, no number, reason."""

    def test_holiday_is_flagged_with_its_reason(self):
        import jdatetime

        from core.testing import (
            make_academic_year, make_assignment, make_bell, make_branch, make_calendar_event,
            make_class_subject, make_enrollment, make_grade, make_school_class, make_student,
            make_subject, make_teacher_profile,
        )
        from teaching.models import SchoolSession

        year = make_academic_year()
        branch = make_branch()
        school_class = make_school_class(branch, make_grade(), year)
        teacher = make_teacher_profile()
        class_subject = make_class_subject(school_class, make_subject(), make_assignment(teacher, branch, year))
        bell = make_bell(1)
        event = make_calendar_event(year, jdatetime.date(1403, 8, 2), title='تاسوعا')
        SchoolSession.objects.create(class_subject=class_subject, date=jdatetime.date(1403, 8, 1), bell=bell)
        SchoolSession.objects.create(
            class_subject=class_subject, date=jdatetime.date(1403, 8, 2), bell=bell,
            status=SchoolSession.Status.HOLIDAY, calendar_event=event, is_auto_created=True,
        )
        student = make_student()
        make_enrollment(student, school_class)
        self.client.force_login(student.user)

        data = self.client.get(
            reverse('student:session_list_json', args=[class_subject.subject.slug])
        ).json()

        holiday, held = data['sessions']
        self.assertTrue(holiday['is_holiday'])
        self.assertEqual(holiday['reason'], 'تاسوعا')
        self.assertTrue(holiday['label'].startswith('تعطیل'))
        # the held session without content no longer breaks the endpoint
        self.assertFalse(held['is_holiday'])
        self.assertIn('اول', held['label'])


class EnrollmentStatesTests(TestCase):
    """A student has one enrolment per year, or none: no page may assume exactly one."""

    def setUp(self):
        self.branch = make_branch()
        self.grade = make_grade()
        self.old_year = make_academic_year(start_date=jdatetime.date(1404, 7, 1), is_current=False)
        self.year = make_academic_year(start_date=jdatetime.date(1405, 7, 1), is_current=True)
        self.old_class = make_school_class(self.branch, self.grade, self.old_year)
        self.school_class = make_school_class(self.branch, self.grade, self.year)
        self.student = make_student()
        self.client.force_login(self.student.user)

    def _pages_work(self):
        self.assertEqual(self.client.get(reverse('student:dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('student:sessions')).status_code, 200)

    def test_student_with_no_enrollment_gets_empty_pages_not_a_500(self):
        self._pages_work()
        response = self.client.get(reverse('student:dashboard'))
        self.assertContains(response, 'برای این حساب ثبت‌نامی پیدا نشد')
        self.assertEqual(response.context['student'], self.student.user)
        self.assertEqual(self.client.get(reverse('student:session_list_json', args=['math'])).status_code, 404)

    def test_student_with_two_years_gets_the_newest(self):
        make_enrollment(self.student, self.old_class)
        make_enrollment(self.student, self.school_class)
        self._pages_work()
        self.assertEqual(panel_enrollment(self.student).school_class, self.school_class)
        response = self.client.get(reverse('student:dashboard'))
        self.assertEqual(response.context['school_class'], self.school_class)
        self.assertNotContains(response, 'برای این حساب ثبت‌نامی پیدا نشد')

    def test_unknown_subject_is_a_404_not_a_500(self):
        make_enrollment(self.student, self.school_class)
        self.assertEqual(self.client.get(reverse('student:session_list_json', args=['nope'])).status_code, 404)

    def test_old_year_only_keeps_the_panel_but_is_not_current(self):
        make_enrollment(self.student, self.old_class)
        self._pages_work()
        self.assertEqual(panel_enrollment(self.student).school_class, self.old_class)
        self.assertIsNone(current_enrollment(self.student))

    def test_current_enrollment_states(self):
        enrollment = make_enrollment(self.student, self.school_class)
        self.assertEqual(current_enrollment(self.student), enrollment)

        for status in ('transferred', 'graduated', 'withdrawn'):
            with self.subTest(status=status):
                StudentEnrollment.objects.filter(pk=enrollment.pk).update(status=status)
                self.assertIsNone(current_enrollment(self.student))
        StudentEnrollment.objects.filter(pk=enrollment.pk).update(status='active')

        self.school_class.is_active = False
        self.school_class.save()
        self.assertIsNone(current_enrollment(self.student))
        self.school_class.is_active = True
        self.school_class.save()

        self.branch.is_active = False
        self.branch.save()
        self.assertIsNone(current_enrollment(self.student))

    def test_two_years_flagged_current_the_newest_wins(self):
        self.old_year.is_current = True
        self.old_year.save()
        make_enrollment(self.student, self.old_class)
        self.assertIsNone(current_enrollment(self.student))

        enrollment = make_enrollment(self.student, self.school_class)
        self.assertEqual(current_enrollment(self.student), enrollment)
