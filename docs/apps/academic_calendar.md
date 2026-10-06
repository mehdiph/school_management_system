# Academic Calendar App

## 1. Overview

The `academic_calendar` app records the days (or bells) on which the school, or part of it, is closed — official holidays such as Nowruz or Tasua/Ashura, and unplanned closures such as snow or air pollution — and makes every panel reflect them:

* every timetable slot a closure covers gets a **holiday session** (`SchoolSession` with status `HL`, «تعطیل») linked to the event, so teachers, students, supervisors and reports see *why* a lesson did not happen;
* holiday sessions **never count**: they have no session number and are left out of every session count, coverage figure and "missing session" list;
* teachers cannot record a session in a closed slot;
* the teacher's weekly schedule shows each cell as a concrete, dated slot that links to the session form (see [§9](#9-clickable-weekly-schedule-teacher-panel)).

Only the system admin (Django admin) creates or changes calendar data. The other panels only read it, and **always through `academic_calendar.services`**: no view, selector or template decides on its own whether a day is a holiday.

Related documents: [database ER diagram](../database-mermaid.md), [database.md](../database.md), ADR-016 … ADR-018 in [architecture-decisions.md](../architecture-decisions.md).

---

## 2. Business Rules

### 2.1 Working days

* **Thursday and Friday are never working days.** They are not part of the academic calendar. An event whose range covers a Thursday or Friday simply has no effect on those days, and no holiday session is ever created on them.
* A date outside the class's academic year is not a working day either.
* No new timetable slot may be put on Thursday (see [§4.4](#44-classschedule-no-new-thursday-slots)).
* Compensatory sessions («جبرانی», `JB`) **may** be recorded on a Thursday, because make-up classes are often held then. A Thursday is still never auto-cancelled and never counted as an expected slot. Fridays are fully blocked.

### 2.2 Event types

| Value | Label | Typical use |
| --- | --- | --- |
| `official` | تعطیل رسمی | Nowruz, religious holidays (planned ahead) |
| `unplanned` | تعطیلی غیرمنتظره | Snow, air pollution (often entered on the day or after it) |

The type is informational. Both behave the same way.

### 2.3 Scope

An event has three optional scopes. **An empty scope means "all".**

* `branches` — which branches are closed.
* `grades` — which grades are closed.
* `bells` — which bells are closed. Empty means the whole day. A bell scope gives a partial-day closure, for example "closed from the 3rd bell on" is bells 3, 4, …

An event only affects classes of its own `academic_year`. Inactive events (`is_active = False`) have no effect.

### 2.4 Automatic cancellation

For every working date in an active event's range, and every `ClassSchedule` slot that matches:

* the weekday of that date,
* the rotation week (`week_type`) of that date (`BOTH` matches both weeks),
* the event's bell scope,
* an active `SchoolClass` inside the event's branch/grade scope (same academic year),
* an active `ClassSubject` whose `start_date … end_date` contains the date,
* an active bell,
* a date inside the academic year,

there is **exactly one** `SchoolSession` for that slot (`class_subject + date + bell`) with status `HL`, `calendar_event` set to the event and `is_auto_created = True`.

**One subject can be taught more than once a day.** Math at bell 1 and at bell 2 are two slots, so a closed day gives two holiday sessions.

When several active events close the same slot, the one that starts earliest (then lowest id) is the reason.

### 2.5 Numbering

* A holiday session has `session_number = NULL` (enforced by a database check constraint). It never takes a number, so the held sessions stay numbered 1, 2, 3, … without gaps.
* Counted sessions (everything except `HL`) are numbered **in teaching order: date, then bell**. A session without a bell (legacy) sorts first on its day.
* Numbers are recomputed whenever a session is created, deleted, moved (date, bell or class subject) or changes status (`renumber_sessions`). **Recording a session for an earlier date, such as a missed session from last week, shifts the numbers of the later sessions by one.** A session number shown in the past can therefore change.
* Renumbering runs inside the save's transaction with the class subject row locked (`SELECT … FOR UPDATE`). It writes only the rows whose number changes, in two phases (first moved out of the way by a large offset, then to their final values), so the unique `(class_subject, session_number)` constraint holds after every statement.

### 2.6 Excluded from every count

The single exclusion rule is `status != HL`, available as `SchoolSession.objects.counted()` (and `.holidays()` for the opposite). Every session count, "last session", activity date and coverage figure uses it:

| Panel | What excludes holidays |
| --- | --- |
| Teacher | dashboard total, recent sessions, last session number/summary, "recorded today"; profile "sessions this year"; session list total; next session number |
| Student | per-subject session count |
| Supervisor | dashboard summary and statistics, recent sessions, latest session (attendance page), missing-session list, today's count; sessions page counts, first/last dates, KPIs, coverage; teachers page count and last activity; timeline count and gaps |
| Reports | per-subject count, first/last dates, held total |

Holiday sessions are still **listed**, with a badge, the event as the reason, the bell and no number, wherever sessions are listed.

### 2.7 Conflicts (retroactive closures)

If a non-holiday session (held, cancelled or compensatory) already exists for a slot that an event later closes, for example a teacher who recorded the lesson before the closure was announced, the sync **does not overwrite or delete it**. It is reported as a **conflict**:

* in the result of every sync (`SyncResult.conflicts`),
* in the admin message after saving an event ("N تداخل", with a link),
* on the admin page «تداخل‌ها».

The admin decides what to do: fix or delete the session, or change the event's scope.

### 2.8 Editing and deactivating events

Events are never deleted, only deactivated (`is_active = False`). The admin has no delete permission, and sessions keep pointing to their reason. After any change the sync runs again, idempotently, over the old and the new range:

* a holiday session no active event needs any more is **removed only if** it is auto-created **and** has no attendance **and** no content; otherwise it is kept and counted as `kept`;
* a holiday session whose event was deactivated while another active event still closes the slot is moved to that event (`updated`).

### 2.9 Timetable changes

When a `ClassSchedule` row is created, changed (including moved to another class subject) or deleted, or a `ClassSubject`, `SchoolClass` or `Bell` is saved, the holiday sessions of the affected class subjects are re-synced over their academic year **after the transaction commits** (`academic_calendar/signals.py`). The timetable editor's bulk writes (`bulk_create`, `bulk_update`, `update`) queue the same re-sync. Only days that have an event or an existing holiday session are looked at.

### 2.10 Recording sessions

Teachers cannot record a session in a closed slot. This is enforced on the server (see [§9.4](#94-server-side-rules)).

---

## 3. Data Model

### 3.1 `CalendarEvent` (`academic_calendar/models/calendar_event.py`) — new

| Field | Type | Notes |
| --- | --- | --- |
| `academic_year` | FK `AcademicYear` (`PROTECT`) | `related_name="calendar_events"` |
| `title` | `CharField(200)` | shown as the reason everywhere |
| `event_type` | `CharField(20)`, choices `official` / `unplanned` | default `official` |
| `start_date` | `jDateField` | |
| `end_date` | `jDateField` | equal to `start_date` for one day |
| `branches` | M2M `Branch`, blank | empty = all branches |
| `grades` | M2M `Grade`, blank | empty = all grades |
| `bells` | M2M `Bell`, blank | empty = the whole day |
| `description` | `TextField`, blank | |
| `created_by` | FK `User` (`SET_NULL`), nullable, not editable | set by the admin |
| `created_at` / `updated_at` | `jDateTimeField` | |
| `is_active` | `BooleanField`, default `True` | soft delete |

* Check constraint `calendar_event_end_after_start`: `end_date >= start_date`.
* Index `calendar_event_range_idx` on `(academic_year, is_active, start_date, end_date)`.
* `clean()`: the range must be inside the academic year.
* Queryset: `.active()`, `.overlapping(start, end)`.

Dates are stored in Gregorian (as every `jDateField`) and shown in Jalali.

### 3.2 `SchoolSession` (`teaching/models/school_session.py`) — changed

| Field | Change |
| --- | --- |
| `bell` | **new**, FK `scheduling.Bell` (`PROTECT`), nullable: the slot's bell. NULL only on sessions recorded before this field existed. |
| `calendar_event` | **new**, FK `CalendarEvent` (`PROTECT`), nullable: the reason of a holiday session. |
| `is_auto_created` | **new**, `BooleanField(default=False)`, not editable: created by the calendar sync, not by a teacher. |
| `status` | **new choice** `HL` («تعطیل»). |
| `session_number` | now **nullable** (NULL exactly for `HL`). |

Constraints:

* `unique_session_number_per_class_subject` (unchanged): `(class_subject, session_number)`. NULLs do not collide.
* `unique_session_per_slot` (**new**): `(class_subject, date, bell)` where `bell IS NOT NULL`, with the message «برای این درس در این زنگ و این تاریخ قبلاً جلسه ثبت شده است».
* `session_number_only_when_counted` (**new**, check): `status = 'HL'` ⇔ `session_number IS NULL`.
* `clean()`: `HL` requires a `calendar_event`, and a `calendar_event` requires `HL`.

Manager: `SchoolSession.objects.counted()` / `.holidays()` (`core/querysets/teaching.py`).

`Attendance.clean()` refuses attendance on an `HL` session, and the attendance page redirects with a message.

### 3.3 Migrations

| Migration | What it does | Existing data |
| --- | --- | --- |
| `academic_calendar/0001_initial` | creates `CalendarEvent` and its M2M tables | — |
| `teaching/0004_session_slot_and_holiday` | adds `bell`, `calendar_event`, `is_auto_created`; makes `session_number` nullable; adds the `HL` choice; adds `unique_session_per_slot` and `session_number_only_when_counted` | Non-destructive. New columns are nullable or defaulted. Existing rows have a number and no `HL` status, so they satisfy the check. The unique index ignores rows without a bell. |

No data migration runs. The bell backfill is a separate, reviewable command (below).

### 3.4 Backfill of existing sessions (`backfill_session_bells`)

Sessions recorded before this change have no bell. A management command matches them to their timetable slot. It runs as a **dry run by default** and only writes with `--apply`:

```bash
python manage.py backfill_session_bells                    # per-session report only
python manage.py backfill_session_bells --csv bells.csv    # ... also as CSV (UTF-8, opens in Excel)
python manage.py backfill_session_bells --apply            # write the bells found, one transaction
python manage.py sync_calendar_sessions                    # then re-sync the holidays
```

For every non-holiday session without a bell, grouped per class subject and date:

1. **Candidates**: the class subject's `ClassSchedule` rows for that weekday in that rotation week (or every week), in bell order. These come from the timetable **as it is now**, because past timetables are not stored.
2. Bells already used by that class subject's sessions that day are **taken**.
3. If the number of bell-less sessions equals the number of free candidates, they are matched **in numbering order to bells in bell order**.
4. Anything else is **left NULL** with its reason:
   * «جمعه» — Friday;
   * «قبل از شروع سال تحصیلی کلاس» — before the academic year;
   * «این درس در این روز و این هفته زنگی در برنامه ندارد» — no slot that day, for example a compensatory session or a changed timetable;
   * «همه‌ی زنگ‌های این روز قبلاً جلسه دارند» — all candidates taken;
   * «N جلسه‌ی بدون زنگ برای M زنگ آزاد: تطبیق مبهم است» — ambiguous, for example one session recorded for a double period.

The report has one row per session: `session_id, class_subject_id, class_subject, date, weekday, week_type, status, session_number, candidates, taken, result (assigned / left_null), bell_id, bell, reason`.

Sessions left NULL keep working everywhere: the sync, the teacher's week and the supervisor's missing-session list count a bell-less session against that day's first uncovered slot in bell order. A teacher editing one is asked to pick its bell only if they change its date, class subject or status.

---

## 4. Calendar Service API (`academic_calendar/services.py`)

All dates may be `datetime.date` or `jdatetime.date`. The service works in Gregorian internally.

### 4.1 Days, events, closures

| Function | Returns |
| --- | --- |
| `is_working_day(date, academic_year=None)` | `False` for Thursday/Friday and for dates outside the academic year (the given one, else the one containing the date) |
| `is_weekend(date)` | Thursday or Friday |
| `get_week_type(date, academic_year=None)` | `WEEK_ONE` / `WEEK_TWO` (`scheduling.utils.get_week_cycle`), or `None` before the year starts |
| `academic_year_for(date)` | the `AcademicYear` containing the date (the current one wins a tie) |
| `get_events(start, end, branch=None, grade=None, academic_year=None, include_inactive=False)` | events overlapping the range whose scope includes the branch/grade, scope prefetched |
| `closing_event(date, school_class, bell=None)` | the active event closing that class at that bell (or for the whole day when `bell` is `None`), or `None` |
| `is_closed(date, school_class, bell=None)` | `closing_event(...) is not None`. Without `bell`, only whole-day closures count |
| `Closures.between(start, end, academic_year=None, branch=None, grade=None)` | an in-memory index of the range's active events (2–5 queries in total): `.event_for(date, school_class, bell)`, `.is_closed(...)`, `.days()` (covered working days). **Pages that check many cells must use this**, never `is_closed` per cell |
| `parse_jalali_date(text)` | `"1405/07/12"` / `"۱۴۰۵-۷-۱۲"` → `jdatetime.date` (`ValueError` when invalid) |

### 4.2 Slots

| Function | Returns |
| --- | --- |
| `get_slots(start, end, days=None, **filters)` | `[ExpectedSlot(class_subject, date, bell, schedule), …]`, the slots the timetable plans (rules in [§2.4](#24-automatic-cancellation)), **closures not removed**. `filters` are extra `ClassSchedule` lookups, e.g. `class_subject__teacher_assignment__teacher=…`. One query |
| `match_sessions(slot_keys, sessions)` | `{slot key: session}`: which recorded session fills which slot, with the count fallback for legacy bell-less sessions; used by the sync, the supervisor, the teacher dashboard and `analytics.engine` |
| `Closures.events(start, end)` | the loaded events overlapping a range (the director dashboard's upcoming closures) |

### 4.3 Sync and writes

| Function | Returns / does |
| --- | --- |
| `sync_cancelled_sessions(start, end, event=None, class_subjects=None, academic_year=None)` | Idempotent. Makes the holiday sessions of the range match the active events. Returns `SyncResult(created, removed, updated, kept, conflicts)`. `event` narrows the range to the event's dates (all events still apply there). Locks the affected class subjects. Writes holiday rows with `bulk_create` |
| `find_conflicts(start=None, end=None, academic_year=None, event=None)` | `[Conflict(session, event, date, bell), …]`, read-only (admin page) |
| `event_impact(event)` | `(holiday sessions linked to it, its conflicts)` |
| `sync_event(event, previous_range=None)` | re-syncs an event's old and new range. Call **after** its M2M scope is saved |
| `deactivate_event(event)` | soft-deletes and re-syncs |
| `create_closure(*, academic_year, title, start_date, end_date=None, event_type=None, branches=(), grades=(), bells=(), description="", created_by=None)` | creates an event with its scope and syncs, in one transaction. Returns `(event, SyncResult)` |
| `import_events(plan, created_by=None)` | creates every row of a valid import plan and syncs, all or nothing. Returns `(events, SyncResult)` |
| `sync_class_subjects(ids)` | re-syncs these class subjects over their academic years (used by the timetable signals) |

`academic_calendar.signals.resync_later(class_subject_ids)` queues `sync_class_subjects` for after the current transaction commits.

### 4.4 `ClassSchedule`: no new Thursday slots

`ClassSchedule.DayChoices.THURSDAY` stays (legacy rows still display), but a slot cannot **become** a Thursday slot on any write path: `save()`/`clean()`, `bulk_create`, `bulk_update`, `update`, and the admin timetable editor, which only keeps an unchanged legacy Thursday cell. The message is «ثبت برنامه در روز پنج‌شنبه مجاز نیست؛ پنج‌شنبه و جمعه تعطیل هستند.» To find legacy rows:

```bash
python manage.py shell -c "from scheduling.models import ClassSchedule; print(ClassSchedule.objects.filter(day_of_week=5).values_list('pk', 'class_subject_id', 'bell_id', 'week_type'))"
```

---

## 5. Management Commands

### 5.1 `sync_calendar_sessions`

Every admin, import and timetable write already syncs. This command is for repairs (data changed directly in the database, after `backfill_session_bells`) and for previewing.

```bash
python manage.py sync_calendar_sessions                                  # the current academic year
python manage.py sync_calendar_sessions --year 3                         # academic year id 3
python manage.py sync_calendar_sessions --from 1405/07/01 --to 1405/07/30
python manage.py sync_calendar_sessions --dry-run                        # report, then roll back
```

Output: `created=… removed=… updated=… kept_with_data=… conflicts=…`, then one line per conflict. A second run reports `created=0 removed=0`.

### 5.2 `backfill_session_bells`

See [§3.4](#34-backfill-of-existing-sessions-backfill_session_bells).

---

## 6. Excel Import

### 6.1 Where

Admin → تقویم آموزشی (تعطیلات) → «ورود از اکسل» (`/admin/academic_calendar/calendarevent/import/`). The template is generated on the fly (`academic_calendar/import_template.py`) and downloaded from that page's «دانلود قالب اکسل» link (`/admin/academic_calendar/calendarevent/import/template/`, file `calendar-events-template.xlsx`). It reflects the current branches, grades and bells.

### 6.2 Columns

The header row must be exactly these, in this order (`importer.COLUMNS`):

| Column | Required | Accepted values |
| --- | --- | --- |
| عنوان | yes | text, at most 200 characters |
| نوع | yes | «تعطیل رسمی» or «تعطیلی غیرمنتظره» (also «رسمی» / «غیرمنتظره») |
| تاریخ شروع | yes | Jalali `YYYY/MM/DD` or `YYYY-MM-DD`, Persian or Latin digits |
| تاریخ پایان | no | same format. Empty = the start date |
| کد شعبه‌ها | no | `Branch.code` values, comma separated (`,` `،` `;`). Empty = all branches |
| پایه‌ها | no | grade levels (`Grade.level`, e.g. `7`) or grade names. Empty = all grades |
| زنگ‌ها | no | bell orders (`Bell.order`, e.g. `3`) or bell titles. Empty = the whole day |
| توضیحات | no | text |

The template's second sheet «راهنما» lists the types, branch codes, grade levels and bells. The date and code columns are Text-formatted so Excel does not turn `1405/07/12` into a date. If it does anyway, the importer reads the digits back.

Example:

| عنوان | نوع | تاریخ شروع | تاریخ پایان | کد شعبه‌ها | پایه‌ها | زنگ‌ها | توضیحات |
| --- | --- | --- | --- | --- | --- | --- | --- |
| تعطیلات نوروز | تعطیل رسمی | 1405/12/25 | 1406/01/13 | | | | |
| آلودگی هوا | تعطیلی غیرمنتظره | 1405/09/10 | | central, east | 7, 8 | 3, 4 | از زنگ سوم |

### 6.3 Validation

Events are imported into the **current** academic year. Every row is checked before anything is written, and the preview shows each row with all its errors:

* empty or too long title;
* unknown type;
* invalid start or end date;
* end before start;
* range outside the current academic year;
* unknown branch code, grade or bell;
* a branch the (non-superuser) admin cannot access, or an empty branch scope from a non-superuser (only superusers may close all branches);
* a duplicate of an active event of the year (same title, start and end), or of another row of the file.

The whole file is refused (no preview) when it is not a readable `.xlsx`, the headers differ, it has no rows, or it has more than 500 rows.

### 6.4 Confirmation (all or nothing)

The preview keeps the raw cells in the session. «تأیید و ثبت همه» validates them **again**, because something may have changed since the preview, and then, only if no row has an error, `services.import_events` creates every event and syncs the whole imported range **in one transaction**. If anything fails, nothing is saved. The result page shows the events created, the sessions cancelled and any conflicts.

---

## 7. System Admin (Django admin)

| Page | URL | Notes |
| --- | --- | --- |
| Event list | `/admin/academic_calendar/calendarevent/` | title, type, dates, branch/grade/bell scope, «جلسات لغوشده» (holiday sessions), active. Filters: active, type, year, date. Actions: «غیرفعال‌کردن …» and «فعال‌کردن …» (no delete) |
| Add / change | `…/add/`, `…/<id>/change/` | scope as checkboxes. After saving: «رویداد «…»: N جلسه به‌دلیل این رویداد لغو شده است؛ M تداخل … پیدا شد» with a link to the conflicts |
| Quick closure | `…/quick-closure/` | «تعطیلی اضطراری»: title, date, optional end date, branches, grades, bells, description. Type = unplanned |
| Conflicts | `…/conflicts/` | «تداخل‌ها», per academic year: date, bell, class, subject, teacher, number, status, the event, a link to the session |
| Import | `…/import/` | see [§6](#6-excel-import) |

Branch-scoped (non-superuser) admins see events of their branches plus global ones. They may only change events whose branches are all theirs, and must pick at least one of their branches.

`SchoolSessionAdmin` shows the bell and the event. The event, the auto-created flag and the number are read-only, and `SchoolSession.clean()` refuses «تعطیل» without an event.

---

## 8. Panel Behaviour

### 8.1 Teacher

* **Session list** (`/teaching/sessions/<id>`): holiday cards with the «تعطیل» badge, «تعطیل: <event>» as the title, the date and bell, «بدون شماره», and no edit/attendance buttons. «تعداد کل» counts held sessions only.
* **Session form**: has a required «زنگ» field and never offers «تعطیل» as a status. Holiday sessions cannot be edited. The read-only number explains that it follows date and bell order.
* **Dashboard**: each bell is its own session. A double period counts as recorded when both bells are, and «ثبت جلسه» prefills the next open bell. A fully closed lesson shows «تعطیل: <event>» and is not pending. A partly closed one shows «بخشی تعطیل».
* **Weekly schedule**: see [§9](#9-clickable-weekly-schedule-teacher-panel).
* **Attendance**: a holiday session has none («این جلسه به‌دلیل «…» لغو شده است و حضور و غیاب ندارد.»).

### 8.2 Student

* **Session list** (`/student/sessions/`): the per-subject count excludes holidays. The timeline JSON (`/student/api/sessions/<slug>`) flags holidays (`is_holiday`, `reason`), labels them «تعطیل - <date> · <bell>» with no number, and the page shows them hatched with a grey tag. Sessions without content no longer break the endpoint.

### 8.3 Supervisor

What changed:

* **Dashboard**: summary and statistics count held sessions only (no `HL` bucket in `by_status`). Recent sessions and the attendance page's latest session skip holidays. «امروز» counts only open slots, never Thursday/Friday.
* **«نیازمند پیگیری» (missing sessions)**: slots are matched to sessions **per bell**, so two bells of one subject are two expected sessions and recording one does not cover the other. A legacy bell-less session covers the day's first uncovered bell. Closed slots are never reported.
* **Training sessions page**: counts, empty counts, first/last dates and KPIs exclude holidays. A new sortable «تعطیل» column gives the per-class-subject number of sessions cancelled by closures, and the KPI card notes the holidays. **Coverage** ("پیشرفت نسبت به برنامه") expects one session per open timetable slot: no closed slots, no Thursday/Friday, two bells = two. `HL` is not offered as a status filter.
* **Timeline**: holidays appear in place (date and bell order) with «بدون شماره», the badge «تعطیل: <event>» and their reason. Gaps are measured between counted sessions, so a closure neither breaks nor creates a long gap.
* **Session detail**: holiday title, bell, «بدون شماره», the reason.
* **Teachers page**: session count and last activity ignore holidays.

Not present, so not changed: the supervisor panel has no consecutive-absence feature (see [§10](#10-decisions-limitations-and-follow-ups)).

### 8.4 Reports

Class and grade reports (page and PDF) list holiday rows greyed, with «تعطیل» instead of a number and «تعطیل: <event>» as the content. They are not counted.

---

## 9. Clickable Weekly Schedule (Teacher Panel)

### 9.1 Behaviour

`/scheduling/teacher/` shows **one calendar week** (Saturday … Wednesday) with its dates and its rotation week («هفته اول» / «هفته دوم»):

* `?week=<Jalali date>` (any day of the week, e.g. `?week=1405-07-18`). Default: this week. Clamped to the academic year.
* «هفته‌ی قبل» / «هفته‌ی بعد» / «برو به این هفته» links.
* The print layout and the PDF are unchanged: both rotation weeks merged, without dates.

Each lesson in a cell is a **slot** (class subject + date + bell), built by `scheduling.services.build_teacher_week` from `get_slots` and `Closures`, with the week's sessions loaded in one query (fixed number of queries, no N+1).

### 9.2 States

| State | When | Rendered as |
| --- | --- | --- |
| `holiday` | an active event closes the slot | not a link, hatched, «تعطیل: <event>» |
| `registered` | a session exists for that class subject, date and bell (a legacy bell-less session covers the day's first uncovered bell) | a link to the session form (the server refuses it), green, «ثبت شد · جلسه‌ی N» |
| `future` | the date is after today (`timezone.localdate()`) | not a link, faded, tooltip «امکان ثبت جلسه برای تاریخ‌های آینده وجود ندارد» |
| `open` | otherwise | a link to `/teaching/session/<class_subject>?date=<Jalali>&bell=<id>&next=<this week>` |

A session at **another bell** of the same day does not make a slot registered.

### 9.3 Progressive enhancement

Everything works without JavaScript: the cells and the week navigation are real links rendered with their state. `teacher-schedule.js` only adds the day tabs on narrow screens and shows the reason in place as a toast: the "already recorded" error with a «مشاهده‌ی جلسه‌ی ثبت‌شده» link, or the future/holiday reason on tap.

### 9.4 Server-side rules

`teaching.services.slot_errors` is used both by the form (POST) and by the prefill check (GET with `?date=&bell=`). On a refused prefill the teacher is redirected to `?next=` (only a local URL) or to the schedule's week, with a `messages` error.

| Rule | Message |
| --- | --- |
| the class subject is the teacher's own | 404 |
| date ≤ today | امکان ثبت جلسه برای تاریخ‌های آینده وجود ندارد |
| not a Friday | جمعه تعطیل است؛ برای جمعه نمی‌توان جلسه ثبت کرد. |
| Thursday only for «جبرانی» | پنج‌شنبه تعطیل است؛ در پنج‌شنبه فقط جلسه‌ی «جبرانی» ثبت می‌شود. |
| inside the class's academic year | تاریخ جلسه بیرون از سال تحصیلی این کلاس است. |
| inside the class subject's window | تاریخ جلسه بیرون از بازه‌ی تدریس این درس است. |
| bell chosen and active | زنگ جلسه را انتخاب کنید. / این زنگ فعال نیست. |
| slot not closed (any status, `JB` included) | این زنگ به‌دلیل «<event>» تعطیل است؛ امکان ثبت جلسه وجود ندارد. |
| no session in this slot | برای این درس در این زنگ و این تاریخ قبلاً جلسه ثبت شده است (+ «مشاهده‌ی جلسه‌ی ثبت‌شده» link on GET) |
| `HD`/`CD` only in one of the subject's timetable slots that day; `JB` at any bell | «<subject>» در این تاریخ در «<bell>» برنامه ندارد؛ … |

On an edit the rules run only when the class subject, date, bell or status changes, so content can always be corrected. The unique slot constraint and the class-subject row lock back the duplicate rule up against races.

---

## 10. Decisions, Limitations and Follow-ups

**Decisions** (see ADR-016 … ADR-018):

* **`bell` FK on the session, not a `ClassSchedule` FK.** Timetable rows are edited, moved and deleted during the year. An FK to them would either block those edits (`PROTECT`) or lose the session's slot (`SET_NULL`). The date already implies the weekday and rotation week, so `class_subject + date + bell` fully identifies the slot, and bells are stable (soft-deactivated).
* **A dedicated `HL` status rather than `CD` plus the FK.** Teacher-entered `CD` sessions are numbered and counted. A separate value makes `status != HL` the single exclusion rule (`counted()`) instead of a two-column condition every query would have to repeat. `calendar_event` still records the reason.
* **`is_auto_created`** tells sync-created rows apart, so cleanup never touches anything a person created.
* **Renumbering in teaching order** instead of refusing earlier dates. Missed sessions can be recorded later, and numbers stay continuous and chronological, at the cost of past numbers changing.
* **Holiday rows are bulk-created** by the sync (they take no number and every value is checked by the service). Teacher saves go through `save()`/`full_clean()`.
* **Backfill as a reviewable command**, not a data migration.
* **The app is named `academic_calendar`**, because `calendar` would shadow Python's standard library module.
* **Non-superuser admins cannot declare all-branch closures.**

**Limitations / open questions:**

* The backfill and the legacy fallback use the **current** timetable. If a class's timetable changed during the year, older sessions may stay unmatched (reported, left NULL).
* A legacy bell-less session is counted against the day's slots in bell order. It is not stored as occupying a specific bell, so the unique slot constraint does not see it. Running the backfill removes the ambiguity.
* Sync work follows timetable changes after commit, in the request that made the change. A very large re-sync (a whole year for many classes) runs synchronously.
* Deactivating a class subject removes its auto-created holiday sessions without data, past ones included.
* Event scope does not include individual classes. Branch + grade (+ bells) is the finest granularity.
* The «جلسه شماره N» shown on the form before saving is "last + 1". For a past date the saved number may be lower (later sessions shift).

**Follow-ups (out of scope here):**

* A student attendance history page with percentages, where holidays show as «تعطیل» and are excluded from denominators. There is no such page yet.
* Consecutive-absence tracking for supervisors (belongs to the upcoming dashboard phase). It must ignore `HL` sessions, so a closure neither breaks nor extends a streak.
* Clean up any legacy Thursday timetable rows (query in [§4.4](#44-classschedule-no-new-thursday-slots)).
