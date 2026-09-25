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
