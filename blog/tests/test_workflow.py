"""``blog.services``: every allowed transition, every refused one, and the stamps (D8, D9, D16)."""

from datetime import timedelta
from unittest import mock

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from blog import services
from blog.models import Post, Tag
from blog.testing import make_author, make_category, make_editor, make_post, make_section, make_tag
from core.testing import make_user
from website.test_about import TempMediaMixin
from website.tests import phone_photo

S = Post.Status
NOW = timezone.make_aware(timezone.datetime(2026, 11, 3, 10, 0))


@mock.patch("django.utils.timezone.now", return_value=NOW)
class TransitionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.section = make_section("مشاوره")
        cls.author = make_author(sections=[cls.section])
        cls.other = make_author(sections=[cls.section])
        cls.editor = make_editor()

    def reload(self, post):
        return Post.objects.get(pk=post.pk)

    def test_create_draft_only_in_a_granted_section(self, _now):
        post = services.create_draft(self.author.user, self.section, title="الف", body="<p>ب</p>")
        self.assertEqual((post.status, post.author), (S.DRAFT, self.author))
        with self.assertRaises(PermissionDenied):
            services.create_draft(self.author.user, make_section(), title="الف")
        with self.assertRaises(PermissionDenied):
            services.create_draft(make_user(User.Roles.STUDENT), self.section, title="الف")

    def test_submit_needs_the_privacy_acknowledgement_and_stamps(self, _now):
        post = make_post(self.author)
        with self.assertRaisesMessage(services.TransitionError, "حریم خصوصی"):
            services.submit(post, self.author.user, privacy_ack=False)
        self.assertEqual(self.reload(post).status, S.DRAFT)

        services.submit(post, self.author.user, privacy_ack=True)
        post = self.reload(post)
        self.assertEqual(post.status, S.SUBMITTED)
        self.assertEqual(post.submitted_at.togregorian(), NOW)
        self.assertEqual(post.privacy_ack_at.togregorian(), NOW)

    def test_submit_is_refused_twice_and_for_others(self, _now):
        post = make_post(self.author)
        services.submit(post, self.author.user, privacy_ack=True)
        with self.assertRaises(services.TransitionError):
            services.submit(post, self.author.user, privacy_ack=True)  # double click / second tab
        with self.assertRaises(PermissionDenied):
            services.submit(make_post(self.author), self.other.user, privacy_ack=True)

    def test_submit_checks_the_post_is_complete(self, _now):
        with self.assertRaises(services.TransitionError):
            services.submit(make_post(self.author, body=""), self.author.user, privacy_ack=True)
        make_category(self.section)
        with self.assertRaisesMessage(services.TransitionError, "دسته"):
            services.submit(make_post(self.author), self.author.user, privacy_ack=True)

    def test_submit_clears_an_old_editor_note(self, _now):
        post = make_post(self.author, review_note="نام کلاس را بردارید.")
        services.submit(post, self.author.user, privacy_ack=True)
        self.assertEqual(self.reload(post).review_note, "")

    def test_author_can_edit_only_drafts(self, _now):
        post = make_post(self.author)
        services.ensure_author_can_edit(self.author.user, post)
        for status in (S.SUBMITTED, S.PUBLISHED, S.ARCHIVED):
            with self.subTest(status=status):
                with self.assertRaises(services.TransitionError):
                    services.ensure_author_can_edit(self.author.user, make_post(self.author, status=status))
        with self.assertRaises(PermissionDenied):
            services.ensure_author_can_edit(self.other.user, post)

    def test_withdraw_archive_and_reopen(self, _now):
        post = make_post(self.author)
        services.submit(post, self.author.user, privacy_ack=True)
        with self.assertRaises(PermissionDenied):
            services.withdraw(post, self.other.user)
        self.assertEqual(services.withdraw(post, self.author.user).status, S.DRAFT)
        with self.assertRaises(services.TransitionError):
            services.withdraw(post, self.author.user)

        self.assertEqual(services.archive(post, self.author.user).status, S.ARCHIVED)
        self.assertTrue(Post.objects.filter(pk=post.pk).exists())  # archived, never deleted
        self.assertEqual(services.reopen(post, self.author.user).status, S.DRAFT)

        submitted = make_post(self.author, status=S.SUBMITTED)
        with self.assertRaises(services.TransitionError):
            services.archive(submitted, self.author.user)

        archived = make_post(self.author, status=S.ARCHIVED)
        self.assertEqual(services.reopen(archived, self.editor).status, S.DRAFT)
        with self.assertRaises(PermissionDenied):
            services.reopen(make_post(self.author, status=S.ARCHIVED), self.other.user)

    def test_authors_cannot_publish_or_feature(self, _now):
        post = make_post(self.author, status=S.SUBMITTED)
        for call in (
            lambda: services.publish(post, self.author.user, checklist_confirmed=True),
            lambda: services.unpublish(post, self.author.user),
            lambda: services.return_to_author(post, self.author.user, "x"),
            lambda: services.set_featured(post, self.author.user, True),
        ):
            with self.assertRaises(PermissionDenied):
                call()
        staff = make_user(User.Roles.ADMIN, is_staff=True)
        with self.assertRaises(PermissionDenied):
            services.publish(post, staff, checklist_confirmed=True)

    def test_publish_needs_the_checklist_and_stamps(self, _now):
        post = make_post(self.author, status=S.SUBMITTED)
        with self.assertRaisesMessage(services.TransitionError, "فهرست بررسی"):
            services.publish(post, self.editor, checklist_confirmed=False)
        services.publish(post, self.editor, checklist_confirmed=True)
        post = self.reload(post)
        self.assertEqual(post.status, S.PUBLISHED)
        self.assertEqual(post.published_at.togregorian(), NOW)
        self.assertEqual(post.reviewed_by, self.editor)
        self.assertEqual(post.reviewed_at.togregorian(), NOW)
        self.assertTrue(post.is_public)

    def test_publish_twice_is_refused(self, _now):
        post = make_post(self.author, status=S.SUBMITTED)
        services.publish(post, self.editor, checklist_confirmed=True)
        with self.assertRaisesMessage(services.TransitionError, "منتشرشده"):
            services.publish(post, self.editor, checklist_confirmed=True)

    def test_scheduled_publishing_goes_public_exactly_at_its_time(self, now):
        at = NOW + timedelta(days=1)
        post = services.publish(make_post(self.author, status=S.SUBMITTED), self.editor, checklist_confirmed=True, at=at)
        self.assertTrue(self.reload(post).is_scheduled)
        self.assertFalse(Post.objects.public().exists())
        now.return_value = at - timedelta(seconds=1)
        self.assertFalse(Post.objects.public().exists())
        now.return_value = at
        self.assertEqual(list(Post.objects.public()), [self.reload(post)])

    def test_publish_from_archive_and_from_draft(self, _now):
        archived = make_post(self.author, status=S.ARCHIVED, published_at=NOW - timedelta(days=5))
        self.assertEqual(services.publish(archived, self.editor, checklist_confirmed=True).status, S.PUBLISHED)
        draft = make_post(self.author)
        self.assertEqual(services.publish(draft, self.editor, checklist_confirmed=True).status, S.PUBLISHED)

    def test_publish_refuses_empty_posts_and_inactive_sections(self, _now):
        with self.assertRaises(services.TransitionError):
            services.publish(make_post(self.author, status=S.SUBMITTED, body=""), self.editor, checklist_confirmed=True)
        closed = make_section(is_active=False)
        with self.assertRaises(services.TransitionError):
            services.publish(make_post(self.author, section=closed, status=S.SUBMITTED), self.editor, checklist_confirmed=True)

    def test_unpublish_archives_and_unfeatures(self, _now):
        post = make_post(self.author, status=S.PUBLISHED, is_featured=True)
        post = services.unpublish(post, self.editor)
        self.assertEqual((post.status, post.is_featured), (S.ARCHIVED, False))
        self.assertIsNotNone(post.published_at)  # kept as history
        with self.assertRaises(services.TransitionError):
            services.unpublish(post, self.editor)

    def test_return_to_author_needs_a_note_and_takes_the_post_offline(self, _now):
        post = make_post(self.author, status=S.PUBLISHED)
        with self.assertRaisesMessage(services.TransitionError, "یادداشت"):
            services.return_to_author(post, self.editor, "  ")
        post = services.return_to_author(post, self.editor, "نام کلاس را بردارید.")
        self.assertEqual((post.status, post.review_note), (S.DRAFT, "نام کلاس را بردارید."))
        self.assertFalse(Post.objects.public().exists())
        with self.assertRaises(services.TransitionError):
            services.return_to_author(post, self.editor, "دوباره")  # already a draft
        # The author can edit it again.
        services.ensure_author_can_edit(self.author.user, post)

    def test_only_published_posts_are_featured(self, _now):
        with self.assertRaises(services.TransitionError):
            services.set_featured(make_post(self.author, status=S.SUBMITTED), self.editor, True)
        post = services.set_featured(make_post(self.author, status=S.PUBLISHED), self.editor, True)
        self.assertTrue(post.is_featured)
        self.assertFalse(services.set_featured(post, self.editor, False).is_featured)


class TagServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.author = make_author(sections=[make_section()])

    def test_sync_reuses_spellings_and_creates_new_tags(self):
        existing = make_tag("کتاب‌خوانی")
        post = make_post(self.author)
        tags = services.sync_tags(post, ["كتاب خوانی", " اردو ", "اردو"])
        self.assertEqual([t.name for t in tags], ["کتاب‌خوانی", "اردو"])
        self.assertEqual(tags[0], existing)
        self.assertEqual(Tag.objects.count(), 2)
        self.assertEqual(set(post.tags.all()), set(tags))

    def test_at_most_five_tags(self):
        post = make_post(self.author)
        with self.settings(BLOG_MAX_TAGS_PER_POST=5):
            services.sync_tags(post, ["۱", "۲", "۳", "۴", "۵"])
            with self.assertRaises(services.TransitionError):
                services.sync_tags(post, ["۱", "۲", "۳", "۴", "۵", "۶"])

    def test_parse_tag_names_accepts_persian_commas(self):
        self.assertEqual(services.parse_tag_names("اردو، والدگری, اردو ,"), ["اردو", "والدگری"])

    def test_merge_moves_posts_and_deactivates_the_sources(self):
        target, old_a, old_b = make_tag("کتاب‌خوانی"), make_tag("مطالعه"), make_tag("کتاب")
        first, second = make_post(self.author), make_post(self.author)
        first.tags.add(old_a, old_b)
        second.tags.add(old_a, target)
        self.assertEqual(services.merge_tags([old_a, old_b, target], target), 2)
        self.assertEqual(list(first.tags.all()), [target])
        self.assertEqual(list(second.tags.all()), [target])
        self.assertEqual(set(Tag.objects.filter(is_active=False)), {old_a, old_b})


class ImageServiceTests(TempMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.section = make_section()
        self.author = make_author(sections=[self.section])
        self.post = make_post(self.author)

    def test_author_adds_images_to_own_draft_only(self):
        image = services.add_image(self.post, phone_photo(), self.author.user)
        self.assertEqual(image.uploaded_by, self.author.user)
        other = make_author(sections=[self.section])
        with self.assertRaises(PermissionDenied):
            services.add_image(self.post, phone_photo(), other.user)
        submitted = make_post(self.author, status=S.SUBMITTED)
        with self.assertRaises(PermissionDenied):
            services.add_image(submitted, phone_photo(), self.author.user)

    def test_editors_add_images_to_any_post(self):
        submitted = make_post(self.author, status=S.SUBMITTED)
        self.assertEqual(services.add_image(submitted, phone_photo(), make_editor()).post, submitted)

    def test_type_and_size_are_validated(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        with self.assertRaises(ValidationError):
            services.add_image(self.post, SimpleUploadedFile("x.gif", b"GIF89a", content_type="image/gif"), self.author.user)
        big = SimpleUploadedFile("x.jpg", b"0" * (2 * 1024 * 1024 + 1), content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            services.add_image(self.post, big, self.author.user)
