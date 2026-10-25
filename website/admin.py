from django.contrib import admin
from django.db import models
from django.forms import Textarea
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.text import Truncator

from core.templatetags.jalali_tags import jalali_datetime

from .models import (
    ContactChannel,
    ContactLocation,
    ContactMessage,
    ContactPage,
    ContactTopic,
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


# ----------------------------------------------------------------- contact page


class ContactLocationInline(PreviewInlineMixin, admin.StackedInline):
    model = ContactLocation
    extra = 0
    preview_attr = "map_image_url"
    readonly_fields = ("preview",)
    fields = (
        ("order", "is_active"),
        "branch",
        "title_override",
        "address_override",
        "hours",
        "map_image",
        "preview",
        "map_image_alt",
        ("neshan_url", "balad_url", "google_maps_url"),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("branch")


class ContactChannelInline(admin.TabularInline):
    model = ContactChannel
    extra = 0
    fields = ("label", "kind", "value", "note", "location", "order", "is_active")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "location":
            kwargs["queryset"] = ContactLocation.objects.select_related("branch")
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "location":
            # Every row's dropdown lists the same locations: query them once.
            if not hasattr(request, "_contact_location_choices"):
                request._contact_location_choices = list(field.choices)
            field.choices = request._contact_location_choices
        return field


class ContactTopicInline(admin.TabularInline):
    model = ContactTopic
    extra = 0
    fields = ("title", "order", "is_active")


@admin.register(ContactPage)
class ContactPageAdmin(SingletonAdmin):
    formfield_overrides = COMPACT_TEXTAREA
    inlines = [ContactLocationInline, ContactChannelInline, ContactTopicInline]
    readonly_fields = ("hero_image_preview",)
    fieldsets = (
        (
            "نمایش سکشن‌ها",
            {
                "description": "سکشن خاموش یا سکشنی که آیتم فعالی ندارد، در صفحه نمایش داده نمی‌شود. "
                               "شبکه‌های اجتماعی همان لینک‌های «شبکه اجتماعی» فوتر در «تنظیمات سایت» هستند.",
                "fields": ("show_social", "show_channels", "show_locations", "show_form", "show_faq"),
            },
        ),
        (
            "بالای صفحه",
            {
                "fields": (
                    "hero_title",
                    "hero_text",
                    "hero_image",
                    "hero_image_preview",
                    "hero_image_alt",
                    ("hero_call_text", "hero_message_text"),
                )
            },
        ),
        ("عنوان سکشن‌ها", {"fields": ("channels_title", "locations_title")}),
        ("فرم پیام", {"fields": ("form_title", "form_intro", "submit_text", "success_message")}),
        ("کادر سوالات متداول", {"fields": ("faq_title", "faq_text", ("faq_link_text", "faq_url"))}),
        ("سئو", {"fields": ("meta_title", "meta_description")}),
    )

    @admin.display(description="پیش‌نمایش تصویر")
    def hero_image_preview(self, obj):
        return image_preview(obj.hero_image_url, 140)


_TO_ASCII_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    """
    Read-only, except «پیگیری شد». Office staff need view_contactmessage,
    plus change_contactmessage to tick «پیگیری شد» (see docs/apps/website.md).
    """

    list_display = ("name", "mobile_display", "topic", "location", "short_message", "sent_at", "is_handled")
    list_editable = ("is_handled",)
    list_filter = ("is_handled", "topic", "location")
    search_fields = ("name", "mobile")
    fields = ("name", "mobile", "topic", "location", "message", "sent_at", "is_handled")
    readonly_fields = ("name", "mobile", "topic", "location", "message", "sent_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        # Spam cleanup only; office staff never delete.
        return request.user.is_superuser

    def get_search_results(self, request, queryset, search_term):
        # Mobiles are stored with ASCII digits; staff may type Persian ones.
        return super().get_search_results(request, queryset, search_term.translate(_TO_ASCII_DIGITS))

    @admin.display(description="شماره موبایل", ordering="mobile")
    def mobile_display(self, obj):
        return obj.mobile_display

    @admin.display(description="متن پیام")
    def short_message(self, obj):
        return Truncator(obj.message).chars(60)

    @admin.display(description="تاریخ ارسال", ordering="created_at")
    def sent_at(self, obj):
        return jalali_datetime(obj.created_at)
