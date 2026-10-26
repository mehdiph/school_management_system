"""
Atom feeds of the public posts (D19): the whole blog at /blog/feed/ and
one per section. Title, summary and link only, not the full text; the
newest ``BLOG_FEED_ITEMS``.
"""

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.feedgenerator import Atom1Feed

from .models import BlogPage, Section
from .selectors import public_posts


class LatestPostsFeed(Feed):
    feed_type = Atom1Feed
    language = "fa"

    def get_object(self, request):
        return BlogPage.load(), None

    def title(self, obj):
        page, section = obj
        return f"{section.title} | {page.title}" if section else page.title

    def subtitle(self, obj):
        page, section = obj
        return section.description if section else page.intro

    def link(self, obj):
        page, section = obj
        return section.get_absolute_url() if section else reverse("blog:home")

    def items(self, obj):
        page, section = obj
        posts = public_posts()
        if section is not None:
            posts = posts.filter(section=section)
        return posts[: settings.BLOG_FEED_ITEMS]

    def item_title(self, post):
        return post.title

    def item_description(self, post):
        return post.summary

    def item_pubdate(self, post):
        return post.published_dt

    def item_updateddate(self, post):
        return post.modified_dt

    def item_author_name(self, post):
        return post.author.name

    def item_categories(self, post):
        return [post.section.title]


class SectionPostsFeed(LatestPostsFeed):
    def get_object(self, request, section):
        return BlogPage.load(), get_object_or_404(Section, slug=section, is_active=True)
