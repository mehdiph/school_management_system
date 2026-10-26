"""
Read side of the public blog: what each page shows, in a fixed number of
queries however many posts, tags and sections there are (plan finding 7).
Every post comes from ``Post.objects.public()`` (or ``public_q`` inside
a count), so a draft, a submitted, scheduled or archived post, or a post
of an inactive section, appears nowhere. The authoring area's list
(``author_dashboard``) starts from ``permissions.author_posts`` instead.
"""

from dataclasses import dataclass, field
from datetime import timezone as dt_timezone

from django.conf import settings
from django.core.paginator import InvalidPage, Paginator
from django.db.models import Case, Count, Exists, IntegerField, OuterRef, Prefetch, Q, Value, When
from django.http import Http404
from django.shortcuts import get_object_or_404

from . import permissions
from .models import BlogAuthor, BlogPage, Category, Post, Section, Tag
from .models.post import public_q
from .text import normalize, search_key

# What a post card shows: its section and category, and its author's name
# and photo (the teacher card's photo is a fallback).
CARD_RELATED = ("section", "category__section", "author__user", "author__teacher_card")
# The post page also says whether the author's teacher card is public.
POST_RELATED = CARD_RELATED + ("author__teacher_card__teacher__staff",)
AUTHOR_RELATED = ("user", "teacher_card__teacher__staff")

SEARCH_MIN_LENGTH = 2
TAG_CLOUD_SIZE = 40
RELATED_POSTS = 3
FEATURED_POSTS = 3


def public_posts():
    return Post.objects.public().select_related(*CARD_RELATED)


def _public_tags():
    return Prefetch("tags", queryset=Tag.objects.filter(is_active=True), to_attr="public_tags")


def _counted(queryset):
    """Sections, categories or tags, each with ``post_count``: its number of public posts."""

    return queryset.annotate(post_count=Count("posts", filter=public_q("posts__"), distinct=True))


def paginate(queryset, number):
    """One page of ``BLOG_PAGE_SIZE`` posts; a page number that isn't there is a 404."""

    paginator = Paginator(queryset, settings.BLOG_PAGE_SIZE)
    try:
        return paginator.page(number or 1)
    except InvalidPage:
        raise Http404("صفحه‌ای با این شماره نیست.")


def public_sections():
    """Active sections, each with its number of public posts (one query)."""

    return _counted(Section.objects.filter(is_active=True))


def public_categories(section):
    """The section's active categories that have public posts: its chips."""

    return [c for c in _counted(section.categories.filter(is_active=True)) if c.post_count]


def tag_cloud():
    """Active tags with public posts, most used first."""

    return list(
        _counted(Tag.objects.filter(is_active=True))
        .filter(post_count__gt=0)
        .order_by("-post_count", "name")[:TAG_CLOUD_SIZE]
    )


# ------------------------------------------------------------------ pages


@dataclass
class Home:
    page: BlogPage
    sections: list
    featured: list
    posts: object  # a Paginator page
    tags: list


def home(number):
    """
    The blog home: the sections, up to three featured posts (on the first
    page) and the latest posts without them, so a post is never listed
    twice and the pages don't shift when a post is featured.
    """

    featured = list(public_posts().filter(is_featured=True)[:FEATURED_POSTS])
    latest = public_posts().exclude(pk__in=[post.pk for post in featured])
    posts = paginate(latest, number)
    first = posts.number == 1  # the later pages are only the list
    return Home(
        page=BlogPage.load(),
        sections=list(public_sections()) if first else [],
        featured=featured if first else [],
        posts=posts,
        tags=tag_cloud() if first else [],
    )


@dataclass
class Listing:
    """A list page: a section, a category, a tag, an author or a search."""

    kind: str
    title: str
    posts: object = None  # a Paginator page; None for a search without a query
    section: Section = None
    category: Category = None
    categories: list = field(default_factory=list)
    tag: Tag = None
    author: BlogAuthor = None
    query: str = ""


def section_listing(slug, number):
    section = get_object_or_404(Section, slug=slug, is_active=True)
    return Listing(
        kind="section",
        title=section.title,
        section=section,
        categories=public_categories(section),
        posts=paginate(public_posts().filter(section=section), number),
    )


def category_listing(section_slug, slug, number):
    category = get_object_or_404(
        Category.objects.select_related("section"),
        section__slug=section_slug,
        section__is_active=True,
        slug=slug,
        is_active=True,
    )
    return Listing(
        kind="category",
        title=category.title,
        section=category.section,
        category=category,
        categories=public_categories(category.section),
        posts=paginate(public_posts().filter(category=category), number),
    )


def tag_listing(slug, number):
    """A tag's posts; a 404 while it has none in public (D14)."""

    tag = get_object_or_404(Tag, slug=slug, is_active=True)
    posts = paginate(public_posts().filter(tags=tag), number)
    if not posts.paginator.count:
        raise Http404("این برچسب نوشته منتشرشده‌ای ندارد.")
    return Listing(kind="tag", title=tag.name, tag=tag, posts=posts)


def author_listing(slug, number):
    """An author's page, while it is switched on and they have public posts (D18)."""

    author = get_object_or_404(BlogAuthor.objects.select_related(*AUTHOR_RELATED), slug=slug, show_profile=True)
    posts = paginate(public_posts().filter(author=author), number)
    if not posts.paginator.count:
        raise Http404("این نویسنده نوشته منتشرشده‌ای ندارد.")
    return Listing(kind="author", title=author.name, author=author, posts=posts)


def search(query, number):
    """
    Posts whose title, excerpt or text contain the query, in any spelling
    (ی/ي, ک/ك, digits, ZWNJ or a space: ``search_key``). A query shorter
    than two letters searches nothing.
    """

    query = normalize(query)[:100]
    listing = Listing(kind="search", title="جستجو", query=query)
    key = search_key(query)
    if len(key) >= SEARCH_MIN_LENGTH:
        listing.posts = paginate(public_posts().filter(search_text__contains=key), number)
    return listing


# ------------------------------------------------------------------- post


@dataclass
class PostPage:
    post: Post
    related: list = field(default_factory=list)
    newer: Post = None
    older: Post = None
    preview: bool = False

    @property
    def show_toc(self):
        return len(self.post.toc) >= settings.BLOG_TOC_MIN_HEADINGS


def _post_queryset(queryset):
    return queryset.select_related(*POST_RELATED).prefetch_related(_public_tags())


def related_posts(post):
    """
    Up to three other public posts: the same category first, then shared
    tags, then the same section; newest first within each.
    """

    tag_ids = [tag.pk for tag in post.public_tags]
    tagged = Post.tags.through.objects.filter(tag_id__in=tag_ids).values("post_id")
    ranks = []
    if post.category_id:
        ranks.append(When(category_id=post.category_id, then=Value(2)))
    if tag_ids:
        ranks.append(When(pk__in=tagged, then=Value(1)))
    match = Q(section_id=post.section_id) | (Q(pk__in=tagged) if tag_ids else Q())
    return list(
        public_posts()
        .exclude(pk=post.pk)
        .filter(match)
        .annotate(rank=Case(*ranks, default=Value(0), output_field=IntegerField()))
        .order_by("-rank", "-published_at", "-pk")[:RELATED_POSTS]
    )


def neighbours(post):
    """The next newer and the next older public post of the same section."""

    same = Post.objects.public().filter(section_id=post.section_id).exclude(pk=post.pk).only("title", "slug")
    at = post.published_dt.astimezone(dt_timezone.utc)  # stored in UTC (Post.save)
    newer = same.filter(Q(published_at__gt=at) | Q(published_at=at, pk__gt=post.pk)).order_by("published_at", "pk")
    older = same.filter(Q(published_at__lt=at) | Q(published_at=at, pk__lt=post.pk)).order_by("-published_at", "-pk")
    return newer.first(), older.first()


def post_page(slug):
    post = get_object_or_404(_post_queryset(Post.objects.public()), slug=slug)
    newer, older = neighbours(post)
    return PostPage(post=post, related=related_posts(post), newer=newer, older=older)


def preview_page(pk):
    """Any post, for its author and editors (``blog.permissions.can_preview``): only the post itself."""

    return PostPage(post=get_object_or_404(_post_queryset(Post.objects.all()), pk=pk), preview=True)


# ---------------------------------------------------------- teachers page


def author_pages_by_card(card_ids):
    """
    {teacher card id: author page URL} for the cards whose linked author has
    a public author page (D21), in one query. With several authors on one
    card, the first by id.
    """

    rows = (
        BlogAuthor.objects.filter(teacher_card_id__in=card_ids, show_profile=True)
        .filter(Exists(Post.objects.public().filter(author=OuterRef("pk"))))
        .order_by("-pk")
        .values_list("teacher_card_id", "slug")
    )
    return {card_id: BlogAuthor(slug=slug).get_absolute_url() for card_id, slug in rows}


# ---------------------------------------------------------- authoring area

WRITE_PAGE_SIZE = 20
WRITE_TABS = (
    ("all", "همه"),
    (Post.Status.DRAFT, "پیش‌نویس"),
    (Post.Status.SUBMITTED, "در انتظار بررسی"),
    (Post.Status.PUBLISHED, "منتشرشده"),
    (Post.Status.ARCHIVED, "بایگانی"),
)


@dataclass
class WriteTab:
    key: str
    label: str
    count: int
    is_current: bool


@dataclass
class AuthorDashboard:
    tab: str
    tabs: list
    page: object


def author_dashboard(user, tab, number):
    """
    «نوشته‌های من»: the author's own posts on one tab (scheduled posts are
    under «منتشرشده»), newest edit first, with every tab's count in one
    aggregate query.
    """

    posts = permissions.author_posts(user)
    keys = [key for key, _ in WRITE_TABS]
    tab = tab if tab in keys else "all"
    counts = posts.aggregate(
        all=Count("pk"),
        **{key: Count("pk", filter=Q(status=key)) for key in keys[1:]},
    )
    shown = posts if tab == "all" else posts.filter(status=tab)
    paginator = Paginator(shown.select_related("section", "category").order_by("-updated_at", "-pk"), WRITE_PAGE_SIZE)
    try:
        page = paginator.page(number or 1)
    except InvalidPage:
        raise Http404("صفحه‌ای با این شماره نیست.")
    return AuthorDashboard(
        tab=tab,
        tabs=[WriteTab(key, label, counts[key], key == tab) for key, label in WRITE_TABS],
        page=page,
    )


def author_page_url(author):
    """The author's public page while it exists (``author_listing``'s rule), else ""."""

    if author.show_profile and Post.objects.public().filter(author=author).exists():
        return author.get_absolute_url()
    return ""
