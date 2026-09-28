"""
The admin timetable grid: scheduling.timetable (load / busy hint / save)
and its SchoolClassAdmin views.
"""

import json
from datetime import time

import jdatetime
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from core.testing import (
    grant_all_model_permissions,
    make_academic_year,
    make_assignment,
    make_branch,
    make_grade,
    make_school_class,
    make_staff,
    make_subject,
    make_superuser,
    make_teacher_profile,
)
from school.models import ClassSubject
from staff.models import TeacherAssignment
from teaching.models import SchoolSession

from . import timetable
from .models.bell import Bell
from .models.class_schedule import ClassSchedule

WEEK_ONE = ClassSchedule.WeekTypeChoices.WEEK_ONE
WEEK_TWO = ClassSchedule.WeekTypeChoices.WEEK_TWO
EVERY_WEEK = ClassSchedule.WeekTypeChoices.BOTH
SAT = ClassSchedule.DayChoices.SATURDAY
SUN = ClassSchedule.DayChoices.SUNDAY

YEAR_START = jdatetime.date(1405, 7, 1)
YEAR_END = jdatetime.date(1406, 3, 31)

FAST_HASHER = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])


class GridFixture:

    def make_fixture(self):
        self.branch = make_branch(name="شعبه-الف")
        self.other_branch = make_branch(name="شعبه-ب")
        self.grade = make_grade()
        self.year = make_academic_year(start_date=YEAR_START, end_date=YEAR_END)
        self.school_class = make_school_class(self.branch, self.grade, self.year)
        self.neighbour = make_school_class(self.branch, self.grade, self.year)
        self.far_class = make_school_class(self.other_branch, self.grade, self.year)

        self.teacher = make_teacher_profile()
        self.teacher.staff.user.first_name, self.teacher.staff.user.last_name = "علی", "رضایی"
        self.teacher.staff.user.save()
        self.t = make_assignment(self.teacher, self.branch, self.year)
        self.t_far = make_assignment(self.teacher, self.other_branch, self.year)
        self.u = make_assignment(make_teacher_profile(), self.branch, self.year)

        self.math = make_subject()
        self.science = make_subject()

        self.bell_1 = Bell.objects.create(title="اول", order=1, start_time=time(8), end_time=time(8, 45))
        self.bell_2 = Bell.objects.create(title="دوم", order=2, start_time=time(9), end_time=time(9, 45))
        self.bell_off = Bell.objects.create(
            title="خاموش", order=9, start_time=time(13), end_time=time(13, 45), is_active=False
        )

    @staticmethod
    def entry(day, bell, subject, assignment, week_type=EVERY_WEEK):
        return {
            "day": day,
            "bell": bell.pk,
            "week_type": week_type,
            "subject": subject.pk if subject else None,
            "teacher": assignment.pk if assignment else None,
        }

    def save(self, *entries, **kwargs):
        return timetable.save_grid(self.school_class, list(entries), **kwargs)

    def rows(self, school_class=None):
        return {
            (r.day_of_week, r.bell_id, r.week_type): (r.class_subject.subject_id, r.class_subject.teacher_assignment_id)
            for r in ClassSchedule.objects.filter(
                class_subject__school_class=school_class or self.school_class
            ).select_related("class_subject")
        }


class SaveGridTests(GridFixture, TestCase):

    def setUp(self):
        self.make_fixture()

    def test_creates_class_subjects_implicitly(self):
        result = self.save(
            self.entry(SAT, self.bell_1, self.math, self.t),
            self.entry(SUN, self.bell_2, self.math, self.t),
            self.entry(SAT, self.bell_2, self.science, self.u, WEEK_ONE),
        )

        self.assertTrue(result.ok, result.errors)
        self.assertEqual((result.created, result.updated, result.deleted), (3, 0, 0))
        self.assertEqual(self.rows(), {
            (SAT, self.bell_1.pk, EVERY_WEEK): (self.math.pk, self.t.pk),
            (SUN, self.bell_2.pk, EVERY_WEEK): (self.math.pk, self.t.pk),
            (SAT, self.bell_2.pk, WEEK_ONE): (self.science.pk, self.u.pk),
        })
        # One ClassSubject per (class, subject, assignment), spanning the year.
        self.assertEqual(ClassSubject.objects.filter(school_class=self.school_class).count(), 2)
        cs = ClassSubject.objects.get(subject=self.math)
        self.assertEqual((cs.start_date, cs.end_date, cs.is_active), (YEAR_START, YEAR_END, True))

    def test_reuses_an_existing_class_subject(self):
        existing = ClassSubject.objects.create(
            school_class=self.school_class, subject=self.math, teacher_assignment=self.t,
            start_date=jdatetime.date(1405, 8, 1), end_date=YEAR_END,
        )
        self.assertTrue(self.save(self.entry(SAT, self.bell_1, self.math, self.t)).ok)
        self.assertEqual(ClassSchedule.objects.get().class_subject, existing)

    def test_saving_the_same_grid_writes_nothing(self):
        grid = [self.entry(SAT, self.bell_1, self.math, self.t), self.entry(SUN, self.bell_1, self.science, self.u)]
        self.save(*grid)
        pks = set(ClassSchedule.objects.values_list("pk", flat=True))

        result = self.save(*grid)

        self.assertEqual((result.created, result.updated, result.deleted), (0, 0, 0))
        self.assertEqual(set(ClassSchedule.objects.values_list("pk", flat=True)), pks)

    def test_changing_a_teacher_updates_the_row_in_place(self):
        self.save(self.entry(SAT, self.bell_1, self.math, self.t))
        row = ClassSchedule.objects.get()

        result = self.save(self.entry(SAT, self.bell_1, self.math, self.u))

        self.assertEqual((result.created, result.updated, result.deleted), (0, 1, 0))
        row.refresh_from_db()
        self.assertEqual(row.class_subject.teacher_assignment, self.u)

    def test_every_week_to_alternating_keeps_the_row_for_week_one(self):
        self.save(self.entry(SAT, self.bell_1, self.math, self.t))
        row = ClassSchedule.objects.get()

        result = self.save(
            self.entry(SAT, self.bell_1, self.math, self.t, WEEK_ONE),
            self.entry(SAT, self.bell_1, self.science, self.u, WEEK_TWO),
        )

        self.assertTrue(result.ok, result.errors)
        self.assertEqual((result.created, result.updated, result.deleted), (1, 1, 0))
        row.refresh_from_db()
        self.assertEqual(row.week_type, WEEK_ONE)

    def test_swapping_the_two_weeks(self):
        grid = [
            self.entry(SAT, self.bell_1, self.math, self.t, WEEK_ONE),
            self.entry(SAT, self.bell_1, self.science, self.u, WEEK_TWO),
        ]
        self.save(*grid)

        result = self.save(
            self.entry(SAT, self.bell_1, self.math, self.t, WEEK_TWO),
            self.entry(SAT, self.bell_1, self.science, self.u, WEEK_ONE),
        )

        self.assertTrue(result.ok, result.errors)
        self.assertEqual(ClassSchedule.objects.count(), 2)
        self.assertEqual(self.rows()[(SAT, self.bell_1.pk, WEEK_TWO)], (self.math.pk, self.t.pk))

    def test_one_half_of_an_alternating_cell_may_stay_empty(self):
        result = self.save(
            self.entry(SAT, self.bell_1, self.math, self.t, WEEK_TWO),
            self.entry(SAT, self.bell_1, None, None, WEEK_ONE),
        )
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(list(self.rows()), [(SAT, self.bell_1.pk, WEEK_TWO)])

    def test_emptied_cells_are_deleted(self):
        self.save(self.entry(SAT, self.bell_1, self.math, self.t), self.entry(SUN, self.bell_1, self.math, self.t))
        result = self.save(self.entry(SAT, self.bell_1, self.math, self.t))
        self.assertEqual(result.deleted, 1)
        self.assertEqual(list(self.rows()), [(SAT, self.bell_1.pk, EVERY_WEEK)])

    def test_unused_class_subject_without_sessions_is_deleted(self):
        self.save(self.entry(SAT, self.bell_1, self.math, self.t))
        old = ClassSubject.objects.get()

        result = self.save(self.entry(SAT, self.bell_1, self.math, self.u))

        self.assertEqual(result.deleted_class_subjects, [old.pk])
        self.assertFalse(ClassSubject.objects.filter(pk=old.pk).exists())

    def test_unused_class_subject_with_sessions_is_deactivated(self):
        self.save(self.entry(SAT, self.bell_1, self.math, self.t))
        old = ClassSubject.objects.get()
        SchoolSession.objects.create(class_subject=old, date=YEAR_START)

        result = self.save()

        self.assertEqual(result.deactivated_class_subjects, [old.pk])
        old.refresh_from_db()
        self.assertFalse(old.is_active)
        self.assertEqual(old.sessions.count(), 1)

    def test_unused_class_subject_is_only_deactivated_without_delete_permission(self):
        self.save(self.entry(SAT, self.bell_1, self.math, self.t))
        result = self.save(can_delete_class_subjects=False)
        self.assertEqual(len(result.deactivated_class_subjects), 1)
        self.assertEqual(ClassSubject.objects.filter(is_active=False).count(), 1)

    def test_reusing_an_inactive_class_subject_reactivates_it_and_drops_its_old_rows(self):
        cs = ClassSubject.objects.create(
            school_class=self.school_class, subject=self.math, teacher_assignment=self.t,
            start_date=YEAR_START, end_date=YEAR_END, is_active=False,
        )
        kept = ClassSchedule.objects.create(class_subject=cs, day_of_week=SAT, bell=self.bell_1)
        ClassSchedule.objects.create(class_subject=cs, day_of_week=SUN, bell=self.bell_2)

        result = self.save(self.entry(SAT, self.bell_1, self.math, self.t))

        self.assertTrue(result.ok, result.errors)
        cs.refresh_from_db()
        self.assertTrue(cs.is_active)
        self.assertEqual(list(ClassSchedule.objects.values_list("pk", flat=True)), [kept.pk])

    def test_rows_on_inactive_bells_are_left_alone(self):
        cs = ClassSubject.objects.create(
            school_class=self.school_class, subject=self.math, teacher_assignment=self.t,
            start_date=YEAR_START, end_date=YEAR_END,
        )
        hidden = ClassSchedule.objects.create(class_subject=cs, day_of_week=SAT, bell=self.bell_off)

        self.assertTrue(self.save().ok)

        self.assertTrue(ClassSchedule.objects.filter(pk=hidden.pk).exists())
        self.assertTrue(ClassSubject.objects.get(pk=cs.pk).is_active)

    def test_other_classes_are_untouched(self):
        timetable.save_grid(self.neighbour, [self.entry(SAT, self.bell_2, self.math, self.u)])
        self.save(self.entry(SAT, self.bell_1, self.math, self.t))
        self.assertEqual(len(self.rows(self.neighbour)), 1)


class SaveGridValidationTests(GridFixture, TestCase):

    def setUp(self):
        self.make_fixture()
        # The teacher already teaches the far class (other branch) on Saturday, bell 1.
        timetable.save_grid(self.far_class, [self.entry(SAT, self.bell_1, self.math, self.t_far)])

    def test_teacher_busy_in_another_branch_rejects_everything(self):
        result = self.save(
            self.entry(SUN, self.bell_2, self.science, self.u),        # fine on its own
            self.entry(SAT, self.bell_1, self.math, self.t),            # the teacher is busy
        )

        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 1)
        error = result.errors[0]
        self.assertEqual((error["day"], error["bell"], error["week_type"]), (SAT, self.bell_1.pk, EVERY_WEEK))
        self.assertIn("این معلم در همین زنگ در کلاس", error["message"])
        self.assertIn(self.far_class.section, error["message"])
        self.assertIn("(شعبه-ب)", error["message"])
        # All or nothing: not even the valid entry, nor a ClassSubject.
        self.assertEqual(self.rows(), {})
        self.assertFalse(ClassSubject.objects.filter(school_class=self.school_class).exists())

    def test_week_one_next_to_the_far_class_every_week_is_rejected(self):
        result = self.save(self.entry(SAT, self.bell_1, self.math, self.t, WEEK_ONE))
        self.assertFalse(result.ok)
        self.assertEqual(result.errors[0]["week_type"], WEEK_ONE)

    def test_week_one_and_week_two_across_classes(self):
        timetable.save_grid(self.far_class, [self.entry(SAT, self.bell_2, self.math, self.t_far, WEEK_ONE)])
        self.assertTrue(self.save(self.entry(SAT, self.bell_2, self.math, self.t, WEEK_TWO)).ok)

    def test_moving_the_teacher_away_in_the_same_save_frees_the_cell(self):
        # Within one class the grid's final state is what counts.
        self.save(self.entry(SUN, self.bell_1, self.math, self.u), self.entry(SUN, self.bell_2, self.science, self.t))
        result = self.save(self.entry(SUN, self.bell_1, self.science, self.t), self.entry(SUN, self.bell_2, self.math, self.u))
        self.assertTrue(result.ok, result.errors)

    def test_incomplete_entry(self):
        result = self.save(self.entry(SUN, self.bell_1, self.math, None))
        self.assertEqual(result.errors[0]["message"], timetable.MSG_INCOMPLETE)

    def test_teacher_of_another_branch_cannot_be_picked(self):
        result = self.save(self.entry(SUN, self.bell_1, self.math, self.t_far))
        self.assertEqual(result.errors[0]["message"], timetable.MSG_BAD_TEACHER)

    def test_inactive_assignment_cannot_be_newly_picked(self):
        self.u.status = TeacherAssignment.AssignmentStatus.TERMINATED
        self.u.save()
        result = self.save(self.entry(SUN, self.bell_1, self.math, self.u))
        self.assertEqual(result.errors[0]["message"], timetable.MSG_BAD_TEACHER)

    def test_inactive_bell_is_not_a_cell(self):
        result = self.save(self.entry(SUN, self.bell_off, self.math, self.u))
        self.assertEqual(result.errors[0]["message"], timetable.MSG_BAD_CELL)

    def test_every_week_and_a_half_in_one_cell(self):
        result = self.save(
            self.entry(SUN, self.bell_1, self.math, self.u),
            self.entry(SUN, self.bell_1, self.science, self.u, WEEK_TWO),
        )
        self.assertIn(timetable.MSG_MIXED_WEEKS, [e["message"] for e in result.errors])

    def test_malformed_payload(self):
        self.assertFalse(timetable.save_grid(self.school_class, "nope").ok)
        self.assertFalse(timetable.save_grid(self.school_class, [{"day": "x"}]).ok)


class LoadGridTests(GridFixture, TestCase):

    def setUp(self):
        self.make_fixture()

    @override_settings(SCHOOL_WORKING_DAYS=[0, 1, 2, 3, 4])
    def test_shape_and_existing_entries(self):
        timetable.save_grid(self.school_class, [
            self.entry(SAT, self.bell_1, self.math, self.t, WEEK_TWO),
            self.entry(SUN, self.bell_2, self.math, self.t),
        ])

        grid = timetable.load_grid(self.school_class)

        self.assertEqual([d["value"] for d in grid["days"]], [0, 1, 2, 3, 4])
        self.assertEqual([b["id"] for b in grid["bells"]], [self.bell_1.pk, self.bell_2.pk])
        self.assertEqual(grid["bells"][0]["time"], "۰۸:۰۰ – ۰۸:۴۵")
        self.assertEqual(
            {(e["day"], e["bell"], e["week_type"]) for e in grid["entries"]},
            {(SAT, self.bell_1.pk, WEEK_TWO), (SUN, self.bell_2.pk, EVERY_WEEK)},
        )
        self.assertEqual(grid["recent_pairs"], [{"subject": self.math.pk, "teacher": self.t.pk}])

    def test_teacher_options_are_the_class_branch_and_year(self):
        ids = {t["id"] for t in timetable.load_grid(self.school_class)["teachers"]}
        self.assertEqual(ids, {self.t.pk, self.u.pk})
        self.assertIn("علی رضایی", [t["name"] for t in timetable.load_grid(self.school_class)["teachers"]])

    def test_busy_hint_lists_other_classes_of_the_teacher_in_any_branch(self):
        timetable.save_grid(self.far_class, [self.entry(SAT, self.bell_1, self.math, self.t_far, WEEK_ONE)])
        timetable.save_grid(self.school_class, [self.entry(SUN, self.bell_1, self.math, self.t)])

        busy = timetable.teacher_busy(self.school_class, self.t)

        self.assertEqual(len(busy), 1)
        self.assertEqual((busy[0]["day"], busy[0]["bell"], busy[0]["week_type"]), (SAT, self.bell_1.pk, WEEK_ONE))
        self.assertIn("(هفته اول)", busy[0]["message"])


@FAST_HASHER
class TimetableAdminViewTests(GridFixture, TestCase):

    def setUp(self):
        self.make_fixture()
        self.url = reverse("admin:school_schoolclass_timetable", args=[self.school_class.pk])
        self.busy_url = reverse("admin:school_schoolclass_timetable_busy", args=[self.school_class.pk])

    def post(self, entries):
        return self.client.post(self.url, json.dumps({"entries": entries}), content_type="application/json")

    def staff_user(self, branch, *perms):
        staff = make_staff(is_staff=True)
        from staff.models import BranchAccess

        BranchAccess.objects.create(staff=staff, branch=branch)
        staff.user.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label__in=["school", "scheduling"],
                codename__in=perms,
            )
        )
        return staff.user

    def test_change_page_and_list_link_to_the_grid(self):
        self.client.force_login(make_superuser())
        change = self.client.get(reverse("admin:school_schoolclass_change", args=[self.school_class.pk]))
        self.assertContains(change, f'href="{self.url}"')
        listing = self.client.get(reverse("admin:school_schoolclass_changelist"))
        self.assertContains(listing, f'href="{self.url}"')

    def test_page_renders_the_grid_data(self):
        timetable.save_grid(self.school_class, [self.entry(SAT, self.bell_1, self.math, self.t)])
        self.client.force_login(make_superuser())

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="tt-data"')
        self.assertContains(response, "school/admin/timetable.js")
        grid = response.context["grid"]
        self.assertTrue(grid["can_edit"])
        self.assertEqual(len(grid["entries"]), 1)

    def test_save_through_the_view(self):
        self.client.force_login(make_superuser())
        response = self.post([self.entry(SAT, self.bell_1, self.math, self.t)])
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["counts"], {"created": 1, "updated": 0, "deleted": 0})
        self.assertEqual(len(body["grid"]["entries"]), 1)

    def test_errors_come_back_per_cell(self):
        timetable.save_grid(self.neighbour, [self.entry(SAT, self.bell_1, self.science, self.t)])
        self.client.force_login(make_superuser())

        response = self.post([self.entry(SAT, self.bell_1, self.math, self.t)])

        self.assertEqual(response.status_code, 400)
        error = response.json()["errors"][0]
        self.assertEqual((error["day"], error["bell"]), (SAT, self.bell_1.pk))
        self.assertIn(self.neighbour.section, error["message"])

    def test_malformed_body(self):
        self.client.force_login(make_superuser())
        response = self.client.post(self.url, "not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["general"])

    def test_busy_endpoint(self):
        timetable.save_grid(self.far_class, [self.entry(SAT, self.bell_1, self.math, self.t_far)])
        self.client.force_login(make_superuser())

        response = self.client.get(self.busy_url, {"teacher": self.t.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["busy"]), 1)
        # Only assignments the grid offers for this class.
        self.assertEqual(self.client.get(self.busy_url, {"teacher": self.t_far.pk}).status_code, 404)
        self.assertEqual(self.client.get(self.busy_url, {"teacher": "x"}).status_code, 404)

    def test_view_only_user_sees_but_cannot_save(self):
        self.client.force_login(self.staff_user(self.branch, "view_schoolclass", "view_classschedule"))

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["grid"]["can_edit"])
        self.assertNotContains(response, "data-tt-save")

        self.assertEqual(self.post([self.entry(SAT, self.bell_1, self.math, self.t)]).status_code, 403)
        self.assertFalse(ClassSchedule.objects.exists())

    def test_editor_can_save(self):
        self.client.force_login(self.staff_user(
            self.branch, "view_schoolclass", "change_schoolclass",
            "add_classschedule", "change_classschedule", "delete_classschedule",
            "add_classsubject", "change_classsubject",
        ))
        response = self.post([self.entry(SAT, self.bell_1, self.math, self.t)])
        self.assertEqual(response.status_code, 200, response.content)

    def test_user_without_schedule_permissions_is_forbidden(self):
        self.client.force_login(self.staff_user(self.branch, "view_schoolclass", "change_schoolclass"))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.busy_url, {"teacher": self.t.pk}).status_code, 403)

    def test_class_of_a_branch_out_of_reach_is_not_found(self):
        user = self.staff_user(self.other_branch, "view_schoolclass", "view_classschedule")
        grant_all_model_permissions(user)
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.post([]).status_code, 404)

    def test_anonymous_goes_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])
