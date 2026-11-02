from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from core.spreadsheet import FileRejected
from core.testing import grant_all_model_permissions, make_branch_access, make_staff, make_superuser
from online_classes import importer, services
from online_classes.admin import IMPORT_SESSION_KEY
from online_classes.import_template import build_template
from online_classes.importer import COLUMNS
from online_classes.models import OnlineEvent, OnlineEventAccess
from online_classes.testing import SchoolMixin, make_access, make_event, make_platform

User = get_user_model()
PERSONAL = OnlineEvent.AccessMode.PERSONAL


def cells(student=None, *, code=None, national="", url="", username="", password="", access_code="", note=""):
    return {
        importer.STUDENT_CODE: code if code is not None else (student.student_code if student else ""),
        importer.NATIONAL_CODE: national,
        importer.NAME: "",
        importer.URL: url,
        importer.USERNAME: username,
        importer.PASSWORD: password,
        importer.ACCESS_CODE: access_code,
        importer.NOTE: note,
    }


def xlsx(rows, header=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(header or COLUMNS)
    for row in rows:
        sheet.append([row.get(column, "") for column in COLUMNS] if isinstance(row, dict) else row)
    buffer = BytesIO()
    workbook.save(buffer)
    return SimpleUploadedFile("access.xlsx", buffer.getvalue())


class ValidateTests(SchoolMixin, TestCase):
    def setUp(self):
        self.make_school()
        self.admin = make_superuser()
        self.event = make_event({"classes": [self.class_a1]}, access_mode=PERSONAL)

    def plan(self, *rows, user=None, event=None):
        return importer.validate(list(rows), event or self.event, user or self.admin)

    def test_valid_row(self):
        plan = self.plan(cells(self.student_a1, password="pw", url="https://example.com/x"))
        self.assertTrue(plan.is_valid)
        self.assertEqual(plan.rows[0].student, self.student_a1)
        self.assertEqual(plan.new_count, 1)

    def test_match_by_national_code_with_lost_leading_zeros_and_persian_digits(self):
        User.objects.filter(pk=self.student_a1.user_id).update(national_code="0012345679")
        for value in ("12345679", "۰۰۱۲۳۴۵۶۷۹", "0012345679"):
            with self.subTest(value):
                plan = self.plan(cells(code="", national=value, password="pw"))
                self.assertTrue(plan.is_valid, plan.rows[0].errors)
                self.assertEqual(plan.rows[0].student, self.student_a1)

    def test_errors(self):
        User.objects.filter(pk=self.student_b1.user_id).update(national_code="0012345679")
        cases = {
            "unknown student code": (cells(code="nope", password="pw"), "پیدا نشد"),
            "unknown national code": (cells(code="", national="1111111111", password="pw"), "پیدا نشد"),
            "no code at all": (cells(code="", password="pw"), "لازم است"),
            "two codes, two students": (cells(self.student_a1, national="0012345679", password="pw"), "دو دانش‌آموز"),
            "bad link": (cells(self.student_a1, url="http://example.com"), "https"),
            "note alone on a new row": (cells(self.student_a1, note="فقط توضیح"), "فقط «توضیح» کافی نیست"),
            "username too long": (cells(self.student_a1, username="x" * 151), "نام کاربری"),
            "note too long": (cells(self.student_a1, username="u", note="x" * 301), "توضیح"),
        }
        for name, (row, expected) in cases.items():
            with self.subTest(name):
                plan = self.plan(row)
                self.assertFalse(plan.is_valid)
                self.assertIn(expected, " ".join(plan.rows[0].errors))

    def test_duplicate_student_in_the_file(self):
        plan = self.plan(cells(self.student_a1, password="a"), cells(self.student_a1, password="b"))
        self.assertFalse(plan.is_valid)
        self.assertIn("ردیف 2", plan.rows[1].errors[0])

    def test_outside_the_audience_is_a_warning_and_is_still_saved(self):
        plan = self.plan(cells(self.student_b1, password="pw"))
        self.assertTrue(plan.is_valid)
        self.assertEqual(len(plan.warnings), 1)
        self.assertIn("مخاطبان", plan.rows[0].warnings[0])
        self.assertEqual(services.save_access_import(plan), (1, 0))

    def test_platform_domains_apply(self):
        event = make_event({"classes": [self.class_a1]}, access_mode=PERSONAL, platform=make_platform(allowed_domains="skyroom.online"))
        self.assertFalse(self.plan(cells(self.student_a1, url="https://example.com/x"), event=event).is_valid)
        self.assertTrue(self.plan(cells(self.student_a1, url="https://a.skyroom.online/x"), event=event).is_valid)

    def test_empty_rows_are_skipped(self):
        plan = self.plan(cells(self.student_a1), cells(self.student_a2, password="pw"))
        self.assertEqual(plan.skipped, 1)
        self.assertEqual(len(plan.rows), 1)
        self.assertEqual(plan.rows[0].number, 3, "the row number still matches the file")

    def test_a_file_with_nothing_to_save_is_rejected(self):
        with self.assertRaises(FileRejected):
            self.plan(cells(self.student_a1))

    def test_no_error_message_echoes_a_link_or_a_secret(self):
        plan = self.plan(cells(self.student_a1, url="http://secret-link.example.com/abc", password="pw-secret"))
        text = " ".join(plan.rows[0].errors)
        self.assertNotIn("secret-link", text)
        self.assertNotIn("pw-secret", text)

    def test_preview_values_are_masked(self):
        row = self.plan(cells(self.student_a1, url="https://host.example.com/secret-path", password="pw", access_code="c")).rows[0]
        self.assertEqual(row.password_display, importer.MASK)
        self.assertEqual(row.access_code_display, importer.MASK)
        self.assertEqual(row.link_display, "host.example.com")

    def test_branch_admin_only_for_their_own_students(self):
        staff = make_staff(is_staff=True)
        make_branch_access(staff, self.branch_a)
        plan = self.plan(cells(self.student_b1, password="pw"), user=staff.user)
        self.assertIn("شعبه‌های شما", " ".join(plan.rows[0].errors))
        self.assertTrue(self.plan(cells(self.student_a1, password="pw"), user=staff.user).is_valid)


class SaveTests(SchoolMixin, TestCase):
    def setUp(self):
        self.make_school()
        self.admin = make_superuser()
        self.event = make_event({"classes": [self.class_a1]}, access_mode=PERSONAL)

    def save(self, *rows):
        return services.save_access_import(importer.validate(list(rows), self.event, self.admin), user=self.admin)

    def test_creates_encrypted_rows_with_who_did_it(self):
        self.assertEqual(self.save(cells(self.student_a1, password="pw", username="u", note="n")), (1, 0))
        row = OnlineEventAccess.objects.get()
        self.assertEqual(row.read_secrets()["password"], "pw")
        self.assertNotIn("pw", row.password_encrypted)
        self.assertEqual((row.username, row.note, row.updated_by), ("u", "n", self.admin))

    def test_blank_cells_keep_what_is_stored(self):
        make_access(self.event, self.student_a1, url="https://example.com/a", username="old-user", password="old-pw", note="old-note")
        self.assertEqual(self.save(cells(self.student_a1, password="new-pw")), (0, 1))
        row = OnlineEventAccess.objects.get()
        self.assertEqual(row.read_secrets(), {"url": "https://example.com/a", "password": "new-pw", "access_code": ""})
        self.assertEqual((row.username, row.note), ("old-user", "old-note"))

    def test_a_note_can_update_an_existing_row(self):
        make_access(self.event, self.student_a1, password="pw")
        self.assertEqual(self.save(cells(self.student_a1, note="تازه")), (0, 1))
        self.assertEqual(OnlineEventAccess.objects.get().note, "تازه")

    def test_all_or_nothing_when_a_write_fails(self):
        plan = importer.validate(
            [cells(self.student_a1, password="a"), cells(self.student_a2, password="b")], self.event, self.admin
        )
        original = OnlineEventAccess.save
        calls = []

        def fail_on_second(row, *args, **kwargs):
            calls.append(row)
            if len(calls) == 2:
                raise RuntimeError("boom")
            original(row, *args, **kwargs)

        with patch.object(OnlineEventAccess, "save", fail_on_second), self.assertRaises(RuntimeError):
            services.save_access_import(plan)
        self.assertEqual(OnlineEventAccess.objects.count(), 0)


class ReadRowsTests(TestCase):
    def test_not_an_excel_file(self):
        with self.assertRaises(FileRejected):
            importer.read_rows(SimpleUploadedFile("x.xlsx", b"not a workbook"))

    def test_wrong_headers(self):
        with self.assertRaises(FileRejected):
            importer.read_rows(xlsx([], header=["a", "b"]))

    @override_settings(ONLINE_ACCESS_IMPORT_MAX_ROWS=2)
    def test_row_cap_comes_from_settings(self):
        rows = [["c", "", "", "", "u"]] * 3
        with self.assertRaisesMessage(FileRejected, "2"):
            importer.read_rows(xlsx(rows))

    def test_too_large_a_file(self):
        big = SimpleUploadedFile("x.xlsx", b"0" * (importer.MAX_UPLOAD_BYTES + 1))
        with self.assertRaisesMessage(FileRejected, "۵ مگابایت"):
            importer.read_rows(big)

    def test_numeric_code_cells_are_read_as_text(self):
        rows = importer.read_rows(xlsx([[1234, 12345679, "", "", "u"]]))
        self.assertEqual(rows[0][importer.STUDENT_CODE], "1234")


class SealTests(SchoolMixin, TestCase):
    def setUp(self):
        self.make_school()
        self.admin = make_superuser()
        self.event = make_event(access_mode=PERSONAL)

    def test_round_trip_holds_no_plain_text(self):
        rows = [cells(self.student_a1, password="pw-secret")]
        token = importer.seal(self.event, self.admin, rows, "a.xlsx")
        self.assertNotIn("pw-secret", token)
        self.assertEqual(importer.unseal(token, self.event, self.admin), (rows, "a.xlsx"))

    def test_tied_to_the_event_and_the_admin(self):
        token = importer.seal(self.event, self.admin, [], "a.xlsx")
        self.assertIsNone(importer.unseal(token, make_event(access_mode=PERSONAL), self.admin))
        self.assertIsNone(importer.unseal(token, self.event, make_superuser()))

    def test_expires(self):
        token = importer.seal(self.event, self.admin, [], "a.xlsx")
        with patch("online_classes.crypto._fernets") as fernets:
            from cryptography.fernet import InvalidToken

            fernets.return_value[0].decrypt.side_effect = InvalidToken
            self.assertIsNone(importer.unseal(token, self.event, self.admin))
            self.assertEqual(fernets.return_value[0].decrypt.call_args.kwargs["ttl"], importer.PREVIEW_SECONDS)

    def test_nothing_or_garbage_is_no_preview(self):
        self.assertIsNone(importer.unseal(None, self.event, self.admin))
        self.assertIsNone(importer.unseal("garbage", self.event, self.admin))


class ImportPageTests(SchoolMixin, TestCase):
    def setUp(self):
        self.make_school()
        self.admin = make_superuser()
        self.client.force_login(self.admin)
        self.event = make_event({"classes": [self.class_a1]}, access_mode=PERSONAL)
        self.url = reverse("admin:online_classes_onlineevent_access_import", args=[self.event.pk])
        self.row = cells(self.student_a1, password="pw-secret", access_code="code-secret", url="https://host.example.com/secret-path")

    def test_preview_masks_and_keeps_only_a_token_in_the_session(self):
        response = self.client.post(self.url, {"file": xlsx([self.row])})
        for secret in ("pw-secret", "code-secret", "secret-path"):
            self.assertNotContains(response, secret)
        self.assertContains(response, importer.MASK)
        self.assertContains(response, "host.example.com")
        self.assertEqual(OnlineEventAccess.objects.count(), 0)

        token = self.client.session[IMPORT_SESSION_KEY]
        self.assertIsInstance(token, str)
        for secret in ("pw-secret", "code-secret", "secret-path"):
            self.assertNotIn(secret, token)

    def test_confirm_saves_and_clears_the_session(self):
        self.client.post(self.url, {"file": xlsx([self.row])})
        response = self.client.post(self.url, {"confirm": "1"})
        self.assertRedirects(response, reverse("admin:online_classes_onlineevent_change", args=[self.event.pk]))
        row = OnlineEventAccess.objects.get()
        self.assertEqual(row.read_secrets()["password"], "pw-secret")
        self.assertEqual(row.updated_by, self.admin)
        self.assertNotIn(IMPORT_SESSION_KEY, self.client.session)

    def test_a_file_with_an_error_saves_nothing(self):
        bad = cells(code="nope", password="x")
        response = self.client.post(self.url, {"file": xlsx([self.row, bad])})
        self.assertContains(response, "ردیف خطا دارد")
        self.assertNotContains(response, 'name="confirm"')
        response = self.client.post(self.url, {"confirm": "1"})
        self.assertContains(response, "ردیف خطا دارد")
        self.assertEqual(OnlineEventAccess.objects.count(), 0)

    def test_validated_again_on_confirm(self):
        self.client.post(self.url, {"file": xlsx([self.row])})
        self.student_a1.student_code = "changed"
        self.student_a1.save()
        response = self.client.post(self.url, {"confirm": "1"})
        self.assertContains(response, "پیدا نشد")
        self.assertEqual(OnlineEventAccess.objects.count(), 0)

    def test_confirm_with_no_preview(self):
        response = self.client.post(self.url, {"confirm": "1"})
        self.assertContains(response, "پیش‌نمایش منقضی شده یا پیدا نشد")

    def test_opening_the_page_clears_a_preview(self):
        self.client.post(self.url, {"file": xlsx([self.row])})
        self.client.get(self.url)
        self.assertNotIn(IMPORT_SESSION_KEY, self.client.session)

    def test_warning_is_shown_and_the_row_can_be_confirmed(self):
        outside = cells(self.student_b1, password="pw")
        response = self.client.post(self.url, {"file": xlsx([outside])})
        self.assertContains(response, "جزو مخاطبان این رویداد نیستند")
        self.assertContains(response, 'name="confirm"')

    def test_only_for_personal_events(self):
        event = make_event()
        url = reverse("admin:online_classes_onlineevent_access_import", args=[event.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_template_lists_the_audience_without_secrets(self):
        make_access(self.event, self.student_a1, username="stored-user", password="stored-pw")
        User.objects.filter(pk=self.student_a1.user_id).update(national_code="0012345679", first_name="=SUM(A1)")
        response = self.client.get(reverse("admin:online_classes_onlineevent_access_template", args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)
        sheet = load_workbook(BytesIO(response.content)).worksheets[0]
        rows = list(sheet.iter_rows(values_only=True))
        self.assertEqual(list(rows[0]), COLUMNS)
        self.assertEqual(rows[1][0], self.student_a1.student_code)
        self.assertEqual(rows[1][1], "0012345679", "leading zeros survive")
        self.assertEqual(sheet.cell(row=2, column=2).number_format, "@")
        self.assertEqual(sheet.cell(row=2, column=3).data_type, "s", "a name is never a formula")
        everything = " ".join(str(value) for row in rows for value in row)
        self.assertNotIn("stored-user", everything)
        self.assertNotIn("stored-pw", everything)
        self.assertEqual(len([r for r in rows[1:] if r[0]]), 1, "only the audience")

    def test_template_then_import_round_trip(self):
        data = build_template(self.event)
        workbook = load_workbook(BytesIO(data))
        sheet = workbook.worksheets[0]
        sheet.cell(row=2, column=COLUMNS.index(importer.PASSWORD) + 1, value="pw-1")
        buffer = BytesIO()
        workbook.save(buffer)
        rows = importer.read_rows(SimpleUploadedFile("t.xlsx", buffer.getvalue()))
        plan = importer.validate(rows, self.event, self.admin)
        self.assertTrue(plan.is_valid)
        self.assertEqual(plan.rows[0].student, self.student_a1)


class ImportPermissionTests(SchoolMixin, TestCase):
    def setUp(self):
        self.make_school()
        self.event = make_event({"classes": [self.class_a1]}, access_mode=PERSONAL)
        self.other = make_event({"classes": [self.class_b1]}, access_mode=PERSONAL)
        self.url = reverse("admin:online_classes_onlineevent_access_import", args=[self.event.pk])

    def test_staff_without_permission_is_refused(self):
        self.client.force_login(make_staff(is_staff=True).user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_non_staff_goes_to_login(self):
        self.client.force_login(make_staff().user)
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_branch_admin_only_for_events_wholly_inside(self):
        staff = make_staff(is_staff=True)
        make_branch_access(staff, self.branch_a)
        grant_all_model_permissions(staff.user)
        self.client.force_login(staff.user)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        other = reverse("admin:online_classes_onlineevent_access_import", args=[self.other.pk])
        self.assertEqual(self.client.get(other).status_code, 404)
        whole = make_event(access_mode=PERSONAL)
        url = reverse("admin:online_classes_onlineevent_access_import", args=[whole.pk])
        self.assertEqual(self.client.get(url).status_code, 403, "whole-school: visible, not changeable")


