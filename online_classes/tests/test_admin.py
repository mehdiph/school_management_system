import tempfile
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from core.moments import format_jalali_datetime
from core.testing import grant_all_model_permissions, make_branch_access, make_staff, make_superuser
from online_classes import services
from online_classes.forms import AnnouncementAdminForm, OnlineEventAdminForm
from online_classes.models import Announcement, OnlineEvent, OnlineEventAccess, OnlinePlatform
from online_classes.testing import NOW, SchoolMixin, make_access, make_announcement, make_event, make_platform

PERSONAL = OnlineEvent.AccessMode.PERSONAL
EVENTS = reverse("admin:online_classes_onlineevent_changelist")
ANNOUNCEMENTS = reverse("admin:online_classes_announcement_changelist")


def change(pk):
    return reverse("admin:online_classes_onlineevent_change", args=[pk])


def reveal(pk):
    return reverse("admin:online_classes_onlineeventaccess_reveal", args=[pk])


def image_file(name="logo.png", mode="RGBA", size=(1200, 800)):
    buffer = BytesIO()
    Image.new(mode, size, (200, 100, 50, 255) if mode == "RGBA" else (200, 100, 50)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class AdminBase(SchoolMixin):
    def setUp(self):
        self.make_school()
        self.superuser = make_superuser()
        self.client.force_login(self.superuser)
        self.platform = make_platform()
        clock = patch("django.utils.timezone.now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)

    def branch_admin(self, *branches, secrets=False):
        staff = make_staff(is_staff=True)
        for branch in branches or (self.branch_a,):
            make_branch_access(staff, branch)
        grant_all_model_permissions(staff.user)
        if not secrets:
            staff.user.user_permissions.remove(Permission.objects.get(codename="view_access_secret"))
        self.client.force_login(staff.user)
        return staff.user

    def event_data(self, **overrides):
        start = NOW + timedelta(hours=1)
        data = {
            "title": "کلاس",
            "event_type": "class",
            "platform": self.platform.pk,
            "start_at": format_jalali_datetime(start),
            "end_at": format_jalali_datetime(start + timedelta(hours=1)),
            "status": "scheduled",
            "access_mode": "shared",
            "join_url": "https://example.com/room",
            "credentials_lead_hours": 0,
            "is_active": "on",
            "access_rows-TOTAL_FORMS": 0,
            "access_rows-INITIAL_FORMS": 0,
        }
        data.update(overrides)
        return {key: value for key, value in data.items() if value is not None}


class EventFormTests(AdminBase, TestCase):
    def test_add_with_jalali_moments_stores_the_right_instant_and_who(self):
        response = self.client.post(
            reverse("admin:online_classes_onlineevent_add"),
            self.event_data(is_whole_school="on", start_at="۱۴۰۵/۰۸/۱۲ ۱۱:۰۰", end_at="1405/08/12 12:00"),
        )
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["errors"])
        event = OnlineEvent.objects.get()
        self.assertEqual(event.start, NOW + timedelta(hours=1))
        self.assertEqual(event.end, NOW + timedelta(hours=2))
        self.assertEqual((event.created_by, event.updated_by), (self.superuser, self.superuser))

    def test_bad_moment_is_a_form_error(self):
        response = self.client.post(reverse("admin:online_classes_onlineevent_add"), self.event_data(start_at="فردا"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "تاریخ و ساعت معتبر نیست")

    def test_change_keeps_the_moments_and_records_who(self):
        event = make_event({"classes": [self.class_a1]})
        admin_two = make_superuser()
        self.client.force_login(admin_two)
        page = self.client.get(change(event.pk))
        self.assertContains(page, format_jalali_datetime(event.start))
        response = self.client.post(
            change(event.pk),
            self.event_data(classes=[self.class_a1.pk], start_at=format_jalali_datetime(event.start), end_at=format_jalali_datetime(event.end), title="تازه"),
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.title, "تازه")
        self.assertEqual(event.start, NOW + timedelta(hours=1))
        self.assertEqual(event.updated_by, admin_two)

    def test_empty_audience_warns(self):
        response = self.client.post(reverse("admin:online_classes_onlineevent_add"), self.event_data(), follow=True)
        self.assertContains(response, "به هیچ‌کس نشان داده نمی‌شود")

    def test_save_reports_the_student_count(self):
        response = self.client.post(
            reverse("admin:online_classes_onlineevent_add"), self.event_data(branches=[self.branch_a.pk]), follow=True
        )
        self.assertContains(response, "این مورد به ۲ دانش‌آموز نشان داده می‌شود")

    def _form_errors(self, **overrides):
        form = OnlineEventAdminForm(self.event_data(**overrides))
        self.assertFalse(form.is_valid())
        return form.errors

    def test_whole_school_refuses_other_targets(self):
        self.assertIn("is_whole_school", self._form_errors(is_whole_school="on", branches=[self.branch_a.pk]))

    def test_listed_and_excluded_is_refused(self):
        errors = self._form_errors(students=[self.student_a1.pk], excluded_students=[self.student_a1.pk])
        self.assertIn("excluded_students", errors)

    def test_whole_school_with_exclusions_is_fine(self):
        form = OnlineEventAdminForm(self.event_data(is_whole_school="on", excluded_students=[self.student_a1.pk]))
        self.assertTrue(form.is_valid(), form.errors)

    def test_old_year_classes_are_not_offered(self):
        from core.testing import make_academic_year, make_school_class
        old = make_school_class(self.branch_a, self.grade_1, make_academic_year(is_current=False))
        form = OnlineEventAdminForm()
        self.assertIn(self.class_a1, form.fields["classes"].queryset)
        self.assertNotIn(old, form.fields["classes"].queryset)

    def test_no_delete(self):
        event = make_event()
        self.assertEqual(self.client.get(reverse("admin:online_classes_onlineevent_delete", args=[event.pk])).status_code, 403)

    def test_list_page(self):
        make_event({"branches": [self.branch_a]}, title="یکی")
        make_event(access_mode=PERSONAL, title="دو")
        make_event(status=OnlineEvent.Status.POSTPONED, status_note="x", title="سه")
        response = self.client.get(EVENTS)
        self.assertContains(response, "یکی")
        self.assertContains(response, "زمان جدید اعلام می‌شود")

    def test_filters(self):
        whole = make_event(title="کل")
        by_class = make_event({"classes": [self.class_a1]}, title="کلاس")
        other = make_event({"classes": [self.class_b1]}, title="دیگر")
        postponed = make_event({"grades": [self.grade_2]}, status="postponed", status_note="x", title="تعویق")
        ended = make_event(
            {"classes": [self.class_b1]}, title="تمام", start_at=NOW - timedelta(days=2), end_at=NOW - timedelta(days=1)
        )

        def found(**params):
            return set(self.client.get(EVENTS, params).context["cl"].queryset.values_list("pk", flat=True))

        self.assertEqual(found(branch=self.branch_a.pk), {whole.pk, by_class.pk, postponed.pk})
        self.assertEqual(found(grade=self.grade_1.pk), {whole.pk, by_class.pk, other.pk, ended.pk})
        self.assertEqual(found(state="postponed"), {postponed.pk})
        self.assertEqual(found(state="ended"), {ended.pk})
        self.assertEqual(found(when="last7"), {ended.pk})
        self.assertEqual(found(platform__id__exact=by_class.platform_id), {by_class.pk})
        self.assertEqual(found(event_type__exact="exam"), set())


class AccessInlineTests(AdminBase, TestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event({"classes": [self.class_a1]}, access_mode=PERSONAL, platform=self.platform)

    def inline_data(self, *rows, initial=0):
        data = self.event_data(
            access_mode="personal",
            join_url="",
            classes=[self.class_a1.pk],
            **{"access_rows-TOTAL_FORMS": len(rows), "access_rows-INITIAL_FORMS": initial},
        )
        for index, row in enumerate(rows):
            for key, value in row.items():
                data[f"access_rows-{index}-{key}"] = value
        return data

    def test_masked_on_the_event_page(self):
        make_access(self.event, self.student_a1, url="https://example.com/secret-path", password="pw-secret", access_code="code-secret")
        response = self.client.get(change(self.event.pk))
        for secret in ("pw-secret", "code-secret", "secret-path"):
            self.assertNotContains(response, secret)
        row = OnlineEventAccess.objects.get()
        self.assertNotContains(response, row.password_encrypted)
        self.assertContains(response, "ثبت شده")

    def test_masked_in_the_rows_list(self):
        row = make_access(self.event, self.student_a1, url="https://example.com/secret-path", password="pw-secret")
        response = self.client.get(reverse("admin:online_classes_onlineeventaccess_changelist"))
        self.assertContains(response, "••••••")
        for secret in ("pw-secret", "secret-path", row.password_encrypted):
            self.assertNotContains(response, secret)

    def test_add_encrypts_and_records_who(self):
        response = self.client.post(change(self.event.pk), self.inline_data({
            "student": self.student_a1.pk, "event": self.event.pk, "password": "pw-new", "url": "https://example.com/n",
        }))
        self.assertEqual(response.status_code, 302)
        row = OnlineEventAccess.objects.get()
        self.assertEqual(row.read_secrets()["password"], "pw-new")
        self.assertEqual(row.updated_by, self.superuser)

    def test_blank_keeps_the_secret_and_a_new_value_replaces_it(self):
        row = make_access(self.event, self.student_a1, password="pw-old", url="https://example.com/old")
        self.client.post(change(self.event.pk), self.inline_data(
            {"id": row.pk, "student": self.student_a1.pk, "event": self.event.pk, "username": "added"}, initial=1,
        ))
        row.refresh_from_db()
        self.assertEqual(row.username, "added")
        self.assertEqual(row.read_secrets()["password"], "pw-old")
        self.client.post(change(self.event.pk), self.inline_data(
            {"id": row.pk, "student": self.student_a1.pk, "event": self.event.pk, "password": "pw-new"}, initial=1,
        ))
        row.refresh_from_db()
        self.assertEqual(row.read_secrets()["password"], "pw-new")
        self.assertEqual(row.read_secrets()["url"], "https://example.com/old")

    def test_a_note_alone_is_refused(self):
        response = self.client.post(change(self.event.pk), self.inline_data({
            "student": self.student_a1.pk, "event": self.event.pk, "note": "فقط توضیح",
        }))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "فقط «توضیح» کافی نیست")
        self.assertEqual(OnlineEventAccess.objects.count(), 0)

    def test_platform_domains_are_enforced(self):
        OnlinePlatform.objects.filter(pk=self.platform.pk).update(allowed_domains="skyroom.online")
        response = self.client.post(change(self.event.pk), self.inline_data({
            "student": self.student_a1.pk, "event": self.event.pk, "url": "https://example.com/x",
        }))
        self.assertContains(response, "دامنه‌های مجاز")
        self.assertEqual(OnlineEventAccess.objects.count(), 0)

    def test_second_row_for_a_student_is_refused(self):
        make_access(self.event, self.student_a1, password="x")
        response = self.client.post(change(self.event.pk), self.inline_data(
            {"id": OnlineEventAccess.objects.get().pk, "student": self.student_a1.pk, "event": self.event.pk},
            {"student": self.student_a1.pk, "event": self.event.pk, "password": "y"},
            initial=1,
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(OnlineEventAccess.objects.count(), 1)

    def test_page_shows_the_count_and_the_list_of_missing_students(self):
        second = self.enrol(self.class_a1)
        make_access(self.event, self.student_a1, password="x")
        response = self.client.get(change(self.event.pk))
        self.assertContains(response, "۱ دانش‌آموز بدون ردیف")
        self.assertContains(response, second.user.get_full_name())
        self.assertEqual([e.student for e in services.missing_access(self.event)], [second])

    def test_shared_event_has_no_inline(self):
        event = make_event()
        self.assertNotContains(self.client.get(change(event.pk)), "access_rows-TOTAL_FORMS")

    @override_settings(ONLINE_ACCESS_INLINE_MAX=1)
    def test_a_large_event_does_not_list_its_rows_and_still_saves(self):
        first = make_access(self.event, self.student_a1, password="a", username="u-first")
        make_access(self.event, self.student_b1, password="b", username="u-second")
        response = self.client.get(change(self.event.pk))
        self.assertNotContains(response, "u-first")
        self.assertContains(response, "فهرست ردیف‌ها")
        response = self.client.post(change(self.event.pk), self.inline_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OnlineEventAccess.objects.count(), 2)
        self.assertTrue(OnlineEventAccess.objects.filter(pk=first.pk).exists())

    def test_row_page_edits_and_keeps_the_student(self):
        row = make_access(self.event, self.student_a1, password="old")
        url = reverse("admin:online_classes_onlineeventaccess_change", args=[row.pk])
        self.assertNotContains(self.client.get(url), row.password_encrypted)
        response = self.client.post(url, {"student": self.student_b1.pk, "username": "u", "url": "", "password": "", "access_code": "", "note": ""})
        self.assertEqual(response.status_code, 302)
        row.refresh_from_db()
        self.assertEqual(row.student, self.student_a1, "a row can't be moved to another student")
        self.assertEqual(row.username, "u")
        self.assertEqual(row.read_secrets()["password"], "old")
        self.assertEqual(row.updated_by, self.superuser)

    def test_no_add_page_for_rows(self):
        self.assertEqual(self.client.get(reverse("admin:online_classes_onlineeventaccess_add")).status_code, 403)


class RevealTests(AdminBase, TestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event({"classes": [self.class_a1]}, access_mode=PERSONAL)
        self.row = make_access(self.event, self.student_a1, password="pw-secret", url="https://example.com/secret-path")

    def test_superuser_get_shows_nothing_until_post(self):
        response = self.client.get(reveal(self.row.pk))
        self.assertNotContains(response, "pw-secret")
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_post_shows_and_is_written_to_history_without_the_value(self):
        response = self.client.post(reveal(self.row.pk))
        self.assertContains(response, "pw-secret")
        self.assertContains(response, "secret-path")
        self.assertIn("no-store", response["Cache-Control"])
        entry = LogEntry.objects.get()
        self.assertEqual(entry.user, self.superuser)
        self.assertEqual(entry.object_id, str(self.row.pk))
        self.assertIn("نمایش اطلاعات ورود", entry.change_message)
        self.assertNotIn("pw-secret", entry.change_message)

    def test_without_the_permission_is_refused(self):
        self.branch_admin(self.branch_a, secrets=False)
        self.assertEqual(self.client.post(reveal(self.row.pk)).status_code, 403)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_with_the_permission_inside_their_branches(self):
        self.branch_admin(self.branch_a, secrets=True)
        self.assertContains(self.client.post(reveal(self.row.pk)), "pw-secret")

    def test_with_the_permission_outside_their_branches_is_a_404(self):
        self.branch_admin(self.branch_b, secrets=True)
        self.assertEqual(self.client.post(reveal(self.row.pk)).status_code, 404)

    def test_non_staff_never_reach_it(self):
        self.client.force_login(self.student_a1.user)
        self.assertEqual(self.client.post(reveal(self.row.pk)).status_code, 302)

    def test_staff_without_the_permission_can_still_replace_a_secret(self):
        self.branch_admin(self.branch_a, secrets=False)
        url = reverse("admin:online_classes_onlineeventaccess_change", args=[self.row.pk])
        response = self.client.post(url, {"username": "", "url": "", "password": "pw-new", "access_code": "", "note": ""})
        self.assertEqual(response.status_code, 302)
        self.row.refresh_from_db()
        self.assertEqual(self.row.read_secrets()["password"], "pw-new")


class BranchScopeTests(AdminBase, TestCase):
    def setUp(self):
        super().setUp()
        self.inside = make_event({"branches": [self.branch_a]}, title="داخل")
        self.outside = make_event({"branches": [self.branch_b]}, title="بیرون")
        self.whole = make_event(title="کل")
        self.user = self.branch_admin(self.branch_a)

    def test_list_shows_what_touches_their_branches(self):
        response = self.client.get(EVENTS)
        found = set(response.context["cl"].queryset.values_list("pk", flat=True))
        self.assertEqual(found, {self.inside.pk, self.whole.pk})

    def test_changes_only_what_is_wholly_inside(self):
        self.assertEqual(self.client.post(change(self.whole.pk), self.event_data(is_whole_school="on")).status_code, 403)
        self.assertEqual(self.client.get(change(self.outside.pk)).status_code, 302, "out of scope: redirected as unknown")
        response = self.client.post(
            change(self.inside.pk),
            self.event_data(
                branches=[self.branch_a.pk], title="ویرایش‌شده",
                start_at=format_jalali_datetime(self.inside.start), end_at=format_jalali_datetime(self.inside.end),
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.inside.refresh_from_db()
        self.assertEqual(self.inside.title, "ویرایش‌شده")

    def _add(self, **overrides):
        return self.client.post(reverse("admin:online_classes_onlineevent_add"), self.event_data(**overrides))

    def test_refused_targets(self):
        cases = {
            "whole school": {"is_whole_school": "on"},
            "another branch": {"branches": [self.branch_b.pk]},
            "another class": {"classes": [self.class_b1.pk]},
            "another student": {"students": [self.student_b1.pk]},
            "excluded student elsewhere": {"branches": [self.branch_a.pk], "excluded_students": [self.student_b1.pk]},
            "a grade alone": {"grades": [self.grade_1.pk]},
            "nothing": {},
        }
        before = OnlineEvent.objects.count()
        for name, targets in cases.items():
            with self.subTest(name):
                self.assertEqual(self._add(**targets).status_code, 200)
        self.assertEqual(OnlineEvent.objects.count(), before)

    def test_allowed_targets(self):
        self.assertEqual(self._add(branches=[self.branch_a.pk], grades=[self.grade_1.pk]).status_code, 302)
        self.assertEqual(self._add(classes=[self.class_a1.pk]).status_code, 302)
        self.assertEqual(self._add(students=[self.student_a1.pk]).status_code, 302)

    def test_form_offers_only_their_branches_and_classes(self):
        response = self.client.get(reverse("admin:online_classes_onlineevent_add"))
        form = response.context["adminform"].form
        self.assertEqual(list(form.fields["branches"].queryset), [self.branch_a])
        self.assertNotIn(self.class_b1, form.fields["classes"].queryset)
        self.assertTrue(form.fields["is_whole_school"].disabled)

    def test_the_whole_school_box_can_not_be_forced(self):
        # The checkbox is disabled, so a forged value is ignored and nothing makes it whole-school.
        self._add(is_whole_school="on", branches=[self.branch_a.pk], title="جعلی")
        self.assertFalse(OnlineEvent.objects.filter(title="جعلی", is_whole_school=True).exists())

    def test_student_picker_only_finds_their_students(self):
        url = reverse("admin:autocomplete")
        params = {"app_label": "online_classes", "model_name": "onlineevent", "field_name": "students", "term": ""}
        ids = {int(item["id"]) for item in self.client.get(url, params).json()["results"]}
        self.assertIn(self.student_a1.pk, ids)
        self.assertNotIn(self.student_b1.pk, ids)

    def test_student_picker_search_by_code(self):
        self.client.force_login(self.superuser)
        url = reverse("admin:autocomplete")
        params = {
            "app_label": "online_classes", "model_name": "onlineevent", "field_name": "students",
            "term": self.student_b1.student_code,
        }
        ids = {int(item["id"]) for item in self.client.get(url, params).json()["results"]}
        self.assertEqual(ids, {self.student_b1.pk})

    def test_inline_new_row_for_another_branch_is_refused(self):
        event = make_event({"branches": [self.branch_a]}, access_mode=PERSONAL, platform=self.platform, title="ش")
        data = self.event_data(
            access_mode="personal", join_url="", branches=[self.branch_a.pk],
            **{
                "access_rows-TOTAL_FORMS": 1, "access_rows-INITIAL_FORMS": 0,
                "access_rows-0-student": self.student_b1.pk, "access_rows-0-event": event.pk, "access_rows-0-password": "x",
            },
        )
        response = self.client.post(change(event.pk), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "در شعبه‌های شما نیست")
        self.assertEqual(OnlineEventAccess.objects.count(), 0)

    def test_no_rows_shown_on_an_item_they_can_only_view(self):
        personal = make_event(access_mode=PERSONAL)
        make_access(personal, self.student_a1, username="u-visible")
        response = self.client.get(change(personal.pk))
        self.assertNotContains(response, "u-visible")
        self.assertNotContains(response, "access_rows-TOTAL_FORMS")
        response = self.client.get(reverse("admin:online_classes_onlineeventaccess_changelist"))
        self.assertNotContains(response, "u-visible")

    def test_announcements_follow_the_same_rules(self):
        inside = make_announcement({"branches": [self.branch_a]}, title="داخل")
        make_announcement({"branches": [self.branch_b]}, title="بیرون")
        whole = make_announcement(title="کل")
        found = set(self.client.get(ANNOUNCEMENTS).context["cl"].queryset.values_list("pk", flat=True))
        self.assertEqual(found, {inside.pk, whole.pk})
        url = reverse("admin:online_classes_announcement_change", args=[whole.pk])
        self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_actions_refuse_what_is_not_theirs(self):
        response = self.client.post(EVENTS, {"action": "duplicate_selected", "_selected_action": [self.whole.pk]})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(OnlineEvent.objects.filter(title__endswith="(کپی)").count(), 0)


class RoleRefusalTests(AdminBase, TestCase):
    def test_every_panel_role_is_kept_out(self):
        from core.testing import make_user

        for role in ("teacher", "supervisor", "director", "student"):
            with self.subTest(role):
                self.client.force_login(make_user(role))
                self.assertEqual(self.client.get(EVENTS).status_code, 302)

    def test_staff_without_permissions_is_refused(self):
        self.client.force_login(make_staff(is_staff=True).user)
        self.assertEqual(self.client.get(EVENTS).status_code, 403)
        self.assertEqual(self.client.get(ANNOUNCEMENTS).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:online_classes_onlineplatform_changelist")).status_code, 403)


class DuplicateTests(AdminBase, TestCase):
    def test_copy_has_the_audience_no_rows_and_starts_hidden(self):
        event = make_event(
            {
                "branches": [self.branch_a], "grades": [self.grade_1], "classes": [self.class_b1],
                "students": [self.student_a2], "excluded_students": [self.student_a1],
            },
            access_mode=PERSONAL,
            status=OnlineEvent.Status.CANCELLED,
            status_note="x",
            title="آزمون",
        )
        make_access(event, self.student_a2, password="x")
        response = self.client.post(EVENTS, {"action": "duplicate_selected", "_selected_action": [event.pk]})
        self.assertEqual(response.status_code, 302)

        copy = OnlineEvent.objects.exclude(pk=event.pk).get()
        self.assertEqual(copy.title, "آزمون (کپی)")
        self.assertFalse(copy.is_active)
        self.assertEqual((copy.status, copy.status_note), (OnlineEvent.Status.SCHEDULED, ""))
        self.assertEqual(copy.created_by, self.superuser)
        self.assertEqual(list(copy.branches.all()), [self.branch_a])
        self.assertEqual(list(copy.grades.all()), [self.grade_1])
        self.assertEqual(list(copy.classes.all()), [self.class_b1])
        self.assertEqual(list(copy.students.all()), [self.student_a2])
        self.assertEqual(list(copy.excluded_students.all()), [self.student_a1])
        self.assertEqual(copy.access_rows.count(), 0)

        event.refresh_from_db()
        self.assertEqual(event.access_rows.count(), 1, "the original is untouched")
        self.assertTrue(event.is_active)

    def test_the_original_instance_is_left_alone(self):
        event = make_event({"branches": [self.branch_a]}, title="اصل")
        copy = services.duplicate_event(event)
        self.assertNotEqual(copy.pk, event.pk)
        self.assertEqual(event.title, "اصل")

    def test_a_long_title_still_fits(self):
        copy = services.duplicate_event(make_event(title="ا" * 200))
        self.assertLessEqual(len(copy.title), 200)
        copy.full_clean()


class ClearAccessTests(AdminBase, TestCase):
    def setUp(self):
        super().setUp()
        self.ended = make_event(access_mode=PERSONAL, start_at=NOW - timedelta(days=2), end_at=NOW - timedelta(days=1))
        self.coming = make_event(access_mode=PERSONAL)
        make_access(self.ended, self.student_a1, password="x")
        make_access(self.coming, self.student_a1, password="y")

    def _post(self, **extra):
        return self.client.post(EVENTS, {
            "action": "clear_access_selected", "_selected_action": [self.ended.pk, self.coming.pk], **extra,
        })

    def test_asks_first(self):
        response = self._post()
        self.assertContains(response, "آیا مطمئن هستید")
        self.assertEqual(OnlineEventAccess.objects.count(), 2)

    def test_clears_only_ended_events(self):
        self.assertEqual(self._post(confirm="1").status_code, 302)
        self.assertEqual(self.ended.access_rows.count(), 0)
        self.assertEqual(self.coming.access_rows.count(), 1)

    def test_needs_the_delete_permission(self):
        staff = make_staff(is_staff=True)
        make_branch_access(staff, self.branch_a)
        grant_all_model_permissions(staff.user)
        staff.user.user_permissions.remove(Permission.objects.get(codename="delete_onlineeventaccess"))
        self.client.force_login(self.superuser)
        OnlineEvent.objects.filter(pk__in=[self.ended.pk, self.coming.pk]).update(is_whole_school=False)
        self.ended.branches.set([self.branch_a])
        self.coming.branches.set([self.branch_a])
        self.client.force_login(staff.user)
        self.assertEqual(self._post(confirm="1").status_code, 403)
        self.assertEqual(self.ended.access_rows.count(), 1)


class PlatformImageTests(AdminBase, TestCase):
    def setUp(self):
        super().setUp()
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)

    def test_logo_is_reencoded_small_and_without_transparency(self):
        platform = OnlinePlatform.objects.create(name="پلتفرم", logo=image_file())
        self.assertTrue(platform.logo.name.endswith(".jpg"))
        with Image.open(platform.logo.path) as stored:
            self.assertEqual(stored.format, "JPEG")
            self.assertLessEqual(max(stored.size), 256)

    def test_svg_is_refused(self):
        svg = SimpleUploadedFile("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", content_type="image/svg+xml")
        response = self.client.post(reverse("admin:online_classes_onlineplatform_add"), {"name": "x", "logo": svg})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(OnlinePlatform.objects.filter(name="x").exists())

    def test_announcement_images_are_reencoded(self):
        item = make_announcement(image=image_file("d.png"), image_mobile=image_file("m.png", size=(2400, 2400)))
        self.assertTrue(item.image.name.endswith(".jpg"))
        with Image.open(item.image_mobile.path) as stored:
            self.assertLessEqual(max(stored.size), 1600)


class AnnouncementFormTests(AdminBase, TestCase):
    def data(self, **overrides):
        data = {
            "title": "الف",
            "level": "info",
            "visible_from": format_jalali_datetime(NOW),
            "visible_until": format_jalali_datetime(NOW + timedelta(days=1)),
            "priority": 0,
            "is_active": "on",
            "is_dismissible": "on",
            "is_whole_school": "on",
        }
        data.update(overrides)
        return data

    def test_urgent_is_saved_as_not_dismissible(self):
        response = self.client.post(reverse("admin:online_classes_announcement_add"), self.data(level="urgent"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Announcement.objects.get().is_dismissible)

    def test_records_who(self):
        self.client.post(reverse("admin:online_classes_announcement_add"), self.data())
        item = Announcement.objects.get()
        self.assertEqual((item.created_by, item.updated_by), (self.superuser, self.superuser))

    def test_bad_button_url_is_refused(self):
        form = AnnouncementAdminForm(self.data(button_label="برو", button_url="//evil.com"))
        self.assertFalse(form.is_valid())
        self.assertIn("button_url", form.errors)

    def test_prefilled_from_an_event(self):
        event = make_event(
            {"branches": [self.branch_a], "excluded_students": [self.student_a1]}, title="آزمون ریاضی",
        )
        response = self.client.get(reverse("admin:online_classes_announcement_add"), {"from_event": event.pk})
        form = response.context["adminform"].form
        self.assertEqual(form.initial["title"], "آزمون ریاضی")
        self.assertEqual(form.initial["event"], event.pk)
        self.assertEqual(form.initial["branches"], [self.branch_a.pk])
        self.assertEqual(form.initial["excluded_students"], [self.student_a1.pk])
        self.assertContains(response, format_jalali_datetime(event.end))

    def test_prefill_ignores_an_event_outside_their_scope(self):
        event = make_event({"branches": [self.branch_b]}, title="پنهان")
        self.branch_admin(self.branch_a)
        response = self.client.get(reverse("admin:online_classes_announcement_add"), {"from_event": event.pk})
        self.assertNotIn("title", response.context["adminform"].form.initial)

    def test_event_page_offers_it(self):
        event = make_event()
        self.assertContains(self.client.get(change(event.pk)), f"?from_event={event.pk}")

    def test_audience_is_a_copy(self):
        event = make_event({"branches": [self.branch_a]})
        self.client.post(
            reverse("admin:online_classes_announcement_add"),
            {k: v for k, v in self.data(event=event.pk, branches=[self.branch_a.pk]).items() if k != "is_whole_school"},
        )
        item = Announcement.objects.get()
        event.branches.set([self.branch_b])
        self.assertEqual(list(item.branches.all()), [self.branch_a])

    def test_list_page(self):
        make_announcement({"branches": [self.branch_a]}, title="یکی")
        self.assertContains(self.client.get(ANNOUNCEMENTS), "یکی")
        self.assertEqual(self.client.get(ANNOUNCEMENTS, {"showing": "now"}).context["cl"].queryset.count(), 1)
        self.assertEqual(self.client.get(ANNOUNCEMENTS, {"showing": "over"}).context["cl"].queryset.count(), 0)
