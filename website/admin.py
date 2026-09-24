from django.contrib import admin
from django.db import models
from django.forms import Textarea
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    FeatureCard,
    FooterLink,
    HeroSlide,
    LandingPage,
    LandingTeacher,
    LearningPoint,
    NavMenuItem,
    SiteSettings,
)


def image_preview(url, height=80):
    if not url:
        return "—"
    return format_html(
        '<img src="{}" alt="" style="max-height:{}px;max-width:220px;'
        'border-radius:8px;object-fit:cover;">',
        url,
        height,
    )


class SingletonAdmin(admin.ModelAdmin):
    """
    Opens the one row's change form directly -- from the admin index and
    from the changelist URL -- and hides "add" and "delete".
    """

    def has_add_permission(self, request):
        return not self.model.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = self.model.load()
        opts = self.model._meta
        return HttpResponseRedirect(
            reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])
        )


# ---------------------------------------------------------------- site settings


class NavMenuItemInline(admin.TabularInline):
    model = NavMenuItem
    extra = 0
    fields = ("title", "url", "open_in_new_tab", "order", "is_active")


class FooterLinkInline(admin.TabularInline):
    model = FooterLink
    extra = 0
    fields = ("title", "url", "kind", "icon", "order", "is_active")


@admin.register(SiteSettings)
class SiteSettingsAdmin(SingletonAdmin):
    inlines = [NavMenuItemInline, FooterLinkInline]
    readonly_fields = ("logo_preview",)
    fieldsets = (
        ("هویت سایت", {"fields": ("site_name", "logo", "logo_preview")}),
        ("دکمه ورود (نوار بالا)", {"fields": ("login_text", "login_url")}),
        ("فوتر", {"fields": ("copyright_text", "footer_note")}),
        ("سئو", {"fields": ("meta_title", "meta_description")}),
    )

    @admin.display(description="پیش‌نمایش لوگو")
    def logo_preview(self, obj):
        return image_preview(obj.logo_url, 60)


# ----------------------------------------------------------------- landing page

COMPACT_TEXTAREA = {models.TextField: {"widget": Textarea(attrs={"rows": 3, "cols": 80})}}


class PreviewInlineMixin:
    preview_attr = "image_url"
    formfield_overrides = COMPACT_TEXTAREA

    @admin.display(description="پیش‌نمایش")
    def preview(self, obj):
        return image_preview(getattr(obj, self.preview_attr, ""))


class HeroSlideInline(PreviewInlineMixin, admin.StackedInline):
    model = HeroSlide
    extra = 0
    readonly_fields = ("preview",)
    fields = (
        ("order", "is_active"),
        ("badge_text", "badge_emoji"),
        "title",
        "description",
        ("button_text", "button_url"),
        "image",
        "preview",
        "image_alt",
        "overlay_color",
    )


class FeatureCardInline(PreviewInlineMixin, admin.StackedInline):
    model = FeatureCard
    extra = 0
    readonly_fields = ("preview",)
    fields = (("order", "is_active"), "title", "description", "image", "preview", "image_alt")


class LearningPointInline(PreviewInlineMixin, admin.TabularInline):
    model = LearningPoint
    extra = 0
    preview_attr = "icon_url"
    readonly_fields = ("preview",)
    fields = ("title", "subtitle", "icon_emoji", "icon_image", "preview", "order", "is_active")


class LandingTeacherInline(PreviewInlineMixin, admin.TabularInline):
    model = LandingTeacher
    extra = 0
    preview_attr = "photo_url"
    readonly_fields = ("preview",)
    autocomplete_fields = ("teacher",)
    fields = ("teacher", "name_override", "specialty_override", "photo_override", "preview", "order", "is_active")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("teacher__staff__user")


@admin.register(LandingPage)
class LandingPageAdmin(SingletonAdmin):
    formfield_overrides = COMPACT_TEXTAREA
    inlines = [HeroSlideInline, FeatureCardInline, LearningPointInline, LandingTeacherInline]
    readonly_fields = ("intro_image_preview", "learning_image_preview")
    fieldsets = (
        (
            "نمایش سکشن‌ها",
            {
                "description": "سکشن خاموش یا سکشنی که آیتم فعالی ندارد، در صفحه نمایش داده نمی‌شود.",
                "fields": ("show_hero_slider", "show_intro", "show_features", "show_learning", "show_teachers"),
            },
        ),
        (
            "سکشن معرفی",
            {
                "fields": (
                    "intro_title",
                    "intro_text",
                    "intro_image",
                    "intro_image_preview",
                    "intro_image_alt",
                    ("intro_primary_text", "intro_primary_url"),
                    ("intro_secondary_text", "intro_secondary_url"),
                )
            },
        ),
        ("سکشن «چرا مدرسه نسل قلم؟»", {"fields": ("features_title", "features_subtitle")}),
        (
            "سکشن یادگیری فعال",
            {"fields": ("learning_title", "learning_subtitle", "learning_image", "learning_image_preview", "learning_image_alt")},
        ),
        ("سکشن اساتید", {"fields": ("teachers_title", "teachers_subtitle")}),
    )

    @admin.display(description="پیش‌نمایش تصویر")
    def intro_image_preview(self, obj):
        return image_preview(obj.intro_image_url, 140)

    @admin.display(description="پیش‌نمایش تصویر")
    def learning_image_preview(self, obj):
        return image_preview(obj.learning_image_url, 140)
