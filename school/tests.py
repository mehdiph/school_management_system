"""
Integrity tests for ``ClassSubject``.

A ``ClassSubject`` row is what ties a teacher to a class, and every
branch-scoped query reaches the teacher through it. So a row whose
teacher assignment belongs to a different branch (or a different
academic year) than the class silently breaks scoping -- ``clean()``
is what makes that impossible.
"""

import jdatetime
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.testing import (
    make_academic_year,
    make_assignment,
    make_branch,
    make_grade,
    make_school_class,
    make_subject,
    make_teacher_profile,
)
from school.models import ClassSubject


class ClassSubjectValidationTests(TestCase):

    def setUp(self):
        self.branch = make_branch()
        self.other_branch = make_branch()
        self.year = make_academic_year(is_current=True)
        self.other_year = make_academic_year(
            start_date=jdatetime.date(1402, 7, 1), is_current=False
        )
        self.grade = make_grade()
        self.subject = make_subject()

        self.school_class = make_school_class(
            self.branch, self.grade, self.year
        )

    def build(self, assignment):
        return ClassSubject(
            school_class=self.school_class,
            subject=self.subject,
            teacher_assignment=assignment,
            start_date=jdatetime.date(1403, 7, 1),
            end_date=jdatetime.date(1404, 3, 31),
        )

    def test_matching_branch_and_year_is_valid(self):
        assignment = make_assignment(
            make_teacher_profile(), self.branch, self.year
        )

        self.build(assignment).full_clean()

    def test_mismatched_branch_is_rejected(self):
        assignment = make_assignment(
            make_teacher_profile(), self.other_branch, self.year
        )

        with self.assertRaises(ValidationError) as ctx:
            self.build(assignment).full_clean()

        self.assertIn("teacher_assignment", ctx.exception.error_dict)
        self.assertIn(
            "شعبه", " ".join(ctx.exception.messages)
        )

    def test_mismatched_academic_year_is_rejected(self):
        assignment = make_assignment(
            make_teacher_profile(), self.branch, self.other_year
        )

        with self.assertRaises(ValidationError) as ctx:
            self.build(assignment).full_clean()

        self.assertIn("teacher_assignment", ctx.exception.error_dict)
        self.assertIn(
            "سال تحصیلی", " ".join(ctx.exception.messages)
        )

    def test_both_mismatches_are_reported_together(self):
        assignment = make_assignment(
            make_teacher_profile(), self.other_branch, self.other_year
        )

        with self.assertRaises(ValidationError) as ctx:
            self.build(assignment).full_clean()

        self.assertEqual(
            len(ctx.exception.error_dict["teacher_assignment"]), 2
        )

    def test_clean_is_a_no_op_before_the_relations_are_set(self):
        """An unsaved, half-filled instance must not blow up in clean()."""

        ClassSubject().clean()

    def test_admin_form_surfaces_the_error(self):
        """
        The admin must show the validation error rather than saving a
        mismatching row -- exercised through the real ModelForm the
        admin builds.
        """

        from django.contrib import admin
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        assignment = make_assignment(
            make_teacher_profile(), self.other_branch, self.year
        )

        model_admin = admin.site._registry[ClassSubject]
        request = RequestFactory().get("/")
        request.user = AnonymousUser()

        form_class = model_admin.get_form(request, obj=None)
        form = form_class(
            data={
                "school_class": self.school_class.pk,
                "subject": self.subject.pk,
                "teacher_assignment": assignment.pk,
                "start_date": "1403-07-01",
                "end_date": "1404-03-31",
                "is_active": "on",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("teacher_assignment", form.errors)
