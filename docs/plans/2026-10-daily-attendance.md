# Daily Attendance by the Grade Supporter: Work Report

Branch `feature/daily-attendance`, on top of `main` (`3edb379`). **Not committed, not pushed, not deployed**; the production database and the local Docker database were not touched (migrations were run on the test database and on scratch SQLite copies only).

Reference documentation: `docs/apps/attendance.md` (models, pages, permissions, the cutoff service, settings), ADR-022 in `docs/architecture-decisions.md`, and the updated `docs/apps/supervisor.md`, `teaching.md`, `analytics.md`, `director.md`, `academic_calendar.md`, `accounts.md`, `database.md`, `database-mermaid.md`, `changelog.md`.

---

## 1. Summary and reasoning

Attendance used to be taken by the teacher in every session (`Attendance`: session × student). That no longer matches the school: some teachers teach every class, and attendance is actually taken **once a day at 8:30 by the grade supporter** («پشتیبان»), who calls the families of absent students the same morning.

From **1 Aban 1405 (23 October 2026)**, set in `ATTENDANCE_DAILY_START_DATE`:

* attendance is **one sheet per class per day** (`DailyAttendanceSheet`), with one record per student (`DailyAttendance`: present / absent / late / excused), taken by the class's supporter;
* everyone is «حاضر» by default and the supporter marks only the exceptions; revisiting the sheet edits it (e.g. absent → late at 9:00) and records who made the change;
* teachers no longer take attendance: after saving a session they go back to their session list, and the attendance buttons are gone;
* the old per-session records are **archived, not converted**: the model is renamed `SessionAttendance`, the table and every row stay as they were, and the app never writes to it again;
* **one service** (`attendance.services`) decides which source a date has — archive before the cutoff, daily sheets from it on — and every page and report reads attendance through it, including the shared `analytics` engine, so the director and the supporters still see the same numbers (ADR-019).

Converting old rows was rejected because a day's status cannot be derived honestly from several sessions (which session's "absent" is the day's?). Archiving keeps history exactly as recorded.

---

## 2. Files changed / added

### Attendance app
| File | Change |
| --- | --- |
| `attendance/models/session_attendance.py` | renamed from `attendance.py`; `Attendance` → `SessionAttendance`, `db_table='attendance_attendance'`, reverse names `session_attendances` |
| `attendance/models/daily_attendance.py` | **new**: `DailyAttendanceSheet`, `DailyAttendance` |
| `attendance/models/__init__.py` | exports; fixed the `__all__ = ['Attedance']` typo |
| `attendance/migrations/0003_…`, `0004_…`, `0005_…` | **new** (§3) |
| `attendance/services.py` | **new**: the cutoff, readers, day rules, saving (§5) |
| `attendance/permissions.py` | `can_record_daily_attendance`, `can_view_session_attendance`, `is_class_supervisor` |
| `attendance/views.py` | `daily_sheet` (new); `session_attendance` (the old form, now read-only) |
| `attendance/urls.py` | `daily/<class_id>/` (`daily_sheet`); `<session_id>/` renamed `session_attendance` |
| `attendance/templates/attendance/daily_sheet.html` | from `attendance_management.html`: four statuses, day switcher, "edited by" marker, error state |
| `attendance/templates/attendance/session_attendance.html` | **new**: read-only archive |
| `attendance/admin.py` | archive admin view-only; new sheet admin with records inline |
| `attendance/static/attendance/css/attendance.css`, `js/attendance.js` | «غیبت موجه» colours and counter, four-option layout, day switcher |
| `attendance/tests.py` | rewritten (§7) |

### Teacher side
| File | Change |
| --- | --- |
| `teaching/views.py` | after creating or editing a session: redirect to the session list |
| `teaching/templates/teaching/session_list.html` | «حضور و غیاب» button removed |
| `teaching/tests.py` | the two redirect assertions |

### Supervisor side
| File | Change |
| --- | --- |
| `supervisor/selectors.py` | `SupervisorAttendanceSelector` rewritten (overview, summary, follow-up), `ClassAttendanceDay`; dashboard rate and today card; drawer counts via the service; `SupervisorScope.attendance()` removed |
| `supervisor/views.py` | attendance page reads `?date=` |
| `supervisor/templates/supervisor/attendance.html` | rebuilt: day picker, class overview, follow-up list |
| `supervisor/templates/supervisor/dashboard.html` | «حضور و غیاب امروز» card |
| `supervisor/templates/supervisor/partials/_session_detail.html` | daily counts after the cutoff |
| `supervisor/templates/supervisor/partials/_attendance_status_badge.html` | **new** |
| `supervisor/static/supervisor/css/attendance.css`, `dashboard.css` | overview cards, day picker, info badge, alert card; the class `<select>` no longer widens the page on phones (§8) |
| `template/partials/sidebar.html` | «حضور و غیاب» also active on the sheet page |
| `supervisor/tests.py`, `test_training_sessions.py` | archive-day page tests, drawer dict |
| `supervisor/test_daily_attendance.py` | **new** |

### Reports and shared layers
| File | Change |
| --- | --- |
| `analytics/definitions.py` | `EXCUSED`, `ABSENCE_STATUSES`; absences = absent + excused |
| `analytics/engine.py` | attendance through the service; `ClassDayRow`, `result.class_days`, `takes_attendance` |
| `analytics/metrics.py` | `excused`, `attendance_expected`, `absences`, `missing_attendance`; class-day grouping (`per_class` keys, `ClassUnit`) |
| `analytics/tests.py` | `DAILY_FROM_SUNDAY_2`, `Fixture.daily()`, `DailyAttendanceTests` |
| `core/querysets/teaching.py`, `core/managers/teaching.py` | `DailyAttendanceQuerySet` / manager; archive `status_counts()` gains `excused` |
| `director/selectors.py` | top absentees and the missing list via the service / class-days; alert «روزهای بدون حضور و غیاب» |
| `director/templates/director/attendance.html`, `partials/_attendance_table.html` | absences, recorded denominator, notes |
| `director/tests.py` | missing-attendance tests rewritten; cross-cutoff page and query-count tests |
| `academic_calendar/services.py`, `tests.py` | reverse name `session_attendances`; model name |
| `teachlog/config/settings/base.py` | `ATTENDANCE_DAILY_START_DATE` |

### Docs
`docs/apps/attendance.md` (new), `docs/plans/2026-10-daily-attendance.md` (this report), ADR-022, and updates to `database.md`, `database-mermaid.md`, `apps/teaching.md`, `apps/supervisor.md`, `apps/analytics.md`, `apps/director.md`, `apps/academic_calendar.md`, `apps/accounts.md`, `apps/scheduling.md`, `changelog.md`.

---

## 3. Models and migrations

| Model | Status | Key points |
| --- | --- | --- |
| `SessionAttendance` | renamed from `Attendance` | table `attendance_attendance` unchanged; read-only; reverse names `session_attendances` |
| `DailyAttendanceSheet` | new | `school_class`, `date` (jDate), `taken_by`, `created_at`; unique `(school_class, date)` |
| `DailyAttendance` | new | `sheet` (`related_name="records"`), `student_enrollment`, `status`, `description`, `updated_by` (nullable), `updated_at`; unique `(sheet, student_enrollment)` |

| Migration | Database effect |
| --- | --- |
| `attendance.0003_rename_attendance_sessionattendance` | **none**: `AlterModelTable` pins the old name, then `RenameModel` (no table rename), verbose / reverse names; Django renames the content type |
| `attendance.0004_daily_attendance` | creates the two tables and constraints |
| `attendance.0005_rename_session_attendance_permissions` | renames the 4 permission rows `*_attendance` → `*_sessionattendance` so existing grants survive; touches `auth_permission` only |

No data migration; no attendance row is converted, changed or deleted.

**Verified on a scratch copy of the local SQLite database** (6 archived rows): after `migrate` the rows are byte-identical (same SHA-1 of every column), the table is still `attendance_attendance`, the two new tables exist, and a group that held `change_attendance` now holds `change_sessionattendance`. `migrate attendance 0002` reverses cleanly with the rows unchanged. `makemigrations --check`: no changes.

Rollback note: migrating back to `0002` **while the new code is checked out** makes Django's `post_migrate` recreate content types / permissions for the code's models, and re-applying then leaves a few stray `*_sessionattendance` permission rows on the daily models' content types (harmless: they grant nothing that exists). A real rollback should migrate back, switch the code, then run `manage.py remove_stale_contenttypes` — or restore the pre-deploy backup.

---

## 4. URLs, views and permission rules

| URL | Name | Who | Others |
| --- | --- | --- | --- |
| `/attendance/daily/<class_id>/?date=<Jalali>` | `attendance:daily_sheet` | supporter whose `SupervisorScope` has the class; superuser; staff with `attendance.change_dailyattendancesheet` and branch access | **403** (teachers, other supporters, students, director); login page if logged out |
| `/attendance/<session_id>/` | `attendance:session_attendance` (was `attendance_form`) | read-only archive for the session's teacher, the class's supporter, superuser, staff with `attendance.view_sessionattendance` and branch access | 404; POST → 405; for a session on/after the cutoff: teacher **403**, supporter/admin → redirect to the daily sheet |
| `/supervisor/attendance/?date=&class=` | `supervisor:attendance` | supporters (`require_supervisor`) | 403 |

Day rules for a new sheet (`services.day_error`): cutoff ≤ day ≤ today; inside the class's academic year; the class's **timetable** has a lesson that day (derived from `ClassSchedule` via `get_slots`, not from a hard-coded Saturday–Wednesday); at least one of those lessons is not closed by the calendar. Same definition as the engine's "expected class-day".

---

## 5. The cutoff: how it works, how to change it

* `teachlog/config/settings/base.py`: `ATTENDANCE_DAILY_START_DATE = date(2026, 10, 23)` (1 Aban 1405).
* Only `attendance.services` reads it (`daily_start()`, `is_daily()`, `split_range()`); every reader splits its range there: archive (held/compensatory sessions only, as before) for dates before, daily sheets from it on. A per-session record dated on/after the cutoff is ignored; a daily sheet before it cannot be created.
* **To change it**: edit the value (or override it in `production.py`) and restart. Nothing to migrate or recompute; pages read it per request. Moving it later re-includes per-session records up to the new date; moving it earlier hides them.
* If go-live slips past Saturday 2 Aban morning (the decision recorded with you: keep 23 Oct, change only if it slips), set it to the first school day the supporters actually record.

---

## 6. Decisions taken (approved plan, plus ambiguities resolved)

Approved: D1 teachers always return to the session list; D2 archive page read-only for everyone, teachers 403 from the cutoff; D3 supporter / superuser / staff admin with permission and branch (not the director); D4 recordable days from the class's timetable + calendar + cutoff ≤ day ≤ today; D5 «غیبت موجه» is an absence; D6 director metrics per class-day, class-level groupings only, missing list = class-days without a sheet; D7 counts across the cutoff are added, not converted; D8 permission codenames migrated.

Resolved during implementation (most consistent with existing code):

1. **Past days are editable** from the cutoff to today (a supporter can fill in a missed morning; corrections after 8:30). Future days are refused.
2. **An existing sheet stays editable** even if the timetable or calendar changed afterwards; only creation checks the day rules.
3. **Who is listed on a sheet**: active enrollments of the class's academic year, plus anyone already recorded on it (a student who left keeps their record).
4. **`updated_by`** is set only when a record changes after the sheet was first taken; the first save is the sheet's `taken_by`. A student added on a later edit (newly enrolled) gets `updated_by` = the editor.
5. **Race safety**: `get_or_create` on (class, day) plus a row lock on the sheet; the model's `save()` leaves the unique check to the database so a racing duplicate resolves to the existing sheet.
6. **Supervisor page default** is today; a day before the cutoff shows the archived records of every session of that class that day (the former page showed only the most recent session).
7. **Session drawer** after the cutoff shows the class's daily sheet of that day (a session has no attendance of its own any more).
8. **Engine "expected class-day" for today** waits until the first open bell is over plus the 15-minute grace (the engine's existing rule); a sheet taken at 8:30 still counts its records immediately.
9. **Director class-subject rows** show only archived attendance (daily attendance has no subject); a note says so; totals and higher levels include daily sheets.
10. **Director query counts**: +1 on the dashboard and +2 on the attendance page when the range spans the cutoff (locked in tests).
11. **Admin**: sheets are editable in the Django admin for corrections; a sheet added there has only the records added to it (the page is the normal path).

---

## 7. Tests

New: `attendance/tests.py` (51 tests: models and constraints, `day_error`, `save_daily_sheet`, the sheet page, access, the archive page and admin, no attendance link for teachers, the readers across the cutoff and a moved cutoff, the table name), `supervisor/test_daily_attendance.py` (15), `analytics.tests.DailyAttendanceTests` (6), director (3 new: archived sessions are not an alert, attendance across the cutoff, query counts across the cutoff). Updated: supervisor attendance-page tests (now on an archive day), teacher redirects, session drawer dict, the two director missing-attendance tests (now class-days).

Everything the task asked for is covered: unique sheet per class/day (`test_one_sheet_per_class_and_day`), permissions (`DailySheetAccessTests`: other supervisor, teacher, student, director → 403), default-present saving, editing a sheet (`SaveDailySheetTests`, `DailySheetPageTests`), the teacher redirect (`teaching.tests`), the service across the cutoff (`ServiceTests`, `DailyAttendanceTests`).

### 7.1 Full run

`POSTGRES_HOST=localhost .venv/bin/python manage.py test --noinput` (PostgreSQL, 23 Oct 2026):

| Run | Tests | Result |
| --- | --- | --- |
| Baseline, `main` before any change | 631 | 1 error: `scheduling.tests.WeeklyScheduleServiceTests.test_invalid_color_in_database_never_reaches_style` (known, PostgreSQL only: it writes more than 7 characters into `Subject.color varchar(7)`) |
| This branch | **689** (+58) | the same single pre-existing error, nothing else |

After the last template / CSS touches (sidebar highlight, phone layout), `supervisor`, `attendance` and `teaching` were re-run on SQLite: 214 tests, OK.

The pages were also checked in headless Chrome against a scratch database (desktop 1280 px and phone 375 px): the supervisor's attendance page and the sheet page have no horizontal scroll; two layout fixes came out of it (spacing in the follow-up section, «غیبت موجه» on one line).

---

## 8. Discrepancies found between docs and code

* `docs/project-overview.md` is empty.
* There was no `docs/apps/attendance.md`; `docs/database.md` had no Attendance section and described `enrollment_date` / `status` on `StudentProfile`, where the code has `StudentEnrollment` (now documented; the old StudentProfile table was left as is, with a pointer).
* `attendance/models/__init__.py` exported `'Attedance'` (typo; fixed).
* `docs/apps/supervisor.md` said "Everything in it is read-only" (no longer true; updated).
* There was **no** validation requiring attendance before a session can be completed, so nothing to remove (task A.4).
* Not a doc issue, found while checking the pages in a browser: on a 375 px phone the **old** supervisor attendance page was 59 px wider than the screen (the class `<select>`'s longest option set the page's minimum width). Fixed for the rebuilt page.
* Before starting, `attendance/` contained compiled files for a `0003_dailyattendance` migration and a `daily_attendance` model with no source anywhere (timestamped 23 Oct 08:23). Neither local database had applied them; deleted on your instruction.

---

## 9. Open questions and manual actions before / on 1 Aban

1. **Today is the cutoff** (Friday, no school). Deploy before Saturday 2 Aban 8:30, or move `ATTENDANCE_DAILY_START_DATE` to the real first day. Any per-session attendance a teacher records in production on/after the cutoff before deploy will be ignored by every report.
2. **Run the migrations in production** (`attendance` 0003–0005) during the deploy; take a database backup first.
3. **Assign every class to its supporter** (`SupervisorClass` in the admin) and check each supporter's `branch` and `grade`: a class without a supporter can only be recorded by an admin, and appears as missing on the director's list.
4. **Brief the supporters**: daily routine at 8:30 from «حضور و غیاب» in their panel; everyone starts present, mark only absences / lateness / excused; revisit to change a status when a student arrives late; the dashboard card shows classes still missing.
5. **Brief the teachers**: they no longer take attendance; after saving a session they return to the session list.
6. **Staff admins** who should correct sheets need `attendance.change_dailyattendancesheet` (and `view_sessionattendance` to read the archive); existing grants on the old model carry over by `0005`.
7. **Timetables must be complete**: a class with no timetable for a day cannot have a sheet that day (by design, D4).
8. **Daily summary table** (due before 1 Dey 1405): its spec in `docs/apps/analytics.md` §8 now needs a per (day, class) part for daily attendance — updated in the spec.
9. Open: should a sheet still missing at, say, 9:00 also appear in the supporter's «نیازمند بررسی» list and its sidebar badge? Not done; the dashboard card and the highlighted overview cover it for now.
10. Open: the follow-up dialog is still UI only (no follow-up record is stored), as before.
11. Not committed: the branch has uncommitted changes, ready to review and commit when you want.
