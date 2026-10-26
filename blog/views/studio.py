"""
«نوشته‌های من» (D6): where authors write, inside their own panel's shell.

Teachers get the teacher panel (``blog/write/teacher/``), everyone else
the ``base.html`` shell with the supervisor panel's components
(``blog/write/panel/``). Every view is behind ``author_required`` and
starts from the author's own posts (``permissions.author_posts``), so
another author's post is a 404. Changes go through ``blog.services``;
publishing stays with the editors in the admin.
"""

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST, require_safe

from accounts.models import User
from blog import permissions, selectors, services
from blog.forms import AuthorPostForm, AuthorProfileForm
from blog.models import BlogPage, Post
from blog.permissions import author_required

TEACHER, PANEL = "teacher", "panel"
INPUT_CLASS = {TEACHER: "ui-input", PANEL: ""}
TRANSITIONS = {
    "withdraw": (services.withdraw, "نوشته پس گرفته شد و دوباره پیش‌نویس است."),
    "archive": (services.archive, "نوشته بایگانی شد."),
    "reopen": (services.reopen, "نوشته به پیش‌نویس برگشت."),
}


def _shell(request):
    return TEACHER if request.user.role == User.Roles.TEACHER else PANEL


def _render(request, name, context, status=200):
    shell = _shell(request)
    if request.user.role == User.Roles.SUPERVISOR:
        # The panel's sidebar shows the supervisor's grade (as require_supervisor sets it).
        from supervisor.models import SupervisorProfile

        request.supervisor = SupervisorProfile.objects.select_related("grade").filter(user=request.user).first()
    return render(request, f"blog/write/{shell}/{name}.html", context, status=status)


def _own_post(request, pk):
    return get_object_or_404(permissions.author_posts(request.user).select_related("section", "category"), pk=pk)


def _post_form(request, post, sections, page):
    shell = _shell(request)
    upload_url = reverse("blog:write_image", args=[post.pk]) if post.pk else ""
    return AuthorPostForm(
        request.POST or None,
        request.FILES or None,
        instance=post,
        user=request.user,
        sections=sections,
        upload_url=upload_url,
        input_class=INPUT_CLASS[shell],
        privacy_label=page.author_ack,
    )


def _save(request, form):
    """
    Save the form's draft, and submit it when «ارسال برای بررسی» was
    pressed. Returns the response, or None to show the form again.
    """

    submitting = request.POST.get("action") == "submit"
    if submitting and not form.cleaned_data.get("privacy_ack"):
        form.add_error("privacy_ack", "پیش از ارسال، این جمله را بخوانید و تیک بزنید.")
        return None
    post = form.instance
    try:
        with transaction.atomic():
            if post.pk is None:
                fields = {name: form.cleaned_data[name] for name in form.saved_fields if name != "section"}
                post = services.create_draft(request.user, form.cleaned_data["section"], **fields)
                services.sync_tags(post, form.cleaned_data["tag_names"])
            else:
                services.save_draft(post, request.user, form.saved_fields, form.cleaned_data["tag_names"])
    except (PermissionDenied, services.TransitionError) as error:
        form.add_error(None, str(error))
        return None
    except ValidationError as error:
        form.add_error(None, " ".join(error.messages))
        return None

    if not submitting:
        messages.success(request, "پیش‌نویس ذخیره شد.")
        return redirect("blog:write_edit", post.pk)
    try:
        services.submit(post, request.user, privacy_ack=True)
    except (PermissionDenied, services.TransitionError) as error:
        messages.error(request, f"پیش‌نویس ذخیره شد، ولی فرستاده نشد: {error}")
        return redirect("blog:write_edit", post.pk)
    messages.success(request, "نوشته برای بررسی فرستاده شد. پس از بررسی ویراستار منتشر می‌شود.")
    return redirect("blog:write")


@require_safe
@author_required
def write_list(request):
    dashboard = selectors.author_dashboard(request.user, request.GET.get("tab"), request.GET.get("page"))
    return _render(request, "list", {"dashboard": dashboard})


@author_required
def write_new(request):
    sections = list(permissions.writable_sections(request.user))
    if not sections:
        messages.error(request, "هنوز بخشی برای نوشتن به شما داده نشده است؛ با مدیر سایت هماهنگ کنید.")
        return redirect("blog:write")
    page = BlogPage.load()
    form = _post_form(request, Post(), sections, page)
    if request.method == "POST" and form.is_valid():
        response = _save(request, form)
        if response is not None:
            return response
    return _render(request, "edit", {"form": form, "post": None, "page": page})


@author_required
def write_edit(request, pk):
    post = _own_post(request, pk)
    reason = permissions.author_edit_block_reason(request.user, post)
    if reason:
        if request.method == "POST":
            messages.error(request, reason)
            return redirect("blog:write_edit", post.pk)
        return _render(request, "edit", {"form": None, "post": post, "reason": reason})

    page = BlogPage.load()
    form = _post_form(request, post, permissions.writable_sections(request.user), page)
    if request.method == "POST" and form.is_valid():
        response = _save(request, form)
        if response is not None:
            return response
    return _render(request, "edit", {"form": form, "post": post, "page": page})


@require_POST
@author_required
def write_action(request, pk, action):
    """Withdraw, archive or reopen the author's own post (D8)."""

    post = _own_post(request, pk)
    if action not in TRANSITIONS:
        return redirect("blog:write_edit", post.pk)
    step, done = TRANSITIONS[action]
    try:
        step(post, request.user)
    except (PermissionDenied, services.TransitionError) as error:
        messages.error(request, str(error))
    else:
        messages.success(request, done)
    return redirect("blog:write_edit", post.pk)


@require_POST
@author_required
def write_image(request, pk):
    """POST an image from the editor -> ``{"url", "width", "height"}`` (the admin's endpoint, for authors)."""

    post = _own_post(request, pk)
    file = request.FILES.get("image")
    if file is None:
        return JsonResponse({"error": "فایلی فرستاده نشد."}, status=400)
    try:
        image = services.add_image(post, file, request.user)
    except ValidationError as error:
        return JsonResponse({"error": " ".join(error.messages)}, status=400)
    except PermissionDenied as error:
        return JsonResponse({"error": str(error)}, status=403)
    except OSError:
        return JsonResponse({"error": "این فایل تصویر قابل خواندن نیست."}, status=400)
    return JsonResponse({"url": image.url, "width": image.width, "height": image.height})


@author_required
def write_profile(request):
    """The author's own bio and photo; their name and page switch are the admin's (D4)."""

    author = permissions.author_for(request.user)
    form = AuthorProfileForm(
        request.POST or None, request.FILES or None, instance=author, input_class=INPUT_CLASS[_shell(request)],
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "معرفی شما ذخیره شد.")
        return redirect("blog:write_profile")
    return _render(request, "profile", {"form": form, "author": author, "author_page": selectors.author_page_url(author)})
