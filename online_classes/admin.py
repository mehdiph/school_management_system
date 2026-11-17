"""
System admin pages of online classes and announcements (Django admin): platforms,
events with their personal access rows and import, announcements.

A superuser sees everything. A branch-scoped admin sees items that touch their
branches and changes only items wholly inside them (D23). Secrets show as
«••••••» everywhere; reading one takes ``view_access_secret`` and a deliberate
click that is written to the admin history (D15).
"""

from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.forms import BaseInlineFormSet, CheckboxSelectMultiple
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.cache import never_cache

from core.moments import to_utc, utc_now
from core.services import access
from core.spreadsheet import FileRejected, normalize
from core.templatetags.jalali_tags import fa_digits, jalali_datetime
from school.models import Branch, Grade
from student.models.student_profile import StudentProfile

from . import audience, crypto, importer, services
from .pickers import URL_NAME as STUDENT_AUTOCOMPLETE, StudentAutocompleteView, StudentPicker, StudentsPicker
from .forms import AccessImportForm, AnnouncementAdminForm, OnlineEventAccessForm, OnlineEventAdminForm
from .import_template import build_template
from .models import Announcement, OnlineEvent, OnlineEventAccess, OnlinePlatform

IMPORT_SESSION_KEY = "online_classes_access_import"
MASK = importer.MASK
SECRET_PERMISSION = "online_classes.view_access_secret"
ADD_ROW_PERMISSION = "online_classes.add_onlineeventaccess"
STUDENTS_PER_PAGE = 100


def _mask(value):
    return MASK if value else "—"


def _stored(row):
    """What an access row holds, by name only («لینک، رمز»), never a value."""

    names = [
        ("لینک", row.url_encrypted),
        ("نام کاربری", row.username),
        ("رمز", row.password_encrypted),
        ("کد", row.access_code_encrypted),
    ]
    return "، ".join(label for label, value in names if value) or "—"


# ----------------------------------------------------------------------
# Filters
# ----------------------------------------------------------------------

class BranchFilter(admin.SimpleListFilter):
    """Includes whole-school items and items that reach the branch through a class."""

    title = "شعبه"
    parameter_name = "branch"

    def lookups(self, request, model_admin):
        branches = Branch.objects.filter(is_active=True)
        if not request.user.is_superuser:
            branches = branches.filter(pk__in=access.get_accessible_branch_ids(request.user, request=request))
        return [(branch.pk, branch.name) for branch in branches.order_by("order", "name")]

    def queryset(self, request, queryset):
        if self.value():
            return audience.touching_branches(queryset, [self.value()])
        return queryset


class GradeFilter(admin.SimpleListFilter):
    title = "پایه"
    parameter_name = "grade"

    def lookups(self, request, model_admin):
        return [(grade.pk, grade.name) for grade in Grade.objects.filter(is_active=True).order_by("level")]

    def queryset(self, request, queryset):
        if self.value():
            return audience.touching_grade(queryset, self.value())
        return queryset


class EventStateFilter(admin.SimpleListFilter):
    """State comes from the clock; "postponed with no new time" is here so a forgotten one can be found."""

    title = "وضعیت زمانی"
    parameter_name = "state"

    def lookups(self, request, model_admin):
        return [
            ("upcoming", "پیش‌رو"),
            ("live", "در حال برگزاری"),
            ("ended", "پایان یافته"),
            ("postponed", "به‌تعویق‌افتاده، بدون زمان جدید"),
            ("cancelled", "لغو شده"),
        ]

    def queryset(self, request, queryset):
        now = utc_now()
        scheduled = queryset.filter(status=OnlineEvent.Status.SCHEDULED)
        match self.value():
            case "upcoming":
                return scheduled.filter(start_at__gt=now)
            case "live":
                return scheduled.filter(start_at__lte=now, end_at__gt=now)
            case "ended":
                return scheduled.filter(end_at__lte=now)
            case "postponed":
                return queryset.filter(status=OnlineEvent.Status.POSTPONED)
            case "cancelled":
                return queryset.filter(status=OnlineEvent.Status.CANCELLED)
        return queryset


class EventDateFilter(admin.SimpleListFilter):
    title = "تاریخ"
    parameter_name = "when"

    def lookups(self, request, model_admin):
        return [("today", "امروز"), ("next7", "۷ روز آینده"), ("last7", "۷ روز گذشته"), ("next30", "۳۰ روز آینده")]

    def queryset(self, request, queryset):
        today = timezone.localdate()
        midnight = to_utc(timezone.make_aware(timezone.datetime(today.year, today.month, today.day)))
        match self.value():
            case "today":
                return queryset.filter(start_at__gte=midnight, start_at__lt=midnight + timedelta(days=1))
            case "next7":
                return queryset.filter(start_at__gte=midnight, start_at__lt=midnight + timedelta(days=8))
            case "last7":
                return queryset.filter(start_at__gte=midnight - timedelta(days=7), start_at__lt=midnight)
            case "next30":
                return queryset.filter(start_at__gte=midnight, start_at__lt=midnight + timedelta(days=31))
        return queryset


# ----------------------------------------------------------------------
# Shared by events and announcements
# ----------------------------------------------------------------------

class StampsMixin:
    """Read-only record times in Jalali, not the raw value ``django_jalali`` prints."""

    @admin.display(description="تاریخ ایجاد", ordering="created_at")
    def created_jalali(self, obj):
        return jalali_datetime(obj.created_at) if obj.pk else "—"

    @admin.display(description="آخرین بروزرسانی", ordering="updated_at")
    def updated_jalali(self, obj):
        return jalali_datetime(obj.updated_at) if obj.pk else "—"


class AudienceAdminMixin(StampsMixin):
    """
    Branches, grades and classes are checkboxes (a few dozen at most). Students
    are server-side autocomplete pickers, never one checkbox per student: a
    ``formfield_overrides`` for every ManyToManyField used to give them
    checkboxes too, since Django only applies autocomplete when no widget is set.
    """

    STUDENT_FIELDS = ("students", "excluded_students")

    class Media:
        css = {"all": ("online_classes/admin/audience.css",)}

    def allowed_branches(self, request):
        return access.get_accessible_branch_ids(request.user, request=request)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        return audience.touching_branches(queryset, self.allowed_branches(request))

    def owns(self, request, obj):
        if obj is None or request.user.is_superuser:
            return True
        return audience.wholly_within(type(obj).objects.filter(pk=obj.pk), self.allowed_branches(request)).exists()

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and self.owns(request, obj)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name in self.STUDENT_FIELDS:
            # The form narrows the queryset to who this admin may pick (setup_audience).
            kwargs["widget"] = StudentsPicker(db_field, self.admin_site)
            kwargs["queryset"] = StudentProfile.objects.select_related("user")
        else:
            kwargs.setdefault("widget", CheckboxSelectMultiple)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        class RequestForm(form):
            def __init__(self, *args, **inner):
                inner["request"] = request
                super().__init__(*args, **inner)

        return RequestForm

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        item = form.instance
        if not audience.has_targets(item):
            self.message_user(request, "مخاطبی انتخاب نشده است؛ این مورد به هیچ‌کس نشان داده نمی‌شود.", messages.WARNING)
            return
        count = audience.reached_enrollments(item).count()
        self.message_user(request, f"این مورد به {fa_digits(count)} دانش‌آموز نشان داده می‌شود.", messages.INFO)

    # -- who it reaches: the summary on the change page and the list page (D1, D2)

    def scope_branch_ids(self, request):
        """``None`` (every branch) for a superuser, else the admin's branches: counts and names stay inside them."""

        return None if request.user.is_superuser else self.allowed_branches(request)

    def report_event(self, obj):
        """The personal event whose access rows are counted; ``None`` here (announcements, shared events)."""

        return None

    def students_url(self, obj):
        return reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_students", args=[obj.pk])

    def audience_context(self, request, obj):
        context = {"has_targets": audience.has_targets(obj), "scoped": not request.user.is_superuser}
        if context["has_targets"]:
            event = self.report_event(obj)
            context.update(
                counts=audience.breakdown(obj, self.scope_branch_ids(request), event),
                students_url=self.students_url(obj),
                rows_url=(
                    reverse("admin:online_classes_onlineeventaccess_changelist") + f"?event__id__exact={obj.pk}"
                    if event is not None and self.has_change_permission(request, obj) else ""
                ),
            )
        return context

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        if obj is not None and obj.pk:
            context["audience"] = self.audience_context(request, obj)
        return super().render_change_form(request, context, add, change, form_url, obj)

    def get_urls(self):
        name = f"{self.opts.app_label}_{self.opts.model_name}_students"
        return [
            path("<int:pk>/students/", self.admin_site.admin_view(never_cache(self.students_view)), name=name),
        ] + super().get_urls()

    def students_view(self, request, pk):
        """
        The students an item reaches, for its admin: same permission and scope
        as the item's page (404 outside the admin's items), counts and names of
        the admin's branches only, searchable, filterable and paginated.
        """

        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        item = get_object_or_404(self.get_queryset(request), pk=pk)
        if not self.has_view_or_change_permission(request, item):
            raise PermissionDenied

        event = self.report_event(item)
        branch_ids = self.scope_branch_ids(request)
        counts = audience.breakdown(item, branch_ids, event)
        enrollments = audience.students(item, branch_ids, event).select_related(
            "student__user", "school_class__grade", "school_class__branch"
        )

        query = normalize(request.GET.get("q", ""))
        for bit in query.split():
            enrollments = enrollments.filter(
                Q(student__user__first_name__icontains=bit)
                | Q(student__user__last_name__icontains=bit)
                | Q(student__student_code__icontains=bit)
                | Q(student__user__national_code__icontains=bit)
            )
        class_id = request.GET.get("class", "")
        if class_id.isdigit() and int(class_id) in {row.class_id for row in counts.classes}:
            enrollments = enrollments.filter(school_class_id=int(class_id))
        else:
            class_id = ""
        access_filter = request.GET.get("access", "") if event is not None else ""
        if access_filter == "with":
            enrollments = enrollments.filter(access_id__isnull=False)
        elif access_filter == "without":
            enrollments = enrollments.filter(access_id__isnull=True)
        else:
            access_filter = ""

        page = Paginator(enrollments, STUDENTS_PER_PAGE).get_page(request.GET.get("p"))
        here = request.get_full_path()
        may_change = self.has_change_permission(request, item)
        rows_by_id = {}
        if event is not None:
            ids = [enrollment.access_id for enrollment in page if enrollment.access_id]
            rows_by_id = OnlineEventAccess.objects.in_bulk(ids)
        can_add = event is not None and may_change and request.user.has_perm(ADD_ROW_PERMISSION)

        lines = []
        for enrollment in page:
            row = rows_by_id.get(getattr(enrollment, "access_id", None))
            line = {"enrollment": enrollment, "row": row, "stored": _stored(row) if row else ""}
            if row is not None and may_change:
                line["row_url"] = reverse("admin:online_classes_onlineeventaccess_change", args=[row.pk]) + "?" + urlencode({"next": here})
            elif event is not None and row is None and can_add:
                line["add_url"] = reverse("admin:online_classes_onlineeventaccess_add") + "?" + urlencode(
                    {"event": item.pk, "student": enrollment.student_id, "next": here}
                )
            lines.append(line)

        def page_url(number):
            params = {key: value for key, value in (("q", query), ("class", class_id), ("access", access_filter)) if value}
            return "?" + urlencode({**params, "p": number})

        return render(request, "admin/online_classes/audience_students.html", {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": f"دانش‌آموزان مخاطب: {item}",
            "item": item,
            "event": event,
            "counts": counts,
            "scoped": branch_ids is not None,
            "lines": lines,
            "page": page,
            "previous_url": page_url(page.previous_page_number()) if page.has_previous() else "",
            "next_url": page_url(page.next_page_number()) if page.has_next() else "",
            "query": query,
            "class_id": class_id,
            "access_filter": access_filter,
            "change_url": reverse(f"admin:{self.opts.app_label}_{self.opts.model_name}_change", args=[item.pk]),
        })

    @admin.display(description="مخاطبان")
    def audience_summary(self, obj):
        if obj.is_whole_school:
            return "کل مدرسه"
        parts = []
        if obj.branches.all():
            parts.append("شعبه: " + "، ".join(branch.name for branch in obj.branches.all()))
        if obj.grades.all():
            parts.append("پایه: " + "، ".join(grade.name for grade in obj.grades.all()))
        if obj.classes.all():
            parts.append(f"{fa_digits(len(obj.classes.all()))} کلاس")
        if obj.students.all():
            parts.append(f"{fa_digits(len(obj.students.all()))} دانش‌آموز")
        return " · ".join(parts) or "هیچ‌کس"


AUDIENCE_PREFETCH = ("branches", "grades", "classes", "students")


# ----------------------------------------------------------------------
# Platforms
# ----------------------------------------------------------------------

@admin.register(OnlinePlatform)
class OnlinePlatformAdmin(StampsMixin, admin.ModelAdmin):
    list_display = ("name", "domains_summary", "support_contact", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("created_jalali", "updated_jalali")

    @admin.display(description="دامنه‌های مجاز")
    def domains_summary(self, obj):
        return "، ".join(obj.domains) or "همه"


# ----------------------------------------------------------------------
# Personal access rows
# ----------------------------------------------------------------------

class AccessFormMixin:
    """Gives each row's form the logged-in request."""

    def _form_with_request(self, request, form_class):
        class RequestAccessForm(form_class):
            pass

        RequestAccessForm.request = request
        return RequestAccessForm


class AccessInlineFormSet(BaseInlineFormSet):
    """
    Blank rows for adding a few by hand; existing rows are never listed on the
    event page (D3), whatever their number. They are edited from the event's
    student list (each row links to its own page) or the access row list.
    """

    def __init__(self, *args, queryset=None, **kwargs):
        super().__init__(*args, queryset=queryset, **kwargs)
        self.queryset = self.queryset.none()

    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        form.parent_event = self.instance
        return form

    @property
    def empty_form(self):
        form = super().empty_form
        form.parent_event = self.instance
        return form


class OnlineEventAccessInline(AccessFormMixin, admin.TabularInline):
    model = OnlineEventAccess
    form = OnlineEventAccessForm
    formset = AccessInlineFormSet
    extra = 1
    autocomplete_fields = ("student",)
    fields = ("student", "url", "username", "password", "access_code", "note", "stored", "reveal_link")
    readonly_fields = ("stored", "reveal_link")
    verbose_name = "دسترسی شخصی"
    verbose_name_plural = "افزودن دسترسی شخصی (ردیف‌های ثبت‌شده از «دانش‌آموزان مخاطب» ویرایش می‌شوند)"

    def _event_owned(self, request, obj):
        return obj is None or request.user.is_superuser or audience.wholly_within(
            OnlineEvent.objects.filter(pk=obj.pk), access.get_accessible_branch_ids(request.user, request=request)
        ).exists()

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and self._event_owned(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "student":
            kwargs["widget"] = StudentPicker(db_field, self.admin_site)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and self._event_owned(request, obj)

    def has_add_permission(self, request, obj=None):
        return super().has_add_permission(request, obj) and self._event_owned(request, obj)

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and self._event_owned(request, obj)

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        formset.form = self._form_with_request(request, formset.form)
        return formset

    @admin.display(description="ثبت‌شده")
    def stored(self, obj):
        return _stored(obj) if obj.pk else "—"

    @admin.display(description="نمایش")
    def reveal_link(self, obj):
        if not obj.pk:
            return "—"
        return format_html(
            '<a href="{}">نمایش</a>', reverse("admin:online_classes_onlineeventaccess_reveal", args=[obj.pk])
        )


@admin.register(OnlineEventAccess)
class OnlineEventAccessAdmin(StampsMixin, AccessFormMixin, admin.ModelAdmin):
    """Every row of an event, masked, searchable; for events too large to list on their own page."""

    form = OnlineEventAccessForm
    list_display = (
        "student_name", "event", "masked_url", "username", "masked_password", "masked_code",
        "updated_by", "updated_jalali", "reveal_link",
    )
    list_select_related = ("student__user", "event", "updated_by")
    search_fields = (
        "student__user__first_name", "student__user__last_name", "student__student_code",
        "student__user__national_code", "event__title",
    )
    autocomplete_fields = ("student",)
    readonly_fields = ("event", "updated_by", "updated_jalali")
    fields = ("event", "student", "url", "username", "password", "access_code", "note", "updated_by", "updated_jalali")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.is_superuser:
            return queryset
        owned = audience.wholly_within(
            OnlineEvent.objects.all(), access.get_accessible_branch_ids(request.user, request=request)
        )
        return queryset.filter(event__in=owned)

    # -- adding one row: only from an event's student list (``?event=&student=&next=``), never on its own

    def has_add_permission(self, request):
        return super().has_add_permission(request) and "event" in request.GET

    def _event_to_add_to(self, request):
        """The personal event of ``?event=``, which this admin may change; else 404 / 403."""

        event_id = request.GET.get("event", "")
        if not event_id.isdigit():
            raise Http404
        event_admin = self.admin_site.get_model_admin(OnlineEvent)
        event = get_object_or_404(event_admin.get_queryset(request).select_related("platform"), pk=event_id)
        if event.access_mode != OnlineEvent.AccessMode.PERSONAL:
            raise Http404
        if not event_admin.has_change_permission(request, event):
            raise PermissionDenied
        return event

    def add_view(self, request, form_url="", extra_context=None):
        if not self.has_add_permission(request):
            raise PermissionDenied
        request.online_access_event = self._event_to_add_to(request)
        extra = {
            "title": f"افزودن دسترسی شخصی: {request.online_access_event.title}",
            "show_save_and_add_another": False,
            **(extra_context or {}),
        }
        return super().add_view(request, form_url, extra)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("student", "url", "username", "password", "access_code", "note")
        return super().get_fields(request, obj)

    def get_readonly_fields(self, request, obj=None):
        return () if obj is None else super().get_readonly_fields(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        form = self._form_with_request(request, super().get_form(request, obj, **kwargs))
        if obj is None:
            # A new row: this event, and the student must be in its audience (and the admin's branches).
            form.parent_event = getattr(request, "online_access_event", None)
            form.require_audience = True
        return form

    def _back_to_list(self, request, row):
        """``?next=``, if it is this site's student list of the row's event; else ``None`` (never an open redirect)."""

        target = request.GET.get("next", "")
        if not target or not url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            return None
        parts = urlsplit(target)
        if parts.scheme or parts.netloc or parts.path != reverse("admin:online_classes_onlineevent_students", args=[row.event_id]):
            return None
        return target

    def _redirect_back(self, request, row, message):
        target = self._back_to_list(request, row)
        if target is None or "_continue" in request.POST or "_addanother" in request.POST:
            return None
        self.message_user(request, message, messages.SUCCESS)
        return HttpResponseRedirect(target)

    def response_add(self, request, obj, post_url_continue=None):
        back = self._redirect_back(request, obj, f"ردیف دسترسی «{obj.student}» ثبت شد.")
        return back or super().response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        back = self._redirect_back(request, obj, f"ردیف دسترسی «{obj.student}» ذخیره شد.")
        return back or super().response_change(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "student":
            kwargs["widget"] = StudentPicker(db_field, self.admin_site)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="دانش‌آموز", ordering="student__user__last_name")
    def student_name(self, obj):
        return obj.student

    @admin.display(description="لینک")
    def masked_url(self, obj):
        return _mask(obj.url_encrypted)

    @admin.display(description="رمز")
    def masked_password(self, obj):
        return _mask(obj.password_encrypted)

    @admin.display(description="کد")
    def masked_code(self, obj):
        return _mask(obj.access_code_encrypted)

    @admin.display(description="نمایش")
    def reveal_link(self, obj):
        return format_html(
            '<a href="{}">نمایش</a>', reverse("admin:online_classes_onlineeventaccess_reveal", args=[obj.pk])
        )

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path("<int:pk>/reveal/", view(never_cache(self.reveal_view)), name="online_classes_onlineeventaccess_reveal"),
        ] + super().get_urls()

    def reveal_view(self, request, pk):
        """POST shows one row's secrets and writes who, which row and when to the admin history."""

        if not request.user.has_perm(SECRET_PERMISSION):
            raise PermissionDenied
        row = get_object_or_404(self.get_queryset(request).select_related("student__user", "event"), pk=pk)

        secrets, failed = None, False
        if request.method == "POST":
            self.log_change(request, row, "نمایش اطلاعات ورود")
            try:
                secrets = row.read_secrets()
            except crypto.DecryptionFailed:
                failed = True

        return render(request, "admin/online_classes/onlineeventaccess/reveal.html", {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": "نمایش اطلاعات ورود",
            "row": row,
            "secrets": secrets,
            "failed": failed,
        })


# ----------------------------------------------------------------------
# Events
# ----------------------------------------------------------------------

@admin.register(OnlineEvent)
class OnlineEventAdmin(AudienceAdminMixin, admin.ModelAdmin):
    form = OnlineEventAdminForm
    change_form_template = "admin/online_classes/onlineevent/change_form.html"
    list_display = (
        "title", "event_type", "platform", "start_jalali", "end_jalali", "time_state", "status",
        "access_mode", "audience_summary", "row_count", "is_active",
    )
    list_filter = (EventDateFilter, EventStateFilter, "event_type", "platform", BranchFilter, GradeFilter, "status", "is_active")
    list_select_related = ("platform",)
    search_fields = ("title", "description")
    ordering = ("-start_at", "-pk")
    autocomplete_fields = ("students", "excluded_students", "subject", "class_subject")
    readonly_fields = ("created_by", "created_jalali", "updated_by", "updated_jalali")
    actions = ("duplicate_selected", "clear_access_selected")

    fieldsets = (
        ("رویداد", {
            "fields": (
                "title", "event_type", "platform", ("subject", "class_subject"),
                ("start_at", "end_at"), "description",
            ),
        }),
        ("وضعیت", {
            "fields": ("status", "status_note", "is_active"),
            "description": "رویداد لغوشده یا به‌تعویق‌افتاده با توضیحش برای خانواده‌ها می‌ماند. رویداد به‌تعویق‌افتاده تا وقتی "
                           "زمان جدید و وضعیت «طبق برنامه» برایش ثبت نشود با عبارت «زمان جدید اعلام می‌شود» در «پیش‌رو» می‌ماند.",
        }),
        ("نحوه‌ی ورود", {
            "fields": ("access_mode", "join_url", "join_lead_minutes", "credentials_lead_hours"),
            "description": "ردیف‌های «جدا برای هر دانش‌آموز» پس از ذخیره‌ی رویداد، پایین همین صفحه و با «ورود از اکسل» ثبت می‌شوند.",
        }),
        ("مخاطبان (هیچ انتخابی یعنی هیچ‌کس)", {
            "fields": ("is_whole_school", "branches", "grades", "classes", "students", "excluded_students"),
            "description": "شعبه و پایه با هم یعنی همان پایه در همان شعبه. کلاس‌ها و دانش‌آموزان به آن اضافه می‌شوند. "
                           "دانش‌آموز مستثنا در هر حال نمی‌بیند.",
        }),
        ("ثبت", {"fields": ("created_by", "created_jalali", "updated_by", "updated_jalali")}),
    )

    inlines = (OnlineEventAccessInline,)

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .prefetch_related(*AUDIENCE_PREFETCH)
            .annotate(rows=Count("access_rows", distinct=True))
        )

    def has_delete_permission(self, request, obj=None):
        # Events are deactivated or marked cancelled, never deleted.
        return False

    def get_inline_instances(self, request, obj=None):
        if obj is None or obj.access_mode != OnlineEvent.AccessMode.PERSONAL:
            return []
        return super().get_inline_instances(request, obj)

    def report_event(self, obj):
        return obj if obj.access_mode == OnlineEvent.AccessMode.PERSONAL else None

    # -- columns

    @admin.display(description="شروع", ordering="start_at")
    def start_jalali(self, obj):
        return jalali_datetime(obj.start)

    @admin.display(description="پایان", ordering="end_at")
    def end_jalali(self, obj):
        return jalali_datetime(obj.end)

    @admin.display(description="وضعیت زمانی")
    def time_state(self, obj):
        if obj.is_postponed:
            return "زمان جدید اعلام می‌شود"
        return obj.state_at(timezone.now()).label

    @admin.display(description="ردیف‌های شخصی", ordering="rows")
    def row_count(self, obj):
        if obj.access_mode != OnlineEvent.AccessMode.PERSONAL:
            return "—"
        return fa_digits(obj.rows)

    # -- actions

    @admin.action(description="کپی رویدادهای انتخاب‌شده با همان مخاطبان (غیرفعال و بدون ردیف‌های شخصی)", permissions=["add"])
    def duplicate_selected(self, request, queryset):
        count = 0
        for event in queryset:
            if not self.owns(request, event):
                raise PermissionDenied
            services.duplicate_event(event, user=request.user)
            count += 1
        self.message_user(
            request,
            f"{fa_digits(count)} کپی ساخته شد. کپی‌ها غیرفعال‌اند؛ زمان را درست کنید و فعالشان کنید.",
            messages.SUCCESS,
        )

    @admin.action(description="حذف دسترسی‌های شخصی رویدادهای پایان‌یافته‌ی انتخاب‌شده", permissions=["change"])
    def clear_access_selected(self, request, queryset):
        if not request.user.has_perm("online_classes.delete_onlineeventaccess"):
            raise PermissionDenied
        events = list(queryset)
        for event in events:
            if not self.owns(request, event):
                raise PermissionDenied

        now = timezone.now()
        ended = [event for event in events if event.state_at(now) == OnlineEvent.State.ENDED]
        if "confirm" in request.POST:
            deleted = services.clear_access_rows(ended)
            self.message_user(request, f"{fa_digits(deleted)} ردیف دسترسی شخصی حذف شد.", messages.SUCCESS)
            return None
        return render(request, "admin/online_classes/onlineevent/clear_access_confirm.html", {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": "حذف دسترسی‌های شخصی",
            "events": ended,
            "skipped": len(events) - len(ended),
            "selected": [event.pk for event in events],
            "action": "clear_access_selected",
            "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
        })

    # -- pages

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path(
                "student-autocomplete/",
                view(StudentAutocompleteView.as_view(admin_site=self.admin_site)),
                name=STUDENT_AUTOCOMPLETE,
            ),
            path("<int:pk>/access-import/", view(never_cache(self.import_view)), name="online_classes_onlineevent_access_import"),
            path("<int:pk>/access-import/template/", view(never_cache(self.import_template_view)), name="online_classes_onlineevent_access_template"),
        ] + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra = dict(extra_context or {})
        obj = self.get_object(request, object_id)
        if obj is not None and self.has_change_permission(request, obj):
            extra["can_import"] = (
                obj.access_mode == OnlineEvent.AccessMode.PERSONAL
                and request.user.has_perm("online_classes.add_onlineeventaccess")
            )
        extra["can_announce"] = request.user.has_perm("online_classes.add_announcement")
        return super().change_view(request, object_id, form_url, extra)

    def _import_event(self, request, pk):
        if not self.has_change_permission(request):
            raise PermissionDenied
        event = get_object_or_404(self.get_queryset(request).select_related("platform"), pk=pk)
        if not (self.has_change_permission(request, event) and request.user.has_perm("online_classes.add_onlineeventaccess")):
            raise PermissionDenied
        if event.access_mode != OnlineEvent.AccessMode.PERSONAL:
            raise Http404
        return event

    def import_template_view(self, request, pk):
        event = self._import_event(request, pk)
        response = HttpResponse(
            build_template(event),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="online-access-{event.pk}.xlsx"'
        return response

    def import_view(self, request, pk):
        """
        POST a file -> preview of every row, passwords masked (the cells are kept
        in the session only as an encrypted, expiring token); POST ``confirm`` ->
        the cells are validated again and, if every row is valid, saved at once.
        """

        event = self._import_event(request, pk)
        form = AccessImportForm(request.POST or None, request.FILES or None)
        context = {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": f"ورود اطلاعات شخصی از اکسل: {event.title}",
            "event": event,
            "form": form,
            "columns": importer.COLUMNS,
            "max_rows": settings.ONLINE_ACCESS_IMPORT_MAX_ROWS,
        }
        template = "admin/online_classes/onlineevent/access_import.html"

        if request.method != "POST":
            request.session.pop(IMPORT_SESSION_KEY, None)
            return render(request, template, context)

        try:
            if "confirm" in request.POST:
                stored = importer.unseal(request.session.get(IMPORT_SESSION_KEY), event, request.user)
                if stored is None:
                    request.session.pop(IMPORT_SESSION_KEY, None)
                    context["file_error"] = "پیش‌نمایش منقضی شده یا پیدا نشد؛ فایل را دوباره بفرستید."
                    return render(request, template, context)
                rows, filename = stored
                plan = importer.validate(rows, event, request.user)
                context["filename"] = filename
                if plan.is_valid:
                    created, updated = services.save_access_import(plan, user=request.user)
                    request.session.pop(IMPORT_SESSION_KEY, None)
                    self.message_user(
                        request,
                        f"{fa_digits(created)} ردیف تازه ثبت و {fa_digits(updated)} ردیف بروزرسانی شد. "
                        "فایل اکسل را پاک کنید؛ رمزها در آن هستند.",
                        messages.SUCCESS,
                    )
                    return redirect("admin:online_classes_onlineevent_change", event.pk)
            elif form.is_valid():
                upload = form.cleaned_data["file"]
                rows = importer.read_rows(upload)
                plan = importer.validate(rows, event, request.user)
                request.session[IMPORT_SESSION_KEY] = importer.seal(event, request.user, rows, upload.name)
                context["filename"] = upload.name
            else:
                return render(request, template, context)
        except FileRejected as error:
            context["file_error"] = str(error)
            return render(request, template, context)

        context["plan"] = plan
        return render(request, template, context)


# ----------------------------------------------------------------------
# Announcements
# ----------------------------------------------------------------------

class AnnouncementActiveFilter(admin.SimpleListFilter):
    title = "زمان نمایش"
    parameter_name = "showing"

    def lookups(self, request, model_admin):
        return [("now", "الان در حال نمایش"), ("coming", "آینده"), ("over", "تمام‌شده")]

    def queryset(self, request, queryset):
        now = utc_now()
        match self.value():
            case "now":
                return queryset.filter(is_active=True, visible_from__lte=now, visible_until__gt=now)
            case "coming":
                return queryset.filter(visible_from__gt=now)
            case "over":
                return queryset.filter(visible_until__lte=now)
        return queryset


@admin.register(Announcement)
class AnnouncementAdmin(AudienceAdminMixin, admin.ModelAdmin):
    form = AnnouncementAdminForm
    change_form_template = "admin/online_classes/announcement/change_form.html"
    list_display = (
        "title", "level", "from_jalali", "until_jalali", "priority", "is_pinned",
        "audience_summary", "dismissed_count", "is_active",
    )
    list_filter = (AnnouncementActiveFilter, "level", BranchFilter, GradeFilter, "is_active")
    search_fields = ("title", "body")
    ordering = ("-visible_from", "-pk")
    autocomplete_fields = ("students", "excluded_students", "event")
    readonly_fields = ("created_by", "created_jalali", "updated_by", "updated_jalali")
    fieldsets = (
        ("اطلاعیه", {
            "fields": ("title", "body", "level", "image", "image_mobile", ("button_label", "button_url"), "event"),
        }),
        ("زمان و ترتیب نمایش", {
            "fields": (("visible_from", "visible_until"), "priority", "is_pinned", "is_dismissible", "is_active"),
        }),
        ("مخاطبان (هیچ انتخابی یعنی هیچ‌کس)", {
            "fields": ("is_whole_school", "branches", "grades", "classes", "students", "excluded_students"),
            "description": "شعبه و پایه با هم یعنی همان پایه در همان شعبه. کلاس‌ها و دانش‌آموزان به آن اضافه می‌شوند. "
                           "دانش‌آموز مستثنا در هر حال نمی‌بیند.",
        }),
        ("ثبت", {"fields": ("created_by", "created_jalali", "updated_by", "updated_jalali")}),
    )

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .prefetch_related(*AUDIENCE_PREFETCH)
            .annotate(dismissed=Count("dismissals", distinct=True))
        )

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and self.owns(request, obj)

    def get_changeform_initial_data(self, request):
        """``?from_event=<id>``: a copy of the event's title, dates and audience (D22)."""

        initial = super().get_changeform_initial_data(request)
        event_id = request.GET.get("from_event", "")
        if not event_id.isdigit():
            return initial
        event_admin = self.admin_site._registry[OnlineEvent]
        event = event_admin.get_queryset(request).filter(pk=event_id).first()
        if event is None:
            return initial
        initial.update({
            "event": event.pk,
            "title": event.title[:Announcement._meta.get_field("title").max_length],
            "visible_from": timezone.now(),
            "visible_until": event.end,
            "is_whole_school": event.is_whole_school,
        })
        for field in audience.ALL_TARGET_FIELDS:
            initial[field] = list(getattr(event, field).values_list("pk", flat=True))
        return initial

    @admin.display(description="از", ordering="visible_from")
    def from_jalali(self, obj):
        return jalali_datetime(obj.visible_from)

    @admin.display(description="تا", ordering="visible_until")
    def until_jalali(self, obj):
        return jalali_datetime(obj.visible_until)

    @admin.display(description="بسته‌شده", ordering="dismissed")
    def dismissed_count(self, obj):
        return fa_digits(obj.dismissed)
