"""
The blog's part of /sitemap.xml (D19): its home, the active sections, and
the categories, tags and author pages that have public posts, and the
public posts themselves. ``website.sitemaps`` adds the site's own pages.
"""

from django.contrib.sitemaps import Sitemap
from django.db.models import Exists, OuterRef
from django.urls import reverse

from .models import BlogAuthor, Category, Post, Section, Tag


class BlogHomeSitemap(Sitemap):
    changefreq = "daily"

    def items(self):
        return ["blog:home"]

    def location(self, item):
        return reverse(item)


class SectionSitemap(Sitemap):
    changefreq = "weekly"

    def items(self):
        return Section.objects.filter(is_active=True)


class CategorySitemap(Sitemap):
    changefreq = "weekly"

    def items(self):
        return (
            Category.objects.filter(is_active=True, section__is_active=True)
            .filter(Exists(Post.objects.public().filter(category=OuterRef("pk"))))
            .select_related("section")
        )


class TagSitemap(Sitemap):
    changefreq = "weekly"

    def items(self):
        return Tag.objects.filter(is_active=True).filter(
            Exists(Post.objects.public().filter(tags=OuterRef("pk")))
        )


class AuthorSitemap(Sitemap):
    changefreq = "weekly"

    def items(self):
        return BlogAuthor.objects.filter(show_profile=True).filter(
            Exists(Post.objects.public().filter(author=OuterRef("pk")))
        )


class PostSitemap(Sitemap):
    changefreq = "monthly"

    def items(self):
        return Post.objects.public().only("slug", "published_at", "content_updated_at").order_by("-published_at")

    def lastmod(self, post):
        return post.modified_dt


SITEMAPS = {
    "blog": BlogHomeSitemap,
    "blog-sections": SectionSitemap,
    "blog-categories": CategorySitemap,
    "blog-tags": TagSitemap,
    "blog-authors": AuthorSitemap,
    "blog-posts": PostSitemap,
}
