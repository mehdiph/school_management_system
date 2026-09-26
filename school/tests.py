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


# ---------------------------------------------------------------------------
# Subject colours
# ---------------------------------------------------------------------------

from django.test import SimpleTestCase, override_settings  # noqa: E402
from django.urls import reverse  # noqa: E402

from core.testing import make_superuser  # noqa: E402
from school.colors import (  # noqa: E402
    DARK_TEXT,
    LIGHT_TEXT,
    SUBJECT_PALETTE,
    contrast_ratio,
    hex_color_validator,
    readable_text_color,
    safe_hex,
    tint,
)
from school.models import Subject  # noqa: E402


class HexColorValidatorTests(SimpleTestCase):

    def test_accepts_six_digit_hex(self):
        for value in ("#2563eb", "#2563EB", "#000000", "#ffffff"):
            with self.subTest(value=value):
                hex_color_validator(value)

    def test_rejects_anything_else(self):
        for value in (
            "2563eb", "#abc", "#2563eb0", "#12345g", "red", "",
            "#2563eb;", "#2563eb\n", "url(x)", "#fff;background:url(x)",
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                hex_color_validator(value)

    def test_safe_hex_falls_back(self):
        self.assertEqual(safe_hex("#2563EB"), "#2563eb")
        self.assertEqual(safe_hex("red", "#111111"), "#111111")
        self.assertEqual(safe_hex(None, "#111111"), "#111111")

    def test_readable_text_color(self):
        self.assertEqual(readable_text_color("#1e3a8a"), LIGHT_TEXT)
        self.assertEqual(readable_text_color("#fde047"), DARK_TEXT)
        self.assertEqual(readable_text_color("#ffffff"), DARK_TEXT)
        self.assertEqual(readable_text_color("#000000"), LIGHT_TEXT)

    def test_palette_is_usable(self):
        colors = [color for color, _ in SUBJECT_PALETTE]
        self.assertEqual(len(colors), len(set(colors)))
        for color in colors:
            with self.subTest(color=color):
                hex_color_validator(color)
                # Non-text UI contrast (accent stripe / icon box) on white.
                self.assertGreaterEqual(contrast_ratio(color, "#ffffff"), 3)
                # And whatever text we put on it is readable.
                self.assertGreaterEqual(contrast_ratio(color, readable_text_color(color)), 4.5)

    def test_tint(self):
        self.assertEqual(tint("#000000", 0.5), "#808080")
        self.assertEqual(tint("#2563eb", 0), "#ffffff")
        self.assertEqual(tint("#2563eb", 1), "#2563eb")


class SubjectColorModelTests(TestCase):

    def test_default_and_normalised(self):
        subject = Subject.objects.create(name="ریاضی", slug="math", color="#2563EB")
        self.assertEqual(subject.color, "#2563eb")
        self.assertEqual(Subject.objects.create(name="x", slug="x").color, "#d96a30")

    def test_full_clean_rejects_invalid_color(self):
        subject = Subject(name="ریاضی", slug="math", color="blue")
        with self.assertRaises(ValidationError) as ctx:
            subject.full_clean()
        self.assertIn("color", ctx.exception.message_dict)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SubjectAdminColorTests(TestCase):

    def setUp(self):
        self.client.force_login(make_superuser())
        self.subject = Subject.objects.create(name="ریاضی", slug="math", color="#2563eb")
        self.url = reverse("admin:school_subject_change", args=[self.subject.pk])

    def post(self, color):
        return self.client.post(self.url, {
            "name": "ریاضی", "slug": "math", "color": color, "is_active": "on",
        })

    def test_form_uses_color_picker(self):
        response = self.client.get(reverse("admin:school_subject_add"))
        self.assertContains(response, 'type="color"')
        self.assertContains(response, "class=\"color-picker__preset\"", count=len(SUBJECT_PALETTE))

    def test_color_can_be_changed(self):
        response = self.post("#16A34A")

        self.assertEqual(response.status_code, 302)
        self.subject.refresh_from_db()
        self.assertEqual(self.subject.color, "#16a34a")

    def test_invalid_color_is_rejected(self):
        response = self.post("red")

        self.assertEqual(response.status_code, 200)
        self.subject.refresh_from_db()
        self.assertEqual(self.subject.color, "#2563eb")
