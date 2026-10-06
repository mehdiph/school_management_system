"""
Who may open the director panel: the director and superusers. Everyone
else is sent to their own dashboard (like the teacher and student
panels), logged-out users to the login page, and the panel accepts no
writes.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.utils import role_dashboard
from core.testing import make_superuser, make_user
from accounts.models import User

#: Every page of the panel.
PAGES = ("director:dashboard", "director:execution", "director:attendance")


class DirectorAccessTests(TestCase):
    def assert_allowed(self, user):
        self.client.force_login(user)
        for name in PAGES:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_director_and_superuser_are_allowed(self):
        self.assert_allowed(make_user(User.Roles.DIRECTOR))
        self.assert_allowed(make_superuser())

    def test_logged_out_users_go_to_the_login_page(self):
        for name in PAGES:
            response = self.client.get(reverse(name))
            self.assertRedirects(
                response, f"{reverse('accounts:login')}?next={reverse(name)}",
                fetch_redirect_response=False,
            )

    def test_every_other_role_goes_to_its_own_dashboard(self):
        others = [role for role in User.Roles.values if role != User.Roles.DIRECTOR]
        self.assertEqual(len(others), 8)

        for role in others:
            for is_staff in (False, True):
                user = make_user(role, is_staff=is_staff)
                self.client.force_login(user)
                for name in PAGES:
                    with self.subTest(role=role, is_staff=is_staff, page=name):
                        response = self.client.get(reverse(name))
                        self.assertRedirects(
                            response, reverse(role_dashboard(user)),
                            fetch_redirect_response=False,
                        )

    def test_the_panel_is_read_only(self):
        self.client.force_login(make_user(User.Roles.DIRECTOR))
        for name in PAGES:
            for method in ("post", "put", "patch", "delete"):
                with self.subTest(page=name, method=method):
                    response = getattr(self.client, method)(reverse(name))
                    self.assertEqual(response.status_code, 405)

    def test_the_director_lands_on_the_panel_after_login(self):
        user = make_user(User.Roles.DIRECTOR, password="test-pass-123")

        response = self.client.post(reverse("accounts:login"), {
            "username": user.username,
            "password": "test-pass-123",
            "role": User.Roles.DIRECTOR,
        })

        self.assertRedirects(response, reverse("director:dashboard"), fetch_redirect_response=False)

    def test_the_sidebar_shows_the_director_menu(self):
        self.client.force_login(make_user(User.Roles.DIRECTOR))

        response = self.client.get(reverse("director:dashboard"))

        self.assertContains(response, f'href="{reverse("director:dashboard")}"')

    def test_role_labels(self):
        self.assertEqual(User.Roles.DIRECTOR.label, "مدیر مدرسه")
        self.assertEqual(User.Roles.ADMIN.label, "مدیر سامانه")
