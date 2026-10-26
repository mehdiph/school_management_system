"""«نوشته‌های من»: the authoring area, every role against it (plan §6), and its ties to the panels."""

import re
from datetime import timedelta
from unittest import mock

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.utils import role_dashboard
from student.models import StudentProfile
from blog import permissions, services
from blog.models import BlogAuthor, Post, Tag
from blog.testing import make_author, make_category, make_editor, make_post, make_section, make_tag
from core.testing import make_branch, make_grade, make_staff, make_student, make_supervisor, make_teacher_profile, make_user
from website.test_about import TempMediaMixin
from website.tests import phone_photo

from .test_public import url

S = Post.Status
# blog.permissions.author_for: the author row of one user (a join on user_id doesn't count).
AUTHORSHIP_SQL = re.compile(r'"blog_blogauthor"\."user_id" = (%s|\d)')


def write(name, *args):
    return reverse(f"blog:{name}", args=args)


class WriteFixture(TestCase):
    """Two sections; a teacher author granted the first, with a draft; another author's draft."""

    @classmethod
    def setUpTestData(cls):
        cls.section = make_section("پرورشی")
        cls.other_section = make_section("مشاوره")
        staff = make_staff(role=User.Roles.TEACHER)
        make_teacher_profile(staff)
        cls.user = staff.user
        cls.user.first_name, cls.user.last_name = "مریم", "احمدی"
        cls.user.save()
        cls.author = make_author(user=cls.user, sections=[cls.section])
        cls.draft = make_post(cls.author, cls.section, title="پیش‌نویس من")
        cls.someone = make_author(sections=[cls.section, cls.other_section], role=User.Roles.COUNSELOR)
        cls.their_draft = make_post(cls.someone, cls.section, title="پیش‌نویس دیگری")

    def setUp(self):
        self.client.force_login(self.user)

    def form_data(self, **fields):
        data = {
            "section": self.section.pk,
            "title": "جشن پاییز",
            "body": "<p>بچه‌ها در حیاط جشن گرفتند.</p>",
            "excerpt": "",
            "category": "",
            "tag_names": "",
            "cover_alt": "",
            "meta_title": "",
            "meta_description": "",
            "slug": "",
            "action": "save",
        }
        data.update(fields)
        return data

    def reload(self, post):
        return Post.objects.get(pk=post.pk)


# ----------------------------------------------------------------- access


class AccessTests(WriteFixture):
    def pages(self):
        return [
            write("write"), write("write_new"), write("write_profile"), write("write_edit", self.draft.pk),
        ]

    def test_logged_out_goes_to_login(self):
        self.client.logout()
        for path in self.pages() + [write("write_image", self.draft.pk), write("write_action", self.draft.pk, "archive")]:
            response = self.client.post(path) if "image" in path or "archive" in path else self.client.get(path)
            with self.subTest(path):
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(reverse("accounts:login")))

    def assert_forbidden(self, user):
        self.client.force_login(user)
        for path in self.pages():
            response = self.client.get(path)
            with self.subTest(path, role=user.role):
                self.assertEqual(response.status_code, 403)
                self.assertContains(response, "اجازه نوشتن در وبلاگ ندارید", status_code=403)
        response = self.client.post(write("write_action", self.draft.pk, "archive"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.reload(self.draft).status, S.DRAFT)

    def test_people_who_are_not_authors_get_403(self):
        branch, grade = make_branch(), make_grade()
        for user in (
            make_student().user,
            make_staff(role=User.Roles.TEACHER).user,
            make_supervisor(branch, grade).user,
            make_user(User.Roles.DIRECTOR),
            make_user(User.Roles.COUNSELOR),
            make_user(User.Roles.ACCOUNTANT),
        ):
            self.assert_forbidden(user)

    def test_staff_and_editors_without_an_author_row_get_403(self):
        self.assert_forbidden(make_user(User.Roles.ADMIN, is_staff=True))
        self.assert_forbidden(make_editor())
        self.assert_forbidden(make_editor(is_superuser=True))

    def test_an_author_who_can_no_longer_write_gets_403_with_the_reason(self):
        BlogAuthor.objects.filter(pk=self.author.pk).update(is_active=False)
        response = self.client.get(write("write"))
        self.assertContains(response, "اجازه نوشتن این نویسنده خاموش است.", status_code=403)

        BlogAuthor.objects.filter(pk=self.author.pk).update(is_active=True)
        User.objects.filter(pk=self.user.pk).update(role=User.Roles.STUDENT)
        StudentProfile.objects.create(user=self.user, student_code="s-1")  # every student has one
        self.assert_forbidden(User.objects.get(pk=self.user.pk))

        User.objects.filter(pk=self.user.pk).update(role=User.Roles.TEACHER)
        self.user.staff_profile.__class__.objects.filter(user=self.user).update(is_active=False)
        self.assert_forbidden(User.objects.get(pk=self.user.pk))

    def test_a_deactivated_account_is_logged_out(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        response = self.client.get(write("write"))
        self.assertEqual(response.status_code, 302)

    def test_every_eligible_role_writes(self):
        branch, grade = make_branch(), make_grade()
        users = {
            "teacher": (self.user, "blog/write/teacher/list.html"),
            "counselor": (make_user(User.Roles.COUNSELOR), "blog/write/panel/list.html"),
            "supervisor": (make_supervisor(branch, grade).user, "blog/write/panel/list.html"),
            "director": (make_user(User.Roles.DIRECTOR), "blog/write/panel/list.html"),
            "admin": (make_user(User.Roles.ADMIN, is_staff=True), "blog/write/panel/list.html"),
        }
        for role, (user, template) in users.items():
            if role != "teacher":
                make_author(user=user, sections=[self.section])
            self.client.force_login(user)
            with self.subTest(role):
                response = self.client.get(write("write"))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)

    def test_the_supervisor_shell_shows_their_grade(self):
        supervisor = make_supervisor(make_branch(), make_grade(4))
        make_author(user=supervisor.user, sections=[self.section])
        self.client.force_login(supervisor.user)
        self.assertContains(self.client.get(write("write")), "پایه 4")

    def test_another_authors_post_is_a_404(self):
        post = self.their_draft
        self.assertEqual(self.client.get(write("write_edit", post.pk)).status_code, 404)
        self.assertEqual(self.client.post(write("write_edit", post.pk), self.form_data()).status_code, 404)
        for action in ("archive", "withdraw", "reopen"):
            self.assertEqual(self.client.post(write("write_action", post.pk, action)).status_code, 404)
        self.assertEqual(self.client.post(write("write_image", post.pk)).status_code, 404)
        self.assertEqual(self.client.get(write("write_edit", 999999)).status_code, 404)
        post.refresh_from_db()
        self.assertEqual((post.title, post.status), ("پیش‌نویس دیگری", S.DRAFT))

    def test_the_list_shows_only_own_posts(self):
        response = self.client.get(write("write"))
        self.assertContains(response, "پیش‌نویس من")
        self.assertNotContains(response, "پیش‌نویس دیگری")

    def test_transitions_and_uploads_take_post_only(self):
        self.assertEqual(self.client.get(write("write_action", self.draft.pk, "archive")).status_code, 405)
        self.assertEqual(self.client.get(write("write_image", self.draft.pk)).status_code, 405)
        self.assertEqual(self.client.post(write("write")).status_code, 405)


# ---------------------------------------------------------------- the list


class ListTests(WriteFixture):
    def test_tabs_count_and_filter(self):
        make_post(self.author, self.section, S.SUBMITTED, title="فرستاده")
        make_post(self.author, self.section, S.PUBLISHED, title="منتشر")
        make_post(self.author, self.section, S.PUBLISHED, title="زمان‌بندی", published_at=timezone.now() + timedelta(days=1))
        make_post(self.author, self.section, S.ARCHIVED, title="بایگانی‌شده")
        response = self.client.get(write("write"))
        tabs = {tab.key: tab.count for tab in response.context["dashboard"].tabs}
        self.assertEqual(tabs, {"all": 5, "draft": 1, "submitted": 1, "published": 2, "archived": 1})
        self.assertContains(response, "زمان‌بندی‌شده")

        response = self.client.get(write("write") + "?tab=published")
        self.assertContains(response, "منتشر")
        self.assertContains(response, "زمان‌بندی")
        self.assertNotContains(response, "پیش‌نویس من")
        self.assertEqual(self.client.get(write("write") + "?tab=nonsense").context["dashboard"].tab, "all")
        self.assertEqual(self.client.get(write("write") + "?page=9").status_code, 404)

    def test_a_returned_draft_shows_the_editors_note(self):
        Post.objects.filter(pk=self.draft.pk).update(review_note="نام کلاس را حذف کنید.")
        self.assertContains(self.client.get(write("write")), "ویراستار برگرداند: «نام کلاس را حذف کنید.»")

    def test_query_count_is_flat(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.client.get(write("write")).status_code, 200)
            return len(ctx.captured_queries)

        # Every panel request: session, user, staff, branch access and assignments (BranchMiddleware),
        # supervisor and student profiles (context processors), site settings, footer links (9).
        # The page: author (with staff; also the sidebar's check), tab counts, page count, posts (4).
        self.assertEqual(count(), 13)
        for i in range(12):
            make_post(self.author, self.section, title=f"نوشته {i}")
        self.assertEqual(count(), 13)


# -------------------------------------------------------------- writing


class WritingTests(TempMediaMixin, WriteFixture):
    def test_a_new_draft(self):
        response = self.client.post(write("write_new"), self.form_data(tag_names="کتاب‌خوانی، اردو، كتاب خواني"))
        post = Post.objects.get(title="جشن پاییز")
        self.assertRedirects(response, write("write_edit", post.pk))
        self.assertEqual((post.author, post.section, post.status), (self.author, self.section, S.DRAFT))
        self.assertEqual(sorted(tag.name for tag in post.tags.all()), ["اردو", "کتاب‌خوانی"])

    def test_the_new_form_offers_only_granted_sections(self):
        response = self.client.post(write("write_new"), self.form_data(section=self.other_section.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("section", response.context["form"].errors)
        self.assertFalse(Post.objects.filter(title="جشن پاییز").exists())
        # One granted section: no choice to make.
        self.assertContains(self.client.get(write("write_new")), 'type="hidden" name="section"')

    def test_without_a_granted_section_there_is_nothing_to_write_in(self):
        self.author.grants.all().delete()
        response = self.client.get(write("write_new"))
        self.assertRedirects(response, write("write"))
        self.assertEqual(self.client.get(write("write")).status_code, 200)

    def test_editing_a_draft_never_touches_the_workflow(self):
        response = self.client.post(write("write_edit", self.draft.pk), self.form_data(
            title="عنوان تازه", status="published", published_at="1405-01-01", is_featured="on", author=self.someone.pk,
        ))
        self.assertRedirects(response, write("write_edit", self.draft.pk))
        post = self.reload(self.draft)
        self.assertEqual((post.title, post.status, post.published_at, post.is_featured, post.author_id),
                         ("عنوان تازه", S.DRAFT, None, False, self.author.pk))

    def test_body_is_sanitized(self):
        self.client.post(write("write_edit", self.draft.pk), self.form_data(
            body='<p onclick="x()">سلام</p><script>alert(1)</script><img src="https://evil.example/a.png">',
        ))
        body = self.reload(self.draft).body
        self.assertNotIn("script", body)
        self.assertNotIn("onclick", body)
        self.assertNotIn("evil", body)
        self.assertIn("سلام", body)

    def test_category_must_belong_to_the_section(self):
        other_category = make_category(self.other_section, "دیگر")
        response = self.client.post(write("write_edit", self.draft.pk), self.form_data(category=other_category.pk))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)

    def test_too_many_tags(self):
        response = self.client.post(write("write_edit", self.draft.pk), self.form_data(tag_names="الف، ب، پ، ت، ث، ج"))
        self.assertIn("tag_names", response.context["form"].errors)
        self.assertFalse(Tag.objects.exists())

    def test_cover_needs_alt_text_and_is_reencoded(self):
        data = self.form_data(cover=phone_photo())
        response = self.client.post(write("write_edit", self.draft.pk), data)
        self.assertIn("cover_alt", response.context["form"].errors)
        response = self.client.post(write("write_edit", self.draft.pk), self.form_data(cover=phone_photo(), cover_alt="حیاط"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.reload(self.draft).cover.name.endswith(".jpg"))

    def test_the_slug_is_frozen_once_published(self):
        self.client.post(write("write_edit", self.draft.pk), self.form_data(slug="جشن-پاییز"))
        self.assertEqual(self.reload(self.draft).slug, "جشن-پاییز")
        Post.objects.filter(pk=self.draft.pk).update(published_at=timezone.now() - timedelta(days=3))  # returned after publication
        response = self.client.get(write("write_edit", self.draft.pk))
        self.assertNotIn("slug", response.context["form"].fields)
        self.client.post(write("write_edit", self.draft.pk), self.form_data(slug="نامک-تازه"))
        self.assertEqual(self.reload(self.draft).slug, "جشن-پاییز")

    def test_a_section_taken_away_makes_the_draft_read_only(self):
        self.author.grants.filter(section=self.section).delete()
        self.author.grants.create(section=self.other_section)
        response = self.client.get(write("write_edit", self.draft.pk))
        self.assertIsNone(response.context["form"])
        self.assertContains(response, "شما دیگر اجازه نوشتن در بخش «پرورشی» را ندارید.")
        response = self.client.post(write("write_edit", self.draft.pk), self.form_data(section=self.other_section.pk))
        self.assertRedirects(response, write("write_edit", self.draft.pk))
        self.assertEqual(self.reload(self.draft).title, "پیش‌نویس من")


class SubmitTests(WriteFixture):
    def test_submitting_needs_the_privacy_acknowledgement(self):
        response = self.client.post(write("write_edit", self.draft.pk), self.form_data(title="عوض‌شده", action="submit"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("privacy_ack", response.context["form"].errors)
        post = self.reload(self.draft)
        self.assertEqual((post.status, post.title), (S.DRAFT, "پیش‌نویس من"))  # nothing saved

    def test_submit(self):
        response = self.client.post(write("write_edit", self.draft.pk), self.form_data(action="submit", privacy_ack="on"))
        self.assertRedirects(response, write("write"))
        post = self.reload(self.draft)
        self.assertEqual(post.status, S.SUBMITTED)
        self.assertIsNotNone(post.privacy_ack_at)
        self.assertEqual(post.title, "جشن پاییز")

    def test_a_new_post_can_be_sent_at_once(self):
        self.client.post(write("write_new"), self.form_data(action="submit", privacy_ack="on"))
        self.assertEqual(Post.objects.get(title="جشن پاییز").status, S.SUBMITTED)

    def test_a_draft_without_text_is_saved_but_not_sent(self):
        response = self.client.post(write("write_edit", self.draft.pk), self.form_data(body="", action="submit", privacy_ack="on"))
        self.assertRedirects(response, write("write_edit", self.draft.pk))
        self.assertEqual(self.reload(self.draft).status, S.DRAFT)
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("فرستاده نشد" in m for m in messages))

    def test_submitted_is_read_only_until_withdrawn(self):
        services.submit(self.draft, self.user, privacy_ack=True)
        response = self.client.get(write("write_edit", self.draft.pk))
        self.assertIsNone(response.context["form"])
        self.assertContains(response, "در انتظار بررسی است")
        self.assertContains(response, "پس گرفتن برای ویرایش")

        self.client.post(write("write_edit", self.draft.pk), self.form_data(title="دزدکی"))
        self.assertEqual(self.reload(self.draft).title, "پیش‌نویس من")

        self.client.post(write("write_action", self.draft.pk, "withdraw"))
        self.assertEqual(self.reload(self.draft).status, S.DRAFT)

    def test_a_save_from_a_stale_tab_is_refused(self):
        """The form was opened while the post was a draft; it was submitted from another tab before saving."""

        stale = self.reload(self.draft)
        services.submit(self.draft, self.user, privacy_ack=True)
        stale.title = "از تب قدیمی"
        with self.assertRaises(services.TransitionError):
            services.save_draft(stale, self.user, ["title"], [])
        post = self.reload(self.draft)
        self.assertEqual((post.title, post.status), ("پیش‌نویس من", S.SUBMITTED))

    def test_published_posts_are_locked_for_their_author(self):
        """D9: an editor fixes a published post, or returns it."""

        post = make_post(self.author, self.section, S.PUBLISHED, title="منتشرشده")
        response = self.client.get(write("write_edit", post.pk))
        self.assertIsNone(response.context["form"])
        self.assertContains(response, "منتشر شده است")
        self.assertNotContains(response, "پس گرفتن")
        for action in ("withdraw", "archive", "reopen"):
            self.client.post(write("write_action", post.pk, action))
        self.client.post(write("write_edit", post.pk), self.form_data())
        post.refresh_from_db()
        self.assertEqual((post.status, post.title), (S.PUBLISHED, "منتشرشده"))

    def test_archive_and_reopen(self):
        self.client.post(write("write_action", self.draft.pk, "archive"))
        self.assertEqual(self.reload(self.draft).status, S.ARCHIVED)
        response = self.client.get(write("write_edit", self.draft.pk))
        self.assertContains(response, "برگرداندن به پیش‌نویس")
        self.client.post(write("write_action", self.draft.pk, "reopen"))
        self.assertEqual(self.reload(self.draft).status, S.DRAFT)

    def test_an_unknown_action_does_nothing(self):
        response = self.client.post(write("write_action", self.draft.pk, "publish"))
        self.assertRedirects(response, write("write_edit", self.draft.pk))
        self.assertEqual(self.reload(self.draft).status, S.DRAFT)

    def test_authors_never_publish(self):
        services.submit(self.draft, self.user, privacy_ack=True)
        with self.assertRaises(Exception):
            services.publish(self.draft, self.user, checklist_confirmed=True)
        self.assertEqual(self.reload(self.draft).status, S.SUBMITTED)


class ImageUploadTests(TempMediaMixin, WriteFixture):
    def test_upload_into_own_draft(self):
        response = self.client.post(write("write_image", self.draft.pk), {"image": phone_photo()})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["url"].startswith("/media/blog/"))
        self.assertEqual(self.draft.images.count(), 1)

    def test_refusals(self):
        self.assertEqual(self.client.post(write("write_image", self.draft.pk)).status_code, 400)
        services.submit(self.draft, self.user, privacy_ack=True)
        response = self.client.post(write("write_image", self.draft.pk), {"image": phone_photo()})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.draft.images.count(), 0)

    def test_the_editor_points_to_the_authors_endpoint(self):
        response = self.client.get(write("write_edit", self.draft.pk))
        self.assertContains(response, f'data-upload-url="{write("write_image", self.draft.pk)}"')
        self.assertNotContains(self.client.get(write("write_new")), "data-upload-url")


class ProfileTests(TempMediaMixin, WriteFixture):
    def test_bio_and_photo_only(self):
        response = self.client.post(write("write_profile"), {
            "bio": "معلم علوم.", "photo": phone_photo(), "display_name": "نام دیگر", "show_profile": "", "is_active": "",
        })
        self.assertRedirects(response, write("write_profile"))
        author = BlogAuthor.objects.get(pk=self.author.pk)
        self.assertEqual((author.bio, author.display_name, author.show_profile, author.is_active),
                         ("معلم علوم.", "", True, True))
        self.assertTrue(author.photo)

    def test_the_author_page_link_appears_with_a_public_post(self):
        self.assertNotContains(self.client.get(write("write_profile")), "صفحه من در وبلاگ")
        make_post(self.author, self.section, S.PUBLISHED)
        self.assertContains(self.client.get(write("write_profile")), self.author.get_absolute_url())


# ------------------------------------------------- the panels around it


class SidebarTests(WriteFixture):
    def test_the_item_shows_for_authors_only(self):
        self.assertContains(self.client.get(write("write")), f'href="{write("write")}"')
        teacher = make_teacher_profile().staff.user
        self.client.force_login(teacher)
        self.assertNotContains(self.client.get(reverse("accounts:profile")), f'href="{write("write")}"')
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse("accounts:profile")), f'href="{write("write")}"')

    def test_a_counselor_sees_only_the_blog_item(self):
        user = make_user(User.Roles.COUNSELOR)
        make_author(user=user, sections=[self.section])
        self.client.force_login(user)
        response = self.client.get(write("write"))
        self.assertContains(response, "نوشته‌های من")
        self.assertNotContains(response, "داشبورد")


class AuthorshipQueryTests(WriteFixture):
    """
    Change 1: the sidebar's authorship check is lazy. The public pages and
    the blog's public views never run it, for a logged-in author either.
    """

    def public_paths(self):
        post = make_post(self.author, self.section, S.PUBLISHED, title="عمومی")
        post.tags.add(make_tag("برچسب"))
        return [
            "/", "/about/", "/teachers/", "/contact/",
            url("home"), self.section.get_absolute_url(), post.tags.first().get_absolute_url(),
            self.author.get_absolute_url(), url("search") + "?q=%D8%B9%D9%85", post.get_absolute_url(),
            url("feed"), "/sitemap.xml", "/robots.txt",
        ]

    def test_public_pages_never_ask(self):
        paths = self.public_paths()
        for user in (self.user, None):
            if user is None:
                self.client.logout()
            for path in paths:
                with self.subTest(path, logged_in=bool(user)), \
                        mock.patch("blog.permissions.can_write", wraps=permissions.can_write) as check, \
                        CaptureQueriesContext(connection) as ctx:
                    self.assertEqual(self.client.get(path).status_code, 200)
                    check.assert_not_called()
                    self.assertFalse([q for q in ctx.captured_queries if AUTHORSHIP_SQL.search(q["sql"])])

    def test_a_panel_page_asks_once(self):
        with mock.patch("blog.permissions.can_write", wraps=permissions.can_write) as check, \
                CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(reverse("accounts:profile")).status_code, 200)
        check.assert_called_once()
        self.assertEqual(len([q for q in ctx.captured_queries if AUTHORSHIP_SQL.search(q["sql"])]), 1)


class LoginLandingTests(TestCase):
    """D7: an author without a panel lands in «نوشته‌های من»."""

    def test_where_people_land(self):
        section = make_section()
        counselor = make_user(User.Roles.COUNSELOR)
        make_author(user=counselor, sections=[section])
        self.assertEqual(role_dashboard(counselor), "blog:write")
        self.assertEqual(role_dashboard(make_user(User.Roles.COUNSELOR)), "website:website")

        staff_admin = make_user(User.Roles.ADMIN, is_staff=True)
        make_author(user=staff_admin, sections=[section])
        self.assertEqual(role_dashboard(staff_admin), "admin:index")

        teacher = make_staff(role=User.Roles.TEACHER).user
        make_author(user=teacher, sections=[section])
        self.assertEqual(role_dashboard(teacher), "core:dashboard")

        off = make_user(User.Roles.COUNSELOR)
        make_author(user=off, sections=[section], is_active=False)
        self.assertEqual(role_dashboard(off), "website:website")

    def test_the_login_form_sends_a_counselor_to_the_blog(self):
        counselor = make_user(User.Roles.COUNSELOR)
        make_author(user=counselor, sections=[make_section()])
        response = self.client.post(reverse("accounts:login"), {"username": counselor.username, "password": "test-pass-123", "role": "counselor"})
        self.assertRedirects(response, write("write"))
