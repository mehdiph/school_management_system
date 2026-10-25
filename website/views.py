from django.contrib import messages
from django.db.models import Prefetch, Q, prefetch_related_objects
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_safe

from accounts.validators import normalize_mobile

from .forms import ContactForm, form_token
from .models import (
    AboutFact,
    AboutHighlight,
    AboutMilestone,
    AboutPage,
    AboutPerson,
    AboutPhoto,
    AboutValue,
    ContactChannel,
    ContactLocation,
    ContactPage,
    ContactTopic,
    FeatureCard,
    HeroSlide,
    LandingPage,
    LearningPoint,
    TeachersPage,
)
from .selectors import public_teachers, teachers_page_listing
from .services import client_ip_hash, rate_limited, submit_contact_message

RATE_LIMIT_MESSAGE = (
    "از این دستگاه یا با این شماره پیام‌های زیادی ثبت شده است؛ "
    "کمی بعد دوباره تلاش کنید یا با دفتر مدرسه تماس بگیرید."
)


def website(request):
    page = LandingPage.load()

    # One query per enabled section; disabled sections cost nothing.
    sections = [
        ("show_hero_slider", "slides", HeroSlide.objects.all()),
        ("show_features", "features", FeatureCard.objects.all()),
        ("show_learning", "learning_points", LearningPoint.objects.all()),
    ]
    lookups = [
        Prefetch(relation, queryset=queryset.filter(is_active=True), to_attr=f"active_{relation}")
        for flag, relation, queryset in sections
        if getattr(page, flag)
    ]
    prefetch_related_objects([page], *lookups)

    context = {"page": page}
    for flag, relation, _ in sections:
        context[relation] = getattr(page, f"active_{relation}", [])
    # The teachers are shared with the «معلمان» page, not the landing page's own rows.
    context["teachers"] = list(public_teachers().filter(on_home=True)) if page.show_teachers else []

    return render(request, "website/index.html", context)


def _public_locations():
    """Locations shown on the public site: active, of an active branch (or none)."""
    return (
        ContactLocation.objects.filter(is_active=True)
        .filter(Q(branch__isnull=True) | Q(branch__is_active=True))
        .select_related("branch")
    )


def _load_contact_page():
    """
    The page with its active locations (of active branches only), channels
    and topics: one query each, however many rows there are. Channels are
    grouped under their location here, in Python.
    """

    page = ContactPage.load()
    lookups = [
        Prefetch("locations", queryset=_public_locations(), to_attr="active_locations"),
        Prefetch("channels", queryset=ContactChannel.objects.filter(is_active=True), to_attr="active_channels"),
    ]
    if page.show_form:
        lookups.append(Prefetch("topics", queryset=ContactTopic.objects.filter(is_active=True), to_attr="active_topics"))
    prefetch_related_objects([page], *lookups)

    by_location = {}
    for channel in page.active_channels:
        by_location.setdefault(channel.location_id, []).append(channel)
    for location in page.active_locations:
        location.contact_channels = by_location.get(location.pk, [])
    page.school_channels = by_location.get(None, [])
    return page


def _call_target(page):
    """The hero's and the phone bar's call button: the first school-wide phone."""
    for channel in page.school_channels:
        if not channel.is_email:
            return {"href": channel.href, "display": channel.display_value}
    for location in page.active_locations:
        for channel in location.contact_channels:
            if not channel.is_email:
                return {"href": channel.href, "display": channel.display_value}
        if location.branch_phone:
            return {"href": location.branch_phone_href, "display": location.branch_phone_display}
    return None


def _directions_url(page):
    for location in page.active_locations:
        if location.map_links:
            return location.map_links[0][1]
    return ""


@require_http_methods(["GET", "POST"])
def contact(request):
    page = _load_contact_page()
    locations = page.active_locations
    topics = getattr(page, "active_topics", [])
    form = ContactForm(
        request.POST if request.method == "POST" and page.show_form else None,
        topics=topics,
        locations=locations,
    )
    status = 200
    success_url = reverse("website:contact") + "#contact-form"

    if form.is_bound:
        if form.is_spam:
            # Look exactly like a success, so the bot learns nothing.
            messages.success(request, page.success_text(normalize_mobile(request.POST.get("mobile"))))
            return redirect(success_url)
        if form.is_valid():
            ip_hash = client_ip_hash(request)
            if rate_limited(ip_hash, form.cleaned_data["mobile"]):
                form.add_error(None, RATE_LIMIT_MESSAGE)
                status = 429
            else:
                submit_contact_message(form.cleaned_data, ip_hash)
                messages.success(request, page.success_text(form.cleaned_data["mobile"]))
                return redirect(success_url)

    context = {
        "page": page,
        "locations": locations if page.show_locations else [],
        "channels": page.school_channels if page.show_channels else [],
        "form": form,
        "form_started": form_token(),
        "call": _call_target(page),
        "directions_url": _directions_url(page),
    }
    return render(request, "website/contact.html", context, status=status)


ABOUT_SECTIONS = [
    ("show_timeline", "milestones", AboutMilestone.objects.all()),
    ("show_values", "belief_values", AboutValue.objects.all()),
    ("show_highlights", "highlights", AboutHighlight.objects.all()),
    ("show_facts", "facts", AboutFact.objects.all()),
    (
        "show_team",
        "people",
        AboutPerson.objects.filter(Q(staff__isnull=True) | Q(staff__is_active=True)).select_related("staff__user"),
    ),
    ("show_gallery", "photos", AboutPhoto.objects.all()),
]


@require_safe
def about(request):
    page = AboutPage.load()

    # One query per enabled section; disabled sections cost nothing.
    lookups = [
        Prefetch(relation, queryset=queryset.filter(is_active=True), to_attr=f"active_{relation}")
        for flag, relation, queryset in ABOUT_SECTIONS
        if getattr(page, flag)
    ]
    prefetch_related_objects([page], *lookups)

    context = {
        "page": page,
        "locations": list(_public_locations()) if page.show_branches else [],
    }
    for flag, relation, _ in ABOUT_SECTIONS:
        context[relation] = getattr(page, f"active_{relation}", [])

    return render(request, "website/about.html", context)


@require_safe
def teachers(request):
    """
    The «معلمان» page. ``?group=<id>`` shows one group; with
    ``?partial=1`` (the page's JS) only the filter and the list are
    rendered, to be swapped into the page (ADR-015).
    """

    page = TeachersPage.load()
    context = {"page": page, "listing": teachers_page_listing(page, request.GET.get("group"))}
    if request.GET.get("partial") == "1":
        return render(request, "website/teachers/_directory.html", context)
    return render(request, "website/teachers.html", context)
