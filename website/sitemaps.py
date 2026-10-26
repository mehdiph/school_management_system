"""The public site's own pages in /sitemap.xml; the blog adds its pages (``blog.sitemaps``)."""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class PagesSitemap(Sitemap):
    changefreq = "monthly"

    def items(self):
        return ["website:website", "website:about", "website:teachers", "website:contact"]

    def location(self, item):
        return reverse(item)
