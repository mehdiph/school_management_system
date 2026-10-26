"""What the blog tells search engines and feed readers (D19): meta tags, JSON-LD, feeds, sitemap, robots.txt."""

import json
import re
from datetime import timedelta
from urllib.parse import quote
from xml.etree import ElementTree

from django.test import override_settings
from django.utils import timezone

from blog.models import BlogAuthor, Post
from blog.testing import make_category, make_post, make_section, make_tag
from website.test_about import TempMediaMixin
from website.tests import phone_photo

from .test_public import LONG_BODY, BlogFixture, url

ATOM = "{http://www.w3.org/2005/Atom}"
SITEMAP = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
LD_JSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)


def ld_blocks(response):
    return [json.loads(block) for block in LD_JSON.findall(response.content.decode())]


class PostMetaTests(TempMediaMixin, BlogFixture):
    def test_post_meta_and_structured_data(self):
        tag = make_tag("ترس")
        post = self.publish(
            "چطور حرف بزنیم؟", excerpt="راهنمای کوتاه برای خانواده‌ها.", body=LONG_BODY,
            cover=phone_photo(), cover_alt="بچه‌ها در حیاط",
        )
        post.tags.add(tag)
        response = self.get(post.get_absolute_url())
        canonical = f"http://testserver{post.get_absolute_url()}"
        for tag_html in (
            "<title>چطور حرف بزنیم؟ | مدرسه نسل قلم</title>",
            '<meta name="description" content="راهنمای کوتاه برای خانواده‌ها.">',
            f'<link rel="canonical" href="{canonical}">',
            '<meta property="og:type" content="article">',
            f'<meta property="og:image" content="http://testserver{post.cover_url}">',
            '<meta property="og:image:alt" content="بچه‌ها در حیاط">',
            '<meta name="twitter:card" content="summary_large_image">',
            '<meta property="article:published_time" content="',
            f'<link rel="alternate" type="application/atom+xml" title="{self.section.title} | وبلاگ نسل قلم" '
            f'href="{url("section_feed", self.section.slug)}">',
        ):
            self.assertContains(response, tag_html)
        self.assertNotContains(response, 'name="robots"')

        article, crumbs = ld_blocks(response)
        self.assertEqual(article["@type"], "BlogPosting")
        self.assertEqual(article["headline"], "چطور حرف بزنیم؟")
        self.assertEqual(article["mainEntityOfPage"], canonical)
        self.assertEqual(article["author"], {
            "@type": "Person", "name": "مریم احمدی", "url": f"http://testserver{self.author.get_absolute_url()}",
        })
        self.assertEqual(article["keywords"], ["ترس"])
        self.assertTrue(article["datePublished"].endswith("+03:30"))
        self.assertEqual(
            [item["name"] for item in crumbs["itemListElement"]],
            ["وبلاگ نسل قلم", self.section.title, self.category.title, "چطور حرف بزنیم؟"],
        )

    def test_seo_fields_win_and_the_default_share_image_fills_in(self):
        post = self.publish("عنوان", meta_title="عنوان سئو", meta_description="توضیح سئو.")
        response = self.get(post.get_absolute_url())
        self.assertContains(response, "<title>عنوان سئو | مدرسه نسل قلم</title>")
        self.assertContains(response, '<meta name="description" content="توضیح سئو.">')
        self.assertNotContains(response, "og:image")
        self.assertContains(response, '<meta name="twitter:card" content="summary">')

    def test_structured_data_cannot_break_out_of_its_block(self):
        title = '</script><script>alert("x")</script> & <b>'
        post = self.publish(title)
        response = self.get(post.get_absolute_url())
        content = response.content.decode()
        self.assertNotIn('<script>alert("x")', content)
        article, _ = ld_blocks(response)
        self.assertEqual(article["headline"], title)

    def test_an_author_without_a_page_has_no_url_in_the_data(self):
        BlogAuthor.objects.filter(pk=self.author.pk).update(show_profile=False)
        post = self.publish()
        article, _ = ld_blocks(self.get(post.get_absolute_url()))
        self.assertNotIn("url", article["author"])


class ListingMetaTests(BlogFixture):
    def test_section_and_category(self):
        self.publish()
        response = self.get(self.section.get_absolute_url())
        self.assertContains(response, f"<title>{self.section.title} | وبلاگ نسل قلم | مدرسه نسل قلم</title>")
        self.assertContains(response, '<meta name="description" content="برای پدر و مادرها.">')
        (crumbs,) = ld_blocks(response)
        self.assertEqual([i["name"] for i in crumbs["itemListElement"]], ["وبلاگ نسل قلم", self.section.title])

        response = self.get(self.category.get_absolute_url())
        self.assertContains(
            response,
            f'<meta name="description" content="نوشته‌های «{self.category.title}» در بخش {self.section.title}، وبلاگ نسل قلم.">',
        )

    @override_settings(BLOG_PAGE_SIZE=1)
    def test_canonical_keeps_the_page_number(self):
        self.publish(days_ago=1)
        self.publish(days_ago=2)
        path = self.section.get_absolute_url()
        self.assertContains(self.get(path), f'<link rel="canonical" href="http://testserver{path}">')
        self.assertContains(self.get(path + "?page=2"), f'<link rel="canonical" href="http://testserver{path}?page=2">')

    def test_blog_home(self):
        response = self.get(url("home"))
        self.assertContains(response, "<title>وبلاگ | مدرسه نسل قلم</title>")
        self.assertContains(response, '<link rel="alternate" type="application/atom+xml" title="وبلاگ نسل قلم" href="/blog/feed/">')


# ----------------------------------------------------------------------- feeds


class FeedTests(BlogFixture):
    def entries(self, path):
        response = self.get(path)
        self.assertEqual(response["Content-Type"], "application/atom+xml; charset=utf-8")
        root = ElementTree.fromstring(response.content)
        return root, [entry.find(f"{ATOM}title").text for entry in root.findall(f"{ATOM}entry")]

    def test_the_blog_feed(self):
        post = self.publish("نوشته عمومی", excerpt="خلاصه.", body="<p>متن کامل که نباید در خوراک بیاید.</p>")
        make_post(self.author, self.section, title="پیش‌نویس")
        root, titles = self.entries(url("feed"))
        self.assertEqual(root.find(f"{ATOM}title").text, "وبلاگ نسل قلم")
        self.assertEqual(titles, ["نوشته عمومی"])
        entry = root.find(f"{ATOM}entry")
        self.assertEqual(entry.find(f"{ATOM}summary").text, "خلاصه.")
        self.assertEqual(entry.find(f"{ATOM}author/{ATOM}name").text, "مریم احمدی")
        self.assertTrue(entry.find(f"{ATOM}link").get("href").endswith(post.get_absolute_url()))
        self.assertNotIn("متن کامل", self.get(url("feed")).content.decode())

    def test_section_feed(self):
        self.publish("در این بخش")
        other = make_section("دیگر")
        self.author.grants.create(section=other)
        make_post(self.author, other, Post.Status.PUBLISHED, title="در بخش دیگر")
        root, titles = self.entries(url("section_feed", self.section.slug))
        self.assertEqual(titles, ["در این بخش"])
        self.assertEqual(root.find(f"{ATOM}title").text, f"{self.section.title} | وبلاگ نسل قلم")
        self.get(url("section_feed", "ناموجود"), 404)

    @override_settings(BLOG_FEED_ITEMS=2)
    def test_newest_first_up_to_the_limit(self):
        for days in (3, 1, 2):
            self.publish(f"{days} روز پیش", days_ago=days)
        _, titles = self.entries(url("feed"))
        self.assertEqual(titles, ["1 روز پیش", "2 روز پیش"])


# --------------------------------------------------------------- sitemap, robots


class SitemapTests(BlogFixture):
    def locations(self):
        response = self.get("/sitemap.xml")
        root = ElementTree.fromstring(response.content)
        return [loc.text for loc in root.iter(f"{SITEMAP}loc")]

    def test_public_urls_only(self):
        tag, unused_tag = make_tag("با نوشته"), make_tag("بی‌نوشته")
        empty_category = make_category(self.section, "خالی")
        post = self.publish("عمومی")
        post.tags.add(tag)
        draft = make_post(self.author, self.section, category=empty_category, title="پیش‌نویس")
        draft.tags.add(unused_tag)
        scheduled = make_post(
            self.author, self.section, Post.Status.PUBLISHED, category=empty_category,
            published_at=timezone.now() + timedelta(days=1),
        )

        locations = self.locations()
        absolute = lambda path: f"http://testserver{path}"  # noqa: E731
        for path in ("/", "/about/", "/teachers/", "/contact/", url("home"), self.section.get_absolute_url(),
                     self.category.get_absolute_url(), tag.get_absolute_url(), self.author.get_absolute_url(),
                     post.get_absolute_url()):
            self.assertIn(absolute(path), locations, path)
        for path in (empty_category.get_absolute_url(), unused_tag.get_absolute_url(),
                     draft.get_absolute_url(), scheduled.get_absolute_url()):
            self.assertNotIn(absolute(path), locations, path)

    def test_authors_without_a_page_are_left_out(self):
        self.publish()
        BlogAuthor.objects.filter(pk=self.author.pk).update(show_profile=False)
        self.assertNotIn(f"http://testserver{self.author.get_absolute_url()}", self.locations())

    def test_lastmod_follows_the_text(self):
        post = self.publish(days_ago=3)
        response = self.get("/sitemap.xml").content.decode()
        self.assertIn(f"<lastmod>{post.published_dt.date().isoformat()}</lastmod>", response)


class RobotsTests(BlogFixture):
    def test_robots(self):
        response = self.get("/robots.txt")
        self.assertEqual(response["Content-Type"], "text/plain; charset=utf-8")
        text = response.content.decode()
        for line in ("User-agent: *", "Disallow: /admin/", "Disallow: /dashboard/", "Disallow: /blog/write/",
                     "Disallow: /blog/preview/", "Disallow: /supervisor/", "Sitemap: http://testserver/sitemap.xml"):
            self.assertIn(line, text)
        self.assertNotIn("Disallow: /blog/\n", text)
        self.assertEqual(self.client.post("/robots.txt").status_code, 405)

    def test_search_results_are_noindex_not_disallowed(self):
        self.assertNotIn("/blog/search/", self.get("/robots.txt").content.decode())
        self.assertContains(self.get(url("search") + "?q=" + quote("نوشته")), 'content="noindex"')
