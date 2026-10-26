from datetime import timedelta
from unittest import mock

import jdatetime
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from blog.models import AuthorSection, BlogAuthor, BlogPage, Post, Tag
from blog.testing import grant, make_author, make_editor, make_post, make_section, make_tag
from core.testing import make_user
from website.test_about import TempMediaMixin
from website.tests import phone_photo

S = Post.Status
NOW = timezone.make_aware(timezone.datetime(2026, 11, 3, 10, 0))


def checklist_data(prefix="publish"):
    items = BlogPage.load().checklist_items()
    head = f"{prefix}-" if prefix else ""
    return {f"{head}check_{i}": "on" for i in range(len(items))}


class AdminFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.section = make_section("مشاوره")
        cls.author = make_author(sections=[cls.section])
        cls.editor = make_editor()

    def setUp(self):
        self.client.force_login(self.editor)

    def reload(self, post):
        return Post.objects.get(pk=post.pk)


class PostAdminTests(AdminFixture):
    def test_pages_open(self):
        post = make_post(self.author, status=S.SUBMITTED)
        for url in (
            reverse("admin:blog_post_changelist"),
            reverse("admin:blog_post_add"),
            reverse("admin:blog_post_change", args=[post.pk]),
            reverse("admin:blog_postawaitingreview_changelist"),
            reverse("admin:blog_section_changelist"),
            reverse("admin:blog_section_change", args=[self.section.pk]),
            reverse("admin:blog_tag_changelist"),
            reverse("admin:blog_blogauthor_changelist"),
            reverse("admin:blog_blogauthor_change", args=[self.author.pk]),
            reverse("admin:blog_post_review", args=[post.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        page = self.client.get(reverse("admin:blog_blogpage_changelist"))
        self.assertRedirects(page, reverse("admin:blog_blogpage_change", args=[BlogPage.load().pk]))

    def test_change_form_has_the_editor_and_the_review_link(self):
        post = make_post(self.author)
        response = self.client.get(reverse("admin:blog_post_change", args=[post.pk]))
        self.assertContains(response, "data-bl-editor")
        self.assertContains(response, reverse("admin:blog_post_upload_image", args=[post.pk]))
        self.assertContains(response, "vendor/trix/trix.umd.min.js")
        self.assertContains(response, reverse("admin:blog_post_review", args=[post.pk]))
        # A new post has no upload address yet: images come after the first save.
        add = self.client.get(reverse("admin:blog_post_add"))
        self.assertContains(add, "data-bl-editor")
        self.assertNotContains(add, "data-upload-url")

    def test_saving_from_the_admin_sanitizes_and_keeps_the_status(self):
        data = {
            "title": "نوشته ادمین",
            "section": self.section.pk,
            "author": self.author.pk,
            "body": '<div>بند<br><br>دوم<script>alert(1)</script></div><p onclick="x">سوم</p>',
            "excerpt": "",
            "cover_alt": "",
            "meta_title": "",
            "meta_description": "",
            "slug": "",
        }
        response = self.client.post(reverse("admin:blog_post_add"), data)
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].form.errors)
        post = Post.objects.get(title="نوشته ادمین")
        self.assertEqual(post.body, "<p>بند</p><p>دوم</p><p>سوم</p>")
        self.assertEqual(post.status, S.DRAFT)

    def test_more_than_five_tags_is_refused(self):
        post = make_post(self.author)
        tags = [make_tag() for _ in range(6)]
        data = {
            "title": post.title, "section": self.section.pk, "author": self.author.pk, "body": post.body,
            "tags": [t.pk for t in tags], "excerpt": "", "cover_alt": "", "meta_title": "", "meta_description": "",
            "slug": post.slug,
        }
        response = self.client.post(reverse("admin:blog_post_change", args=[post.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("tags", response.context["adminform"].form.errors)

    def test_staff_without_blog_permissions_get_nothing(self):
        staff = make_user(User.Roles.ADMIN, is_staff=True)
        self.client.force_login(staff)
        post = make_post(self.author, status=S.SUBMITTED)
        for url in (
            reverse("admin:blog_post_changelist"),
            reverse("admin:blog_post_change", args=[post.pk]),
            reverse("admin:blog_postawaitingreview_changelist"),
            reverse("admin:blog_post_review", args=[post.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        upload = self.client.post(reverse("admin:blog_post_upload_image", args=[post.pk]), {"image": phone_photo()})
        self.assertEqual(upload.status_code, 403)

    def test_change_permission_without_publish_hides_publishing(self):
        staff = grant(make_user(User.Roles.ADMIN, is_staff=True), "view_post", "change_post")
        self.client.force_login(staff)
        post = make_post(self.author, status=S.SUBMITTED)
        change = self.client.get(reverse("admin:blog_post_change", args=[post.pk]))
        self.assertEqual(change.status_code, 200)
        self.assertNotContains(change, reverse("admin:blog_post_review", args=[post.pk]))
        self.assertTrue(change.context["adminform"].form.fields["is_featured"].disabled)
        self.assertEqual(self.client.get(reverse("admin:blog_post_review", args=[post.pk])).status_code, 403)
        listing = self.client.get(reverse("admin:blog_post_changelist"))
        self.assertNotContains(listing, "publish_selected")
        # Even a crafted POST of the action does nothing.
        self.client.post(reverse("admin:blog_post_changelist"), {
            "action": "publish_selected", ACTION_CHECKBOX_NAME: [post.pk], "apply": "1", **checklist_data(prefix=""),
        })
        self.assertEqual(self.reload(post).status, S.SUBMITTED)

    def test_only_superusers_delete_posts(self):
        post = make_post(self.author)
        response = self.client.get(reverse("admin:blog_post_delete", args=[post.pk]))
        self.assertEqual(response.status_code, 403)


@mock.patch("django.utils.timezone.now", return_value=NOW)
class ReviewViewTests(AdminFixture):
    def url(self, post):
        return reverse("admin:blog_post_review", args=[post.pk])

    def test_page_lists_every_checklist_item_and_warns_on_drafts(self, _now):
        draft = make_post(self.author)
        response = self.client.get(self.url(draft))
        for item in BlogPage.load().checklist_items():
            self.assertContains(response, item)
        self.assertContains(response, "برای بررسی نفرستاده است")
        self.assertNotContains(self.client.get(self.url(make_post(self.author, status=S.SUBMITTED))), "برای بررسی نفرستاده است")

    def test_publish_needs_every_tick(self, _now):
        post = make_post(self.author, status=S.SUBMITTED)
        data = {"action": "publish", "publish-when": "now", **checklist_data()}
        data.pop("publish-check_0")
        response = self.client.post(self.url(post), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "این مورد را بررسی و تیک بزنید.")
        self.assertEqual(self.reload(post).status, S.SUBMITTED)

    def test_publish_now(self, _now):
        post = make_post(self.author, status=S.SUBMITTED)
        response = self.client.post(self.url(post), {"action": "publish", "publish-when": "now", **checklist_data()})
        self.assertRedirects(response, reverse("admin:blog_post_change", args=[post.pk]))
        post = self.reload(post)
        self.assertEqual((post.status, post.reviewed_by), (S.PUBLISHED, self.editor))
        self.assertEqual(post.published_at.togregorian(), NOW)

    def test_schedule_with_a_jalali_date_in_persian_digits(self, _now):
        post = make_post(self.author, status=S.SUBMITTED)
        response = self.client.post(self.url(post), {
            "action": "publish", "publish-when": "at", "publish-publish_at": "۱۴۰۵/۰۸/۲۰ ۰۸:۳۰", **checklist_data(),
        })
        self.assertEqual(response.status_code, 302)
        post = self.reload(post)
        self.assertTrue(post.is_scheduled)
        local = timezone.localtime(post.published_at.togregorian())
        self.assertEqual(jdatetime.datetime.fromgregorian(datetime=local).strftime("%Y/%m/%d %H:%M"), "1405/08/20 08:30")

    def test_bad_date_is_refused(self, _now):
        post = make_post(self.author, status=S.SUBMITTED)
        for value in ("", "فردا", "1405/13/01 10:00"):
            with self.subTest(value=value):
                response = self.client.post(self.url(post), {
                    "action": "publish", "publish-when": "at", "publish-publish_at": value, **checklist_data(),
                })
                self.assertEqual(response.status_code, 200)
                self.assertIn("publish_at", response.context["publish_form"].errors)
        self.assertEqual(self.reload(post).status, S.SUBMITTED)

    def test_return_needs_a_note(self, _now):
        post = make_post(self.author, status=S.SUBMITTED)
        response = self.client.post(self.url(post), {"action": "return", "return-note": ""})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.reload(post).status, S.SUBMITTED)
        self.client.post(self.url(post), {"action": "return", "return-note": "عکس چهره دارد."})
        post = self.reload(post)
        self.assertEqual((post.status, post.review_note), (S.DRAFT, "عکس چهره دارد."))

    def test_unpublish(self, _now):
        post = make_post(self.author, status=S.PUBLISHED)
        self.client.post(self.url(post), {"action": "unpublish"})
        self.assertEqual(self.reload(post).status, S.ARCHIVED)

    def test_a_refused_transition_is_reported_not_raised(self, _now):
        post = make_post(self.author, status=S.PUBLISHED)
        response = self.client.post(self.url(post), {"action": "publish", "publish-when": "now", **checklist_data()}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.reload(post).status, S.PUBLISHED)


@mock.patch("django.utils.timezone.now", return_value=NOW)
class BulkActionTests(AdminFixture):
    def post_action(self, action, posts, **extra):
        return self.client.post(
            reverse("admin:blog_post_changelist"),
            {"action": action, ACTION_CHECKBOX_NAME: [p.pk for p in posts], **extra},
        )

    def test_bulk_publish_confirms_with_the_checklist(self, _now):
        submitted = make_post(self.author, status=S.SUBMITTED)
        archived = make_post(self.author, status=S.ARCHIVED, published_at=NOW - timedelta(days=9))
        draft = make_post(self.author)

        page = self.post_action("publish_selected", [submitted, archived, draft])
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "انتشار 2 نوشته")
        self.assertEqual(self.reload(submitted).status, S.SUBMITTED)

        missing = self.post_action("publish_selected", [submitted, archived, draft], apply="1")
        self.assertEqual(missing.status_code, 200)
        self.assertEqual(self.reload(submitted).status, S.SUBMITTED)

        done = self.post_action("publish_selected", [submitted, archived, draft], apply="1", **checklist_data(prefix=""))
        self.assertEqual(done.status_code, 302)
        self.assertEqual(self.reload(submitted).status, S.PUBLISHED)
        self.assertEqual(self.reload(archived).status, S.PUBLISHED)
        self.assertEqual(self.reload(draft).status, S.DRAFT)  # drafts only from their own review page

    def test_unpublish_and_feature(self, _now):
        live = make_post(self.author, status=S.PUBLISHED)
        waiting = make_post(self.author, status=S.SUBMITTED)
        self.post_action("feature_selected", [live, waiting])
        self.assertTrue(self.reload(live).is_featured)
        self.assertFalse(self.reload(waiting).is_featured)
        self.post_action("unfeature_selected", [live])
        self.assertFalse(self.reload(live).is_featured)
        self.post_action("unpublish_selected", [live, waiting])
        self.assertEqual(self.reload(live).status, S.ARCHIVED)
        self.assertEqual(self.reload(waiting).status, S.SUBMITTED)


class AwaitingReviewTests(AdminFixture):
    def test_lists_submitted_posts_oldest_first(self):
        newer = make_post(self.author, status=S.SUBMITTED, submitted_at=NOW)
        older = make_post(self.author, status=S.SUBMITTED, submitted_at=NOW - timedelta(days=2))
        make_post(self.author)
        make_post(self.author, status=S.PUBLISHED)
        response = self.client.get(reverse("admin:blog_postawaitingreview_changelist"))
        self.assertEqual(list(response.context["cl"].result_list), [Post.objects.get(pk=older.pk), Post.objects.get(pk=newer.pk)])
        self.assertContains(response, reverse("admin:blog_post_review", args=[older.pk]))

    def test_view_permission_on_posts_is_enough(self):
        staff = grant(make_user(User.Roles.ADMIN, is_staff=True), "view_post")
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse("admin:blog_postawaitingreview_changelist")).status_code, 200)


class AuthorAdminTests(AdminFixture):
    def form_data(self, user, sections, **extra):
        return {
            "user": user.pk, "is_active": "on", "grant_sections": [s.pk for s in sections],
            "display_name": "", "bio": "", "slug": "", "show_profile": "on", **extra,
        }

    def test_granting_and_removing_sections_records_who_granted(self):
        counselor = make_user(User.Roles.COUNSELOR)
        other = make_section("پرورشی")
        response = self.client.post(reverse("admin:blog_blogauthor_add"), self.form_data(counselor, [self.section, other]))
        self.assertEqual(response.status_code, 302)
        author = BlogAuthor.objects.get(user=counselor)
        self.assertEqual(set(author.sections.all()), {self.section, other})
        self.assertEqual({g.granted_by for g in AuthorSection.objects.filter(author=author)}, {self.editor})

        self.client.post(reverse("admin:blog_blogauthor_change", args=[author.pk]), self.form_data(counselor, [other]))
        self.assertEqual(list(author.sections.all()), [other])

    def test_students_cannot_be_made_authors(self):
        student = make_user(User.Roles.STUDENT)
        response = self.client.post(reverse("admin:blog_blogauthor_add"), self.form_data(student, [self.section]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BlogAuthor.objects.filter(user=student).exists())

    def test_writing_status_explains_why_not(self):
        author = make_author(sections=[self.section])
        author.user.role = User.Roles.STUDENT
        author.user.save()
        response = self.client.get(reverse("admin:blog_blogauthor_change", args=[author.pk]))
        self.assertContains(response, "نمی‌تواند بنویسد")
        self.assertContains(response, "اجازه نویسندگی ندارد")


class TagAdminTests(AdminFixture):
    def test_merge_action(self):
        target, old = make_tag("کتاب‌خوانی"), make_tag("مطالعه")
        post = make_post(self.author)
        post.tags.add(old)
        url = reverse("admin:blog_tag_changelist")
        page = self.client.post(url, {"action": "merge_tags", ACTION_CHECKBOX_NAME: [old.pk]})
        self.assertContains(page, "ادغام در برچسب")
        self.client.post(url, {"action": "merge_tags", ACTION_CHECKBOX_NAME: [old.pk], "apply": "1", "target": target.pk})
        self.assertEqual(list(post.tags.all()), [target])
        self.assertFalse(Tag.objects.get(pk=old.pk).is_active)

    def test_search_finds_other_spellings(self):
        tag = make_tag("کتاب‌خوانی")
        response = self.client.get(reverse("admin:blog_tag_changelist"), {"q": "كتاب خوانی"})
        self.assertEqual(list(response.context["cl"].result_list), [tag])


class UploadTests(TempMediaMixin, AdminFixture):
    def url(self, post):
        return reverse("admin:blog_post_upload_image", args=[post.pk])

    def test_upload_returns_the_reencoded_image(self):
        post = make_post(self.author)
        response = self.client.post(self.url(post), {"image": phone_photo(size=(2400, 1200))})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["url"].startswith("/media/blog/posts/"))
        self.assertEqual((body["width"], body["height"]), (800, 1600))
        self.assertEqual(post.images.get().uploaded_by, self.editor)

    def test_refusals(self):
        post = make_post(self.author)
        self.assertEqual(self.client.get(self.url(post)).status_code, 405)
        self.assertEqual(self.client.post(self.url(post)).status_code, 400)
        gif = SimpleUploadedFile("x.gif", b"GIF89a", content_type="image/gif")
        bad_type = self.client.post(self.url(post), {"image": gif})
        self.assertEqual(bad_type.status_code, 400)
        self.assertIn("error", bad_type.json())
        fake = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
        self.assertEqual(self.client.post(self.url(post), {"image": fake}).status_code, 400)
        self.assertEqual(self.client.post(reverse("admin:blog_post_upload_image", args=[999999]), {"image": phone_photo()}).status_code, 404)
        self.assertFalse(post.images.exists())
