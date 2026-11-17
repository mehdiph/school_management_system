"""
Who an event or announcement reaches, in the admin: counts and a per-class
breakdown on the item's page, the names on a separate list page, adding a
missing row from there (audience-lists change, D1–D4).
"""

from unittest.mock import patch
from urllib.parse import urlencode

from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from core.testing import make_school_class
from online_classes import audience
from online_classes.models import OnlineEvent, OnlineEventAccess
from online_classes.testing import make_access, make_announcement, make_event
from student.models.student_enrollment import StudentEnrollment

from .test_admin import AdminBase, change
from .test_importer import cells, xlsx

PERSONAL = OnlineEvent.AccessMode.PERSONAL
SCOPED = "فقط دانش‌آموزان شعبه‌های شما"


def students_url(item, **params):
    name = "onlineevent" if isinstance(item, OnlineEvent) else "announcement"
    url = reverse(f"admin:online_classes_{name}_students", args=[item.pk])
    return url + ("?" + urlencode(params) if params else "")


def announcement_change(item):
    return reverse("admin:online_classes_announcement_change", args=[item.pk])


ADD_ROW = reverse("admin:online_classes_onlineeventaccess_add")


class BreakdownTests(AdminBase, TestCase):
    def counts(self, item, **kwargs):
        result = audience.breakdown(item, **kwargs)
        return {row.class_id: (row.total, row.missing) for row in result.classes}, result

    def test_each_audience_rule(self):
        extra = self.enrol(self.class_a1)
        cases = {
            "whole school": ({}, {self.class_a1.pk: 2, self.class_a2.pk: 1, self.class_b1.pk: 1}),
            "branch": ({"branches": [self.branch_a]}, {self.class_a1.pk: 2, self.class_a2.pk: 1}),
            "branch and grade": ({"branches": [self.branch_a], "grades": [self.grade_1]}, {self.class_a1.pk: 2}),
            "grade only": ({"grades": [self.grade_1]}, {self.class_a1.pk: 2, self.class_b1.pk: 1}),
            "class plus student": ({"classes": [self.class_a2], "students": [self.student_b1]}, {self.class_a2.pk: 1, self.class_b1.pk: 1}),
            "exclusion wins": ({"branches": [self.branch_a], "excluded_students": [extra]}, {self.class_a1.pk: 1, self.class_a2.pk: 1}),
        }
        for name, (targets, expected) in cases.items():
            with self.subTest(name):
                item = make_announcement(targets or None)
                found, result = self.counts(item)
                self.assertEqual({key: total for key, (total, _) in found.items()}, expected)
                self.assertEqual(result.total, sum(expected.values()))
                # Same answer as the list the import and everything else use.
                self.assertEqual(result.total, audience.reached_enrollments(item).count())

    def test_with_and_without_a_row(self):
        event = make_event({"branches": [self.branch_a]}, access_mode=PERSONAL)
        make_access(event, self.student_a1, password="x")
        make_access(event, self.student_b1, password="y")  # outside the audience: not counted
        found, result = self.counts(event, event=event)
        self.assertEqual(found, {self.class_a1.pk: (1, 0), self.class_a2.pk: (1, 1)})
        self.assertEqual((result.total, result.with_row, result.missing), (2, 1, 1))

    def test_a_class_change_moves_the_student(self):
        event = make_event({"classes": [self.class_a1]})
        self.assertEqual(self.counts(event)[1].total, 1)
        StudentEnrollment.objects.filter(student=self.student_a1).update(school_class=self.class_a2)
        self.assertEqual(self.counts(event)[1].total, 0)

    def test_one_row_per_class_ordered_by_grade_section_branch(self):
        a1_b = make_school_class(self.branch_a, self.grade_1, self.year)
        a1_b.section = "zz"
        a1_b.save()
        self.class_a1.section = "aa"
        self.class_a1.save()
        self.class_b1.section = "aa"
        self.class_b1.save()
        self.enrol(a1_b)
        self.enrol(self.class_a1)
        _, result = self.counts(make_event())
        order = [row.class_id for row in result.classes]
        self.assertEqual(len(order), len(set(order)))
        # Grade 1 «aa» (both branches, by branch), grade 1 «zz», then grade 2.
        self.assertEqual(order, [self.class_a1.pk, self.class_b1.pk, a1_b.pk, self.class_a2.pk])

    def test_branch_scope(self):
        _, result = self.counts(make_event(), branch_ids=[self.branch_b.pk])
        self.assertEqual([row.class_id for row in result.classes], [self.class_b1.pk])


class PageSummaryTests(AdminBase, TestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event(access_mode=PERSONAL, platform=self.platform)  # whole school
        make_access(self.event, self.student_a1, password="x")
        self.announcement = make_announcement()

    def test_event_page_summary_and_breakdown(self):
        response = self.client.get(change(self.event.pk))
        html = response.content.decode()
        self.assertIn("۳ دانش‌آموز مخاطب", html)
        self.assertIn("۱ با ردیف دسترسی", html)
        self.assertIn("۲ بدون ردیف", html)
        self.assertIn("<details", html)
        self.assertNotIn("<details open", html)
        self.assertIn(students_url(self.event) + "?access=without", html)
        self.assertIn(students_url(self.event) + f"?class={self.class_a1.pk}", html)
        self.assertNotIn(SCOPED, html)
        # Never a name: the page doesn't list students.
        for student in (self.student_a1, self.student_a2, self.student_b1):
            self.assertNotIn(student.user.get_full_name(), html)

    def test_shared_event_and_announcement_show_the_audience_count_only(self):
        shared = make_event()
        for url in (change(shared.pk), announcement_change(self.announcement)):
            with self.subTest(url):
                html = self.client.get(url).content.decode()
                self.assertIn("۳ دانش‌آموز مخاطب", html)
                self.assertNotIn("بدون ردیف", html)

    def test_nobody_selected(self):
        empty = make_announcement({})  # targets given but empty: not whole school, nobody
        self.assertContains(self.client.get(announcement_change(empty)), "این مورد به هیچ‌کس نشان داده نمی‌شود")

    def test_add_pages_have_no_summary(self):
        for url in (reverse("admin:online_classes_onlineevent_add"), reverse("admin:online_classes_announcement_add")):
            self.assertNotContains(self.client.get(url), "چه کسانی می‌بینند")

    def test_branch_admin_sees_their_branches_only(self):
        self.branch_admin(self.branch_a)
        for url, total in ((change(self.event.pk), "۲ دانش‌آموز مخاطب"), (announcement_change(self.announcement), "۲ دانش‌آموز مخاطب")):
            with self.subTest(url):
                html = self.client.get(url).content.decode()
                self.assertIn(SCOPED, html)
                self.assertIn(total, html)
                self.assertNotIn(self.class_b1.section, html.split("چه کسانی می‌بینند", 1)[1])

    def test_query_count_is_fixed(self):
        def measure():
            counts = []
            for url in (change(self.event.pk), announcement_change(self.announcement)):
                self.client.get(url)  # the session save and caches are one-off
                with CaptureQueriesContext(connection) as captured:
                    self.client.get(url)
                counts.append(len(captured))
            return counts

        small = measure()
        for school_class in (self.class_a1, self.class_a2, self.class_b1):
            for _ in range(19):
                make_access(self.event, self.enrol(school_class), password="p")
        self.assertEqual(measure(), small)
        self.assertEqual(small, [25, 19])  # locked: event page, announcement page


class ListPageTests(AdminBase, TestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event(access_mode=PERSONAL, platform=self.platform)
        self.row = make_access(self.event, self.student_a1, url="https://example.com/secret-path", password="pw-secret")

    def names(self, response):
        self.assertEqual(response.status_code, 200)
        return {line["enrollment"].student_id for line in response.context["lines"]}

    def test_all_with_and_without(self):
        everyone = {self.student_a1.pk, self.student_a2.pk, self.student_b1.pk}
        self.assertEqual(self.names(self.client.get(students_url(self.event))), everyone)
        self.assertEqual(self.names(self.client.get(students_url(self.event, access="with"))), {self.student_a1.pk})
        self.assertEqual(self.names(self.client.get(students_url(self.event, access="without"))), everyone - {self.student_a1.pk})

    def test_search_by_name_student_code_and_national_code(self):
        User.objects.filter(pk=self.student_b1.user_id).update(national_code="0012345679", last_name="یگانه‌نام")
        for term in ("یگانه‌نام", self.student_b1.student_code, "0012345679", "۰۰۱۲۳۴۵۶۷۹"):
            with self.subTest(term):
                response = self.client.get(students_url(self.event, q=term))
                self.assertEqual(self.names(response), {self.student_b1.pk})
                self.assertNotContains(response, "0012345679</td>")  # searchable, never shown

    def test_class_filter_is_limited_to_the_audience_classes(self):
        self.assertEqual(self.names(self.client.get(students_url(self.event, **{"class": self.class_b1.pk}))), {self.student_b1.pk})
        narrow = make_event({"classes": [self.class_a1]}, access_mode=PERSONAL, platform=self.platform)
        response = self.client.get(students_url(narrow, **{"class": self.class_b1.pk}))
        self.assertEqual(self.names(response), {self.student_a1.pk}, "a class outside the audience is ignored")
        self.assertEqual([row.class_id for row in response.context["counts"].classes], [self.class_a1.pk])

    def test_pagination_keeps_the_filters(self):
        for _ in range(3):
            self.enrol(self.class_a1)
        with patch("online_classes.admin.STUDENTS_PER_PAGE", 2):
            first = self.client.get(students_url(self.event, access="without", q=""))
            self.assertEqual(len(first.context["lines"]), 2)
            self.assertIn("access=without", first.context["next_url"])
            second = self.client.get(students_url(self.event, access="without") + "&p=2")
            self.assertEqual(len(second.context["lines"]), 2)
            last = self.client.get(students_url(self.event, access="without") + "&p=99")
            self.assertEqual(last.context["page"].number, 3)

    def test_plain_get_form_and_no_secrets(self):
        response = self.client.get(students_url(self.event))
        html = response.content.decode()
        self.assertIn('<form method="get"', html)
        for secret in ("pw-secret", "secret-path", self.row.password_encrypted, self.row.url_encrypted):
            self.assertNotIn(secret, html)
        self.assertIn("لینک، رمز", html)

    def test_announcement_list_has_no_access_column(self):
        item = make_announcement()
        response = self.client.get(students_url(item))
        self.assertEqual(self.names(response), {self.student_a1.pk, self.student_a2.pk, self.student_b1.pk})
        self.assertNotContains(response, "ردیف دسترسی")

    def test_branch_admin_scope(self):
        self.branch_admin(self.branch_a)
        response = self.client.get(students_url(self.event))
        self.assertEqual(self.names(response), {self.student_a1.pk, self.student_a2.pk})
        self.assertContains(response, SCOPED)
        outside = make_event({"branches": [self.branch_b]}, access_mode=PERSONAL)
        self.assertEqual(self.client.get(students_url(outside)).status_code, 404)
        b_item = make_announcement({"branches": [self.branch_b]})
        self.assertEqual(self.client.get(students_url(b_item)).status_code, 404)

    def test_permissions(self):
        user = self.branch_admin(self.branch_a)
        user.user_permissions.remove(*Permission.objects.filter(codename__in=["view_onlineevent", "change_onlineevent"]))
        self.assertEqual(self.client.get(students_url(self.event)).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(students_url(self.event)).status_code, 302)  # to the login page

    def test_query_count_is_fixed(self):
        url = students_url(self.event)
        self.client.get(url)
        with CaptureQueriesContext(connection) as small:
            self.client.get(url)
        for school_class in (self.class_a1, self.class_a2, self.class_b1):
            for _ in range(20):
                make_access(self.event, self.enrol(school_class), password="p")
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(url)
        self.assertEqual(len(response.context["lines"]), 63)
        self.assertEqual(len(large), len(small))
        self.assertEqual(len(small), 18)  # locked


class AddRowTests(AdminBase, TestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event({"branches": [self.branch_a]}, access_mode=PERSONAL, platform=self.platform)
        self.list_url = students_url(self.event, access="without", q="", p=1)

    def add_url(self, student, event=None, next_url=None):
        params = {"event": (event or self.event).pk, "student": student.pk}
        if next_url is not False:
            params["next"] = next_url or self.list_url
        return ADD_ROW + "?" + urlencode(params)

    def post(self, url, **fields):
        return self.client.post(url, {"student": "", "url": "", "username": "", "password": "", "access_code": "", "note": "", "_save": "1", **fields})

    def test_list_page_links_missing_students_to_a_prefilled_add_form(self):
        response = self.client.get(students_url(self.event))
        line = next(line for line in response.context["lines"] if line["enrollment"].student_id == self.student_a2.pk)
        self.assertIn(f"event={self.event.pk}", line["add_url"])
        self.assertIn(f"student={self.student_a2.pk}", line["add_url"])
        page = self.client.get(line["add_url"])
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, f'<option value="{self.student_a2.pk}" selected>')
        self.assertContains(page, self.event.title)
        self.assertNotContains(page, 'name="_addanother"')

    def test_add_saves_on_this_event_and_returns_to_the_list_with_its_filters(self):
        response = self.post(self.add_url(self.student_a2), student=self.student_a2.pk, password="pw")
        self.assertRedirects(response, self.list_url, fetch_redirect_response=False)
        row = OnlineEventAccess.objects.get()
        self.assertEqual((row.event, row.student, row.updated_by), (self.event, self.student_a2, self.superuser))
        self.assertEqual(row.read_secrets()["password"], "pw")

    def test_the_student_can_not_be_swapped_outside_the_audience_or_the_branches(self):
        cases = {
            "outside the audience": (None, self.student_b1, "جزو مخاطبان این رویداد نیست"),
            "outside the branches": (self.branch_a, self.student_b1, "در شعبه‌های شما نیست"),
        }
        for name, (branch, student, message) in cases.items():
            with self.subTest(name):
                if branch:
                    self.branch_admin(branch)
                response = self.post(self.add_url(self.student_a2), student=student.pk, password="pw")
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, message)
                self.assertFalse(OnlineEventAccess.objects.exists())

    def test_a_second_row_for_the_same_student_is_refused(self):
        make_access(self.event, self.student_a2, password="old")
        response = self.post(self.add_url(self.student_a2), student=self.student_a2.pk, password="pw")
        self.assertContains(response, "ردیف ثبت شده است")
        self.assertEqual(OnlineEventAccess.objects.count(), 1)

    def test_add_is_reachable_only_for_an_event_this_admin_may_change(self):
        self.assertEqual(self.client.get(ADD_ROW).status_code, 403)
        self.assertEqual(self.client.get(ADD_ROW + "?event=abc").status_code, 404)
        shared = make_event({"branches": [self.branch_a]})
        self.assertEqual(self.client.get(self.add_url(self.student_a1, event=shared)).status_code, 404)

        self.branch_admin(self.branch_a)
        whole = make_event(access_mode=PERSONAL, platform=self.platform)  # visible to them, not theirs to change
        self.assertEqual(self.client.get(self.add_url(self.student_a1, event=whole)).status_code, 403)
        outside = make_event({"branches": [self.branch_b]}, access_mode=PERSONAL, platform=self.platform)
        self.assertEqual(self.client.get(self.add_url(self.student_b1, event=outside)).status_code, 404)
        self.assertEqual(self.client.get(self.add_url(self.student_a1)).status_code, 200)

        # The rows list itself has no «add» button.
        self.assertNotContains(self.client.get(reverse("admin:online_classes_onlineeventaccess_changelist")), ADD_ROW)

    def test_add_link_only_for_who_may_add(self):
        whole = make_event(access_mode=PERSONAL, platform=self.platform)
        user = self.branch_admin(self.branch_a)
        lines = self.client.get(students_url(whole)).context["lines"]
        self.assertFalse(any("add_url" in line for line in lines), "a whole-school event isn't theirs to change")
        lines = self.client.get(students_url(self.event)).context["lines"]
        self.assertTrue(all("add_url" in line for line in lines))
        user.user_permissions.remove(Permission.objects.get(codename="add_onlineeventaccess"))
        lines = self.client.get(students_url(self.event)).context["lines"]
        self.assertFalse(any("add_url" in line for line in lines))

    def test_next_is_never_an_open_redirect(self):
        other = make_event({"branches": [self.branch_a]}, access_mode=PERSONAL, platform=self.platform)
        for bad in (
            "https://evil.example.com/admin/online_classes/onlineevent/1/students/",
            "//evil.example.com" + students_url(self.event),
            "http://testserver" + students_url(self.event),
            "/\\evil.example.com",
            students_url(other),
            reverse("admin:online_classes_onlineevent_change", args=[self.event.pk]),
            "javascript:alert(1)",
        ):
            with self.subTest(bad):
                OnlineEventAccess.objects.all().delete()
                response = self.post(self.add_url(self.student_a2, next_url=bad), student=self.student_a2.pk, password="pw")
                self.assertEqual(response.status_code, 302)
                self.assertNotIn("evil", response["Location"])
                self.assertEqual(response["Location"], reverse("admin:online_classes_onlineeventaccess_changelist"))

    def test_without_next_the_admin_default_applies(self):
        response = self.post(self.add_url(self.student_a2, next_url=False), student=self.student_a2.pk, password="pw")
        self.assertRedirects(response, reverse("admin:online_classes_onlineeventaccess_changelist"), fetch_redirect_response=False)

    def test_saving_a_row_opened_from_the_list_returns_there(self):
        row = make_access(self.event, self.student_a1, password="old")
        response = self.client.get(students_url(self.event, access="with", p=1))
        line = next(line for line in response.context["lines"] if line["row"])
        self.assertIn("next=", line["row_url"])
        response = self.client.post(line["row_url"], {"username": "u", "url": "", "password": "", "access_code": "", "note": "", "_save": "1"})
        self.assertRedirects(response, students_url(self.event, access="with", p=1), fetch_redirect_response=False)
        row.refresh_from_db()
        self.assertEqual(row.username, "u")

    def test_save_and_continue_stays_on_the_row(self):
        row = make_access(self.event, self.student_a1, password="old")
        url = reverse("admin:online_classes_onlineeventaccess_change", args=[row.pk]) + "?" + urlencode({"next": self.list_url})
        response = self.client.post(url, {"username": "u", "url": "", "password": "", "access_code": "", "note": "", "_continue": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response["Location"], self.list_url)


class InlineTests(AdminBase, TestCase):
    def test_the_event_page_offers_only_blank_rows(self):
        event = make_event(access_mode=PERSONAL, platform=self.platform)
        for student in (self.student_a1, self.student_a2):
            make_access(event, student, password="x", username=f"user-{student.pk}")
        html = self.client.get(change(event.pk)).content.decode()
        self.assertIn('name="access_rows-INITIAL_FORMS" value="0"', html)
        self.assertNotIn(f"user-{self.student_a1.pk}", html)


class ImportPreviewTests(AdminBase, TestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event({"classes": [self.class_a1, self.class_a2]}, access_mode=PERSONAL, platform=self.platform)
        self.url = reverse("admin:online_classes_onlineevent_access_import", args=[self.event.pk])

    def test_only_flagged_rows_are_listed_and_valid_ones_counted_per_class(self):
        make_access(self.event, self.student_a2, password="old")
        rows = [
            cells(self.student_a1, password="p1", username="valid-new"),
            cells(self.student_a2, password="p2", username="valid-update"),
            cells(self.student_b1, password="p3", username="warned"),  # outside the audience
            cells(code="nope", password="p4", username="broken"),
        ]
        response = self.client.post(self.url, {"file": xlsx(rows)})
        html = response.content.decode()
        self.assertNotIn("valid-new", html)
        self.assertNotIn("valid-update", html)
        self.assertIn("warned", html)
        self.assertIn("broken", html)
        groups = {group["label"]: (group["new"], group["update"]) for group in response.context["plan"].by_class}
        a1 = f"{self.class_a1.grade.name} {self.class_a1.section} · {self.branch_a.name}"
        a2 = f"{self.class_a2.grade.name} {self.class_a2.section} · {self.branch_a.name}"
        b1 = f"{self.class_b1.grade.name} {self.class_b1.section} · {self.branch_b.name}"
        self.assertEqual(groups, {a1: (1, 0), a2: (0, 1), b1: (1, 0)})
        self.assertIn("<details", html)

    def test_preview_query_count_does_not_grow_with_rows(self):
        def preview(students):
            rows = [cells(student, password="p") for student in students]
            with CaptureQueriesContext(connection) as captured:
                self.client.post(self.url, {"file": xlsx(rows)})
            return len(captured)

        self.client.post(self.url, {"file": xlsx([cells(self.student_a1, password="p")])})
        few = preview([self.student_a1])
        many = preview([self.student_a1] + [self.enrol(self.class_a1) for _ in range(30)])
        self.assertEqual(many, few)
