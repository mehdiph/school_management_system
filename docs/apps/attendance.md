# Attendance App

## 1. Purpose

The `attendance` app records which students were in school, and is the only place that decides **which attendance applies to a date**.

Since **1 Aban 1405 (23 October 2026)** attendance is taken **once a day per class, at 8:30, by the grade supporter** («پشتیبان پایه», `SupervisorProfile`), so absent students can be followed up the same morning. Before that date the teacher took attendance in every session; those records are kept as a **read-only archive**. The date is a setting, `ATTENDANCE_DAILY_START_DATE` (§6).

| Period | Who | Unit | Model | In the app |
| --- | --- | --- | --- | --- |
| before the cutoff | the session's teacher | one session | `SessionAttendance` (archive) | read only |
| from the cutoff on | the class's grade supporter | one class, one day | `DailyAttendanceSheet` + `DailyAttendance` | recorded and edited |

Exactly one of them applies to a date: every page and report reads attendance through `attendance.services` (§4), never from the models directly. The decision and its consequences are ADR-022 (`docs/architecture-decisions.md`).

---

## 2. Models (`attendance/models/`)

### 2.1 DailyAttendanceSheet (`daily_attendance.py`)

The attendance of one class on one day.

| Field | Type | Description |
| --- | --- | --- |
| `school_class` | `ForeignKey(SchoolClass)`, `PROTECT` | Reverse name `daily_attendance_sheets` |
| `date` | `jDateField` | The day (Jalali, like `SchoolSession.date`) |
| `taken_by` | `ForeignKey(User)`, `PROTECT` | Who first saved the sheet |
| `created_at` | `jDateTimeField` | When it was first saved |

* **Constraint:** `unique_daily_attendance_sheet_per_class_day` on `(school_class, date)`.
* **Validation:** a **new** sheet must be for a day `services.day_error` accepts (§5); an existing sheet stays editable even if the timetable or the calendar changed afterwards. `save()` runs `full_clean()` without the unique check: two first saves racing for one sheet are resolved by the database constraint and `get_or_create` (§4.3).

### 2.2 DailyAttendance (`daily_attendance.py`)

One student's status on a sheet.

| Field | Type | Description |
| --- | --- | --- |
| `sheet` | `ForeignKey(DailyAttendanceSheet)`, `CASCADE` | Reverse name `records` |
| `student_enrollment` | `ForeignKey(StudentEnrollment)`, `PROTECT` | Reverse name `daily_attendances` |
| `status` | `CharField` | `present` «حاضر» (default), `absent` «غایب», `late` «تأخیر», `excused` «غیبت موجه» |
| `description` | `TextField`, blank | Reason, arrival time, … |
| `updated_by` | `ForeignKey(User)`, nullable, `SET_NULL` | Who last changed the record **after** the sheet was first taken; empty for a record nobody changed |
| `updated_at` | `jDateTimeField` (`auto_now`) | Last change |

* **Constraint:** `unique_daily_attendance_per_sheet` on `(sheet, student_enrollment)`.
* **Validation:** the student must be enrolled in the sheet's class.
* **Manager:** `DailyAttendanceQuerySet` (`core/querysets/teaching.py`): `for_branch()`, `status_counts()`.

### 2.3 SessionAttendance (`session_attendance.py`) — archive

The former `Attendance` model, renamed. Fields unchanged: `session` (FK `SchoolSession`), `student_enrollment`, `status` (`present` / `absent` / `late`), `description`, `created_at`; constraint `unique_attendance_per_session`; `clean()` refuses holiday sessions and students of another class.

* The table keeps its name, **`attendance_attendance`** (`Meta.db_table`), and every row. Reverse names are now `session_attendances` (on `SchoolSession` and `StudentEnrollment`).
* **Read-only:** no view creates or changes a row; its Django admin is view-only (no add, change or delete). Records dated on or after the cutoff are ignored by every reader.
* **Manager:** `AttendanceQuerySet`: `for_branch()`, `delivered()` (held and compensatory sessions only), `status_counts()` (with `excused` always 0, so both querysets return the same keys).

### 2.4 Migrations

| Migration | What it does |
| --- | --- |
| `0003_rename_attendance_sessionattendance` | Pins `db_table='attendance_attendance'`, then `RenameModel('Attendance', 'SessionAttendance')`, new verbose names and reverse names. **No database change**: no table rename, no row touched. Django renames the content type with it. |
| `0004_daily_attendance` | Creates `DailyAttendanceSheet` and `DailyAttendance` with their constraints. |
| `0005_rename_session_attendance_permissions` | Renames the four permission rows `*_attendance` → `*_sessionattendance`, so groups and users keep what they were granted. Only `auth_permission` rows change. |

There is **no data migration**: archived rows are neither converted nor deleted.

---

## 3. Pages and URLs (`attendance/urls.py`, namespace `attendance`)

| URL | Name | View | Who |
| --- | --- | --- | --- |
| `/attendance/daily/<class_id>/?date=<Jalali>` | `daily_sheet` | `daily_sheet` | the class's supporter, superusers, staff admins (§3.3) |
| `/attendance/<session_id>/` | `session_attendance` | `session_attendance` | the session's teacher, the class's supporter, superusers, staff admins (§3.3) |

`attendance_form` (the old per-session form) no longer exists; its URL now shows the archive.

### 3.1 Daily sheet («حضور و غیاب روزانه»)

* `?date=` is a Jalali date (`1405/08/01`, `1405-8-1`, Persian or Latin digits); missing → today, invalid → today with a message.
* Lists the class's **active enrollments of its academic year** (plus anyone already on the sheet — a student who left keeps their record), by last name. **Everyone starts «حاضر»**; the supporter only marks the exceptions (one radio group per student, `status-<enrollment id>`, and an optional `description-<enrollment id>`).
* **Saving** (`services.save_daily_sheet`): `get_or_create` on (class, day), so saving twice never makes two sheets; the sheet row is locked while records are written. A student without a posted status is «حاضر» on a new sheet and unchanged on an existing one.
* **Revisiting edits the sheet**: the page shows the saved statuses («ذخیره‌ی تغییرات»); changing one (e.g. a student marked «غایب» at 8:30 who arrives at 9 becomes «تأخیر») sets that record's `updated_by`, shown next to the student.
* After saving, a supporter goes back to their attendance page for that day and class (`supervisor:attendance?date=&class=`); an admin stays on the sheet.
* A day that cannot have a sheet (§5) shows the reason and no form; a POST for it saves nothing.
* Same shell and styles as the former attendance page (`attendance/css/attendance.css`, `attendance/js/attendance.js`: live counters, «همه حاضر», search, notes that open for absent / late / excused, no double submit, unsaved-changes warning).

### 3.2 Archived session attendance

* `GET` only (`require_safe`; a POST is 405). Lists the session's records with their status and description and a note that per-session attendance ended on the cutoff date.
* For a session **on or after the cutoff**: its teacher gets **403**; a supporter or admin who may take the class's daily attendance is redirected to the daily sheet of that class and day.
* A holiday session redirects with «… حضور و غیاب ندارد» as before.
* Teachers have no link to it any more (the session list's «حضور و غیاب» button was removed).

### 3.3 Permissions (`attendance/permissions.py`)

| Action | Allowed | Otherwise |
| --- | --- | --- |
| Take or edit a daily sheet (`can_record_daily_attendance`) | a supervisor whose `SupervisorScope` includes the class; a superuser; a staff user with **`attendance.change_dailyattendancesheet`** who may see the class's branch (`core.services.access`) | **403** (logged out: login page) |
| View the archive of a session (`can_view_session_attendance`) | the teacher of the session's class subject; a supervisor of the class; a superuser; a staff user with **`attendance.view_sessionattendance`** and branch access | **404**, so session ids are not revealed |

Teachers, students and the director never take daily attendance (the director's panel is read-only, ADR-020). Roles and `is_staff` stay independent: a system admin («مدیر سامانه») needs the staff flag and the permission.

---

## 4. Services (`attendance/services.py`)

The one place the cutoff is applied. Dates are Gregorian or Jalali; ranges are inclusive, `None` = unbounded.

### 4.1 The cutoff

| Function | Returns |
| --- | --- |
| `daily_start()` | `settings.ATTENDANCE_DAILY_START_DATE` |
| `is_daily(day)` | `day >= daily_start()` |
| `split_range(start, end)` | `(archive part, daily part)`: each a `(start, end)` pair or `None` when the range has no day on that side |

### 4.2 Readers

| Function | Used by | What |
| --- | --- | --- |
| `get_absences(target, start, end, statuses=FOLLOW_UP_STATUSES)` | supervisor follow-up list, director (today's absent students, a student's days) | `AbsenceRecord`s (date, enrollment, status, label, description, `recorded_at`, `session` for archive records) of a `StudentEnrollment`, a `SchoolClass`, a queryset of classes or a queryset of enrollments; by default every record that is not «حاضر»; newest day first, then by name |
| `attendance_counts(target, start, end)` | supervisor dashboard rate, follow-up summary | `total`, `present`, `absent`, `late`, `excused`, `absences` (absent + excused), `rate` |
| `session_counts(session)` | supervisor session drawer | before the cutoff the session's own records; from the cutoff on the class's daily sheet of that day (`daily: True`) |
| `student_tallies(target, start, end)` | director «غیبت‌های پرتکرار» | the counts per student, with names and class |
| `session_tallies(start, end, **lookups)` | `analytics.engine` | per archived session (`session_id, total, absent, late`) |
| `class_day_tallies(start, end, class_ids)` | `analytics.engine`, supervisor overview, `class_day_statuses` | per sheet (`class_id, day, total, absent, late, excused`) |
| `class_day_statuses(start, end, classes, as_of=None, closures=None)` | director panel | `{(class id, day): ClassDay}` from the cutoff to today: **recorded** (a sheet, with its counts), **closed** (every lesson closed, with the event), **missing** (an open lesson and no sheet: a past day at once, today once the first open bell has ended plus the registration grace, `analytics.definitions.slot_deadline`) or **pending** (today, before that). A day without lessons is not in the result. Three queries (timetable, sheets, events) |

The target of the readers that take one (`get_absences`, `attendance_counts`, `student_tallies`) is a `StudentEnrollment`, a `SchoolClass`, a queryset of classes or a queryset of enrollments (the director's frequent absentees: one query for the listed students' days).

Each reader runs one query per side of the cutoff it needs (none for a side the range does not reach). Archived records count only for **held and compensatory** sessions, as before; every daily record counts.

**Across the cutoff** an absence is one missed **session** before it and one missed **day** after it. Counts over a range that spans the cutoff add the two; nothing is converted.

### 4.3 Writing

| Function | What |
| --- | --- |
| `day_error(school_class, day, today=None)` | why the class cannot have a sheet that day (a Persian message), or `None` (§5) |
| `planned_class_days(start, end, classes, closures=None)` | `{(class id, day): closing event or None}` for the days the timetable has a lesson (§5); `closures` when the caller has loaded the range's events already (the director's home page) |
| `sheet_enrollments(school_class, sheet=None)` | the students a sheet lists |
| `save_daily_sheet(school_class, day, user, entries)` | create or edit the sheet: `(sheet, created)` |

---

## 5. Which days have daily attendance

A class can have a sheet on a day when all of these hold (`day_error`, messages in brackets):

1. on or after the cutoff («حضور و غیاب روزانه از … شروع شده است …»);
2. not after today («… روزهای آینده را نمی‌توان ثبت کرد»);
3. inside the class's academic year («این روز در سال تحصیلی این کلاس نیست»);
4. the class's **weekly timetable** (`ClassSchedule`, through `academic_calendar.services.get_slots`) has at least one lesson that day — so the days come from the timetable, not from a fixed list of weekdays; Thursday and Friday never have lessons («این کلاس در این روز طبق برنامه‌ی هفتگی کلاسی ندارد»);
5. at least one of those lessons is **not closed** by the academic calendar: a full-day closure, or closures that together cover every bell the class has that day, mean no attendance («کلاس در این روز به‌دلیل «…» تعطیل است»).

This is the same definition as an **expected class-day** in the analytics engine (`docs/apps/analytics.md` §3.4): a day with at least one open expected slot. The engine additionally waits, for today, until the first open bell is over plus the registration grace before it counts the day as expected (a sheet taken in the morning still counts at once). `class_day_statuses` applies the same wait before it calls a day **missing** (until then **pending**), and is tested to agree with both the engine and the supervisor's overview. The supervisor's overview itself shows «ثبت نشده» without waiting: the supporter takes attendance at 8:30.

---

## 6. Settings

| Setting | Value | Meaning |
| --- | --- | --- |
| `ATTENDANCE_DAILY_START_DATE` | `date(2026, 10, 23)` (1 Aban 1405), in `teachlog/config/settings/base.py` | First day of daily attendance. Before it, every reader uses the archive; from it on, the daily sheets. |

To change it, edit the value in `base.py` (or override it in `development.py` / `production.py`) and restart. Nothing is migrated or recomputed: every page reads it on each request. Moving it **later** makes per-session records up to the new date count again and hides the daily sheets before it; moving it **earlier** does the opposite. Tests override it with `override_settings` (`analytics.tests.DAILY_FROM_SUNDAY_2`).

---

## 7. Admin (`attendance/admin.py`)

* **حضور و غیاب روزانه** (`DailyAttendanceSheetAdmin`): sheets with their records inline, scoped to the admin's branches (`BranchScopedAdminMixin`). The class and day of an existing sheet are read-only; `taken_by` is the admin who adds a sheet, and a record changed here gets `updated_by`. Meant for corrections: a sheet added here has only the records added to it (the sheet page lists the whole class).
* **حضور و غیاب جلسه‌ها (بایگانی)** (`SessionAttendanceAdmin`): view only.

---

## 8. Who reads attendance

| Page | What | Source |
| --- | --- | --- |
| Supervisor attendance page (`/supervisor/attendance/`) | today's (or any day's) classes, recorded or not, and the follow-up list | `class_day_tallies`, `planned_class_days`, `get_absences`, `attendance_counts` |
| Supervisor dashboard | «حضور و غیاب امروز» card, «نرخ حضور دانش‌آموزان» | `attendance_counts` |
| Supervisor session drawer | attendance counts of the session / of the class that day | `session_counts` |
| Director home page | today's absences, classes without attendance, today's absent students | `class_day_statuses`, `get_absences` |
| Director attendance page | absent students per day, the classes table | `class_day_statuses` |
| Director «غیبت‌های پرتکرار» (both pages) | students absent on several days, and their days | `student_tallies`, `get_absences` (a queryset of enrollments) |

The teacher panel and the student panel show no attendance.

---

## 9. Tests

* `attendance/tests.py`: one sheet per class and day, one record per student, the record's class; `day_error` (cutoff, future, timetable instead of weekday, Thursday, full and partial closures, inactive class); `save_daily_sheet` (present by default, editing the same sheet, `updated_by`, kept descriptions, students who join or leave); the sheet page (defaults, saving, editing, invalid dates, days without attendance, empty class); access (logged out, teacher, other supervisor, other class, student, director → 403; superuser and staff admin with permission and branch); the archive page (read-only, POST 405, 403 for teachers from the cutoff on, supervisor redirect, 404 for others, view permission, view-only admin); no attendance link for teachers; the readers across the cutoff and a moved cutoff; the table name.
* `supervisor/test_daily_attendance.py`: overview statuses, summary, archive and future days, the page (links, highlight, follow-up list, default day, query count), the dashboard card and rate, the session drawer.
* `attendance/test_class_days.py`: `class_day_statuses` (the grace, partial and full closures, no lessons, Thursday / Friday, past days, clamping to the cutoff and to today), its agreement with the supervisor's overview and with the engine's expected class-days, `planned_class_days` with preloaded closures, the readers with a queryset of enrollments, `supervisor.selectors.class_supervisors`.
* `analytics/tests.py` (`DailyAttendanceTests`): metrics and groupings across the cutoff. `director/tests.py`: the director's pages (daily attendance only).
