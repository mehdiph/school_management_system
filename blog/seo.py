"""
What the blog's public pages tell search engines and link previews (D19):
title, description, canonical URL, Open Graph, the feed link and the
JSON-LD data blocks. Built here from the selectors' data, rendered by
``blog/_meta.html``; views only pick which one to build.
"""

from dataclasses import dataclass, field

from django.urls import reverse

from .text import summary


@dataclass
class Crumb:
    title: str
    url: str = ""  # "" for the current page


@dataclass
class PageMeta:
    title: str
    description: str = ""
    canonical: str = ""
    og_type: str = "website"
    image: str = ""
    image_alt: str = ""
    published: object = None
    modified: object = None
    noindex: bool = False
    feed_url: str = ""
    feed_title: str = ""
    crumbs: list = field(default_factory=list)
    json_ld: list = field(default_factory=list)


def _absolute(request, url):
    return request.build_absolute_uri(url) if url else ""


def _canonical(request, page_number=1):
    """The page's own URL, with ``?page=`` only beyond the first page."""

    url = request.path
    if page_number and page_number > 1:
        url = f"{url}?page={page_number}"
    return request.build_absolute_uri(url)


def blog_crumb(page):
    return Crumb(page.title, reverse("blog:home"))


def breadcrumbs_ld(request, crumbs):
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": position,
                "name": crumb.title,
                "item": _absolute(request, crumb.url or request.path),
            }
            for position, crumb in enumerate(crumbs, start=1)
        ],
    }


def _default_image(request, page):
    return _absolute(request, page.og_image.url) if page.og_image else ""


def _feed(page, section=None):
    if section is not None:
        return reverse("blog:section_feed", args=[section.slug]), f"{section.title} | {page.title}"
    return reverse("blog:feed"), page.title


def home_meta(request, home):
    page = home.page
    feed_url, feed_title = _feed(page)
    return PageMeta(
        title=page.meta_title or page.title,
        description=page.meta_description or page.intro,
        canonical=_canonical(request, home.posts.number),
        image=_default_image(request, page),
        feed_url=feed_url,
        feed_title=feed_title,
    )


LISTING_DESCRIPTIONS = {
    "category": "نوشته‌های «{title}» در بخش {section}، {blog}.",
    "tag": "نوشته‌های {blog} با برچسب «{title}».",
    "author": "نوشته‌های {title} در {blog}.",
}


def listing_meta(request, page, listing):
    """Section, category, tag, author and search pages."""

    crumbs = [blog_crumb(page)]
    if listing.section is not None:
        crumbs.append(Crumb(listing.section.title, listing.section.get_absolute_url()))
    if listing.kind != "section":
        crumbs.append(Crumb(listing.title))
    else:
        crumbs[-1].url = ""

    if listing.kind == "section":
        description = listing.section.description
    elif listing.kind == "author":
        description = summary(listing.author.public_bio, 160) or LISTING_DESCRIPTIONS["author"].format(
            title=listing.title, blog=page.title
        )
    elif listing.kind == "search":
        description = ""
    else:
        description = LISTING_DESCRIPTIONS[listing.kind].format(
            title=listing.title, blog=page.title, section=getattr(listing.section, "title", "")
        )

    if listing.kind == "search":
        title = f"جستجوی «{listing.query}»" if listing.query else "جستجو"
    else:
        title = listing.title
    number = listing.posts.number if listing.posts is not None else 1
    feed_url, feed_title = _feed(page, listing.section)
    meta = PageMeta(
        title=f"{title} | {page.title}",
        description=description,
        canonical="" if listing.kind == "search" else _canonical(request, number),
        image=_absolute(request, listing.author.photo_url) if listing.kind == "author" else _default_image(request, page),
        noindex=listing.kind == "search",
        feed_url=feed_url,
        feed_title=feed_title,
        crumbs=crumbs,
    )
    if listing.kind != "search":
        meta.json_ld.append(breadcrumbs_ld(request, crumbs))
    return meta


def post_meta(request, page, post_page):
    post = post_page.post
    crumbs = [blog_crumb(page), Crumb(post.section.title, post.section.get_absolute_url())]
    if post.category_id and post.category.is_active:
        crumbs.append(Crumb(post.category.title, post.category.get_absolute_url()))
    crumbs.append(Crumb(post.title))

    image = _absolute(request, post.cover_url) or _default_image(request, page)
    url = request.build_absolute_uri(post.get_absolute_url())
    feed_url, feed_title = _feed(page, post.section)
    meta = PageMeta(
        title=post.seo_title,
        description=post.seo_description,
        canonical="" if post_page.preview else url,
        og_type="article",
        image=image,
        image_alt=post.cover_alt if post.cover else "",
        published=post.published_dt,
        modified=post.modified_dt,
        noindex=post_page.preview,
        feed_url=feed_url,
        feed_title=feed_title,
        crumbs=crumbs,
    )
    if post_page.preview:
        return meta

    author = post.author
    article = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": post.title,
        "description": post.seo_description,
        "inLanguage": "fa-IR",
        "mainEntityOfPage": url,
        "datePublished": post.published_dt.isoformat(),
        "dateModified": post.modified_dt.isoformat(),
        "author": {"@type": "Person", "name": author.name},
        "articleSection": post.section.title,
    }
    if author.show_profile:
        article["author"]["url"] = request.build_absolute_uri(author.get_absolute_url())
    if image:
        article["image"] = image
    if post.public_tags:
        article["keywords"] = [tag.name for tag in post.public_tags]
    meta.json_ld = [article, breadcrumbs_ld(request, crumbs)]
    return meta
