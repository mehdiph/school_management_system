"""
Tests for the attendance page: what it renders (shell, one radio group
per student, existing records in edit mode) and that the POST data it
sends -- "status-<enrollment id>" radios plus the optional
"description-<enrollment id>" -- is saved as before.
"""

import jdatetime
from django.test import TestCase
from django.urls import reverse

from attendance.models import Attendance
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
)
from supervisor.models import SupervisorClass
from teaching.models import SchoolSession


def make_enrolled_student(school_class, first_name, last_name):
    student = make_student()
    student.user.first_name = first_name
    student.user.last_name = last_name
    student.user.save()
    return make_enrollment(student, school_class)


class AttendanceViewTestCase(TestCase):

    def setUp(self):
        self.teacher = make_teacher_profile()
        branch = make_branch()
        year = make_academic_year()
        self.school_class = make_school_class(branch, make_grade(), year)
        self.class_subject = make_class_subject(
            self.school_class, make_subject(), make_assignment(self.teacher, branch, year)
        )
        self.session = SchoolSession.objects.create(
            class_subject=self.class_subject, date=jdatetime.date(1403, 8, 1)
        )
        # created out of order: the page lists them by last name
        self.second = make_enrolled_student(self.school_class, 'علی', 'موسوی')
        self.first = make_enrolled_student(self.school_class, 'سارا', 'احمدی')

        self.client.force_login(self.teacher.staff.user)
        self.url = reverse('attendance:attendance_form', args=[self.session.pk])
        self.branch = branch


class AttendancePageTests(AttendanceViewTestCase):

    def test_uses_the_teacher_shell_not_the_old_navbar(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'teacher/base.html')
        self.assertContains(response, 'id="teacherSidebar"')
        self.assertContains(response, 'class="ui-topbar"')
        self.assertNotContains(response, 'nav-info')
        self.assertContains(response, 'attendance/js/attendance.js')

    def test_one_radio_group_per_student_sorted_by_last_name(self):
        response = self.client.get(self.url)
        html = response.content.decode()

        for enrollment in (self.first, self.second):
            for value in ('present', 'absent', 'late'):
                self.assertIn(f'name="status-{enrollment.pk}" value="{value}"', html)
            self.assertIn(f'name="description-{enrollment.pk}"', html)

        self.assertLess(html.index('سارا احمدی'), html.index('علی موسوی'))
        # the search box is client-side only: it must never be posted
        self.assertNotIn('name="search', html)
        self.assertEqual(html.count('name="csrfmiddlewaretoken"'), 1)

    def test_new_attendance_defaults_to_present(self):
        response = self.client.get(self.url)

        self.assertEqual(
            [student.current_status for student in response.context['students']],
            ['present', 'present'],
        )

    def test_edit_mode_shows_recorded_status_and_description(self):
        Attendance.objects.create(
            session=self.session,
            student_enrollment=self.second,
            status=Attendance.AttendanceStatus.ABSENT,
            description='بیمار بود',
        )

        response = self.client.get(self.url)

        html = response.content.decode()
        self.assertRegex(html, rf'name="status-{self.second.pk}" value="absent"\s+checked')
        self.assertNotRegex(html, rf'name="status-{self.second.pk}" value="present"\s+checked')
        self.assertContains(response, 'بیمار بود</textarea>')

    def test_class_without_students_shows_empty_state(self):
        Attendance.objects.all().delete()
        self.first.delete()
        self.second.delete()

        response = self.client.get(self.url)

        self.assertContains(response, 'دانش‌آموزی در این کلاس ثبت‌نام نشده است')
        self.assertNotContains(response, 'id="attendanceForm"')


class AttendanceSubmitTests(AttendanceViewTestCase):

    def post(self, data):
        return self.client.post(self.url, data)

    def test_post_saves_status_and_redirects_to_session_list(self):
        response = self.post({
            f'status-{self.first.pk}': 'present',
            f'status-{self.second.pk}': 'late',
            f'description-{self.second.pk}': '  ده دقیقه تاخیر  ',
        })

        self.assertRedirects(
            response,
            reverse('teaching:session_list', args=[self.class_subject.pk]),
            fetch_redirect_response=False,
        )
        saved = {
            record.student_enrollment_id: (record.status, record.description)
            for record in Attendance.objects.filter(session=self.session)
        }
        self.assertEqual(saved, {
            self.first.pk: ('present', ''),
            self.second.pk: ('late', 'ده دقیقه تاخیر'),
        })

    def test_post_updates_existing_record(self):
        Attendance.objects.create(
            session=self.session, student_enrollment=self.first, status='absent'
        )

        self.post({f'status-{self.first.pk}': 'present'})

        record = Attendance.objects.get(session=self.session, student_enrollment=self.first)
        self.assertEqual(record.status, 'present')
        self.assertEqual(Attendance.objects.filter(session=self.session).count(), 1)

    def test_post_without_description_keeps_the_old_one(self):
        Attendance.objects.create(
            session=self.session,
            student_enrollment=self.first,
            status='absent',
            description='بیمار بود',
        )

        # the old page's POST: status radios only
        self.post({f'status-{self.first.pk}': 'late'})

        record = Attendance.objects.get(session=self.session, student_enrollment=self.first)
        self.assertEqual((record.status, record.description), ('late', 'بیمار بود'))

    def test_unknown_or_missing_status_is_skipped(self):
        self.post({f'status-{self.first.pk}': 'excused'})

        self.assertFalse(Attendance.objects.exists())


class AttendanceAccessTests(AttendanceViewTestCase):
    """Only the session's teacher, its class's supervisor or an admin of its branch."""

    def post_absent(self):
        return self.client.post(self.url, {f'status-{self.first.pk}': 'absent'})

    def assert_denied(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.post_absent().status_code, 404)
        self.assertFalse(Attendance.objects.exists())

    def test_logged_out_user_is_sent_to_login(self):
        self.client.logout()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response['Location'])
        self.post_absent()
        self.assertFalse(Attendance.objects.exists())

    def test_another_teacher_gets_404(self):
        self.client.force_login(make_teacher_profile().staff.user)

        self.assert_denied()

    def test_student_gets_404(self):
        self.client.force_login(self.first.student.user)

        self.assert_denied()

    def test_supervisor_of_the_class_may_save_and_stays_on_the_page(self):
        supervisor = make_supervisor(self.branch, self.school_class.grade)
        SupervisorClass.objects.create(supervisor=supervisor, school_class=self.school_class)
        self.client.force_login(supervisor.user)

        self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.post_absent()

        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.assertTrue(Attendance.objects.filter(status='absent').exists())

    def test_supervisor_of_another_class_gets_404(self):
        supervisor = make_supervisor(self.branch, self.school_class.grade)
        self.client.force_login(supervisor.user)

        self.assert_denied()

    def test_superuser_may_save(self):
        self.client.force_login(make_superuser())

        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.post_absent()
        self.assertTrue(Attendance.objects.exists())

    def test_staff_admin_needs_the_permission_and_the_branch(self):
        staff = make_staff(is_staff=True)
        self.client.force_login(staff.user)
        make_branch_access(staff, self.branch)
        self.assert_denied()  # no permission yet

        grant_all_model_permissions(staff.user)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_staff_admin_of_another_branch_gets_404(self):
        staff = make_staff(is_staff=True)
        grant_all_model_permissions(staff.user)
        make_branch_access(staff, make_branch())
        self.client.force_login(staff.user)

        self.assert_denied()
