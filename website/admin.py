from django.contrib import admin
from django.db import models
from django.forms import Textarea
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.text import Truncator

from core.templatetags.jalali_tags import jalali_datetime

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
    TeacherGroup,
    TeachersPage,
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

TEACHERS_SECTION_NOTE = (
    "معلمان این سکشن در «{link}» انتخاب می‌شوند: «فعال» و «نمایش در صفحه اصلی». "
    "لینک زیر سکشن به صفحه معلمان می‌رود؛ با خالی گذاشتن متن یا لینک نمایش داده نمی‌شود."
)


def with_teachers_link(fieldsets, title):
    """
    Put a link to the «معلمان سایت» list into the description of the
    fieldset named ``title`` (reversed per request, not at import time).
    """

    link = format_html(
        '<a href="{}">{}</a>', reverse("admin:website_landingteacher_changelist"), LandingTeacher._meta.verbose_name_plural
    )
    result = []
    for name, options in fieldsets:
        if name == title:
            options = {**options, "description": format_html(options["description"], link=link)}
        result.append((name, options))
    return result


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


@admin.register(LandingPage)
class LandingPageAdmin(SingletonAdmin):
    formfield_overrides = COMPACT_TEXTAREA
    inlines = [HeroSlideInline, FeatureCardInline, LearningPointInline]
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
        (
            "سکشن اساتید",
            {
                "description": TEACHERS_SECTION_NOTE,
                "fields": ("teachers_title", "teachers_subtitle", ("teachers_link_text", "teachers_link_url")),
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        return with_teachers_link(super().get_fieldsets(request, obj), "سکشن اساتید")

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


# -------------------------------------------------------------------- about page


class AboutMilestoneInline(admin.TabularInline):
    model = AboutMilestone
    extra = 0
    formfield_overrides = COMPACT_TEXTAREA
    fields = ("year", "title", "text", "order", "is_active")


class AboutValueInline(admin.TabularInline):
    model = AboutValue
    extra = 0
    fields = ("emoji", "title", "text", "order", "is_active")


class AboutHighlightInline(PreviewInlineMixin, admin.StackedInline):
    model = AboutHighlight
    extra = 0
    readonly_fields = ("preview",)
    fields = (("order", "is_active"), "title", "text", "image", "preview", "image_alt")


class AboutFactInline(admin.TabularInline):
    model = AboutFact
    extra = 0
    fields = ("value", "label", "order", "is_active")


class AboutPersonInline(PreviewInlineMixin, admin.TabularInline):
    model = AboutPerson
    extra = 0
    preview_attr = "photo_url"
    readonly_fields = ("preview",)
    autocomplete_fields = ("staff",)
    fields = ("staff", "name_override", "role", "bio", "photo_override", "preview", "order", "is_active")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("staff__user")


class AboutPhotoInline(PreviewInlineMixin, admin.TabularInline):
    model = AboutPhoto
    extra = 0
    readonly_fields = ("preview",)
    fields = ("image", "preview", "image_alt", "caption", "order", "is_active")


@admin.register(AboutPage)
class AboutPageAdmin(SingletonAdmin):
    formfield_overrides = COMPACT_TEXTAREA
    inlines = [
        AboutMilestoneInline,
        AboutValueInline,
        AboutHighlightInline,
        AboutFactInline,
        AboutPersonInline,
        AboutPhotoInline,
    ]
    readonly_fields = ("hero_image_preview", "quote_photo_preview")
    fieldsets = (
        (
            "نمایش سکشن‌ها",
            {
                "description": "سکشن خاموش یا سکشنی که آیتم فعالی ندارد، در صفحه نمایش داده نمی‌شود. "
                               "همه متن‌ها، اعداد و عکس‌های این صفحه عمومی‌اند و از داده‌های سامانه "
                               "محاسبه نمی‌شوند.",
                "fields": (
                    ("show_story", "show_timeline", "show_quote"),
                    ("show_values", "show_highlights", "show_facts"),
                    ("show_team", "show_gallery", "show_branches", "show_cta"),
                ),
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
                    ("hero_button_text", "hero_button_url"),
                )
            },
        ),
        (
            "داستان ما",
            {
                "description": "رویدادهای مسیر سال‌ها در جدول «مسیر سال‌ها» پایین صفحه وارد می‌شوند.",
                "fields": ("story_title", "story_text", "timeline_title"),
            },
        ),
        (
            "سخن مدیر",
            {"fields": ("quote_text", ("quote_name", "quote_role"), "quote_photo", "quote_photo_preview", "quote_photo_alt")},
        ),
        (
            "باورهای ما",
            {"fields": ("values_title", "mission_title", "mission_text", "vision_title", "vision_text")},
        ),
        ("در نسل قلم، بچه‌ها…", {"fields": ("highlights_title", "highlights_text")}),
        (
            "اعداد، همکاران و گالری",
            {
                "description": "سکشن همکاران فقط برای مدیران و کارکنان دفتر است؛ معلمان در صفحه "
                               "جداگانه معلمان معرفی می‌شوند. عکس همکاران فقط همان عکسی است که "
                               "اینجا بارگذاری می‌کنید.",
                "fields": ("facts_title", "team_title", "team_text", "gallery_title"),
            },
        ),
        (
            "شعبه‌ها",
            {"fields": ("branches_title", "branches_text", ("branches_link_text", "branches_link_url"))},
        ),
        (
            "دعوت پایانی",
            {
                "fields": (
                    "cta_title",
                    "cta_text",
                    ("cta_primary_text", "cta_primary_url"),
                    ("cta_secondary_text", "cta_secondary_url"),
                )
            },
        ),
        ("سئو", {"fields": ("meta_title", "meta_description")}),
    )

    @admin.display(description="پیش‌نمایش تصویر")
    def hero_image_preview(self, obj):
        return image_preview(obj.hero_image_url, 140)

    @admin.display(description="پیش‌نمایش عکس")
    def quote_photo_preview(self, obj):
        return image_preview(obj.quote_photo_url, 100)


# ----------------------------------------------------------------- teachers page


@admin.register(LandingTeacher)
class LandingTeacherAdmin(admin.ModelAdmin):
    """
    The teachers of the public site, shared by the landing page's row and
    the «معلمان» page: two ticks say where each one appears.
    """

    formfield_overrides = COMPACT_TEXTAREA
    list_display = (
        "thumbnail",
        "name_column",
        "specialty_column",
        "group",
        "on_teachers_page",
        "on_home",
        "is_active",
        "order",
    )
    list_display_links = ("thumbnail", "name_column")
    list_editable = ("on_teachers_page", "on_home", "is_active", "order")
    list_filter = ("on_teachers_page", "on_home", "is_active", "group")
    list_select_related = ("teacher__staff__user", "group")
    search_fields = (
        "name_override",
        "specialty_override",
        "teacher__staff__user__first_name",
        "teacher__staff__user__last_name",
    )
    autocomplete_fields = ("teacher",)
    readonly_fields = ("preview",)
    fieldsets = (
        (
            "معلم",
            {
                "description": "معلم را از حساب‌های سامانه انتخاب کنید یا فقط نام نمایشی بنویسید. "
                               "از حساب فقط نام و رشته تحصیلی خوانده می‌شود.",
                "fields": ("teacher", "name_override", "specialty_override"),
            },
        ),
        (
            "نمایش",
            {
                "description": "تا یکی از دو گزینه نمایش زده نشود، معلم در سایت دیده نمی‌شود. "
                               "«فعال» خاموش یعنی هیچ‌جا، بدون پاک شدن گزینه‌ها.",
                "fields": (("is_active", "on_teachers_page", "on_home"), "group", "order"),
            },
        ),
        ("عکس", {"fields": ("photo_override", "preview")}),
        ("معرفی", {"fields": ("experience", "education", "quote", "bio")}),
        ("لینک", {"fields": ("slug",)}),
    )

    @admin.display(description="عکس")
    def thumbnail(self, obj):
        return image_preview(obj.photo_url, 48)

    @admin.display(description="پیش‌نمایش")
    def preview(self, obj):
        return image_preview(obj.photo_url, 140)

    @admin.display(description="نام", ordering="name_override")
    def name_column(self, obj):
        return obj.display_name

    @admin.display(description="تخصص")
    def specialty_column(self, obj):
        return obj.display_specialty or "—"


class TeacherGroupInline(admin.TabularInline):
    model = TeacherGroup
    extra = 0
    fields = ("title", "order", "is_active")


@admin.register(TeachersPage)
class TeachersPageAdmin(SingletonAdmin):
    formfield_overrides = COMPACT_TEXTAREA
    inlines = [TeacherGroupInline]
    fieldsets = (
        (
            "نمایش سکشن‌ها",
            {
                "description": "معلمان این صفحه در «{link}» انتخاب می‌شوند (گزینه «نمایش در صفحه معلمان»). "
                               "همه متن‌ها عمومی‌اند و از داده‌های سامانه محاسبه نمی‌شوند.",
                "fields": (("show_intro", "show_filter", "show_cta"),),
            },
        ),
        ("بالای صفحه", {"fields": ("hero_title", "hero_text")}),
        ("فهرست", {"fields": ("filter_label", "all_text", "list_title", "other_group_title", "empty_text")}),
        (
            "دعوت پایانی",
            {
                "fields": (
                    "cta_title",
                    "cta_text",
                    ("cta_primary_text", "cta_primary_url"),
                    ("cta_secondary_text", "cta_secondary_url"),
                )
            },
        ),
        ("سئو", {"fields": ("meta_title", "meta_description")}),
    )

    def get_fieldsets(self, request, obj=None):
        return with_teachers_link(super().get_fieldsets(request, obj), "نمایش سکشن‌ها")
