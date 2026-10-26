"""The public blog: what is visible, to whom, on which page, and at what cost."""

from datetime import timedelta
from html.parser import HTMLParser
from unittest import mock
from urllib.parse import quote

import jdatetime
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from blog.models import BlogAuthor, Post
from blog.testing import grant, make_author, make_category, make_editor, make_post, make_section, make_tag
from core.testing import make_user
from website.models import LandingTeacher
from website.test_about import TempMediaMixin, upload
from website.tests import make_teacher, phone_photo

ZWNJ = "\N{ZERO WIDTH NON-JOINER}"
LONG_BODY = (
    "<h2>چرا بچه‌ها می‌ترسند؟</h2><p>ترس بخشی از رشد است.</p>"
    "<h2>وقتی حرف می‌زند</h2><p>گوش بدهید.</p><blockquote>آرام باشید.</blockquote>"
    "<h3>چند جمله</h3><ul><li>می‌فهمم.</li></ul><ol><li>یک</li></ol>"
)


def url(name, *args):
    return reverse(f"blog:{name}", args=args)


class BlogFixture(TestCase):
    """A section with a category, an author with a name, and helpers to publish."""

    @classmethod
    def setUpTestData(cls):
        cls.section = make_section("راهنمایی خانواده", paper="sky", description="برای پدر و مادرها.")
        cls.category = make_category(cls.section, "فرزندپروری")
        user = make_user(User.Roles.COUNSELOR)
        user.first_name, user.last_name = "مریم", "احمدی"
        user.save()
        cls.author = make_author(user=user, sections=[cls.section], bio="مشاور مدرسه.")

    def publish(self, title=None, days_ago=1, **fields):
        fields.setdefault("category", self.category)
        fields.setdefault("section", self.section)
        if title:
            fields["title"] = title
        return make_post(
            self.author,
            status=Post.Status.PUBLISHED,
            published_at=timezone.now() - timedelta(days=days_ago),
            **fields,
        )

    def get(self, path, status=200, **kwargs):
        response = self.client.get(path, **kwargs)
        self.assertEqual(response.status_code, status, path)
        return response


# ------------------------------------------------------------------ visibility


class VisibilityTests(BlogFixture):
    """Plan §6 and §7.8: only public posts appear anywhere, for anyone."""

    def setUp(self):
        self.tag = make_tag("کتاب‌خوانی")
        self.public = self.publish("نوشته عمومی")
        self.public.tags.add(self.tag)
        self.hidden = {
            "draft": make_post(self.author, self.section, category=self.category, title="پنهان پیش‌نویس"),
            "submitted": make_post(self.author, self.section, Post.Status.SUBMITTED, category=self.category, title="پنهان ارسال‌شده"),
            "archived": make_post(
                self.author, self.section, Post.Status.ARCHIVED, category=self.category, title="پنهان بایگانی",
                published_at=timezone.now() - timedelta(days=5),
            ),
            "scheduled": make_post(
                self.author, self.section, Post.Status.PUBLISHED, category=self.category, title="پنهان زمان‌بندی",
                published_at=timezone.now() + timedelta(days=2),
            ),
        }
        closed = make_section("بخش بسته", is_active=False)
        self.author.grants.create(section=closed)
        self.hidden["inactive section"] = make_post(self.author, closed, Post.Status.PUBLISHED, title="پنهان بخش بسته")
        for post in self.hidden.values():
            post.tags.add(self.tag)

    def pages(self):
        """Every list, feed and the sitemap: (path, whether the public post is on it)."""

        return [
            (url("home"), True),
            (self.section.get_absolute_url(), True),
            (self.category.get_absolute_url(), True),
            (self.tag.get_absolute_url(), True),
            (self.author.get_absolute_url(), True),
            (url("search") + "?q=" + quote("پنهان"), False),
            (url("search") + "?q=" + quote("نوشته"), True),
            (url("feed"), True),
            (url("section_feed", self.section.slug), True),
            ("/sitemap.xml", True),
        ]

    def test_non_public_posts_are_a_404_and_listed_nowhere(self):
        for name, post in self.hidden.items():
            with self.subTest(name):
                self.get(post.get_absolute_url(), 404)
        for page, lists_public in self.pages():
            content = self.get(page).content.decode()
            if lists_public:
                self.assertIn(self.public.get_absolute_url(), content, page)
            for name, post in self.hidden.items():
                self.assertNotIn(post.title, content, f"{page}: {name}")
                self.assertNotIn(post.get_absolute_url(), content, f"{page}: {name}")

    def test_staff_and_editors_get_the_404_too(self):
        for user in (make_editor(), make_editor(is_superuser=True), self.author.user):
            self.client.force_login(user)
            self.get(self.hidden["draft"].get_absolute_url(), 404)

    def test_a_scheduled_post_appears_exactly_at_its_time(self):
        post = self.hidden["scheduled"]
        at = post.published_dt
        with mock.patch("django.utils.timezone.now", return_value=at - timedelta(seconds=1)):
            self.get(post.get_absolute_url(), 404)
            self.assertNotContains(self.get(url("home")), post.title)
        with mock.patch("django.utils.timezone.now", return_value=at):
            self.get(post.get_absolute_url())
            self.assertContains(self.get(url("home")), post.title)

    def test_post_requests_are_refused(self):
        self.assertEqual(self.client.post(url("home")).status_code, 405)
        self.assertEqual(self.client.post(self.public.get_absolute_url()).status_code, 405)
        self.assertEqual(self.client.head(self.public.get_absolute_url()).status_code, 200)


# --------------------------------------------------------------------- preview


class PreviewTests(BlogFixture):
    def setUp(self):
        self.draft = make_post(self.author, self.section, category=self.category, title="پیش‌نویس من", body=LONG_BODY)
        self.path = url("preview", self.draft.pk)

    def test_author_and_editors_see_the_preview(self):
        for user in (self.author.user, make_editor()):
            self.client.force_login(user)
            response = self.get(self.path)
            self.assertContains(response, "پیش‌نمایش؛ هنوز منتشر نشده.")
            self.assertContains(response, '<meta name="robots" content="noindex">')
            self.assertNotContains(response, 'rel="canonical"')
            self.assertNotContains(response, "application/ld+json")
            self.assertContains(response, "چرا بچه‌ها می‌ترسند؟")

    def test_everyone_else_gets_a_404(self):
        other = make_author(sections=[self.section])
        staff = grant(make_user(User.Roles.ADMIN, is_staff=True), "view_post", "change_post")
        student = make_user(User.Roles.STUDENT)
        self.get(self.path, 404)  # anonymous
        for user in (other.user, staff, student, make_user(User.Roles.TEACHER)):
            self.client.force_login(user)
            self.get(self.path, 404)

    def test_an_author_who_can_no_longer_write_gets_a_404(self):
        BlogAuthor.objects.filter(pk=self.author.pk).update(is_active=False)
        self.client.force_login(User.objects.get(pk=self.author.user.pk))
        self.get(self.path, 404)

    def test_a_public_post_goes_to_its_public_url(self):
        post = self.publish("منتشرشده")
        self.client.force_login(self.author.user)
        response = self.get(url("preview", post.pk), 302)
        self.assertEqual(response["Location"], post.get_absolute_url())

    def test_the_scheduled_time_is_shown(self):
        post = make_post(
            self.author, self.section, Post.Status.PUBLISHED, category=self.category,
            published_at=timezone.now() + timedelta(days=2),
        )
        self.client.force_login(self.author.user)
        self.assertContains(self.get(url("preview", post.pk)), "وضعیت: زمان‌بندی‌شده، انتشار در")


# ----------------------------------------------------------------------- pages


class HomeTests(BlogFixture):
    def test_deploy_day(self):
        response = self.get(url("home"))
        self.assertTemplateUsed(response, "blog/home.html")
        self.assertContains(response, "هنوز نوشته‌ای در وبلاگ منتشر نشده است.")
        # The seeded sections and this one, with their counts written out.
        self.assertContains(response, "پرورشی")
        self.assertContains(response, "هنوز نوشته‌ای ندارد")
        # The masthead: each word of the blog's name on its own card.
        self.assertContains(response, '<span class="bl-cut bl-paper--tomato">وبلاگ</span>', html=False)
        self.assertContains(response, '<span class="bl-cut bl-paper--sky">قلم</span>', html=False)

    def test_featured_posts_are_not_repeated_in_the_latest(self):
        featured = self.publish("ویژه یکم", is_featured=True)
        self.publish("معمولی")
        content = self.get(url("home")).content.decode()
        self.assertEqual(content.count(f'href="{featured.get_absolute_url()}"'), 1)
        self.assertIn("نوشته‌های ویژه", content)
        self.assertIn("۲ نوشته", content)

    @override_settings(BLOG_PAGE_SIZE=2)
    def test_pages(self):
        for i in range(5):
            self.publish(f"نوشته {i}", days_ago=i + 1)
        first = self.get(url("home"))
        self.assertContains(first, 'href="/blog/?page=2" rel="next"')
        self.assertContains(first, 'aria-current="page">۱</a>')
        second = self.get(url("home") + "?page=2")
        self.assertContains(second, "نوشته‌ها، صفحه ۲")
        self.assertContains(second, 'href="/blog/" rel="prev"')
        self.assertNotContains(second, "بخش‌های وبلاگ")  # sections and tags only on the first page
        for bad in ("9", "0", "abc"):
            self.get(url("home") + f"?page={bad}", 404)

    def test_the_navbar_marks_the_blog_on_every_blog_page(self):
        post = self.publish()
        exact = self.get(url("home"))
        self.assertContains(exact, 'href="/blog/" class="public-nav__link is-active"')
        self.assertContains(exact, 'aria-current="page"')
        inner = self.get(post.get_absolute_url()).content.decode()
        self.assertIn('href="/blog/" class="public-nav__link is-active"', inner)
        nav = inner[inner.index('class="public-nav"'):inner.index("</nav>")]
        self.assertNotIn('aria-current="page"', nav)


class ListingTests(BlogFixture):
    def test_section(self):
        post = self.publish("در بخش")
        other = make_section("دیگر")
        self.author.grants.create(section=other)
        make_post(self.author, other, Post.Status.PUBLISHED, title="در بخش دیگر")
        response = self.get(self.section.get_absolute_url())
        self.assertTemplateUsed(response, "blog/listing.html")
        self.assertContains(response, '<span class="bl-cut">راهنمایی خانواده</span>', html=False)
        self.assertContains(response, post.title)
        self.assertNotContains(response, "در بخش دیگر")
        # The category chips: only categories with public posts.
        make_category(self.section, "بی‌نوشته")
        response = self.get(self.section.get_absolute_url())
        self.assertContains(response, 'aria-current="page">همه</a>')
        self.assertContains(response, f'href="{self.category.get_absolute_url()}"')
        self.assertNotContains(response, "بی‌نوشته")

    def test_inactive_or_unknown_section_is_a_404(self):
        self.get(url("section", "ناموجود"), 404)
        self.section.is_active = False
        self.section.save()
        self.get(self.section.get_absolute_url(), 404)
        self.get(url("section_feed", self.section.slug), 404)

    def test_category(self):
        post = self.publish("در دسته")
        response = self.get(self.category.get_absolute_url())
        self.assertContains(response, post.title)
        self.assertContains(response, f'aria-current="page">{self.category.title}</a>')
        self.get(url("category", "ناموجود", self.category.slug), 404)

    def test_an_inactive_category_hides_its_page_and_links_not_its_posts(self):
        post = self.publish("در دسته بسته")
        self.category.is_active = False
        self.category.save()
        self.get(self.category.get_absolute_url(), 404)
        response = self.get(post.get_absolute_url())
        self.assertNotContains(response, f'href="{self.category.get_absolute_url()}"')
        self.assertContains(self.get(self.section.get_absolute_url()), post.title)

    def test_tag(self):
        tag = make_tag("کتاب‌خوانی")
        self.get(tag.get_absolute_url(), 404)  # no public posts yet
        post = self.publish("با برچسب")
        post.tags.add(tag)
        response = self.get(tag.get_absolute_url())
        self.assertContains(response, post.title)
        self.assertContains(response, "۱ نوشته با این برچسب")
        tag.is_active = False
        tag.save()
        self.get(tag.get_absolute_url(), 404)
        self.assertNotContains(self.get(post.get_absolute_url()), tag.get_absolute_url())

    def test_author(self):
        self.get(self.author.get_absolute_url(), 404)  # no public posts yet
        post = self.publish("از مریم")
        response = self.get(self.author.get_absolute_url())
        self.assertContains(response, "مریم احمدی")
        self.assertContains(response, "مشاور مدرسه.")
        self.assertContains(response, post.title)
        self.assertContains(self.get(post.get_absolute_url()), f'href="{self.author.get_absolute_url()}"')

        BlogAuthor.objects.filter(pk=self.author.pk).update(show_profile=False)
        self.get(self.author.get_absolute_url(), 404)
        response = self.get(post.get_absolute_url())
        self.assertContains(response, "مریم احمدی")  # the name stays on the post (D18)
        self.assertNotContains(response, f'href="{self.author.get_absolute_url()}"')


class SearchTests(BlogFixture):
    def setUp(self):
        self.post = self.publish(f"کتاب{ZWNJ}خوانی در خانه", body="<p>کلاس ۳ و مسئله‌ها</p>")

    def search(self, query):
        return self.get(url("search") + "?q=" + quote(query))

    def test_spellings_match(self):
        for query in (f"کتاب{ZWNJ}خوانی", "کتاب خوانی", "کتابخوانی", "كتاب خواني", "کلاس 3", "كلاس ٣", "مسئله"):
            with self.subTest(query):
                response = self.search(query)
                self.assertContains(response, self.post.title)
                self.assertContains(response, "۱ نوشته پیدا شد.")

    def test_no_result_and_short_queries(self):
        self.assertContains(self.search("ریاضی"), "نوشته‌ای با «ریاضی» پیدا نشد.")
        for query in ("", "ک", " "):
            response = self.search(query)
            self.assertContains(response, "دست‌کم دو حرف بنویسید")
            self.assertNotContains(response, self.post.title)

    def test_search_pages_are_not_indexed(self):
        response = self.search("کتاب")
        self.assertContains(response, '<meta name="robots" content="noindex">')
        self.assertNotContains(response, 'rel="canonical"')
        self.assertContains(response, 'value="کتاب"')

    @override_settings(BLOG_PAGE_SIZE=1)
    def test_page_links_keep_the_query(self):
        self.publish("کتاب دوم")
        response = self.search("کتاب")
        self.assertContains(response, 'href="/blog/search/?q=%DA%A9%D8%AA%D8%A7%D8%A8&amp;page=2"')


class PostPageTests(TempMediaMixin, BlogFixture):
    def test_the_post(self):
        tag = make_tag("ترس")
        post = self.publish("چطور حرف بزنیم؟", body=LONG_BODY, excerpt="راهنمای کوتاه.")
        post.tags.add(tag)
        response = self.get(post.get_absolute_url())
        self.assertTemplateUsed(response, "blog/post.html")
        for text in (
            '<h1 class="bl-post__title" id="bl-post-title"',
            "راهنمای کوتاه.",
            "۱ دقیقه مطالعه",
            "فهرست این نوشته",
            "پرسشی دارید؟",
            'href="/contact/"',
            f'href="{tag.get_absolute_url()}"',
            "https://t.me/share/url?url=",
            "data-bl-copy=",
        ):
            self.assertContains(response, text)
        # Three headings: the table of contents, twice (fold and note).
        self.assertEqual(response.content.decode().count('class="bl-toc__list"'), 2)

    @override_settings(BLOG_TOC_MIN_HEADINGS=4)
    def test_no_table_of_contents_below_the_minimum(self):
        post = self.publish(body=LONG_BODY)
        self.assertNotContains(self.get(post.get_absolute_url()), "فهرست این نوشته")

    def test_the_body_is_sanitized_again_on_render(self):
        post = self.publish()
        Post.objects.filter(pk=post.pk).update(
            body='<p onclick="steal()">متن<script>alert(1)</script><img src="https://evil.example/x.png"></p>'
        )
        content = self.get(post.get_absolute_url()).content.decode()
        self.assertIn("متن", content)
        for bad in ("onclick", "alert(1)", "evil.example"):
            self.assertNotIn(bad, content)

    def test_updated_date_only_after_a_day(self):
        post = self.publish(days_ago=5)
        Post.objects.filter(pk=post.pk).update(content_updated_at=post.published_at + timedelta(hours=3))
        self.assertNotContains(self.get(post.get_absolute_url()), "به‌روزرسانی:")
        Post.objects.filter(pk=post.pk).update(content_updated_at=post.published_at + timedelta(days=2))
        self.assertContains(self.get(post.get_absolute_url()), "به‌روزرسانی:")

    def test_related_posts_and_neighbours(self):
        older = self.publish("قدیمی‌تر", days_ago=10)
        post = self.publish("این نوشته", days_ago=5)
        newer = self.publish("تازه‌تر", days_ago=1)
        elsewhere = make_section("جای دیگر")
        self.author.grants.create(section=elsewhere)
        tag = make_tag("مشترک")
        post.tags.add(tag)
        shared = make_post(self.author, elsewhere, Post.Status.PUBLISHED, title="با برچسب مشترک")
        shared.tags.add(tag)
        make_post(self.author, elsewhere, Post.Status.PUBLISHED, title="بی‌ربط")

        response = self.get(post.get_absolute_url())
        related = [p.title for p in response.context["post_page"].related]
        self.assertEqual(related, ["تازه‌تر", "قدیمی‌تر", "با برچسب مشترک"])
        self.assertEqual(response.context["post_page"].newer, newer)
        self.assertEqual(response.context["post_page"].older, older)
        self.assertContains(response, 'rel="next"')
        self.assertNotIn("بی‌ربط", related)

    def test_neighbours_an_hour_apart(self):
        """Moments are compared in UTC: hours apart is as reliable as days apart (SQLite compares text)."""

        base = timezone.now() - timedelta(hours=5)
        older, post, newer = (
            make_post(self.author, self.section, Post.Status.PUBLISHED, category=self.category,
                      published_at=base + timedelta(hours=hours))
            for hours in (0, 1, 2)
        )
        page = self.get(Post.objects.get(pk=post.pk).get_absolute_url()).context["post_page"]
        self.assertEqual((page.newer, page.older), (newer, older))

    def test_teacher_page_link_only_while_the_card_is_public(self):
        card = LandingTeacher.objects.create(teacher=make_teacher(first_name="مریم"), on_teachers_page=True)
        BlogAuthor.objects.filter(pk=self.author.pk).update(teacher_card=card)
        post = self.publish()
        link = f'href="/teachers/#{card.slug}"'
        self.assertContains(self.get(post.get_absolute_url()), link)
        for change in ({"on_teachers_page": False}, {"is_active": False}):
            LandingTeacher.objects.filter(pk=card.pk).update(**change)
            self.assertNotContains(self.get(post.get_absolute_url()), link)
            LandingTeacher.objects.filter(pk=card.pk).update(on_teachers_page=True, is_active=True)
        staff = card.teacher.staff
        staff.is_active = False
        staff.save()
        self.assertNotContains(self.get(post.get_absolute_url()), link)

    def test_author_photo_falls_back_to_the_card_never_the_avatar(self):
        user = self.author.user
        user.avatar = upload("avatar-secret.png")
        user.save()
        post = self.publish()
        content = self.get(post.get_absolute_url()).content.decode()
        self.assertNotIn("avatar-secret", content)
        self.assertIn('<span class="bl-avatar" aria-hidden="true">\n    م\n</span>', content)

        card = LandingTeacher.objects.create(name_override="مریم", photo_override=phone_photo())
        BlogAuthor.objects.filter(pk=self.author.pk).update(teacher_card=card)
        content = self.get(post.get_absolute_url()).content.decode()
        self.assertIn(card.photo_override.url, content)
        self.assertNotIn("avatar-secret", content)


# ---------------------------------------------------------------- query counts


class QueryCountTests(BlogFixture):
    """Every public page costs the same however many posts and tags (finding 7)."""

    def count(self, path):
        with CaptureQueriesContext(connection) as ctx:
            self.get(path)
        return len(ctx.captured_queries)

    def fill(self, n):
        tags = [make_tag(f"برچسب {n}-{i}") for i in range(n)]
        posts = []
        for i in range(n):
            post = self.publish(f"نوشته {n}-{i}", days_ago=i + 1, is_featured=1 <= i <= 2, body=LONG_BODY)
            post.tags.add(*tags)
            posts.append(post)
        return tags, posts

    def paths(self, tag, post):
        return {
            # page row, sections, featured, count, latest, tags + navbar/footer (3)
            "home": (url("home"), 9),
            # section, categories, count, posts, page row + 3
            "section": (self.section.get_absolute_url(), 8),
            "category": (self.category.get_absolute_url(), 8),
            # tag, count, posts, page row + 3
            "tag": (tag.get_absolute_url(), 7),
            "author": (self.author.get_absolute_url(), 7),
            # count, posts, page row + 3
            "search": (url("search") + "?q=" + quote("نوشته"), 6),
            # post, its tags, related, newer, older, page row + 3
            "post": (post.get_absolute_url(), 9),
        }

    def test_flat(self):
        tags, posts = self.fill(1)
        for name, (path, expected) in self.paths(tags[0], posts[0]).items():
            with self.subTest(name, posts=1):
                self.assertEqual(self.count(path), expected)
        more_tags, more_posts = self.fill(12)
        for name, (path, expected) in self.paths(more_tags[0], more_posts[5]).items():
            with self.subTest(name, posts=13):
                self.assertEqual(self.count(path), expected)


# ------------------------------------------------------------ CSP and markup


class _Markup(HTMLParser):
    """Collects what a strict CSP would refuse: inline styles and scripts, event handlers."""

    def __init__(self):
        super().__init__()
        self.problems, self.ld_json = [], 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "style" in attrs:
            self.problems.append(f"style attribute on <{tag}>")
        for name in attrs:
            if name.startswith("on"):
                self.problems.append(f"{name} on <{tag}>")
        if tag == "style":
            self.problems.append("<style> element")
        if tag == "script":
            if attrs.get("type") == "application/ld+json":
                self.ld_json += 1
            elif not attrs.get("src"):
                self.problems.append("inline <script>")
        for name in ("href", "src", "action"):
            if (attrs.get(name) or "").strip().lower().startswith("javascript:"):
                self.problems.append(f"javascript: URL in {name}")


class CspTests(TempMediaMixin, BlogFixture):
    def setUp(self):
        self.tag = make_tag("برچسب")
        self.post = self.publish(
            "نوشته کامل",
            body=LONG_BODY + '<p><a href="https://example.com">پیوند</a></p>',
            cover=phone_photo(),
            cover_alt="عکس",
            is_featured=True,
        )
        self.post.tags.add(self.tag)
        self.draft = make_post(self.author, self.section, category=self.category, body=LONG_BODY)

    def public_pages(self):
        return [
            url("home"),
            self.section.get_absolute_url(),
            self.category.get_absolute_url(),
            self.tag.get_absolute_url(),
            self.author.get_absolute_url(),
            url("search") + "?q=" + quote("نوشته"),
            url("search"),
            self.post.get_absolute_url(),
        ]

    def test_blog_pages_send_the_strict_policy(self):
        for path in self.public_pages():
            policy = self.get(path)["Content-Security-Policy"]
            for directive in (
                "default-src 'self'", "script-src 'self'", "style-src 'self'", "img-src 'self'",
                "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'self'",
            ):
                self.assertIn(directive, policy, path)
        self.client.force_login(self.author.user)
        self.assertIn("Content-Security-Policy", self.get(url("preview", self.draft.pk)))

    def test_the_rest_of_the_site_is_unchanged(self):
        for path in ("/", "/about/", "/teachers/", "/contact/", reverse("accounts:login")):
            self.assertNotIn("Content-Security-Policy", self.get(path), path)

    def test_no_inline_styles_or_scripts_on_blog_pages(self):
        """Change 4: nothing a strict CSP would silently refuse, except the JSON-LD data blocks."""

        self.client.force_login(self.author.user)
        pages = self.public_pages() + [url("preview", self.draft.pk)]
        self.client.logout()
        for path in pages:
            if "preview" in path:
                self.client.force_login(self.author.user)
            parser = _Markup()
            parser.feed(self.get(path).content.decode())
            with self.subTest(path):
                self.assertEqual(parser.problems, [])
        parser = _Markup()
        parser.feed(self.get(self.post.get_absolute_url()).content.decode())
        self.assertEqual(parser.ld_json, 2)  # BlogPosting and BreadcrumbList


# ------------------------------------------------------------------- privacy


class PrivacyTests(TempMediaMixin, BlogFixture):
    def test_the_authors_private_data_never_reaches_a_blog_page(self):
        teacher = make_teacher(first_name="ریحانه", last_name="محمدی", avatar=upload("secret.png"))
        user = teacher.staff.user
        user.username = "zz-login-marker"
        user.national_code = "9876543210"
        user.phone_number = "09121112233"
        user.email = "secret.teacher@example.com"
        user.save()
        staff = teacher.staff
        staff.personnel_code = "PCODE-7788"
        staff.birth_date = jdatetime.date(1361, 5, 17)
        staff.address = "نشانی-محرمانه-خانه"
        staff.save()
        author = make_author(user=user, sections=[self.section])
        tag = make_tag("برچسب")
        post = make_post(author, self.section, Post.Status.PUBLISHED, category=self.category)
        post.tags.add(tag)

        markers = [
            "zz-login-marker", "9876543210", "۹۸۷۶۵۴۳۲۱۰", "09121112233", "۰۹۱۲۱۱۱۲۲۳۳",
            "secret.teacher@example.com", "PCODE-7788", "نشانی-محرمانه-خانه", "users/avatars", user.avatar.name,
        ]
        pages = [
            url("home"), post.get_absolute_url(), author.get_absolute_url(), tag.get_absolute_url(),
            self.section.get_absolute_url(), self.category.get_absolute_url(), url("feed"), "/sitemap.xml",
            url("search") + "?q=" + quote(post.title),
        ]
        for path in pages:
            content = self.get(path).content.decode()
            if "sitemap" not in path:
                self.assertIn("ریحانه محمدی", content, path)
            for marker in markers:
                self.assertNotIn(marker, content, f"{path}: {marker}")
