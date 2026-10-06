# [0.1.0] - 2026-02-07

## Added

### Teacher Dashboard

- Each day schedule
- Submit sessions
- Get Report from sessions

# [0.2.0] - 2026-06-07

### Student Dashboard

- Weekly schedule page
- Subject-based session history
- Homework overview

### Documentation

- README
- Database documentation
- Architecture decisions document

# [Unreleased]

## Added

### Director Panel (Phase 1, read-only analytics)

- New role «مدیر مدرسه» (`User.Roles.DIRECTOR`, migration `accounts/0004_director_role`, choices only); the system admin's role is relabelled «مدیر سامانه»
- `director` app at `/director/`: only the director and superusers; other roles are sent to their own dashboard; GET only
- Dashboard: active students, classes, teachers; attendance, execution and content rates with the change vs the previous period of as many teaching days; both branches side by side; teaching days elapsed / remaining, days lost to closures and closures of the next 30 days; alerts (classes under 85% attendance and teachers with 3+ unregistered slots over the last 7 teaching days, held sessions without attendance after a day, conflicts with the calendar), thresholds in settings
- Execution page: expected slots held / cancelled by the teacher / unregistered, lost to closures, compensatory sessions and makeup coverage; drill-down branch → grade → class → class subject, a per-teacher view, the same subject across the classes of a grade, the conflicts
- Attendance page: daily attendance rate with closure days marked (Chart.js, with a table twin), comparison by branch → grade → class, students with the most absences, sessions without attendance
- Filters on every page as GET parameters (presets, custom Jalali range, branch, grade); empty states; usable on a tablet; a fixed number of queries per page, locked in tests
- `analytics` app: the single definition of every metric (scope, slot engine, breakdowns, teaching days, previous period); `academic_calendar.services.match_sessions` (the legacy bell-less fallback, now shared by the sync, the supervisor and the teacher dashboard); `AttendanceQuerySet.delivered()` / `status_counts()`
- Chart.js 4.5.1 vendored under `static/vendor/chartjs/`
- Documentation: `docs/apps/analytics.md`, `docs/apps/director.md`, ADR-019 to ADR-021, `docs/plans/director-dashboard.md`

### Academic Calendar (holidays and closures)

- `academic_calendar` app with `CalendarEvent`: official holidays and unplanned closures, scoped by branches, grades and bells (empty = all), soft-deleted with `is_active`
- Automatic «تعطیل» (`HL`) sessions for every closed timetable slot (class subject + date + bell), linked to the event; never numbered, excluded from every session count (`SchoolSession.objects.counted()`); idempotent sync (`academic_calendar.services.sync_cancelled_sessions`) after event, import and timetable changes; held sessions in closed slots are reported as conflicts, never overwritten
- System admin: event list with cancelled-session counts and deactivate/activate actions, impact message after saving, «تعطیلی اضطراری» quick form, «تداخل‌ها» conflicts page, Excel import with a downloadable template, per-row validation preview and all-or-nothing confirmation
- Management commands `sync_calendar_sessions` (`--from/--to`, `--year`, `--dry-run`) and `backfill_session_bells` (dry run by default, per-session report, `--csv`, `--apply`)
- `SchoolSession.bell`, `calendar_event`, `is_auto_created`; unique `(class_subject, date, bell)`; migration `teaching/0004_session_slot_and_holiday`
- Teacher weekly schedule shows one dated week with previous/next navigation; every lesson links to the session form for that slot, and future, already recorded and holiday slots say why they cannot be recorded (works without JavaScript)
- Session form: required bell, prefill from `?date=&bell=`, and server-side slot rules (not in the future, no Friday, Thursday only for compensatory sessions, not closed, not already recorded, held sessions only in timetable slots)
- Supervisor training sessions page: per-class-subject «تعطیل» column and KPI note
- Documentation: `docs/apps/academic_calendar.md`, `docs/database-mermaid.md` (ER diagram), ADR-016 to ADR-018

### Supervisor Panel

- Training sessions page (جلسات آموزشی): sessions per teacher, subject and class, with GET filters (academic year, teacher, subject, class, Jalali date range with week / month / year shortcuts, status), KPI cards, sorting, pagination and progress against the weekly timetable
- Session timeline per class subject, expandable in the table or as its own page, marking sessions without content and long gaps
- Session detail in a drawer or as its own page, with content, homework, activity, notes and attendance counts
- Supervised teachers page (معلمان من): cards or table, search, subject / year filters, sorting, session statistics and an inactivity marker, linking to the teacher's sessions
- Database index on `SchoolSession(class_subject, date)`

## Fixed

- The student dashboard and session list no longer load Font Awesome from cdnjs (the vendored copy in `static/assets` was already loaded)
- The student session list JSON no longer fails on sessions without content

- The attendance page (`/attendance/<session id>/`) required no login and no ownership: it now needs a login and is limited to the session's teacher, a supervisor of its class, a superuser, or a staff admin with `attendance.change_attendance` on the class's branch (`attendance/permissions.py`); anyone else gets 404

## Changed

- Supervisor training sessions «پیشرفت» column is the analytics engine's execution rate, the number the director dashboard shows: expected slots held by a session recorded in that slot (HD, or JB in a regular slot), over open expected slots; a slot of today counts once its bell ended + 15 minutes. It used to count every HD + JB session of the range (sessions on days without a slot, Thursday compensatory sessions and sessions in closed slots included), so it could pass 100%. `academic_calendar.services.count_open_slots` and the `delivered_count` annotation are removed
- One attendance rate everywhere: records that are not absent (present **and late**) over all records of held and compensatory sessions (`analytics.definitions.attendance_rate`). The supervisor dashboard's «نرخ حضور دانش‌آموزان» used to count «حاضر» only (late lowered it) and included records of cancelled sessions; it now shows the same number as the director dashboard
- Session numbers follow teaching order (date, then bell) and are renumbered on every save/delete: recording a missed past session shifts the later numbers
- Teacher dashboard: each bell is its own session (a double period is recorded when both bells are); closed lessons are shown and are not pending
- Supervisor «نیازمند پیگیری» matches sessions per bell and never reports closed slots; coverage leaves closed slots, Thursdays and Fridays out; the timeline orders by date and bell and shows holidays without counting them
- Student and teacher session lists, supervisor timeline/detail and reports show holiday sessions with their reason and no number
- No new timetable slot may be put on Thursday (model, bulk writes and the admin timetable editor)
- Supervisor pages redirect logged-out users to the login page instead of returning 403

### Documentation

- `docs/apps/supervisor.md`, ADR-014 and ADR-015
