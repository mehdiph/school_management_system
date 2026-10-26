"""``blog.permissions``: the one place that says who can write, preview and publish (§6 of the plan)."""

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from accounts.models import User
from blog import permissions
from blog.models import Post
from blog.testing import grant, make_author, make_editor, make_post, make_section
from core.testing import make_staff, make_superuser, make_user


class WritingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s = make_section("پرورشی")
        cls.t = make_section("مشاوره")
        cls.closed = make_section("بسته", is_active=False)

    def assert_can_write(self, user, sections):
        user = User.objects.get(pk=user.pk) if user.is_authenticated else user
        self.assertEqual(permissions.can_write(user), bool(sections))
        self.assertEqual(list(permissions.writable_sections(user)), sections)

    def test_every_eligible_role_writes_in_its_granted_active_sections_only(self):
        for role in (User.Roles.TEACHER, User.Roles.COUNSELOR, User.Roles.SUPERVISOR, User.Roles.DIRECTOR, User.Roles.ADMIN):
            with self.subTest(role=role):
                author = make_author(role=role, sections=[self.s, self.closed])
                self.assert_can_write(author.user, [self.s])
                self.assertTrue(permissions.can_write_in(author.user, self.s))
                self.assertFalse(permissions.can_write_in(author.user, self.t))
                self.assertFalse(permissions.can_write_in(author.user, self.closed))

    def test_nobody_else_writes(self):
        self.assert_can_write(AnonymousUser(), [])
        for role in User.Roles.values:
            with self.subTest(role=role):
                self.assert_can_write(make_user(role), [])  # no BlogAuthor row
        self.assert_can_write(make_superuser(), [])
        self.assert_can_write(make_editor(), [])  # editing is not writing: editors use the admin

    def test_a_grant_never_overrides_the_role(self):
        for role in (User.Roles.STUDENT, User.Roles.ACCOUNTANT, User.Roles.IT, User.Roles.SERVICES):
            with self.subTest(role=role):
                author = make_author(sections=[self.s])
                author.user.role = role
                author.user.save()
                self.assert_can_write(author.user, [])

    def test_inactive_author_account_or_staff_record_stops_writing(self):
        author = make_author(sections=[self.s], is_active=False)
        self.assert_can_write(author.user, [])
        self.assertIn("خاموش", permissions.write_block_reason(author))

        author = make_author(sections=[self.s])
        author.user.is_active = False
        author.user.save()
        self.assert_can_write(author.user, [])

        staff = make_staff(role=User.Roles.TEACHER)
        author = make_author(user=staff.user, sections=[self.s])
        self.assert_can_write(author.user, [self.s])
        staff.is_active = False
        staff.save()
        self.assert_can_write(author.user, [])
        self.assertIn("پرسنلی", permissions.write_block_reason(author))

    def test_without_a_section_an_author_cannot_write_anywhere(self):
        author = make_author()
        self.assertTrue(permissions.can_write(author.user))
        self.assertEqual(list(permissions.writable_sections(author.user)), [])

    def test_author_posts_are_their_own_only(self):
        mine = make_author(sections=[self.s])
        theirs = make_author(sections=[self.s])
        own = make_post(mine)
        make_post(theirs)
        self.assertEqual(list(permissions.author_posts(mine.user)), [own])
        self.assertEqual(list(permissions.author_posts(make_user(User.Roles.TEACHER))), [])

    def test_an_author_edits_only_own_drafts_in_a_granted_section(self):
        mine = make_author(sections=[self.s])
        other = make_author(sections=[self.s])
        draft = make_post(mine)
        self.assertTrue(permissions.can_edit_as_author(mine.user, draft))
        self.assertFalse(permissions.can_edit_as_author(other.user, draft))
        for status in (Post.Status.SUBMITTED, Post.Status.PUBLISHED, Post.Status.ARCHIVED):
            with self.subTest(status=status):
                post = make_post(mine, status=status)
                self.assertFalse(permissions.can_edit_as_author(mine.user, post))
        in_t = make_post(mine, section=self.t)  # e.g. the grant was taken back
        self.assertFalse(permissions.can_edit_as_author(mine.user, in_t))


class EditorTests(TestCase):
    def test_editor_is_active_staff_with_publish_post(self):
        self.assertTrue(permissions.is_editor(make_editor()))
        self.assertTrue(permissions.is_editor(make_superuser()))

        staff = make_user(User.Roles.ADMIN, is_staff=True)
        self.assertFalse(permissions.is_editor(staff))
        self.assertFalse(permissions.is_editor(grant(staff, "change_post")))
        self.assertTrue(permissions.is_editor(grant(staff, "publish_post")))

        not_staff = grant(make_user(User.Roles.TEACHER), "publish_post")
        self.assertFalse(permissions.is_editor(not_staff))

        editor = make_editor()
        editor.is_active = False
        self.assertFalse(permissions.is_editor(editor))

    def test_preview_is_for_the_author_and_editors_only(self):
        section = make_section()
        author = make_author(sections=[section])
        post = make_post(author, status=Post.Status.SUBMITTED)
        self.assertTrue(permissions.can_preview(author.user, post))
        self.assertTrue(permissions.can_preview(make_editor(), post))
        self.assertFalse(permissions.can_preview(make_author(sections=[section]).user, post))
        self.assertFalse(permissions.can_preview(make_user(User.Roles.ADMIN, is_staff=True), post))
        self.assertFalse(permissions.can_preview(AnonymousUser(), post))

        author.is_active = False
        author.save()
        self.assertFalse(permissions.can_preview(User.objects.get(pk=author.user.pk), post))

    def test_author_lookup_is_one_query_per_request_user(self):
        author = make_author(sections=[make_section()])
        user = User.objects.get(pk=author.user.pk)
        with self.assertNumQueries(2):  # the author row, then the sections
            permissions.can_write(user)
            permissions.can_write(user)
            list(permissions.writable_sections(user))
