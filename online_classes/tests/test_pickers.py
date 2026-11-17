"""
The audience student pickers: autocomplete, never one checkbox per student.

Until this fix, ``AudienceAdminMixin.formfield_overrides`` gave every
ManyToManyField a ``CheckboxSelectMultiple``, and Django only applies
autocomplete when no widget is set, so «دانش‌آموزان» and «دانش‌آموزان مستثنا»
rendered every student profile (all years, all branches) as a checkbox, twice.
"""

import re

import jdatetime
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from accounts.models import User
from core.testing import make_academic_year, make_enrollment, make_school_class, make_student
from online_classes.models import Announcement, OnlineEvent
from online_classes.testing import make_announcement, make_event
from student.models.student_enrollment import StudentEnrollment

from .test_admin import AdminBase, change

PICKER = reverse("admin:online_classes_student_autocomplete")


def picker(client, term="", model_name="onlineevent", field_name="students"):
    return client.get(PICKER, {"app_label": "online_classes", "model_name": model_name, "field_name": field_name, "term": term})


class PageTests(AdminBase, TestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event({"classes": [self.class_a1], "students": [self.student_b1]})
        self.announcement = make_announcement({"classes": [self.class_a1], "excluded_students": [self.student_a1]})
        self.pages = (
            change(self.event.pk),
            reverse("admin:online_classes_announcement_change", args=[self.announcement.pk]),
            reverse("admin:online_classes_onlineevent_add"),
            reverse("admin:online_classes_announcement_add"),
        )

    def test_no_checkbox_per_student_and_the_pickers_search_on_the_server(self):
        for url in self.pages:
            with self.subTest(url):
                html = self.client.get(url).content.decode()
                for name in ("students", "excluded_students"):
                    self.assertNotIn(f'type="checkbox" name="{name}"', html)
                    self.assertIn(f'name="{name}"', html)
                self.assertIn(f'data-ajax--url="{PICKER}"', html)
                # Branches, grades and classes stay checkboxes.
                for name in ("branches", "grades", "classes"):
                    self.assertIn(f'type="checkbox" name="{name}"', html)

    def test_selected_students_are_rendered_as_options(self):
        html = self.client.get(change(self.event.pk)).content.decode()
        select = re.search(r'<select name="students".*?</select>', html, re.S).group(0)
        self.assertEqual(re.findall(r'<option value="(\d+)"', select), [str(self.student_b1.pk)])

    def _measure(self):
        for url in self.pages:  # once first: the session save and the content-type cache are one-off
            self.client.get(url)
        sizes, counts = [], []
        for url in self.pages:
            with CaptureQueriesContext(connection) as captured:
                response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            sizes.append(len(response.content))
            counts.append(len(captured))
        return sizes, counts

    def test_query_count_and_size_do_not_grow_with_the_number_of_students(self):
        sizes, counts = self._measure()
        for school_class in (self.class_a1, self.class_a2, self.class_b1):
            for _ in range(15):
                self.enrol(school_class)
        more_sizes, more_counts = self._measure()
        self.assertEqual(more_counts, counts)
        for before, after in zip(sizes, more_sizes):
            # Only digits of a count may change; 45 more checkboxes would be several kilobytes.
            self.assertLess(abs(after - before), 100)


class AutocompleteTests(AdminBase, TestCase):
    def setUp(self):
        super().setUp()
        old_year = make_academic_year(start_date=jdatetime.date(1404, 7, 1), is_current=False)
        self.former = make_student()
        make_enrollment(self.former, make_school_class(self.branch_a, self.grade_1, old_year))
        self.withdrawn = make_student()
        make_enrollment(self.withdrawn, self.class_a1, status=StudentEnrollment.EnrollmentStatus.WITHDRAWN)

    def ids(self, response):
        self.assertEqual(response.status_code, 200)
        return {int(item["id"]) for item in response.json()["results"]}

    def test_superuser_finds_every_current_student_only(self):
        found = self.ids(picker(self.client))
        self.assertEqual(found, {self.student_a1.pk, self.student_a2.pk, self.student_b1.pk})

    def test_branch_admin_finds_their_branches_only(self):
        self.branch_admin(self.branch_a)
        for model_name, field_name in (
            ("onlineevent", "students"), ("onlineevent", "excluded_students"),
            ("announcement", "students"), ("announcement", "excluded_students"), ("onlineeventaccess", "student"),
        ):
            with self.subTest(model_name=model_name, field_name=field_name):
                found = self.ids(picker(self.client, model_name=model_name, field_name=field_name))
                self.assertEqual(found, {self.student_a1.pk, self.student_a2.pk})

    def test_search_by_name_student_code_and_national_code(self):
        user = self.student_b1.user
        User.objects.filter(pk=user.pk).update(national_code="0012345679", last_name="یگانه‌نام")
        for term in ("یگانه‌نام", self.student_b1.student_code, "0012345679"):
            with self.subTest(term):
                self.assertEqual(self.ids(picker(self.client, term)), {self.student_b1.pk})

    def test_label_has_name_code_and_class(self):
        results = picker(self.client, self.student_a1.student_code).json()["results"]
        self.assertEqual(len(results), 1)
        text = results[0]["text"]
        for part in (self.student_a1.user.get_full_name(), self.student_a1.student_code, self.class_a1.section, self.branch_a.name):
            self.assertIn(part, text)

    def test_only_this_apps_student_fields_may_ask(self):
        for params in (
            {"app_label": "online_classes", "model_name": "announcement", "field_name": "event"},
            {"app_label": "student", "model_name": "studentenrollment", "field_name": "student"},
            {"app_label": "online_classes", "model_name": "onlineevent"},
        ):
            with self.subTest(params):
                self.assertEqual(self.client.get(PICKER, params).status_code, 403)

    def test_needs_permission_to_view_students(self):
        user = self.branch_admin(self.branch_a)
        # Django treats the change permission as view too.
        user.user_permissions.remove(*user.user_permissions.filter(codename__in=["view_studentprofile", "change_studentprofile"]))
        self.assertEqual(picker(self.client).status_code, 403)

    def test_query_count_does_not_grow(self):
        picker(self.client)  # warm up: the session save is one-off
        with CaptureQueriesContext(connection) as before:
            picker(self.client)
        for _ in range(15):
            self.enrol(self.class_a1)
        with CaptureQueriesContext(connection) as after:
            picker(self.client)
        self.assertEqual(len(after), len(before))


class ForgedIdTests(AdminBase, TestCase):
    def test_branch_admin_can_not_post_a_student_of_another_branch(self):
        self.branch_admin(self.branch_a)
        for field in ("students", "excluded_students"):
            with self.subTest(field):
                data = self.event_data(title=f"جعلی {field}", branches=[self.branch_a.pk], **{field: [self.student_b1.pk]})
                response = self.client.post(reverse("admin:online_classes_onlineevent_add"), data)
                self.assertEqual(response.status_code, 200)
                self.assertFalse(OnlineEvent.objects.filter(title=f"جعلی {field}").exists())

    def test_branch_admin_announcement_refuses_it_too(self):
        self.branch_admin(self.branch_a)
        response = self.client.post(reverse("admin:online_classes_announcement_add"), {
            "title": "جعلی", "level": "info", "visible_from": "1405/08/12 10:00", "visible_until": "1405/08/13 10:00",
            "priority": 0, "is_active": "on", "is_dismissible": "on", "branches": [self.branch_a.pk],
            "students": [self.student_b1.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Announcement.objects.filter(title="جعلی").exists())

    def test_a_student_without_a_current_enrolment_can_not_be_added(self):
        nobody = make_student()
        data = self.event_data(title="بی‌کلاس", is_whole_school=None, students=[nobody.pk])
        response = self.client.post(reverse("admin:online_classes_onlineevent_add"), data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(OnlineEvent.objects.filter(title="بی‌کلاس").exists())

    def test_an_already_selected_student_who_left_stays_valid(self):
        event = make_event({"classes": [self.class_a1], "students": [self.student_b1]})
        StudentEnrollment.objects.filter(student=self.student_b1).update(status=StudentEnrollment.EnrollmentStatus.TRANSFERRED)
        data = self.event_data(
            classes=[self.class_a1.pk], students=[self.student_b1.pk], title="هنوز",
            start_at=self.event_data()["start_at"], end_at=self.event_data()["end_at"],
        )
        response = self.client.post(change(event.pk), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(OnlineEvent.objects.get(pk=event.pk).students.all()), [self.student_b1])
