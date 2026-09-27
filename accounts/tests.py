from django.test import TestCase
from django.urls import reverse

from core.testing import make_superuser, make_user

LOGIN_URL = reverse('accounts:login')


class LoginRedirectTests(TestCase):
    """An already logged-in user opening the login page is sent onwards, never a 500."""

    def assertLoginPageRedirects(self, user, target):
        self.client.force_login(user)

        response = self.client.get(LOGIN_URL)

        self.assertRedirects(response, reverse(target), fetch_redirect_response=False)

    def test_roles_with_a_dashboard(self):
        for role, target in (
            ('teacher', 'core:dashboard'),
            ('student', 'student:dashboard'),
            ('supervisor', 'supervisor:dashboard'),
        ):
            with self.subTest(role=role):
                self.assertLoginPageRedirects(make_user(role), target)

    def test_superuser_without_role_goes_to_admin(self):
        user = make_superuser()
        user.role = ''
        user.save()

        self.assertLoginPageRedirects(user, 'admin:index')

    def test_role_without_dashboard_goes_to_website(self):
        self.assertLoginPageRedirects(make_user('accountant'), 'website:website')

    def test_login_post_for_role_without_dashboard(self):
        user = make_user('accountant', password='test-pass-123')

        response = self.client.post(
            LOGIN_URL,
            {'username': user.username, 'password': 'test-pass-123', 'role': 'accountant'},
        )

        self.assertRedirects(
            response, reverse('website:website'), fetch_redirect_response=False
        )


# ---------------------------------------------------------------------------
# Avatars: User.avatar_url / User.initials and partials/avatar.html
# ---------------------------------------------------------------------------

import re  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

import jdatetime  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.test import override_settings  # noqa: E402

from accounts.models import User  # noqa: E402
from core.testing import (  # noqa: E402
    make_academic_year,
    make_assignment,
    make_branch,
    make_class_subject,
    make_enrollment,
    make_grade,
    make_school_class,
    make_student,
    make_subject,
    make_teacher_profile,
)

#: 1x1 GIF, enough for ImageField validation.
PIXEL = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04"
    b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)
MISSING_AVATAR = 'users/avatars/deleted-from-disk.png'


class AvatarAccessorTests(TestCase):

    def test_no_avatar(self):
        for value in (None, ''):
            with self.subTest(value=value):
                self.assertIsNone(User(username='u', avatar=value).avatar_url)

    def test_missing_file_still_gets_a_url_without_touching_storage(self):
        user = User(username='u', avatar=MISSING_AVATAR)
        self.assertEqual(user.avatar_url, '/media/' + MISSING_AVATAR)

    def test_initials_fall_back_to_last_name_then_username(self):
        self.assertEqual(User(username='ali99', first_name='مریم', last_name='حسینی').initials, 'م')
        self.assertEqual(User(username='ali99', first_name='  ', last_name='حسینی').initials, 'ح')
        self.assertEqual(User(username='ali99').initials, 'A')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AvatarRenderingTests(TestCase):
    """
    Every avatar state renders the student dashboard, the teacher
    dashboard and the header (shared by both) with a 200.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp()
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_root)
        cls.media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        branch = make_branch()
        year = make_academic_year(start_date=jdatetime.date(1405, 7, 1), is_current=True)
        school_class = make_school_class(branch, make_grade(), year)

        teacher = make_teacher_profile()
        assignment = make_assignment(teacher, branch, year)
        make_class_subject(
            school_class, make_subject(), assignment,
            jdatetime.date(1405, 7, 1), jdatetime.date(1406, 3, 31),
        )
        self.teacher = teacher.staff.user

        student = make_student()
        make_enrollment(student, school_class)
        self.student = student.user

        for user, first, last in ((self.teacher, 'سعید', 'معروف'), (self.student, 'محمد', 'تقی‌زاده')):
            user.first_name, user.last_name = first, last
            user.save()

    def pages(self):
        return (
            (self.student, reverse('student:dashboard')),
            (self.teacher, reverse('core:dashboard')),
        )

    def render(self, user, url):
        self.client.force_login(user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        header = re.search(r'<header class="main-header">(.*?)</header>', html, re.S).group(1)
        return html, header

    def test_no_avatar(self):
        for user, url in self.pages():
            with self.subTest(url=url):
                html, header = self.render(user, url)
                initial = f'<span class="avatar__initial" aria-hidden="true">{user.first_name[0]}</span>'
                self.assertIn(initial, header)
                self.assertNotIn('avatar__img', html)

    def test_avatar_file_missing_from_media_root(self):
        User.objects.filter(pk__in=[self.student.pk, self.teacher.pk]).update(avatar=MISSING_AVATAR)

        for user, url in self.pages():
            with self.subTest(url=url):
                html, header = self.render(user, url)
                # The browser gets the URL; onerror swaps in the (hidden) initial.
                self.assertIn(f'src="/media/{MISSING_AVATAR}"', header)
                self.assertIn('onerror="this.hidden = true;', header)
                self.assertIn(
                    f'<span class="avatar__initial" aria-hidden="true" hidden>{user.first_name[0]}</span>',
                    header,
                )

    def test_valid_avatar(self):
        for user in (self.student, self.teacher):
            user.avatar = SimpleUploadedFile('face.gif', PIXEL, content_type='image/gif')
            user.save()

        for user, url in self.pages():
            with self.subTest(url=url):
                html, header = self.render(user, url)
                self.assertIn(f'src="{user.avatar.url}"', header)
                self.assertIn(f'alt="{user.get_full_name()}"', html)
                # Fixed intrinsic size, so the layout does not shift while it loads.
                self.assertRegex(header, r'width="\d+"\s+height="\d+"')

    def test_user_without_first_name(self):
        User.objects.filter(pk__in=[self.student.pk, self.teacher.pk]).update(first_name='')

        for user, url in self.pages():
            with self.subTest(url=url):
                html, header = self.render(user, url)
                self.assertIn(
                    f'<span class="avatar__initial" aria-hidden="true">{user.last_name[0]}</span>',
                    header,
                )


# ---------------------------------------------------------------------------
# National code, normalisation
# ---------------------------------------------------------------------------

from io import BytesIO  # noqa: E402

from django.contrib.admin.models import LogEntry  # noqa: E402
from django.core.exceptions import ValidationError  # noqa: E402
from django.test import SimpleTestCase  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402

from accounts.user_import import (  # noqa: E402
    FileRejected,
    normalize_text,
    parse_gender,
    parse_grade_level,
    run_import,
)
from accounts.user_import_template import build_template  # noqa: E402
from accounts.validators import (  # noqa: E402
    NotNationalCodePasswordValidator,
    is_valid_national_code,
    normalize_national_code,
    validate_national_code,
)
from school.models import AcademicYear, SchoolClass  # noqa: E402
from staff.models import BranchAccess, Staff, TeacherAssignment  # noqa: E402
from student.models.student_enrollment import StudentEnrollment  # noqa: E402
from supervisor.models.supervisor_profile import SupervisorProfile  # noqa: E402

FAST_HASHER = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


def national_code(prefix):
    """A valid national code from 9 digits (adds the check digit)."""
    remainder = sum(int(prefix[i]) * (10 - i) for i in range(9)) % 11
    return prefix + str(remainder if remainder < 2 else 11 - remainder)


CODE_A = national_code('412345678')
CODE_B = national_code('512345678')
CODE_ZERO = national_code('001234567')  # leading zeros


class NationalCodeTests(SimpleTestCase):

    def test_checksum(self):
        for code in (CODE_A, CODE_B, CODE_ZERO, '0499370899'):
            with self.subTest(code=code):
                self.assertTrue(is_valid_national_code(code))
                validate_national_code(code)

    def test_rejects(self):
        wrong_check = CODE_A[:9] + str((int(CODE_A[9]) + 1) % 10)
        for code in (wrong_check, '1111111111', '0000000000', '123456789', '12345678901', 'abcdefghij', ''):
            with self.subTest(code=code):
                self.assertFalse(is_valid_national_code(code))
                with self.assertRaises(ValidationError):
                    validate_national_code(code)

    def test_normalize(self):
        self.assertEqual(normalize_national_code(int(CODE_ZERO)), CODE_ZERO)          # Excel number
        self.assertEqual(normalize_national_code(float(int(CODE_ZERO))), CODE_ZERO)   # 12345678.0
        self.assertEqual(normalize_national_code('۰۰۱۲۳۴۵۶۷' + '٩'), '0012345679')   # Persian/Arabic digits
        self.assertEqual(normalize_national_code(' 001-234-5679 '), '0012345679')
        self.assertEqual(normalize_national_code(None), '')
        self.assertEqual(normalize_national_code('12345678901'), '12345678901')  # not truncated

    def test_user_field_uses_the_validator(self):
        field = User._meta.get_field('national_code')
        with self.assertRaises(ValidationError):
            field.clean('1234567890', User())
        self.assertEqual(field.clean(CODE_A, User()), CODE_A)


class NormalizationTests(SimpleTestCase):

    def test_text(self):
        self.assertEqual(normalize_text('  علي   رضايي '), 'علی رضایی')
        self.assertEqual(normalize_text('كلاس ۲'), 'کلاس 2')
        self.assertEqual(normalize_text('٣'), '3')
        self.assertEqual(normalize_text(3.0), '3')
        self.assertEqual(normalize_text(None), '')
        self.assertEqual(normalize_text('محمد‌رضا'), 'محمد‌رضا')  # ZWNJ kept

    def test_grade(self):
        for value in (3, 3.0, '3', '۳', 'سوم', 'پایه سوم'):
            with self.subTest(value=value):
                self.assertEqual(parse_grade_level(value), 3)
        self.assertIsNone(parse_grade_level('سه‌ام'))

    def test_gender(self):
        self.assertEqual(parse_gender('پسر'), Staff.Gender.MALE)
        self.assertEqual(parse_gender('Female'), Staff.Gender.FEMALE)
        self.assertEqual(parse_gender(''), '')
        self.assertIsNone(parse_gender('نامشخص'))


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

HEADERS = {
    'student': ['نام', 'نام خانوادگی', 'کد ملی', 'کد شعبه', 'پایه', 'کلاس'],
    'teacher': ['نام', 'نام خانوادگی', 'کد ملی', 'کد شعبه', 'جنسیت'],
    'supervisor': ['نام', 'نام خانوادگی', 'کد ملی', 'کد شعبه', 'پایه'],
}


def xlsx(rows, headers):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return SimpleUploadedFile('users.xlsx', buffer.getvalue())


@FAST_HASHER
class UserImportTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.admin = make_superuser()
        cls.branch = make_branch(name='b1')
        cls.year = make_academic_year(start_date=jdatetime.date(1405, 7, 1), is_current=True)
        cls.grade = make_grade(level=3)
        cls.school_class = make_school_class(cls.branch, cls.grade, cls.year)
        cls.school_class.section = 'یک'
        cls.school_class.save()

    def run_file(self, role, rows, headers=None):
        return run_import(xlsx(rows, headers or HEADERS[role]), role, self.admin)

    def test_student(self):
        result = self.run_file('student', [['علي', 'رضايي', CODE_A, 'b1', '۳', 'يک']])

        self.assertTrue(result.committed)
        user = User.objects.get(username=CODE_A)
        self.assertEqual((user.national_code, user.first_name, user.last_name, user.role),
                         (CODE_A, 'علی', 'رضایی', 'student'))
        self.assertTrue(user.check_password(CODE_A))
        self.assertTrue(user.must_change_password)
        self.assertFalse(user.is_staff)
        self.assertIsNone(user.student_profile.student_code)
        enrollment = StudentEnrollment.objects.get(student__user=user)
        self.assertEqual((enrollment.school_class, enrollment.academic_year, enrollment.status),
                         (self.school_class, self.year, 'active'))
        self.assertEqual(LogEntry.objects.filter(user=self.admin).count(), 1)

    def test_teacher(self):
        self.run_file('teacher', [['سارا', 'احمدی', CODE_A, 'b1', 'دختر'], ['علی', 'کریمی', CODE_B, 'b1', '']])

        staff = Staff.objects.get(user__national_code=CODE_A)
        self.assertEqual(staff.gender, 'female')
        self.assertEqual(Staff.objects.get(user__national_code=CODE_B).gender, '')
        assignment = TeacherAssignment.objects.get(teacher__staff=staff)
        self.assertEqual((assignment.branch, assignment.academic_year, assignment.hire_date, assignment.status),
                         (self.branch, self.year, self.year.start_date, 'active'))
        self.assertTrue(BranchAccess.objects.filter(staff=staff, branch=self.branch, is_default=True).exists())
        self.assertEqual(staff.user.role, 'teacher')

    def test_teacher_file_without_optional_gender_column(self):
        result = self.run_file('teacher', [['سارا', 'احمدی', CODE_A, 'b1']], headers=HEADERS['teacher'][:4])
        self.assertTrue(result.committed)

    def test_supervisor(self):
        self.run_file('supervisor', [['رضا', 'نوری', CODE_A, 'b1', 'سوم']])

        profile = SupervisorProfile.objects.get(user__national_code=CODE_A)
        self.assertEqual((profile.branch, profile.grade, profile.user.role), (self.branch, self.grade, 'supervisor'))

    def test_existing_user_is_skipped_and_untouched(self):
        existing = make_user('teacher')
        existing.national_code, existing.first_name = CODE_A, 'قبلی'
        existing.save()

        result = self.run_file('student', [
            ['جدید', 'نام', CODE_A, 'b1', 3, 'یک'],
            ['دیگر', 'نام', CODE_B, 'b1', 3, 'یک'],
        ])

        self.assertTrue(result.committed)
        self.assertEqual([row.number for row in result.skipped], [2])
        existing.refresh_from_db()
        self.assertEqual((existing.first_name, existing.role), ('قبلی', 'teacher'))
        self.assertFalse(existing.must_change_password)
        self.assertTrue(User.objects.filter(username=CODE_B).exists())

    def test_existing_enrollment_is_skipped(self):
        self.run_file('student', [['علی', 'رضایی', CODE_A, 'b1', 3, 'یک']])

        result = self.run_file('student', [['علی', 'رضایی', CODE_A, 'b1', 3, 'یک']])

        self.assertEqual(len(result.created), 0)
        self.assertIn('ثبت‌نام دارد', result.skipped[0].reasons[0])
        self.assertEqual(StudentEnrollment.objects.filter(student__user__username=CODE_A).count(), 1)

    def test_any_error_rolls_back_everything(self):
        result = self.run_file('student', [
            ['علی', 'رضایی', CODE_A, 'b1', 3, 'یک'],
            ['سارا', 'احمدی', CODE_B, 'b1', 3, 'دو'],  # no such class
        ])

        self.assertFalse(result.committed)
        self.assertEqual([row.number for row in result.errors], [3])
        self.assertIn('کلاس «دو»', result.errors[0].reasons[0])
        self.assertFalse(User.objects.filter(username__in=[CODE_A, CODE_B]).exists())
        self.assertEqual(SchoolClass.objects.count(), 1)  # never auto-created

    def test_duplicate_code_in_file(self):
        result = self.run_file('student', [
            ['علی', 'رضایی', CODE_A, 'b1', 3, 'یک'],
            ['سارا', 'احمدی', f'{CODE_A[:3]}-{CODE_A[3:]}', 'b1', 3, 'یک'],
        ])

        self.assertEqual([row.number for row in result.errors], [2, 3])
        self.assertIn('تکراری', result.errors[0].reasons[0])
        self.assertFalse(User.objects.filter(username=CODE_A).exists())

    def test_leading_zero_code_given_as_number(self):
        self.run_file('student', [['علی', 'رضایی', int(CODE_ZERO), 'b1', 3, 'یک']])

        self.assertTrue(User.objects.filter(username=CODE_ZERO, national_code=CODE_ZERO).exists())

    def test_row_errors(self):
        make_branch(name='closed', is_active=False)
        result = self.run_file('teacher', [
            ['', 'احمدی', CODE_A, 'b1', ''],
            ['سارا', 'احمدی', '1234567890', 'b1', ''],
            ['سارا', 'احمدی', CODE_B, 'nope', ''],
            ['سارا', 'احمدی', national_code('612345678'), 'closed', ''],
            ['سارا', 'احمدی', national_code('712345678'), 'b1', 'نامشخص'],
        ])

        reasons = {row.number: ' '.join(row.reasons) for row in result.errors}
        self.assertIn('«نام» خالی است', reasons[2])
        self.assertIn('نامعتبر', reasons[3])
        self.assertIn('وجود ندارد', reasons[4])
        self.assertIn('غیرفعال', reasons[5])
        self.assertIn('جنسیت', reasons[6])
        self.assertEqual(User.objects.filter(role='teacher').count(), 0)

    def test_empty_rows_are_ignored(self):
        result = self.run_file('student', [[None] * 6, ['علی', 'رضایی', CODE_A, 'b1', 3, 'یک'], ['', '  ', '', '', '', '']])
        self.assertEqual(len(result.rows), 1)

    def test_wrong_headers_rejected(self):
        with self.assertRaisesMessage(FileRejected, 'سرستون'):
            self.run_file('supervisor', [['علی', 'رضایی', CODE_A, 'b1', 3, 'یک']], headers=HEADERS['student'])

    def test_needs_exactly_one_current_year(self):
        AcademicYear.objects.update(is_current=False)
        with self.assertRaisesMessage(FileRejected, 'جاری'):
            self.run_file('student', [['علی', 'رضایی', CODE_A, 'b1', 3, 'یک']])

    def test_not_an_excel_file(self):
        with self.assertRaises(FileRejected):
            run_import(SimpleUploadedFile('x.xlsx', b'not a zip'), 'student', self.admin)


@FAST_HASHER
class UserImportAdminTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.branch = make_branch(name='b1')
        make_academic_year(start_date=jdatetime.date(1405, 7, 1), is_current=True)
        make_grade(level=3)

    def setUp(self):
        self.client.force_login(make_superuser())

    def test_changelist_button_and_page(self):
        self.assertContains(self.client.get(reverse('admin:accounts_user_changelist')), 'ورود گروهی از اکسل')
        response = self.client.get(reverse('admin:accounts_user_import'))
        self.assertContains(response, 'type="file"')
        self.assertContains(response, 'accept=".xlsx')

    def test_staff_without_add_user_is_forbidden(self):
        self.client.force_login(make_user('admin', is_staff=True))
        self.assertEqual(self.client.get(reverse('admin:accounts_user_import')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:accounts_user_import_template', args=['student'])).status_code, 403)

    def test_upload_shows_result(self):
        response = self.client.post(reverse('admin:accounts_user_import'), {
            'role': 'supervisor',
            'file': xlsx([['رضا', 'نوری', CODE_A, 'b1', 3]], HEADERS['supervisor']),
        })
        self.assertContains(response, 'ورود گروهی پشتیبان انجام شد')
        self.assertTrue(User.objects.filter(username=CODE_A).exists())

    def test_rejects_non_xlsx(self):
        response = self.client.post(reverse('admin:accounts_user_import'), {
            'role': 'student', 'file': SimpleUploadedFile('users.csv', b'a,b'),
        })
        self.assertContains(response, 'فقط فایل')

    def test_template_download(self):
        response = self.client.get(reverse('admin:accounts_user_import_template', args=['teacher']))

        self.assertEqual(response['Content-Disposition'], 'attachment; filename="user-import-teacher.xlsx"')
        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook.worksheets[0]
        self.assertEqual([cell.value for cell in sheet[1]], HEADERS['teacher'])
        self.assertEqual(sheet['C2'].number_format, '@')
        self.assertTrue(sheet.sheet_view.rightToLeft)
        ranges = {str(v.sqref).split(':')[0] for v in sheet.data_validations.dataValidation}
        self.assertEqual(ranges, {'D2', 'E2'})  # branch, gender
        self.assertEqual(workbook['lists']['A1'].value, 'b1')

    def test_unknown_role_template_is_404(self):
        self.assertEqual(self.client.get(reverse('admin:accounts_user_import_template', args=['x'])).status_code, 404)


# ---------------------------------------------------------------------------
# Forced password change
# ---------------------------------------------------------------------------


@FAST_HASHER
class ForcedPasswordChangeTests(TestCase):

    def setUp(self):
        self.user = make_user('teacher')
        self.user.national_code = CODE_A
        self.user.set_password(CODE_A)
        self.user.must_change_password = True
        self.user.save()
        self.change_url = reverse('accounts:password_change')

    def test_login_goes_to_password_change(self):
        response = self.client.post(LOGIN_URL, {'username': self.user.username, 'password': CODE_A, 'role': 'teacher'})
        self.assertRedirects(response, self.change_url, fetch_redirect_response=False)

    def test_every_page_redirects_until_changed(self):
        self.client.force_login(self.user)
        for url in (reverse('core:dashboard'), reverse('student:dashboard'), '/'):
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), self.change_url, fetch_redirect_response=False)

    def test_admin_login_path_too(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(reverse('admin:index')), self.change_url, fetch_redirect_response=False)

    def test_json_requests_get_403_with_error_code(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('student:session_list_json', args=['math']), HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error'], 'must_change_password')

    def test_exempt_paths(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.change_url).status_code, 200)
        response = self.client.get('/static/css/base.css')
        self.assertNotEqual(response.get('Location'), self.change_url)
        self.assertRedirects(self.client.get(reverse('accounts:logout')), LOGIN_URL, fetch_redirect_response=False)

    def test_national_code_is_refused_as_new_password(self):
        self.client.force_login(self.user)
        response = self.client.post(self.change_url, {
            'old_password': CODE_A, 'new_password1': CODE_A, 'new_password2': CODE_A,
        })
        self.assertContains(response, 'نباید با کد ملی یکسان باشد')
        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)

    def test_successful_change_clears_the_flag(self):
        self.client.force_login(self.user)
        response = self.client.post(self.change_url, {
            'old_password': CODE_A, 'new_password1': 'Kh0sh-Amadid-2026', 'new_password2': 'Kh0sh-Amadid-2026',
        })
        self.assertRedirects(response, reverse('core:dashboard'), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password('Kh0sh-Amadid-2026'))
        # Still logged in, and no longer redirected.
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_set_password_alone_does_not_clear_the_flag(self):
        self.user.set_password('something-else-123')
        self.user.save()
        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)

    def test_validator(self):
        validator = NotNationalCodePasswordValidator()
        user = User(national_code=CODE_ZERO)
        for password in (CODE_ZERO, CODE_ZERO.lstrip('0'), ' ۰۰' + CODE_ZERO[2:]):
            with self.subTest(password=password), self.assertRaises(ValidationError):
                validator.validate(password, user)
        validator.validate('x' + CODE_ZERO, user)  # merely containing it is fine
        validator.validate(CODE_ZERO, User())      # users without a code
