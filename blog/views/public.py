"""
The public blog (D2). GET only, a strict Content-Security-Policy on every
page (D12), and nothing that isn't public: drafts, submitted, scheduled
and archived posts are a 404 here for everyone; their authors and the
editors use the preview.
"""

from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.csp import CSP
from django.views.decorators.csp import csp_override
from django.views.decorators.http import require_safe

from blog import selectors, seo
from blog.models import BlogPage
from blog.permissions import can_preview

#: The blog's public pages run author-written HTML: even if the sanitizer
#: let something through, a browser would load and run nothing that isn't
#: the site's own. JSON-LD is a data block, not a script, and is allowed.
PUBLIC_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF],
    "img-src": [CSP.SELF],
    "font-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.SELF],
}
public_csp = csp_override(PUBLIC_CSP)


def _page_number(request):
    return request.GET.get("page") or 1


@require_safe
@public_csp
def home(request):
    home = selectors.home(_page_number(request))
    return render(request, "blog/home.html", {
        "page": home.page,
        "home": home,
        "posts": home.posts,
        "meta": seo.home_meta(request, home),
    })


def _listing(request, listing):
    page = BlogPage.load()
    return render(request, "blog/listing.html", {
        "page": page,
        "listing": listing,
        "posts": listing.posts,
        "meta": seo.listing_meta(request, page, listing),
    })


@require_safe
@public_csp
def section(request, section):
    return _listing(request, selectors.section_listing(section, _page_number(request)))


@require_safe
@public_csp
def category(request, section, category):
    return _listing(request, selectors.category_listing(section, category, _page_number(request)))


@require_safe
@public_csp
def tag(request, tag):
    return _listing(request, selectors.tag_listing(tag, _page_number(request)))


@require_safe
@public_csp
def author(request, author):
    return _listing(request, selectors.author_listing(author, _page_number(request)))


@require_safe
@public_csp
def search(request):
    return _listing(request, selectors.search(request.GET.get("q", ""), _page_number(request)))


def _post(request, post_page):
    page = BlogPage.load()
    return render(request, "blog/post.html", {
        "page": page,
        "post_page": post_page,
        "post": post_page.post,
        "meta": seo.post_meta(request, page, post_page),
    })


@require_safe
@public_csp
def post(request, slug):
    return _post(request, selectors.post_page(slug))


@require_safe
@public_csp
def preview(request, pk):
    """
    A post as it will look, for its author and editors only; a 404 for
    anyone else (the post's existence isn't revealed). A post that is
    already public goes to its public URL.
    """

    post_page = selectors.preview_page(pk)
    if not can_preview(request.user, post_page.post):
        raise Http404("نوشته‌ای با این نشانی نیست.")
    if post_page.post.is_public:
        return redirect(post_page.post)
    return _post(request, post_page)
