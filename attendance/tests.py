"""
Attendance: the supporter's daily sheet and the teacher's archived
per-session attendance.

* the models: one sheet per class and day, one record per student;
* ``services.day_error``: which days a class can have a sheet (its
  timetable, the calendar, the cutoff, today);
* ``services.save_daily_sheet``: everyone present by default, edits set
  ``updated_by``, never two sheets;
* the sheet page and who may use it (the class's supporter and admins;
  never a teacher);
* the archive page: read-only, and closed to teachers from the cutoff on;
* the readers (``get_absences`` & co.) across the cutoff;
* the migration kept the old table.

The fixture is ``analytics.tests.Fixture`` (year 1405; class A in branch A
has math at bells 1 and 2 on Sundays, class B physics at bell 1). The
cutoff is moved to Sunday 12 Mehr (``DAILY_FROM_SUNDAY_2``) and "now" is
Wednesday 15 Mehr at noon, so the tests never depend on the real date.
"""

from datetime import date, timedelta
from unittest import mock

from django.contrib.admin.sites import site
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory, override_settings
from django.urls import reverse

from accounts.models import User
from analytics.tests import AS_OF, DAILY_FROM_SUNDAY_2, SUNDAY_1, SUNDAY_2, THURSDAY, Fixture, J
from attendance import services
from attendance.models import DailyAttendance, DailyAttendanceSheet, SessionAttendance
from core.testing import (
    grant_all_model_permissions,
    make_branch_access,
    make_calendar_event,
    make_enrollment,
    make_schedule,
    make_staff,
    make_student,
    make_superuser,
    make_supervisor,
    make_user,
)
from scheduling.models import ClassSchedule
from student.models.student_enrollment import StudentEnrollment
from supervisor.models import SupervisorClass
from teaching.models import SchoolSession

now = mock.patch("django.utils.timezone.now", lambda: AS_OF)

MONDAY = J(1405, 7, 13)
NO_LESSONS = J(1405, 7, 14)     # a Tuesday: no lesson in the timetable
NEXT_SUNDAY = J(1405, 7, 19)    # after "now"

PRESENT, ABSENT, LATE, EXCUSED = "present", "absent", "late", "excused"


def jalali_query(day):
    return {"date": day.strftime("%Y/%m/%d")}


@DAILY_FROM_SUNDAY_2
class AttendanceTestCase(Fixture):
    def setUp(self):
        now.start()
        self.addCleanup(now.stop)
        self.supervisor = make_supervisor(self.branch_a, self.grade)
        SupervisorClass.objects.create(supervisor=self.supervisor, school_class=self.class_a)

    def enroll(self, school_class=None, first_name="", last_name="", **kwargs):
        enrollment = make_enrollment(make_student(), school_class or self.class_a, **kwargs)
        user = enrollment.student.user
        user.first_name, user.last_name = first_name, last_name
        user.save()
        return enrollment

    def monday_with_lesson(self):
        """Give math a Monday lesson and return that Monday (13 Mehr)."""

        make_schedule(self.math, ClassSchedule.DayChoices.MONDAY, self.bell_1)
        return MONDAY

    def sheet_url(self, school_class=None, day=SUNDAY_2):
        url = reverse("attendance:daily_sheet", args=[(school_class or self.class_a).pk])
        return f"{url}?date={day.strftime('%Y/%m/%d')}"


# ----------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------

class DailyAttendanceModelTests(AttendanceTestCase):
    def test_one_sheet_per_class_and_day(self):
        self.daily(self.class_a, SUNDAY_2)

        with self.assertRaises(IntegrityError), transaction.atomic():
            DailyAttendanceSheet.objects.create(
                school_class=self.class_a, date=SUNDAY_2, taken_by=self.supervisor.user,
            )
        # another class, or another day, is another sheet
        self.daily(self.class_b, SUNDAY_2)
        self.daily(self.class_a, self.monday_with_lesson())
        self.assertEqual(DailyAttendanceSheet.objects.count(), 3)

    def test_one_record_per_student_on_a_sheet(self):
        sheet = self.daily(self.class_a, SUNDAY_2)
        enrollment = self.enroll()
        DailyAttendance.objects.create(sheet=sheet, student_enrollment=enrollment)

        with self.assertRaises(IntegrityError), transaction.atomic():
            DailyAttendance.objects.create(sheet=sheet, student_enrollment=enrollment, status=ABSENT)

    def test_a_record_must_be_a_student_of_the_class(self):
        sheet = self.daily(self.class_a, SUNDAY_2)
        record = DailyAttendance(sheet=sheet, student_enrollment=self.enroll(self.class_b))

        with self.assertRaises(ValidationError):
            record.full_clean()

    def test_a_new_sheet_is_refused_on_a_day_without_lessons(self):
        with self.assertRaises(ValidationError) as caught:
            self.daily(self.class_a, NO_LESSONS)

        self.assertIn("date", caught.exception.message_dict)

    def test_the_archive_keeps_its_table(self):
        self.assertEqual(SessionAttendance._meta.db_table, "attendance_attendance")


# ----------------------------------------------------------------------
# Which days can have a sheet
# ----------------------------------------------------------------------

class DayErrorTests(AttendanceTestCase):
    def error(self, day, school_class=None):
        return services.day_error(school_class or self.class_a, day)

    def test_a_day_with_lessons_from_the_cutoff_to_today(self):
        self.assertIsNone(self.error(SUNDAY_2))

    def test_before_the_cutoff(self):
        self.assertIn("حضور و غیاب روزانه از", self.error(SUNDAY_1))

    def test_in_the_future(self):
        self.assertEqual(self.error(NEXT_SUNDAY), "حضور و غیاب روزهای آینده را نمی‌توان ثبت کرد.")

    def test_the_timetable_decides_not_the_weekday(self):
        # Tuesday is a working day, but class A has no lesson on it ...
        self.assertIn("برنامه‌ی هفتگی", self.error(NO_LESSONS))
        # ... until its timetable has one.
        make_schedule(self.math, ClassSchedule.DayChoices.TUESDAY, self.bell_1)
        self.assertIsNone(self.error(NO_LESSONS))

    def test_thursday_never_has_lessons(self):
        with override_settings(ATTENDANCE_DAILY_START_DATE=THURSDAY.togregorian()):
            self.assertIn("برنامه‌ی هفتگی", self.error(THURSDAY))

    def test_a_full_day_closure(self):
        make_calendar_event(self.year, SUNDAY_2, branches=[self.branch_a], title="آلودگی هوا")

        self.assertEqual(self.error(SUNDAY_2), "کلاس در این روز به‌دلیل «آلودگی هوا» تعطیل است.")
        self.assertIsNone(self.error(SUNDAY_2, self.class_b))       # the other branch

    def test_a_closure_of_some_bells_only(self):
        # Bell 1 closed, bell 2 still open: the class is in school.
        make_calendar_event(self.year, SUNDAY_2, bells=[self.bell_1])
        self.assertIsNone(self.error(SUNDAY_2))

        # Every bell of the day closed: no attendance.
        make_calendar_event(self.year, SUNDAY_2, bells=[self.bell_2], title="اردو")
        self.assertIn("تعطیل است", self.error(SUNDAY_2))

    def test_an_inactive_class_has_no_lessons(self):
        self.class_a.is_active = False
        self.class_a.save()

        self.assertIn("برنامه‌ی هفتگی", self.error(SUNDAY_2))


# ----------------------------------------------------------------------
# Saving a sheet
# ----------------------------------------------------------------------

class SaveDailySheetTests(AttendanceTestCase):
    def setUp(self):
        super().setUp()
        self.ali = self.enroll(first_name="علی", last_name="موسوی")
        self.sara = self.enroll(first_name="سارا", last_name="احمدی")
        self.reza = self.enroll(first_name="رضا", last_name="کریمی")

    def save(self, entries, user=None, day=SUNDAY_2):
        return services.save_daily_sheet(self.class_a, day, user or self.supervisor.user, entries)

    def statuses(self, sheet):
        return {r.student_enrollment_id: r.status for r in sheet.records.all()}

    def test_everyone_is_present_unless_marked(self):
        sheet, created = self.save({self.ali.pk: (ABSENT, "بیمار")})

        self.assertTrue(created)
        self.assertEqual(sheet.taken_by, self.supervisor.user)
        self.assertEqual(self.statuses(sheet), {
            self.ali.pk: ABSENT, self.sara.pk: PRESENT, self.reza.pk: PRESENT,
        })
        self.assertEqual(sheet.records.get(student_enrollment=self.ali).description, "بیمار")
        # the first save is the sheet's taker; nobody "updated" a record yet
        self.assertFalse(sheet.records.exclude(updated_by=None).exists())

    def test_saving_twice_edits_the_same_sheet(self):
        first, _ = self.save({self.ali.pk: (ABSENT, None)})
        admin = make_superuser()

        # Ali arrives at 9: absent -> late.
        second, created = self.save({self.ali.pk: (LATE, "ساعت ۹ رسید")}, user=admin)

        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(DailyAttendanceSheet.objects.count(), 1)
        self.assertEqual(DailyAttendance.objects.count(), 3)
        ali = second.records.get(student_enrollment=self.ali)
        self.assertEqual((ali.status, ali.description, ali.updated_by), (LATE, "ساعت ۹ رسید", admin))
        # unchanged records keep updated_by empty, and the taker stays
        self.assertIsNone(second.records.get(student_enrollment=self.sara).updated_by)
        second.refresh_from_db()
        self.assertEqual(second.taken_by, self.supervisor.user)

    def test_an_edit_without_a_status_or_description_keeps_them(self):
        self.save({self.ali.pk: (EXCUSED, "نامه‌ی پزشک")})

        sheet, _ = self.save({self.ali.pk: (None, None)})

        ali = sheet.records.get(student_enrollment=self.ali)
        self.assertEqual((ali.status, ali.description, ali.updated_by), (EXCUSED, "نامه‌ی پزشک", None))

    def test_a_student_enrolled_after_the_sheet_is_added_on_the_next_edit(self):
        self.save({})
        late_comer = self.enroll()

        sheet, _ = self.save({})

        record = sheet.records.get(student_enrollment=late_comer)
        self.assertEqual((record.status, record.updated_by), (PRESENT, self.supervisor.user))

    def test_a_student_who_left_keeps_the_record_but_is_not_added_elsewhere(self):
        self.save({self.reza.pk: (ABSENT, None)})
        self.reza.status = StudentEnrollment.EnrollmentStatus.WITHDRAWN
        self.reza.save()

        sheet, _ = self.save({})
        monday_sheet, _ = self.save({}, day=self.monday_with_lesson())

        self.assertEqual(sheet.records.get(student_enrollment=self.reza).status, ABSENT)
        self.assertFalse(monday_sheet.records.filter(student_enrollment=self.reza).exists())

    def test_a_new_sheet_on_a_day_without_lessons_is_refused(self):
        with self.assertRaises(ValidationError):
            self.save({}, day=NO_LESSONS)
        self.assertFalse(DailyAttendanceSheet.objects.exists())


# ----------------------------------------------------------------------
# The sheet page
# ----------------------------------------------------------------------

class DailySheetPageTests(AttendanceTestCase):
    def setUp(self):
        super().setUp()
        self.ali = self.enroll(first_name="علی", last_name="موسوی")
        self.sara = self.enroll(first_name="سارا", last_name="احمدی")
        self.client.force_login(self.supervisor.user)

    def test_lists_the_class_with_everyone_present(self):
        response = self.client.get(self.sheet_url())
        html = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "attendance/daily_sheet.html")
        self.assertEqual([s["status"] for s in response.context["students"]], [PRESENT, PRESENT])
        for enrollment in (self.ali, self.sara):
            for value in (PRESENT, ABSENT, LATE, EXCUSED):
                self.assertIn(f'name="status-{enrollment.pk}" value="{value}"', html)
        self.assertRegex(html, rf'name="status-{self.ali.pk}" value="present"\s+checked')
        # by last name
        self.assertLess(html.index("سارا احمدی"), html.index("علی موسوی"))
        self.assertContains(response, "هنوز ثبت نشده")

    def test_saving_marks_only_the_exceptions_and_goes_back_to_the_overview(self):
        response = self.client.post(self.sheet_url(), {
            f"status-{self.ali.pk}": ABSENT,
            f"description-{self.ali.pk}": "  تماس گرفته شد  ",
        })

        self.assertRedirects(
            response,
            f"{reverse('supervisor:attendance')}?date=1405%2F07%2F12&class={self.class_a.pk}",
            fetch_redirect_response=False,
        )
        sheet = DailyAttendanceSheet.objects.get(school_class=self.class_a, date=SUNDAY_2)
        self.assertEqual(
            {(r.student_enrollment_id, r.status, r.description) for r in sheet.records.all()},
            {(self.ali.pk, ABSENT, "تماس گرفته شد"), (self.sara.pk, PRESENT, "")},
        )

    def test_revisiting_edits_the_sheet(self):
        self.client.post(self.sheet_url(), {f"status-{self.ali.pk}": ABSENT})

        response = self.client.get(self.sheet_url())
        self.assertRegex(response.content.decode(), rf'name="status-{self.ali.pk}" value="absent"\s+checked')
        self.assertContains(response, "ذخیره‌ی تغییرات")

        self.client.post(self.sheet_url(), {
            f"status-{self.ali.pk}": LATE, f"status-{self.sara.pk}": PRESENT,
        })

        self.assertEqual(DailyAttendanceSheet.objects.count(), 1)
        ali = DailyAttendance.objects.get(student_enrollment=self.ali)
        self.assertEqual((ali.status, ali.updated_by), (LATE, self.supervisor.user))

    def test_an_unknown_status_is_ignored(self):
        self.client.post(self.sheet_url(), {f"status-{self.ali.pk}": "gone"})

        self.assertEqual(DailyAttendance.objects.get(student_enrollment=self.ali).status, PRESENT)

    def test_without_a_date_it_is_today(self):
        url = reverse("attendance:daily_sheet", args=[self.class_a.pk])

        response = self.client.get(url)

        # "now" is Wednesday 15 Mehr: class A has no lesson on Wednesdays.
        self.assertEqual(response.context["day"], J(1405, 7, 15))
        self.assertIn("برنامه‌ی هفتگی", response.context["error"])

    def test_an_invalid_date_falls_back_to_today_with_a_message(self):
        url = reverse("attendance:daily_sheet", args=[self.class_a.pk])

        response = self.client.get(url, {"date": "1405/13/40"})

        self.assertEqual(response.context["day"], J(1405, 7, 15))
        self.assertContains(response, "تاریخ واردشده معتبر نیست")

    def test_a_day_that_cannot_have_a_sheet_shows_why_and_saves_nothing(self):
        for day, message in ((SUNDAY_1, "حضور و غیاب روزانه از"), (NO_LESSONS, "برنامه‌ی هفتگی"),
                             (NEXT_SUNDAY, "روزهای آینده")):
            response = self.client.get(self.sheet_url(day=day))
            self.assertContains(response, message)
            self.assertNotContains(response, 'id="attendanceForm"')

            response = self.client.post(self.sheet_url(day=day), {f"status-{self.ali.pk}": ABSENT})
            self.assertEqual(response.status_code, 200)
        self.assertFalse(DailyAttendanceSheet.objects.exists())

    def test_a_class_without_students(self):
        DailyAttendance.objects.all().delete()
        StudentEnrollment.objects.filter(school_class=self.class_a).delete()

        response = self.client.get(self.sheet_url())

        self.assertContains(response, "دانش‌آموزی در این کلاس ثبت‌نام نشده است")


class DailySheetAccessTests(AttendanceTestCase):
    """Only the class's supporter, a superuser or a staff admin of its branch."""

    def setUp(self):
        super().setUp()
        self.student = self.enroll()

    def assert_forbidden(self):
        self.assertEqual(self.client.get(self.sheet_url()).status_code, 403)
        response = self.client.post(self.sheet_url(), {f"status-{self.student.pk}": ABSENT})
        self.assertEqual(response.status_code, 403)
        self.assertFalse(DailyAttendanceSheet.objects.exists())

    def test_logged_out_is_sent_to_login(self):
        response = self.client.get(self.sheet_url())

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_a_teacher_cannot_take_daily_attendance(self):
        # even the teacher of a class subject of this class
        self.client.force_login(self.teacher.staff.user)

        self.assert_forbidden()

    def test_another_supervisor_of_the_same_grade_and_branch(self):
        other = make_supervisor(self.branch_a, self.grade)
        self.client.force_login(other.user)

        self.assert_forbidden()

    def test_the_supervisor_of_another_class(self):
        other = make_supervisor(self.branch_b, self.grade)
        SupervisorClass.objects.create(supervisor=other, school_class=self.class_b)
        self.client.force_login(other.user)

        self.assert_forbidden()
        self.assertEqual(self.client.get(self.sheet_url(self.class_b)).status_code, 200)

    def test_a_student(self):
        self.client.force_login(self.student.student.user)

        self.assert_forbidden()

    def test_the_director_only_reads(self):
        self.client.force_login(make_user(User.Roles.DIRECTOR))

        self.assert_forbidden()

    def test_a_superuser(self):
        self.client.force_login(make_superuser())

        self.client.post(self.sheet_url(), {f"status-{self.student.pk}": ABSENT})

        self.assertTrue(DailyAttendance.objects.filter(status=ABSENT).exists())

    def test_a_staff_admin_needs_the_permission_and_the_branch(self):
        staff = make_staff(role=User.Roles.ADMIN, is_staff=True)
        self.client.force_login(staff.user)
        make_branch_access(staff, self.branch_a)
        self.assert_forbidden()         # no permission yet

        grant_all_model_permissions(staff.user)
        response = self.client.post(self.sheet_url(), {f"status-{self.student.pk}": ABSENT})
        self.assertRedirects(response, self.sheet_url().replace("%2F", "/"), fetch_redirect_response=False)

    def test_a_staff_admin_of_another_branch(self):
        staff = make_staff(role=User.Roles.ADMIN, is_staff=True)
        grant_all_model_permissions(staff.user)
        make_branch_access(staff, self.branch_b)
        self.client.force_login(staff.user)

        self.assert_forbidden()


# ----------------------------------------------------------------------
# The archive (per-session attendance)
# ----------------------------------------------------------------------

class SessionAttendancePageTests(AttendanceTestCase):
    def setUp(self):
        super().setUp()
        self.archived = self.session(self.math, SUNDAY_1, self.bell_1)
        self.after = self.session(self.math, SUNDAY_2, self.bell_1)
        self.student = self.enroll(first_name="سارا", last_name="احمدی")
        SessionAttendance.objects.create(
            session=self.archived, student_enrollment=self.student, status=ABSENT, description="بیمار",
        )
        self.client.force_login(self.teacher.staff.user)

    def url(self, session):
        return reverse("attendance:session_attendance", args=[session.pk])

    def test_the_teacher_reads_the_archive(self):
        response = self.client.get(self.url(self.archived))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "attendance/session_attendance.html")
        self.assertContains(response, "سارا احمدی")
        self.assertContains(response, "بیمار")
        self.assertNotContains(response, "<form")

    def test_the_archive_cannot_be_written(self):
        response = self.client.post(self.url(self.archived), {f"status-{self.student.pk}": PRESENT})

        self.assertEqual(response.status_code, 405)
        self.assertEqual(SessionAttendance.objects.get().status, ABSENT)

    def test_a_teacher_gets_403_from_the_cutoff_on(self):
        self.assertEqual(self.client.get(self.url(self.after)).status_code, 403)

    def test_a_supervisor_is_sent_to_the_daily_sheet(self):
        self.client.force_login(self.supervisor.user)

        response = self.client.get(self.url(self.after))

        self.assertRedirects(response, self.sheet_url().replace("%2F", "/"), fetch_redirect_response=False)

    def test_another_teacher_gets_404(self):
        from core.testing import make_teacher_profile

        self.client.force_login(make_teacher_profile().staff.user)

        self.assertEqual(self.client.get(self.url(self.archived)).status_code, 404)
        self.assertEqual(self.client.get(self.url(self.after)).status_code, 404)

    def test_a_staff_admin_needs_the_view_permission(self):
        staff = make_staff(role=User.Roles.ADMIN, is_staff=True)
        make_branch_access(staff, self.branch_a)
        self.client.force_login(staff.user)
        self.assertEqual(self.client.get(self.url(self.archived)).status_code, 404)

        from django.contrib.auth.models import Permission

        staff.user.user_permissions.add(Permission.objects.get(codename="view_sessionattendance"))
        self.assertEqual(self.client.get(self.url(self.archived)).status_code, 200)

    def test_the_admin_is_view_only(self):
        request = RequestFactory().get("/")
        request.user = make_superuser()
        model_admin = site._registry[SessionAttendance]

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request))
        self.assertTrue(model_admin.has_view_permission(request))


class TeacherSessionListTests(AttendanceTestCase):
    def test_no_attendance_link_on_the_session_list(self):
        self.session(self.math, SUNDAY_1, self.bell_1)
        self.session(self.math, SUNDAY_2, self.bell_1)
        self.client.force_login(self.teacher.staff.user)

        response = self.client.get(reverse("teaching:session_list", args=[self.math.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/attendance/")
        self.assertNotContains(response, "حضور و غیاب")


# ----------------------------------------------------------------------
# Readers across the cutoff
# ----------------------------------------------------------------------

class ServiceTests(AttendanceTestCase):
    def setUp(self):
        super().setUp()
        self.student = self.enroll(first_name="علی", last_name="موسوی")
        self.other = self.enroll(first_name="سارا", last_name="احمدی")
        archived = self.session(self.math, SUNDAY_1, self.bell_1)
        cancelled = self.session(self.math, SUNDAY_1, self.bell_2, SchoolSession.Status.CANCELED)
        SessionAttendance.objects.create(session=archived, student_enrollment=self.student, status=ABSENT)
        SessionAttendance.objects.create(session=archived, student_enrollment=self.other, status=PRESENT)
        # a cancelled session's records never count (as before)
        SessionAttendance.objects.create(session=cancelled, student_enrollment=self.student, status=ABSENT)
        # a per-session record after the cutoff is ignored
        after = self.session(self.math, SUNDAY_2, self.bell_1)
        SessionAttendance.objects.create(session=after, student_enrollment=self.student, status=ABSENT)
        services.save_daily_sheet(self.class_a, SUNDAY_2, self.supervisor.user, {
            self.student.pk: (EXCUSED, "نامه"), self.other.pk: (LATE, None),
        })

    def test_split_range(self):
        cutoff = SUNDAY_2.togregorian()
        day = timedelta(days=1)

        self.assertEqual(services.split_range(SUNDAY_1, SUNDAY_2),
                         ((SUNDAY_1.togregorian(), cutoff - day), (cutoff, cutoff)))
        self.assertEqual(services.split_range(SUNDAY_1, SUNDAY_1),
                         ((SUNDAY_1.togregorian(), SUNDAY_1.togregorian()), None))
        self.assertEqual(services.split_range(SUNDAY_2, None), (None, (cutoff, None)))
        self.assertEqual(services.split_range(), ((None, cutoff - day), (cutoff, None)))

    def test_get_absences_of_a_student_across_the_cutoff(self):
        records = services.get_absences(self.student, SUNDAY_1, SUNDAY_2)

        self.assertEqual(
            [(r.date, r.status, r.is_daily) for r in records],
            [(SUNDAY_2.togregorian(), EXCUSED, True), (SUNDAY_1.togregorian(), ABSENT, False)],
        )
        self.assertEqual(records[0].status_label, "غیبت موجه")
        self.assertEqual(records[1].session.class_subject, self.math)

    def test_get_absences_of_a_class_on_one_day(self):
        before = services.get_absences(self.class_a, SUNDAY_1, SUNDAY_1)
        after = services.get_absences(self.class_a, SUNDAY_2, SUNDAY_2)

        self.assertEqual([r.student_enrollment for r in before], [self.student])
        # by name: سارا احمدی before علی موسوی
        self.assertEqual([(r.student_enrollment, r.status) for r in after],
                         [(self.other, LATE), (self.student, EXCUSED)])
        self.assertEqual(services.get_absences(self.class_b, SUNDAY_1, SUNDAY_2), [])

    def test_counts_across_the_cutoff(self):
        counts = services.attendance_counts(self.class_a)

        self.assertEqual(
            {key: counts[key] for key in ("total", "present", "absent", "late", "excused", "absences")},
            {"total": 4, "present": 1, "absent": 1, "late": 1, "excused": 1, "absences": 2},
        )
        self.assertEqual(counts["rate"], 50)
        self.assertEqual(services.attendance_counts(self.class_a, SUNDAY_2, SUNDAY_2)["total"], 2)

    def test_student_tallies(self):
        tallies = services.student_tallies(self.class_a, SUNDAY_1, SUNDAY_2)

        self.assertEqual(
            {k: tallies[self.student.pk][k] for k in ("total", "absent", "excused", "absences", "last_name")},
            {"total": 2, "absent": 1, "excused": 1, "absences": 2, "last_name": "موسوی"},
        )

    def test_session_counts(self):
        archived = SchoolSession.objects.get(date=SUNDAY_1, bell=self.bell_1)
        after = SchoolSession.objects.get(date=SUNDAY_2, bell=self.bell_1)

        self.assertEqual(services.session_counts(archived)["daily"], False)
        self.assertEqual(services.session_counts(archived)["total"], 2)
        # from the cutoff on: the class's sheet of that day, not the session's own record
        after_counts = services.session_counts(after)
        self.assertEqual((after_counts["daily"], after_counts["total"], after_counts["excused"]),
                         (True, 2, 1))

    def test_moving_the_cutoff_moves_every_reader(self):
        with override_settings(ATTENDANCE_DAILY_START_DATE=date(2026, 10, 23)):
            records = services.get_absences(self.student, SUNDAY_1, SUNDAY_2)

        # all archive now: the two absences in delivered sessions, no sheet
        self.assertEqual([(r.date, r.is_daily) for r in records],
                         [(SUNDAY_2.togregorian(), False), (SUNDAY_1.togregorian(), False)])
