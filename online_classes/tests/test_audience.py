from django.test import TestCase

from online_classes import audience
from online_classes.models import Announcement, OnlineEvent
from online_classes.testing import SchoolMixin, make_announcement, make_event
from student.models.student_enrollment import StudentEnrollment
from student.selectors import current_enrollment


class AudienceMatrixTests(SchoolMixin, TestCase):
    """Each row of the semantics table (D3), in both directions, on both kinds of item."""

    def setUp(self):
        self.make_school()
        self.students = [self.student_a1, self.student_a2, self.student_b1]

    def _check(self, make, model, expected_builder):
        expected, kwargs = expected_builder()
        item = make(kwargs.get("targets"), is_whole_school=kwargs.get("whole", False))

        # one item -> its students
        reached = set(audience.reached_enrollments(item).values_list("student_id", flat=True))
        self.assertEqual(reached, {s.pk for s in expected})

        # one student -> their items
        for student in self.students:
            seen = audience.visible_to(model.objects.filter(pk=item.pk), current_enrollment(student)).exists()
            self.assertEqual(seen, student in expected, student)

    CASES = {
        "nothing selected is nobody": lambda self: ([], {}),
        "whole school": lambda self: (self.students, {"whole": True}),
        "whole school minus an excluded student": lambda self: (
            [self.student_a1, self.student_a2],
            {"whole": True, "targets": {"excluded_students": [self.student_b1]}},
        ),
        "one branch": lambda self: (
            [self.student_a1, self.student_a2], {"targets": {"branches": [self.branch_a]}},
        ),
        "one grade in every branch": lambda self: (
            [self.student_a1, self.student_b1], {"targets": {"grades": [self.grade_1]}},
        ),
        "branch and grade narrow each other": lambda self: (
            [self.student_a1], {"targets": {"branches": [self.branch_a], "grades": [self.grade_1]}},
        ),
        "branch + grade, plus a class of another branch": lambda self: (
            [self.student_a1, self.student_b1],
            {"targets": {"branches": [self.branch_a], "grades": [self.grade_1], "classes": [self.class_b1]}},
        ),
        "branch + grade, plus a listed student": lambda self: (
            [self.student_a1, self.student_a2],
            {"targets": {"branches": [self.branch_a], "grades": [self.grade_1], "students": [self.student_a2]}},
        ),
        "a class alone": lambda self: ([self.student_a2], {"targets": {"classes": [self.class_a2]}}),
        "a student alone": lambda self: ([self.student_b1], {"targets": {"students": [self.student_b1]}}),
        "exclusion beats a listed student": lambda self: (
            [], {"targets": {"students": [self.student_b1], "excluded_students": [self.student_b1]}},
        ),
        "exclusion beats a class": lambda self: (
            [], {"targets": {"classes": [self.class_a1], "excluded_students": [self.student_a1]}},
        ),
        "excluded alone is nobody": lambda self: ([], {"targets": {"excluded_students": [self.student_a1]}}),
    }

    def test_events(self):
        for name, builder in self.CASES.items():
            with self.subTest(name):
                self._check(make_event, OnlineEvent, lambda b=builder: b(self))

    def test_announcements(self):
        for name, builder in self.CASES.items():
            with self.subTest(name):
                self._check(make_announcement, Announcement, lambda b=builder: b(self))


class AudienceFromCurrentEnrolmentTests(SchoolMixin, TestCase):
    def setUp(self):
        self.make_school()

    def _sees(self, student, item):
        return audience.visible_to(type(item).objects.filter(pk=item.pk), current_enrollment(student)).exists()

    def test_changing_class_changes_what_the_student_sees_at_once(self):
        old = make_event({"classes": [self.class_a1]})
        new = make_event({"classes": [self.class_a2]})
        self.assertTrue(self._sees(self.student_a1, old))
        self.assertFalse(self._sees(self.student_a1, new))

        enrollment = self.student_a1.enrollments.get()
        enrollment.school_class = self.class_a2
        enrollment.save()

        self.assertFalse(self._sees(self.student_a1, old))
        self.assertTrue(self._sees(self.student_a1, new))

    def test_someone_who_left_sees_nothing_even_when_listed(self):
        event = make_event({"students": [self.student_a1]})
        whole = make_event()
        StudentEnrollment.objects.filter(student=self.student_a1).update(status="withdrawn")

        self.assertFalse(self._sees(self.student_a1, event))
        self.assertFalse(self._sees(self.student_a1, whole))
        self.assertNotIn(self.student_a1.pk, audience.reached_enrollments(event).values_list("student_id", flat=True))
        self.assertEqual(audience.visible_to(OnlineEvent.objects.all(), None).count(), 0)

    def test_no_current_year_means_nobody(self):
        event = make_event()
        self.year.is_current = False
        self.year.save()
        self.assertFalse(audience.reached_enrollments(event).exists())
        self.assertFalse(self._sees(self.student_a1, event))


class AdminScopeTests(SchoolMixin, TestCase):
    """What a branch-scoped admin sees and changes; ``wholly_within`` and ``targets_problems`` must agree."""

    def setUp(self):
        self.make_school()
        self.allowed = {self.branch_a.pk}

    def _within(self, item):
        return audience.wholly_within(OnlineEvent.objects.filter(pk=item.pk), self.allowed).exists()

    def _no_problems(self, targets, whole=False):
        ids = lambda name: [v.pk for v in targets.get(name, [])]  # noqa: E731
        return not audience.targets_problems(
            is_whole_school=whole,
            branch_ids=ids("branches"),
            grade_ids=ids("grades"),
            class_ids=ids("classes"),
            student_ids=ids("students"),
            excluded_ids=ids("excluded_students"),
            allowed=self.allowed,
        )

    def test_both_rules_agree(self):
        cases = {
            "own branch": ({"branches": [self.branch_a]}, False, True),
            "own branch and a grade": ({"branches": [self.branch_a], "grades": [self.grade_1]}, False, True),
            "own class": ({"classes": [self.class_a1]}, False, True),
            "own student": ({"students": [self.student_a1]}, False, True),
            "own branch minus own student": ({"branches": [self.branch_a], "excluded_students": [self.student_a1]}, False, True),
            "whole school": ({}, True, False),
            "nothing": ({}, False, False),
            "grade alone is every branch": ({"grades": [self.grade_1]}, False, False),
            "other branch": ({"branches": [self.branch_b]}, False, False),
            "both branches": ({"branches": [self.branch_a, self.branch_b]}, False, False),
            "other class": ({"branches": [self.branch_a], "classes": [self.class_b1]}, False, False),
            "other student": ({"branches": [self.branch_a], "students": [self.student_b1]}, False, False),
            "excluded student of another branch": ({"branches": [self.branch_a], "excluded_students": [self.student_b1]}, False, False),
        }
        for name, (targets, whole, expected) in cases.items():
            with self.subTest(name):
                item = make_event(targets, is_whole_school=whole)
                self.assertEqual(self._within(item), expected)
                self.assertEqual(self._no_problems(targets, whole), expected)

    def test_touching_branches(self):
        reaches = [
            make_event(),
            make_event({"branches": [self.branch_a]}),
            make_event({"classes": [self.class_a1]}),
            make_event({"grades": [self.grade_1]}),
            make_event({"students": [self.student_a1]}),
        ]
        away = [
            make_event({"branches": [self.branch_b]}),
            make_event({"classes": [self.class_b1]}),
            make_event({"students": [self.student_b1]}),
        ]
        found = set(audience.touching_branches(OnlineEvent.objects.all(), self.allowed).values_list("pk", flat=True))
        self.assertEqual(found, {e.pk for e in reaches})
        self.assertFalse(found & {e.pk for e in away})

    def test_touching_grade(self):
        reaches = [
            make_event(),
            make_event({"grades": [self.grade_1]}),
            make_event({"classes": [self.class_a1]}),
            make_event({"branches": [self.branch_b]}),
        ]
        make_event({"grades": [self.grade_2]})
        make_event({"classes": [self.class_a2]})
        found = set(audience.touching_grade(OnlineEvent.objects.all(), self.grade_1.pk).values_list("pk", flat=True))
        self.assertEqual(found, {e.pk for e in reaches})
