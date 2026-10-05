"""
System admin pages of the academic calendar (Django admin).

* the event list / form (no delete: «غیرفعال‌کردن» instead, which removes
  the holiday sessions only that event needed);
* «تعطیلی اضطراری»: a short form for unplanned closures;
* «تداخل‌ها»: held sessions recorded for slots later declared closed;
* «ورود از اکسل»: template download, upload -> preview -> confirm.

Every write goes through ``academic_calendar.services`` so the session
sync always runs -- for the event form after its many-to-many scope is
saved (``save_related``).
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Count, Q
from django.forms import CheckboxSelectMultiple
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django_jalali.admin.filters import JDateFieldListFilter
import django_jalali.admin as jadmin  # noqa: F401  (Jalali widgets for jDateField)

from core.services import access
from teaching.models import SchoolSession

from . import importer, services
from .forms import CalendarEventAdminForm, ConflictFilterForm, EventImportForm, QuickClosureForm
from .import_template import build_template
from .models import CalendarEvent

IMPORT_SESSION_KEY = "academic_calendar_import"


def _scope_label(values, all_label):
    values = list(values)
    return "، ".join(str(v) for v in values) if values else all_label


def impact_message(event, result=None):
    """«۱۲ جلسه لغو شد · ۲ تداخل» (with a link to the conflicts page when there are some)."""

    cancelled, conflicts = services.event_impact(event)
    text = f"رویداد «{event.title}»: {cancelled} جلسه به‌دلیل این رویداد لغو شده است"
    if result is not None and result.removed:
        text += f"، {result.removed} جلسه‌ی لغوشده‌ی قبلی حذف شد"
    if result is not None and result.kept:
        text += f"، {result.kept} جلسه‌ی لغوشده چون حضور و غیاب یا محتوا دارد نگه داشته شد"
    if conflicts:
        url = reverse("admin:academic_calendar_calendarevent_conflicts") + f"?year={event.academic_year_id}"
        return format_html(
            '{}؛ <a href="{}">{} تداخل</a> (جلسه‌ی ثبت‌شده در زنگ تعطیل) پیدا شد.',
            text, url, len(conflicts),
        ), messages.WARNING
    return f"{text}؛ تداخلی پیدا نشد.", messages.SUCCESS


@admin.register(CalendarEvent)
class CalendarEventAdmin(admin.ModelAdmin):
    form = CalendarEventAdminForm
    list_display = (
        "title", "event_type", "start_date", "end_date", "branch_scope",
        "grade_scope", "bell_scope", "cancelled_count", "is_active",
    )
    list_filter = (
        "is_active", "event_type", "academic_year",
        ("start_date", JDateFieldListFilter),
    )
    search_fields = ("title", "description")
    date_hierarchy = "start_date"
    ordering = ("-start_date", "-pk")
    readonly_fields = ("created_by", "created_at", "updated_at")
    actions = ("deactivate_selected", "activate_selected")
    formfield_overrides = {
        models.ManyToManyField: {"widget": CheckboxSelectMultiple},
    }
    fieldsets = (
        ("رویداد", {
            "fields": ("academic_year", "title", "event_type", ("start_date", "end_date"), "description"),
            "description": "پنج‌شنبه و جمعه همیشه تعطیل‌اند؛ اگر بازه آن‌ها را بپوشاند، نادیده گرفته می‌شوند.",
        }),
        ("دامنه (خالی یعنی همه)", {
            "fields": ("branches", "grades", "bells"),
        }),
        ("وضعیت", {
            "fields": ("is_active", "created_by", "created_at", "updated_at"),
        }),
    )

    # ------------------------------------------------------------------
    # Scoping: a branch admin sees events of their branches (and the
    # global ones), and may only change events wholly inside them.
    # ------------------------------------------------------------------

    def get_queryset(self, request):
        queryset = (
            super().get_queryset(request)
            .prefetch_related("branches", "grades", "bells")
            .annotate(cancelled=Count("sessions", filter=Q(sessions__status=SchoolSession.Status.HOLIDAY)))
        )
        if request.user.is_superuser:
            return queryset
        allowed = access.get_accessible_branch_ids(request.user, request=request)
        return queryset.filter(Q(branches__in=allowed) | Q(branches__isnull=True)).distinct()

    def _owns(self, request, obj):
        if obj is None or request.user.is_superuser:
            return True
        branch_ids = {b.pk for b in obj.branches.all()}
        allowed = set(access.get_accessible_branch_ids(request.user, request=request))
        return bool(branch_ids) and branch_ids <= allowed

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and self._owns(request, obj)

    def has_delete_permission(self, request, obj=None):
        # Events are deactivated, never deleted: sessions keep their reason.
        return False

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        class RequestForm(form):
            def __init__(self, *args, **inner):
                inner["request"] = request
                super().__init__(*args, **inner)

        return RequestForm

    # ------------------------------------------------------------------
    # Columns
    # ------------------------------------------------------------------

    @admin.display(description="شعبه‌ها")
    def branch_scope(self, obj):
        return _scope_label(obj.branches.all(), "همه")

    @admin.display(description="پایه‌ها")
    def grade_scope(self, obj):
        return _scope_label(obj.grades.all(), "همه")

    @admin.display(description="زنگ‌ها")
    def bell_scope(self, obj):
        return _scope_label(obj.bells.all(), "کل روز")

    @admin.display(description="جلسات لغوشده", ordering="cancelled")
    def cancelled_count(self, obj):
        return obj.cancelled

    # ------------------------------------------------------------------
    # Saving: the sync runs after the many-to-many scope is saved.
    # ------------------------------------------------------------------

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
            request._calendar_previous_range = None
        else:
            request._calendar_previous_range = (
                CalendarEvent.objects.filter(pk=obj.pk).values_list("start_date", "end_date").first()
            )
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        event = form.instance
        result = services.sync_event(event, getattr(request, "_calendar_previous_range", None))
        message, level = impact_message(event, result)
        self.message_user(request, message, level)

    @admin.action(description="غیرفعال‌کردن رویدادهای انتخاب‌شده (جلسات لغوشده‌ی آن‌ها حذف می‌شود)")
    def deactivate_selected(self, request, queryset):
        removed = kept = 0
        for event in queryset.filter(is_active=True):
            if not self._owns(request, event):
                raise PermissionDenied
            result = services.deactivate_event(event)
            removed, kept = removed + result.removed, kept + result.kept
        text = f"رویدادها غیرفعال شدند؛ {removed} جلسه‌ی لغوشده حذف شد."
        if kept:
            text += f" {kept} جلسه چون حضور و غیاب یا محتوا دارد نگه داشته شد."
        self.message_user(request, text, messages.SUCCESS)

    @admin.action(description="فعال‌کردن رویدادهای انتخاب‌شده")
    def activate_selected(self, request, queryset):
        for event in queryset.filter(is_active=False):
            if not self._owns(request, event):
                raise PermissionDenied
            event.is_active = True
            event.save(update_fields=["is_active", "updated_at"])
            message, level = impact_message(event, services.sync_event(event))
            self.message_user(request, message, level)

    # ------------------------------------------------------------------
    # Extra pages
    # ------------------------------------------------------------------

    def get_urls(self):
        view = self.admin_site.admin_view
        return [
            path("conflicts/", view(self.conflicts_view), name="academic_calendar_calendarevent_conflicts"),
            path("quick-closure/", view(self.quick_closure_view), name="academic_calendar_calendarevent_quick_closure"),
            path("import/", view(self.import_view), name="academic_calendar_calendarevent_import"),
            path("import/template/", view(self.import_template_view), name="academic_calendar_calendarevent_import_template"),
        ] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "can_add": self.has_add_permission(request)}
        return super().changelist_view(request, extra_context=extra_context)

    def _context(self, request, title, **extra):
        return {
            **self.admin_site.each_context(request),
            "opts": self.opts,
            "title": title,
            **extra,
        }

    def conflicts_view(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        form = ConflictFilterForm(request.GET or None)
        year = form.cleaned_data["year"] if form.is_valid() else None
        year = year or form.fields["year"].queryset.filter(is_current=True).first()
        if year is not None and not request.GET:
            form = ConflictFilterForm(initial={"year": year})

        conflicts = services.find_conflicts(academic_year=year) if year else []
        if not request.user.is_superuser:
            allowed = set(access.get_accessible_branch_ids(request.user, request=request))
            conflicts = [c for c in conflicts if c.session.class_subject.school_class.branch_id in allowed]
        conflicts.sort(key=lambda c: (c.date, c.bell.order if c.bell else 0), reverse=True)

        return render(request, "admin/academic_calendar/calendarevent/conflicts.html", self._context(
            request, "تداخل‌ها: جلسه‌های ثبت‌شده در زنگ‌های تعطیل",
            form=form, year=year, conflicts=conflicts,
        ))

    def quick_closure_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        form = QuickClosureForm(request.POST or None, user=request.user)
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            event, result = services.create_closure(
                academic_year=form.academic_year,
                title=data["title"],
                start_date=data["date"],
                end_date=data["end_date"],
                branches=data["branches"],
                grades=data["grades"],
                bells=data["bells"],
                description=data["description"],
                created_by=request.user,
            )
            message, level = impact_message(event, result)
            self.message_user(request, message, level)
            return redirect("admin:academic_calendar_calendarevent_changelist")

        return render(request, "admin/academic_calendar/calendarevent/quick_closure.html", self._context(
            request, "ثبت تعطیلی اضطراری", form=form, media=self.media + form.media,
        ))

    def import_template_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        response = HttpResponse(
            build_template(request.user),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = 'attachment; filename="calendar-events-template.xlsx"'
        return response

    def import_view(self, request):
        """
        POST a file -> preview of every row with its errors (the raw cells
        are kept in the session); POST ``confirm`` -> the cells are
        validated again and, if every row is valid, imported at once.
        """

        if not self.has_add_permission(request):
            raise PermissionDenied

        form = EventImportForm(request.POST or None, request.FILES or None)
        context = self._context(
            request, "ورود رویدادهای تقویم از اکسل",
            form=form, columns=importer.COLUMNS, type_values=list(importer.TYPE_VALUES),
        )
        template = "admin/academic_calendar/calendarevent/import.html"

        if request.method != "POST":
            request.session.pop(IMPORT_SESSION_KEY, None)
            return render(request, template, context)

        try:
            if "confirm" in request.POST:
                stored = request.session.get(IMPORT_SESSION_KEY)
                if not stored:
                    context["file_error"] = "پیش‌نمایشی برای تأیید پیدا نشد؛ فایل را دوباره بفرستید."
                    return render(request, template, context)
                plan = importer.validate(stored["rows"], request.user)
                context["filename"] = stored["filename"]
                if plan.is_valid:
                    events, result = services.import_events(plan, created_by=request.user)
                    request.session.pop(IMPORT_SESSION_KEY, None)
                    return render(request, "admin/academic_calendar/calendarevent/import_result.html", self._context(
                        request, "نتیجه‌ی ورود رویدادها",
                        events=events, result=result, filename=stored["filename"],
                    ))
            elif form.is_valid():
                upload = form.cleaned_data["file"]
                rows = importer.read_rows(upload)
                plan = importer.validate(rows, request.user)
                request.session[IMPORT_SESSION_KEY] = {"rows": rows, "filename": upload.name}
                context["filename"] = upload.name
            else:
                return render(request, template, context)
        except importer.FileRejected as error:
            context["file_error"] = str(error)
            return render(request, template, context)

        context["plan"] = plan
        return render(request, template, context)
