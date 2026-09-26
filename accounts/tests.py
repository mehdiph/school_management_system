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
