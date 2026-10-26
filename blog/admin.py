"""
The blog in the admin («وبلاگ»): its page texts, sections and categories,
tags, authors (who may write where), and posts with the review queue.

Publishing is never a plain field edit: the status changes only through
``blog.services``, from the post's «بررسی و انتشار» page (checklist
required) or the bulk actions, which need ``blog.publish_post`` (D8).
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join

from core.templatetags.jalali_tags import jalali_datetime
from website.admin import COMPACT_TEXTAREA, SingletonAdmin, image_preview

from . import permissions, services
from .forms import BlogAuthorAdminForm, BulkPublishForm, PostAdminForm, PublishForm, ReturnForm, TagMergeForm
from .models import AuthorSection, BlogAuthor, BlogPage, Category, Paper, Post, PostAwaitingReview, Section, Tag
from .models.post import public_q, utc_now
from .text import search_key
from .widgets import EditorWidget

PAPER_SWATCH = {
    Paper.TOMATO: "#ff7a59",
    Paper.SUNFLOWER: "#ffd23f",
    Paper.GRASS: "#5cc98f",
    Paper.SKY: "#5db2ff",
    Paper.GRAPE: "#a58bff",
    Paper.BUBBLEGUM: "#ff94c6",
}


# ------------------------------------------------------------------ page, sections


@admin.register(BlogPage)
class BlogPageAdmin(SingletonAdmin):
    formfield_overrides = COMPACT_TEXTAREA
    readonly_fields = ("og_image_preview",)
    fieldsets = (
        ("صفحه اصلی وبلاگ", {"fields": ("title", "intro")}),
        (
            "حریم خصوصی دانش‌آموزان",
            {
                "description": "این متن‌ها در صفحه نوشتن و پیش از انتشار نمایش داده می‌شوند.",
                "fields": ("author_reminder", "author_ack", "review_checklist"),
            },
        ),
        ("سئو و اشتراک‌گذاری", {"fields": ("meta_title", "meta_description", "og_image", "og_image_preview")}),
    )

    @admin.display(description="پیش‌نمایش")
    def og_image_preview(self, obj):
        return image_preview(obj.og_image.url if obj.og_image else "", 100)


class CategoryInline(admin.TabularInline):
    model = Category
    extra = 0
    fields = ("title", "slug", "order", "is_active")


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    inlines = [CategoryInline]
    list_display = ("title", "paper_swatch", "description", "public_posts", "order", "is_active")
    list_editable = ("order", "is_active")
    fields = ("title", "description", "paper", "slug", "order", "is_active")

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            public_count=Count("posts", filter=public_q("posts__"), distinct=True)
        )

    @admin.display(description="رنگ کاغذ", ordering="paper")
    def paper_swatch(self, obj):
        return format_html(
            '<span style="display:inline-block;width:1.1em;height:1.1em;border-radius:3px;'
            'vertical-align:middle;background:{}"></span> {}',
            PAPER_SWATCH.get(obj.paper, "#ccc"),
            obj.get_paper_display(),
        )

    @admin.display(description="نوشته‌های منتشرشده", ordering="public_count")
    def public_posts(self, obj):
        return obj.public_count


# ------------------------------------------------------------------------- tags


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "public_posts", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "key")
    fields = ("name", "slug", "is_active")
    actions = ["merge_tags"]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            public_count=Count("posts", filter=public_q("posts__"), distinct=True)
        )

    @admin.display(description="نوشته‌های منتشرشده", ordering="public_count")
    def public_posts(self, obj):
        return obj.public_count

    def get_search_results(self, request, queryset, search_term):
        # Find «كتاب خوانی» when typing «کتاب‌خوانی», and the reverse.
        results, distinct = super().get_search_results(request, queryset, search_term)
        key = search_key(search_term)
        if key:
            results = results | queryset.filter(key__contains=key)
        return results, distinct

    @admin.action(description="ادغام در برچسب دیگر…", permissions=["change"])
    def merge_tags(self, request, queryset):
        form = TagMergeForm(request.POST if "apply" in request.POST else None)
        if form.is_bound and form.is_valid():
            target = form.cleaned_data["target"]
            count = services.merge_tags(list(queryset), target)
            self.message_user(request, f"برچسب‌ها در «{target}» ادغام شدند؛ {count} نوشته به‌روز شد.", messages.SUCCESS)
            return None
        return render(request, "admin/blog/tag/merge.html", {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": "ادغام برچسب‌ها",
            "tags": queryset,
            "form": form,
            "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
        })


# ---------------------------------------------------------------------- authors


@admin.register(BlogAuthor)
class BlogAuthorAdmin(admin.ModelAdmin):
    form = BlogAuthorAdminForm
    list_display = ("name_column", "user", "role_column", "sections_column", "writing_status", "is_active")
    list_filter = ("is_active", "sections", "user__role")
    list_select_related = ("user", "user__staff_profile")
    search_fields = ("display_name", "user__first_name", "user__last_name", "user__username")
    autocomplete_fields = ("user", "teacher_card")
    readonly_fields = ("writing_status", "grants_column", "photo_preview")
    fieldsets = (
        (
            "نویسنده",
            {
                "description": "نویسنده شدن اجازه‌ای جدا از نقش است. فقط کسانی می‌نویسند که هم حسابشان فعال است، "
                               "هم نقششان اجازه دارد، هم اینجا «اجازه نوشتن» دارند و هم بخشی برایشان تیک خورده است.",
                "fields": ("user", "is_active", "writing_status", "grant_sections", "grants_column"),
            },
        ),
        (
            "معرفی عمومی",
            {
                "description": "این اطلاعات در سایت عمومی، زیر نوشته‌ها و در صفحه نویسنده نمایش داده می‌شوند.",
                "fields": ("display_name", "bio", "photo", "photo_preview", "teacher_card", "show_profile", "slug"),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("sections")

    @admin.display(description="نام", ordering="display_name")
    def name_column(self, obj):
        return obj.name

    @admin.display(description="نقش", ordering="user__role")
    def role_column(self, obj):
        return obj.user.get_role_display()

    @admin.display(description="بخش‌ها")
    def sections_column(self, obj):
        return "، ".join(section.title for section in obj.sections.all()) or "—"

    @admin.display(description="وضعیت نویسندگی")
    def writing_status(self, obj):
        if obj.pk is None:
            return "—"
        reason = permissions.write_block_reason(obj)
        if reason:
            return f"نمی‌تواند بنویسد: {reason}"
        sections = [s for s in obj.sections.all() if s.is_active]
        if not sections:
            return "نمی‌تواند بنویسد: هیچ بخش فعالی برایش تیک نخورده است."
        return "می‌تواند بنویسد در: " + "، ".join(s.title for s in sections)

    @admin.display(description="سابقه اجازه‌ها")
    def grants_column(self, obj):
        if obj.pk is None:
            return "—"
        grants = obj.grants.select_related("section", "granted_by")
        return format_html_join(
            "", "<div>{} — {}{}</div>",
            (
                (
                    grant.section.title,
                    jalali_datetime(grant.granted_at),
                    f"، به‌دست {grant.granted_by.get_full_name() or grant.granted_by.username}" if grant.granted_by else "",
                )
                for grant in grants
            ),
        ) or "—"

    @admin.display(description="پیش‌نمایش عکس")
    def photo_preview(self, obj):
        return image_preview(obj.photo_url, 100)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        author = form.instance
        wanted = set(form.cleaned_data.get("grant_sections") or [])
        current = {grant.section: grant for grant in author.grants.select_related("section")}
        for section, grant in current.items():
            if section not in wanted:
                grant.delete()
        for section in wanted - set(current):
            AuthorSection.objects.create(author=author, section=section, granted_by=request.user)


# ------------------------------------------------------------------------ posts


class StatusFilter(admin.SimpleListFilter):
    title = "وضعیت"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return [*Post.Status.choices[:2], ("scheduled", "زمان‌بندی‌شده"), *Post.Status.choices[2:]]

    def queryset(self, request, queryset):
        now = utc_now()
        value = self.value()
        if value == "scheduled":
            return queryset.filter(status=Post.Status.PUBLISHED, published_at__gt=now)
        if value == Post.Status.PUBLISHED:
            return queryset.filter(status=value, published_at__lte=now)
        if value in Post.Status.values:
            return queryset.filter(status=value)
        return queryset


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    form = PostAdminForm
    change_form_template = "admin/blog/post/change_form.html"

    def view_on_site(self, obj):
        """«مشاهده در سایت»: the preview, which sends a public post on to its public page."""
        return obj.preview_url

    list_display = ("title", "section", "category", "author", "status_badge", "published_column", "is_featured")
    list_filter = (
        StatusFilter,
        "section",
        ("category", admin.RelatedOnlyFieldListFilter),
        ("author", admin.RelatedOnlyFieldListFilter),
        "is_featured",
    )
    list_select_related = ("section", "category", "author__user")
    search_fields = ("title", "excerpt", "author__display_name", "author__user__first_name", "author__user__last_name")
    autocomplete_fields = ("author", "tags")
    readonly_fields = ("status_column", "published_column", "review_column", "cover_preview")
    actions = ["publish_selected", "unpublish_selected", "feature_selected", "unfeature_selected"]
    fieldsets = (
        (
            None,
            {
                "description": "وضعیت نوشته فقط از صفحه «بررسی و انتشار» یا عملیات فهرست تغییر می‌کند.",
                "fields": ("status_column", "published_column", "review_column"),
            },
        ),
        ("نوشته", {"fields": ("title", ("section", "category"), "author", "excerpt", "body", "tags")}),
        ("تصویر شاخص", {"fields": ("cover", "cover_preview", "cover_alt")}),
        ("سئو و نشانی", {"classes": ("collapse",), "fields": ("meta_title", "meta_description", "slug")}),
        ("نمایش", {"fields": ("is_featured",)}),
    )

    # --- the form

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        upload_url = reverse("admin:blog_post_upload_image", args=[obj.pk]) if obj else ""
        form.base_fields["body"].widget = EditorWidget(upload_url=upload_url)
        form.base_fields["body"].help_text = (
            "«عنوان» و «زیرعنوان» سرفصل‌های متن‌اند. زیرنویس هر تصویر، متن جایگزین آن هم هست. "
            "تصویر داخل متن پس از نخستین ذخیره نوشته اضافه می‌شود."
        )
        if "is_featured" in form.base_fields and not permissions.can_publish(request.user):
            form.base_fields["is_featured"].disabled = True
        return form

    def has_delete_permission(self, request, obj=None):
        # Archive instead (ADR-011); a superuser may remove spam or test rows.
        return request.user.is_superuser

    # --- list columns

    @admin.display(description="وضعیت", ordering="status")
    def status_badge(self, obj):
        colours = {
            "پیش‌نویس": "#6b7280",
            "در انتظار بررسی": "#b45309",
            "زمان‌بندی‌شده": "#1d4ed8",
            "منتشرشده": "#15803d",
            "بایگانی": "#4b5563",
        }
        label = obj.status_label
        return format_html(
            '<span style="display:inline-block;padding:0 .5em;border-radius:1em;color:#fff;background:{}">{}</span>',
            colours.get(label, "#6b7280"),
            label,
        )

    @admin.display(description="وضعیت")
    def status_column(self, obj):
        if obj.pk is None:
            return "پیش‌نویس (پس از ذخیره)"
        return obj.status_label

    @admin.display(description="زمان انتشار", ordering="published_at")
    def published_column(self, obj):
        return jalali_datetime(obj.published_at) if obj.published_at else "—"

    @admin.display(description="بررسی")
    def review_column(self, obj):
        if obj.pk is None:
            return "—"
        parts = []
        if obj.submitted_at:
            parts.append(f"ارسال برای بررسی: {jalali_datetime(obj.submitted_at)}")
        if obj.reviewed_by_id:
            name = obj.reviewed_by.get_full_name() or obj.reviewed_by.username
            parts.append(f"بررسی: {name}، {jalali_datetime(obj.reviewed_at)}")
        if obj.review_note:
            parts.append(f"یادداشت برای نویسنده: «{obj.review_note}»")
        return format_html_join("", "<div>{}</div>", ((part,) for part in parts)) or "—"

    @admin.display(description="پیش‌نمایش")
    def cover_preview(self, obj):
        return image_preview(obj.cover_url, 140)

    # --- extra views

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path("<int:object_id>/review/", view(self.review_view), name="blog_post_review"),
            path("<int:object_id>/upload-image/", view(self.upload_image_view), name="blog_post_upload_image"),
            *super().get_urls(),
        ]

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = {**(extra_context or {}), "can_review": permissions.can_publish(request.user)}
        return super().change_view(request, object_id, form_url, extra_context)

    def review_view(self, request, object_id):
        """«بررسی و انتشار»: publish (now or scheduled) with the checklist, return with a note, or unpublish."""

        if not permissions.can_publish(request.user):
            raise PermissionDenied
        post = get_object_or_404(Post.objects.select_related("section", "author__user"), pk=object_id)
        page = BlogPage.load()
        checklist = page.checklist_items()
        action = request.POST.get("action") if request.method == "POST" else None

        publish_form = PublishForm(request.POST if action == "publish" else None, checklist=checklist, prefix="publish")
        return_form = ReturnForm(request.POST if action == "return" else None, prefix="return")
        done = None
        try:
            if action == "publish" and publish_form.is_valid():
                published = services.publish(
                    post, request.user, checklist_confirmed=True, at=publish_form.cleaned_data["moment"]
                )
                done = "نوشته زمان‌بندی شد." if published.is_scheduled else "نوشته منتشر شد."
            elif action == "return" and return_form.is_valid():
                services.return_to_author(post, request.user, return_form.cleaned_data["note"])
                done = "نوشته با یادداشت به نویسنده بازگردانده شد."
            elif action == "unpublish":
                services.unpublish(post, request.user)
                done = "نوشته از انتشار خارج و بایگانی شد."
        except services.TransitionError as error:
            self.message_user(request, str(error), messages.ERROR)
        if done:
            self.message_user(request, done, messages.SUCCESS)
            return redirect("admin:blog_post_change", post.pk)

        status = post.status
        return render(request, "admin/blog/post/review.html", {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": f"بررسی و انتشار: {post.title}",
            "post": post,
            "publish_form": publish_form,
            "return_form": return_form,
            "can_publish": status in (Post.Status.DRAFT, Post.Status.SUBMITTED, Post.Status.ARCHIVED),
            "can_return": status in (Post.Status.SUBMITTED, Post.Status.PUBLISHED, Post.Status.ARCHIVED),
            "can_unpublish": status == Post.Status.PUBLISHED,
            "is_draft": status == Post.Status.DRAFT,
        })

    def upload_image_view(self, request, object_id):
        """POST an image from the editor -> ``{"url", "width", "height"}``; the editor's one JSON endpoint."""

        if request.method != "POST":
            return JsonResponse({"error": "روش درخواست نادرست است."}, status=405)
        post = get_object_or_404(Post, pk=object_id)
        if not self.has_change_permission(request, post):
            return JsonResponse({"error": "اجازه افزودن تصویر به این نوشته را ندارید."}, status=403)
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

    # --- bulk actions (editors only)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not permissions.can_publish(request.user):
            for name in ("publish_selected", "unpublish_selected", "feature_selected", "unfeature_selected"):
                actions.pop(name, None)
        return actions

    @admin.action(description="انتشار نوشته‌های انتخاب‌شده (با فهرست بررسی)…")
    def publish_selected(self, request, queryset):
        eligible = [p for p in queryset if p.status in (Post.Status.SUBMITTED, Post.Status.ARCHIVED)]
        skipped = [p for p in queryset if p not in eligible]
        form = BulkPublishForm(
            request.POST if "apply" in request.POST else None, checklist=BlogPage.load().checklist_items()
        )
        if form.is_bound and form.is_valid():
            published = 0
            for post in eligible:
                try:
                    services.publish(post, request.user, checklist_confirmed=True)
                    published += 1
                except services.TransitionError as error:
                    self.message_user(request, f"«{post}»: {error}", messages.WARNING)
            self.message_user(request, f"{published} نوشته منتشر شد.", messages.SUCCESS)
            return None
        return render(request, "admin/blog/post/publish_selected.html", {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": "انتشار نوشته‌ها",
            "eligible": eligible,
            "skipped": skipped,
            "queryset": queryset,
            "form": form,
            "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
        })

    @admin.action(description="خارج کردن از انتشار (بایگانی)")
    def unpublish_selected(self, request, queryset):
        done = 0
        for post in queryset.filter(status=Post.Status.PUBLISHED):
            services.unpublish(post, request.user)
            done += 1
        self.message_user(request, f"{done} نوشته از انتشار خارج شد.", messages.SUCCESS)

    @admin.action(description="ویژه کردن")
    def feature_selected(self, request, queryset):
        done = 0
        for post in queryset.filter(status=Post.Status.PUBLISHED):
            services.set_featured(post, request.user, True)
            done += 1
        self.message_user(request, f"{done} نوشته ویژه شد. فقط نوشته منتشرشده ویژه می‌شود.", messages.SUCCESS)

    @admin.action(description="برداشتن از ویژه‌ها")
    def unfeature_selected(self, request, queryset):
        done = 0
        for post in queryset.filter(is_featured=True):
            services.set_featured(post, request.user, False)
            done += 1
        self.message_user(request, f"{done} نوشته از ویژه‌ها برداشته شد.", messages.SUCCESS)


@admin.register(PostAwaitingReview)
class PostAwaitingReviewAdmin(admin.ModelAdmin):
    """The review queue: submitted posts, oldest first; the permissions are those of ``Post``."""

    list_display = ("title", "section", "category", "author", "submitted_column", "links")
    list_display_links = None
    list_filter = ("section",)
    list_select_related = ("section", "category", "author__user")
    ordering = ("submitted_at", "id")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(status=Post.Status.SUBMITTED)

    def _post_perm(self, request, action):
        return request.user.has_perm(f"blog.{action}_post")

    def has_module_permission(self, request):
        return self._post_perm(request, "view") or self._post_perm(request, "change")

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="ارسال برای بررسی", ordering="submitted_at")
    def submitted_column(self, obj):
        return jalali_datetime(obj.submitted_at) if obj.submitted_at else "—"

    @admin.display(description="")
    def links(self, obj):
        edit = reverse("admin:blog_post_change", args=[obj.pk])
        review = reverse("admin:blog_post_review", args=[obj.pk])
        return format_html(
            '<a href="{}">پیش‌نمایش</a> | <a href="{}">ویرایش</a> | <a href="{}">بررسی و انتشار</a>',
            obj.preview_url, edit, review,
        )
