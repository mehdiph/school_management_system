from datetime import timedelta
from datetime import timezone as dt_timezone
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from blog.models import AuthorSection, BlogAuthor, Category, Post, PostImage, Tag
from blog.testing import make_author, make_category, make_post, make_section, make_tag
from core.testing import make_user
from website.models import LandingTeacher
from website.test_about import TempMediaMixin
from website.tests import phone_photo

NOW = timezone.make_aware(timezone.datetime(2026, 11, 3, 10, 0))
ZWNJ = "\N{ZERO WIDTH NON-JOINER}"


class PostFieldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.section = make_section("پرورشی")
        cls.author = make_author(sections=[cls.section])

    def test_category_must_be_in_the_posts_section(self):
        other = make_category(make_section())
        post = Post(section=self.section, category=other, author=self.author, title="الف", body="<p>ب</p>")
        with self.assertRaises(ValidationError) as caught:
            post.full_clean()
        self.assertIn("category", caught.exception.message_dict)

    def test_category_is_required_when_the_section_has_active_ones(self):
        post = Post(section=self.section, author=self.author, title="الف", body="<p>ب</p>")
        post.full_clean()  # no categories yet: fine
        make_category(self.section, is_active=False)
        post.full_clean()  # only an inactive one: fine
        make_category(self.section)
        with self.assertRaises(ValidationError):
            post.full_clean()

    def test_cover_needs_alt_text(self):
        post = Post(section=self.section, author=self.author, title="الف", body="<p>ب</p>", cover="blog/covers/x.jpg")
        with self.assertRaises(ValidationError) as caught:
            post.full_clean(exclude=["cover"])  # the file itself doesn't exist here
        self.assertIn("cover_alt", caught.exception.message_dict)

    def test_slug_keeps_persian_and_is_unique(self):
        first = make_post(self.author, title="جشن پاییز")
        second = make_post(self.author, title="جشن  پاییز")
        self.assertEqual(first.slug, "جشن-پاییز")
        self.assertEqual(second.slug, "جشن-پاییز-2")

    def test_slug_does_not_follow_title_changes(self):
        post = make_post(self.author, title="عنوان اول")
        post.title = "عنوان دوم"
        post.save()
        self.assertEqual(post.slug, "عنوان-اول")

    def test_derived_fields_are_computed_on_save(self):
        post = make_post(
            self.author,
            title=" كتاب   خوانی ",
            body="<h2>یک</h2><p>" + "کلمه " * 400 + "</p><h3>دو</h3>",
        )
        self.assertEqual(post.title, "کتاب خوانی")
        self.assertEqual(post.reading_minutes, 3)
        self.assertEqual([item["title"] for item in post.toc], ["یک", "دو"])
        self.assertTrue(post.body_text.startswith("یک\nکلمه"))
        self.assertIn("کتابخوانی", post.search_text)
        self.assertTrue(post.summary.startswith("یک کلمه"))
        self.assertTrue(post.summary.endswith("…"))

    def test_excerpt_wins_over_the_automatic_summary(self):
        post = make_post(self.author, excerpt="خلاصه من")
        self.assertEqual(post.summary, "خلاصه من")
        self.assertEqual(post.seo_description, "خلاصه من")
        self.assertEqual(post.seo_title, post.title)

    def test_saving_with_update_fields_still_sanitizes(self):
        post = make_post(self.author)
        post.body = '<p onclick="x">a<script>b</script></p>'
        post.save(update_fields=["body"])
        post.refresh_from_db()
        self.assertEqual(post.body, "<p>a</p>")
        self.assertEqual(post.body_text, "a")

    def test_published_post_needs_a_date(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Post.objects.filter(pk=make_post(self.author).pk).update(status=Post.Status.PUBLISHED, published_at=None)

    def test_content_updated_at_only_after_publication(self):
        post = make_post(self.author)
        post.body = "<p>متن تازه</p>"
        post.save()
        self.assertIsNone(post.content_updated_at)

        post = make_post(self.author, status=Post.Status.PUBLISHED)
        post.is_featured = True
        post.save()
        self.assertIsNone(post.content_updated_at)  # not a content change
        post.body = "<p>متن تازه</p>"
        post.save()
        self.assertIsNotNone(post.content_updated_at)


@mock.patch("django.utils.timezone.now", return_value=NOW)
class PublicQuerySetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.section = make_section()
        cls.author = make_author(sections=[cls.section])

    def test_only_published_posts_whose_time_has_come_in_active_sections(self, _now):
        published = make_post(self.author, status=Post.Status.PUBLISHED, published_at=NOW - timedelta(minutes=1))
        due_now = make_post(self.author, status=Post.Status.PUBLISHED, published_at=NOW)
        make_post(self.author, status=Post.Status.PUBLISHED, published_at=NOW + timedelta(minutes=1))  # scheduled
        make_post(self.author, status=Post.Status.DRAFT)
        make_post(self.author, status=Post.Status.SUBMITTED)
        make_post(self.author, status=Post.Status.ARCHIVED, published_at=NOW - timedelta(days=3))
        hidden = make_section(is_active=False)
        make_post(self.author, section=hidden, status=Post.Status.PUBLISHED, published_at=NOW - timedelta(days=1))

        self.assertQuerySetEqual(Post.objects.public(), {published, due_now}, ordered=False)

    def test_scheduled_post_becomes_public_at_its_time(self, now):
        post = make_post(self.author, status=Post.Status.PUBLISHED, published_at=NOW + timedelta(hours=2))
        self.assertTrue(post.is_scheduled)
        self.assertEqual(post.status_label, "زمان‌بندی‌شده")
        self.assertFalse(Post.objects.public().exists())

        now.return_value = NOW + timedelta(hours=2)
        post.refresh_from_db()
        self.assertTrue(post.is_public)
        self.assertFalse(post.is_scheduled)
        self.assertEqual(list(Post.objects.public()), [post])

    def test_saving_a_loaded_post_keeps_its_moment(self, now):
        """
        A loaded post holds aware jdatetimes; saved as they are, SQLite got
        «…13:00+03:30» text and compared it as text, hiding the post for
        hours. The instant must survive any number of saves, on any database.
        """

        now.return_value = NOW.astimezone(dt_timezone.utc)  # what Django's timezone.now() returns
        post = make_post(self.author, status=Post.Status.PUBLISHED, published_at=NOW - timedelta(minutes=1))
        for _ in range(2):
            post = Post.objects.get(pk=post.pk)
            post.title = "ویرایش‌شده"
            post.save()
        self.assertEqual(list(Post.objects.public()), [post])
        self.assertEqual(Post.objects.get(pk=post.pk).published_dt, NOW - timedelta(minutes=1))

        now.return_value = (NOW - timedelta(minutes=1, seconds=1)).astimezone(dt_timezone.utc)
        self.assertFalse(Post.objects.public().exists())

    def test_inactive_category_or_tag_does_not_hide_the_post(self, _now):
        category = make_category(self.section, is_active=False)
        post = make_post(self.author, category=category, status=Post.Status.PUBLISHED)
        post.tags.add(make_tag(is_active=False))
        self.assertEqual(list(Post.objects.public()), [post])


class CategoryTests(TestCase):
    def test_the_feed_slug_stays_free(self):
        """A category called «feed» would hide behind its section's feed URL."""

        section = make_section()
        self.assertEqual(make_category(section, "feed").slug, "feed-2")
        with self.assertRaises(ValidationError) as caught:
            Category(section=section, title="خوراک", slug="feed").full_clean()
        self.assertIn("slug", caught.exception.message_dict)
        Category(section=section, title="خوراک", slug="feeds").full_clean()


class TagTests(TestCase):
    def test_one_tag_per_spelling(self):
        tag = make_tag(f"کتاب{ZWNJ}خوانی")
        self.assertEqual(Tag.objects.named("كتاب خواني").get(), tag)
        self.assertEqual(Tag.objects.named("کتابخوانی").get(), tag)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Tag.objects.create(name="كتاب خوانی")

    def test_validation_reports_the_clash_on_the_name(self):
        make_tag("اردو")
        with self.assertRaises(ValidationError) as caught:
            Tag(name="ارد و").full_clean()
        self.assertIn("name", caught.exception.message_dict)

    def test_named_ignores_empty_names(self):
        self.assertFalse(Tag.objects.named("  ").exists())


class AuthorTests(TempMediaMixin, TestCase):
    def test_name_falls_back_to_the_account_name_never_the_username(self):
        user = make_user(User.Roles.COUNSELOR)
        user.first_name, user.last_name = "مریم", "احمدی"
        user.save()
        author = make_author(user=user)
        self.assertEqual(author.name, "مریم احمدی")
        self.assertEqual(author.slug, "مریم-احمدی")
        author.display_name = "خانم احمدی"
        self.assertEqual(author.name, "خانم احمدی")

        nameless = make_user(User.Roles.TEACHER)
        nameless.first_name = nameless.last_name = ""
        nameless.save()
        with self.assertRaises(ValidationError) as caught:
            BlogAuthor(user=nameless).full_clean()
        self.assertIn("display_name", caught.exception.message_dict)
        self.assertNotIn(nameless.username, BlogAuthor(user=nameless).name)

    def test_only_eligible_roles_can_be_made_authors(self):
        for role in (User.Roles.TEACHER, User.Roles.COUNSELOR, User.Roles.SUPERVISOR, User.Roles.DIRECTOR, User.Roles.ADMIN):
            with self.subTest(role=role):
                BlogAuthor(user=make_user(role)).full_clean()
        for role in (User.Roles.STUDENT, User.Roles.ACCOUNTANT, User.Roles.IT, User.Roles.SERVICES):
            with self.subTest(role=role), self.assertRaises(ValidationError):
                BlogAuthor(user=make_user(role)).full_clean()

    def test_an_author_whose_role_changed_can_still_be_edited(self):
        author = make_author()
        author.user.role = User.Roles.STUDENT
        author.user.save()
        author.is_active = False
        author.full_clean()  # the admin can still switch them off
        self.assertIn(author.user, User.objects.filter(BlogAuthor._meta.get_field("user").get_limit_choices_to()))

    def test_photo_is_reencoded_without_metadata(self):
        author = make_author(photo=phone_photo())
        author.photo.open("rb")
        data = author.photo.read()
        author.photo.close()
        self.assertNotIn(b"SecretPhone", data)
        self.assertTrue(author.photo.name.endswith(".jpg"))

    def test_photo_and_bio_fall_back_to_the_teacher_card_never_the_avatar(self):
        card = LandingTeacher.objects.create(name_override="معلم", photo_override=phone_photo(), bio="معرفی کارت")
        author = make_author(teacher_card=card)
        author.user.avatar = "users/avatars/me.jpg"
        author.user.save()
        self.assertEqual(author.photo_url, card.photo_url)
        self.assertEqual(author.public_bio, "معرفی کارت")

        bare = make_author()
        bare.user.avatar = "users/avatars/me.jpg"
        bare.user.save()
        self.assertEqual(bare.photo_url, "")
        self.assertEqual(bare.initial, bare.name[0])

    def test_one_grant_per_section(self):
        section = make_section()
        author = make_author(sections=[section])
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuthorSection.objects.create(author=author, section=section)


class PostImageTests(TempMediaMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.author = make_author(sections=[make_section()])
        self.post = make_post(self.author)

    def test_image_is_reencoded_and_measured(self):
        image = PostImage.objects.create(post=self.post, image=phone_photo(size=(2400, 1200)))
        image.image.open("rb")
        data = image.image.read()
        image.image.close()
        self.assertNotIn(b"SecretPhone", data)
        # Turned upright (1200×2400), then scaled to fit 1600.
        self.assertEqual((image.width, image.height), (800, 1600))
        self.assertTrue(image.url.startswith("/media/blog/posts/"))

    def test_images_dropped_from_the_body_are_pruned_after_a_day(self):
        kept = PostImage.objects.create(post=self.post, image=phone_photo())
        dropped = PostImage.objects.create(post=self.post, image=phone_photo())
        fresh = PostImage.objects.create(post=self.post, image=phone_photo())
        PostImage.objects.filter(pk__in=[kept.pk, dropped.pk]).update(created_at=timezone.now() - timedelta(days=2))

        self.post.body = f'<figure><img src="{kept.url}" alt=""></figure>'
        with self.captureOnCommitCallbacks(execute=True):
            self.post.save()

        remaining = set(self.post.images.values_list("pk", flat=True))
        self.assertEqual(remaining, {kept.pk, fresh.pk})  # the fresh one may still be in an open editor
        self.assertFalse(dropped.image.storage.exists(dropped.image.name))
