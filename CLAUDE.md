# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Django school management system («TeachLog») for one school with several branches. The UI is entirely Persian (RTL), and dates are Jalali via `django_jalali` / `jdatetime`. Settings use `LANGUAGE_CODE='fa-ir'` and `TIME_ZONE='Asia/Tehran'`. Every user-facing string, label and message must be Persian and match the style of the existing dashboards.

## Commands

The virtualenv is `.venv/`. Settings live in `teachlog/config/settings/`:
- `base.py`
- `development.py`, the default for `manage.py`, which adds `django_extensions` and `django_erd_generator`.
- `production.py`, used by the Dockerfile.

`base.py` loads `.env`. If `POSTGRES_DB` is set it uses PostgreSQL; otherwise it uses `db.sqlite3`.

```bash
# Tests. .env sets POSTGRES_HOST=db (the Docker service name), which doesn't resolve from the host.
POSTGRES_HOST=localhost .venv/bin/python manage.py test --noinput
POSTGRES_HOST=localhost .venv/bin/python manage.py test --noinput attendance                                   # one app
POSTGRES_HOST=localhost .venv/bin/python manage.py test --noinput supervisor.test_daily_attendance.OverviewTests # one class
POSTGRES_DB= .venv/bin/python manage.py test --noinput attendance    # on SQLite, e.g. while a Postgres run is going

.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py runserver
```

Notes on testing:
- Don't use `--parallel`. A known Postgres-only failure, `scheduling.tests.WeeklyScheduleServiceTests.test_invalid_color_in_database_never_reaches_style`, can't be pickled and the error cascades. That test passes on SQLite and is the only expected error.
- The full suite takes about 17 minutes. Run it in the background and grep the log for `^Ran|FAILED|^ERROR:|^FAIL:`.
- Two runs can't share the Postgres test database at once.
- Test files are `tests.py` plus `test_*.py` per app.
- Shared factories are in `core/testing.py` (`make_school_class`, `make_supervisor`, `make_schedule`, …).
- `analytics.tests.Fixture` is a ready-made year, timetable and calendar that the attendance, supervisor and director tests reuse.
- Tests never depend on the real date: they mock `django.utils.timezone.now` and move the attendance cutoff with `analytics.tests.DAILY_FROM_SUNDAY_2`.
- Many views lock their query counts in tests, so a change that adds queries per row will fail them.

No linter or formatter is configured.

Management commands (in `academic_calendar` and `staff`):
- `sync_calendar_sessions` (idempotent)
- `backfill_session_bells` (dry run first)
- `cleanup_redundant_branch_access`

Deployment is `docker-compose.yml`: Postgres, gunicorn and nginx. `migrate` and `collectstatic` are run by hand (`docker compose exec web ...`); nothing runs them automatically. Ask before migrating the local Docker database or touching anything production.

## Architecture

Read `docs/architecture-decisions.md` (ADR-001…022) before changing domain rules; most cross-app behaviour is decided there. `docs/apps/<app>.md` documents each app, and `docs/database.md` / `docs/database-mermaid.md` the schema.

### Domain spine
- `school`: `AcademicYear`, then `SchoolClass`, then `ClassSubject` (class + subject + teacher), the core entity (ADR-005). Data is isolated per academic year, and most entities are soft-deactivated (`is_active`) rather than deleted.
- `scheduling`: the weekly timetable (`ClassSchedule`), with rotation weeks and `Bell`s.
- `teaching`: `SchoolSession` belongs to a `ClassSubject`. A session is identified by `(class_subject, date, bell)` (ADR-016). Counted sessions are renumbered in teaching order on every save or delete (ADR-018), so use ids, never session numbers, as stable references.
- `academic_calendar.services` owns all holiday and closure logic: `Closures`, `get_slots`, `is_working_day` and `match_sessions`. A closed slot becomes an auto-created session with status `HL`, and `SchoolSession.objects.counted()` excludes those (ADR-017). Writes that change which slots are closed must re-sync, as the admin, the importer and `academic_calendar.signals` do.

### Roles and panels
`accounts.User` is the custom user, with `User.Roles`. Each role has its own app and panel:
- teacher: `core` dashboard, `teaching`
- student: `student`
- grade supporter («پشتیبان», `SupervisorProfile`): `supervisor`
- school director: `director`, read-only and GET-only (ADR-020)
- system admin: the Django admin

Role and `is_staff` are independent of each other.

### Branch scoping
- `core.middleware.branch.BranchMiddleware` sets `request.branch`.
- `core.services.access` is the single source of truth for which branches a user may see. It derives this from teaching assignments, `BranchAccess`, supervisor profile and enrolments; nothing should query those directly for access.
- Supervisor queries all start from `SupervisorScope` in `supervisor/selectors.py` (ADR-014). Filters only narrow it, and objects outside it are a 404.
- The director uses its own `?branch=` filter, not `request.branch`.

### Code layout conventions
- Models are packages (`<app>/models/`).
- Query logic lives in `core/querysets/` and `core/managers/`.
- Read-side page data comes from `selectors.py`, writes and rules from `services.py`, access checks from `permissions.py`.
- Views stay thin.

### Metrics
Every metric is defined once in `analytics` (ADR-019) so the director and supporters see the same numbers:
- `definitions.py` holds the rules and imports no models.
- `scope.py` / `engine.compute` makes one pass over slots and sessions.
- `metrics.Breakdown` / `breakdowns()` does the grouping.

Panels choose a scope, a window and a grouping; they never re-derive a rule. A new metric goes into `analytics` and is tested there.

### Attendance
See ADR-022 and `docs/apps/attendance.md`.
- Before `settings.ATTENDANCE_DAILY_START_DATE`, attendance is the archived per-session `SessionAttendance` (table `attendance_attendance`, read-only).
- From that date on, it is `DailyAttendanceSheet` / `DailyAttendance`, one sheet per class per day, taken by the class's supporter.
- `attendance.services` is the only code that reads the cutoff. Every page and the engine get attendance through it.
- «غیبت موجه» (excused) counts as an absence.
- Never convert or delete archived rows.

### Front end
- Server-rendered templates: project-wide ones in `template/`, plus app templates and static files.
- JS enhancement fetches the same URL with `?partial=1` to get just the fragment (ADR-015); every page must work without JS.
- Third-party CSS, JS and fonts are vendored under `static/`; never load from a CDN (ADR-021).
- Check new pages at phone width (375px) for horizontal overflow; on small screens the scroller is `.app-shell`.

## Repo conventions

- Feature work goes on a branch and is merged into `main` with `git merge --no-ff` ("Merge branch '…'").
- Commit subjects are plain imperative sentences, with a bulleted body for larger changes.
- A feature change also updates:
  - the relevant `docs/apps/*.md`
  - `docs/changelog.md`
  - an ADR when a rule changes
  - for larger work, a report in `docs/plans/`
