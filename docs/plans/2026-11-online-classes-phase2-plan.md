# Plan: online classes and announcements, Phase 2 of 3

Status: **awaiting approval.** Planned in two parts, implemented and merged separately:

- **Part A (admin and student side):** §1 series, §2 groups, §3 «جدید» / «تغییر کرد», §4 open tracking, §5
  acknowledgements. Reports are in the Django admin only. Branch `feature/online-phase2-a`, from `main` after
  approval. I stop for your review after Part A, and Part A is merged into `main` on its own.
- **Part B (other panels):** §6 authoring by teachers and supervisors, and the open and acknowledgement reports in
  their panels. Branch `feature/online-phase2-b`, from `main` after Part A is merged.

Builds on Phase 1 (`2026-11-online-classes*`), the allowed-domains fix (`2026-11-online-domains*`), the audience
lists (`2026-11-online-audience-lists*`), `docs/apps/online_classes.md` and ADR-027. Still no notifications and no
scheduler.

## 0. Baseline and findings

| Run on `main` (f870e93) | Result |
|---|---|
| Full suite, PostgreSQL | **Not run: blocked.** Postgres closes the connection at once. The VPN interface `singbox_tun` holds `172.18.0.1/30`, so traffic to the `db` container (`172.18.0.3`) goes into the tunnel; the same cause as on 2026-10-26. I haven't touched Docker or the VPN. Once the VPN no longer takes that range, I run it before implementing and add the result here. |
| Full suite, SQLite | **1349 tests OK** (1 skipped: `scheduling/test_conflicts.py`'s `select_for_update` test, which SQLite can't run), 19.6 min. No failures. |

Findings from reading:

1. **The calendar's sync already has one entry point for closure changes.** Every closure write (admin save and
   deactivate, quick closure, Excel import, `sync_calendar_sessions`) ends in
   `academic_calendar.services.sync_cancelled_sessions`. Timetable changes reach it too, through
   `sync_class_subjects` with `class_subjects=`. A signal sent from there when `class_subjects is None` lets
   occurrences follow closures, and `academic_calendar` never imports this app (D4).
2. **Closures are per class, and audiences aren't.** A `CalendarEvent` covers classes by year, branch and grade,
   and optionally by bell. An online occurrence reaches whatever its audience reaches, possibly several branches.
   A closure that covers some of those classes and not others needs a rule (D4).
3. **Thursday and Friday:** the calendar gives closures no effect on those days, and the timetable refuses new
   Thursday slots. Online classes may differ (D6, policy).
4. **Personal rows are keyed to one event.** The unique `(event, student)` constraint, the importer, the reveal
   page, `reencrypt_online_access`, the audience list's `access_id` subquery and the student page's row query all
   assume `event`. Series-level rows must fit into these paths, not into copies of them (D3).
5. **Locked query counts that this changes:** the event page (25), the announcement page (19), the audience list
   page (18), and the student online page (`LOCKED_PAGE_QUERIES = 13`). The sidebar badge (§3) adds queries to
   every student page that renders the sidebar, so other apps' student tests with locked counts change too. Every
   lock is updated with the reason in the test, never removed.
6. **On deploy, every upcoming event would be «جدید» to every student** unless the rule limits it, since no
   last-seen rows exist yet (D10).
7. **`student.context_processors.student_info`** reads an enrolment with its own rule (newest active), not
   `current_enrollment`. The badge uses `current_enrollment`, as the online pages do. I won't change
   `student_info`.

## 1. Decisions (please confirm)

### Recurring classes (§1)

- **D1, concrete occurrences.** A series (`OnlineSeries`) generates real `OnlineEvent` rows, one per date, each
  with `series` and `occurrence_date` (unique together).
  - **Why concrete:** opens, acknowledgements, the change log, last-seen rows and access rows all need an event id.
    `audience.visible_to`, the tabs, the student cards and the admin keep working unchanged, and an occurrence can
    be edited or cancelled like any event. A year of a twice-weekly class is about 60 rows.
  - **Rejected, virtual occurrences** (a rule plus an exceptions table): every reader would need to expand dates,
    and anything recorded per occurrence would have to key on (series, date) instead of an event.
  - **Generation:** the whole date range at once, no horizon. Only occurrences that haven't ended yet are created,
    so a series entered mid-week doesn't make past rows.
- **D2, what a series edit changes.** "Future" means not started yet; started occurrences never change.
  - **Fields taken from the series:** title, type, platform, subject, class subject, description, access mode,
    link, leads, start and end time, and audience (including groups).
  - **Fields the series never changes:** an occurrence's status and status note, and its `is_active`.
  - **Editing an occurrence on its own** marks it «جدا از سری» (`detached`). The series then leaves its fields
    alone; status and closures still apply. The occurrence page shows this and offers «برگرداندن به سری», which
    applies the series' current values again.
  - **Dates that drop out** (a shorter range, a weekday removed): future occurrences that aren't detached are
    deactivated (`is_active=False`; events are never deleted). Detached ones are kept and listed as a warning on
    the series page.
  - **One time for all weekdays.** A class at different times on different days is two series.
  - **Range:** inside one academic year (the one containing the start date), so closures can be read for it.
- **D3, personal access for a series.** `OnlineEventAccess` gets a nullable `series` beside `event`.
  - **Constraints:** exactly one of the two is set, plus unique `(event, student)` and `(series, student)`, each
    conditional.
  - **The rule:** for occurrence O of series S and student X, the row used is **O's own row for X if there is one,
    otherwise S's row for X**. The whole row wins, not field by field, because merging a link from one row and a
    password from another would confuse everyone.
  - **Where series rows are managed:** the series page's audience summary and list page («با ردیف / بدون ردیف»,
    «افزودن ردیف» with `next`), the Excel template and import on the series page, reveal, and
    `reencrypt_online_access`. All of these reuse the existing code with a row owner (event or series) in place of
    the event.
  - **An occurrence's counts:** a student without a row is one with neither an occurrence row nor a series row.
  - **The student page** still reads all of a student's rows in one query (`event in … OR series in …`).
  - **Clearing rows:** «حذف دسترسی‌های شخصی» on a series works once its last occurrence has ended.
  - **Rejected, a separate `OnlineSeriesAccess` table:** it would need a second reveal page, re-encryption, masking
    and import path.
- **D4, closures (technical, with a policy edge).**
  - **The signal:** `academic_calendar` gets one signal, `closures_synced(start, end, academic_year)`, sent by
    `sync_cancelled_sessions` inside its transaction when it wasn't narrowed to class subjects.
    `online_classes` connects to it, so `academic_calendar` doesn't import `online_classes`. A dry run of
    `sync_calendar_sessions` rolls back both together.
  - **When a day counts as closed:** a closure applies to an occurrence when one active **whole-day** closure (no
    bell scope) covers **every class** its audience reaches on that date, read through `Closures`.
  - **Bell-scoped closures** are ignored, because online times aren't bells.
  - **A closure covering only part of the audience** leaves the occurrence scheduled. The series page lists it as
    «تعطیلی بخشی از مخاطبان», so the admin can cancel it by hand or narrow the audience.
- **D5, cancelled by a closure versus by hand.**
  - **Cancelled by a closure:** status «لغو شده», the closure's title as the note, and `closure` set to that
    `CalendarEvent`.
  - **When the closure goes away,** the occurrence returns to scheduled and its note is cleared, but only if it
    still points at that closure and nobody changed its status since.
  - **A status set by hand** (`status_by_hand`) is never changed by the sync, either way.
  - **The command:** `sync_online_series [--series ID] [--dry-run]`, idempotent, on the `sync_calendar_sessions`
    pattern. It runs generation and closures, and a second run reports no changes.
- **D6, Thursday and Friday [policy].**
  - **Proposed:** a series may include Thursday and Friday (online extras often fall on the weekend), and the form
    shows a note when it does.
  - **Closures there:** none, which follows the calendar's own rule that closures have no effect on those days.
  - **The alternative:** refuse Thursday, as the timetable does.

### Groups (§2)

- **D7, groups as a target.**
  - **The model:** `StudentGroup` (name, branch, academic year, members, active, description).
  - **The target:** `AudienceTargets.groups` is one more M2M, and `audience.py` gets one more term ("the student is a
    member of a selected active group of the current year"). The term is added in `visible_to`,
    `reached_enrollments`, `touching_branches` (the group's branch), `wholly_within` (every group in the admin's
    branches) and `targets_problems`.
  - **The current-enrolment rule still applies,** so a member who has left receives nothing.
  - **Members:** they must be currently enrolled in the group's branch when added. A member who later moves branch
    stays listed but is shown as «خارج از شعبه‌ی گروه» on the group page.
  - **Breakdown, summary and list page:** the per-class counts include group members with no extra code, because
    they come from `reached_enrollments`. The «مخاطبان» column names the groups.
- **D8, the groups picker.** Autocomplete from the start, scoped to active groups of the current year in the admin's
  branches (superuser: all), not checkboxes with a limit to watch. The cost is one select2 field.
  - **The members picker** is the same scoped student autocomplete (`pickers.py`, a new source
    `("studentgroup", "members")`).
  - **The group page** shows a member count and links to a paginated member list, like the audience list page.

### «جدید» and «تغییر کرد» (§3)

- **D9, the change log** (`OnlineEventChange`: event, kind, the student for a personal-row change or nobody for
  everyone, who, when, and old and new text).
  - **What it records:**

    | Kind | Changes | Values stored |
    |---|---|---|
    | زمان | start, end | old → new |
    | لینک | event link, platform | `••••••` only |
    | وضعیت | status | old → new, with the note |
    | اطلاعات ورود | a personal row's link, username, password or code | `••••••` only; for that student only |

  - **Where changes come from:** every write path calls one service function: the admin, a series sync, a closure
    sync, access rows (inline, add page, import), and Part B's pages.
  - **Who:** a sync's changes are recorded with no user and the reason «تقویم» or «سری».
  - **Where it shows:** the event page lists the latest changes in a closed `<details>`, at a fixed query cost.
- **D10, «جدید» / «تغییر کرد: زمان / لینک / وضعیت / اطلاعات ورود».**
  - **What a student sees:** an event they have never seen is «جدید», but only if it was created within
    `ONLINE_NEW_DAYS` (proposed 7). Otherwise it is «تغییر کرد: …», listing the kinds recorded since they last saw
    it.
  - **Why the 7-day limit:** it stops the deploy from marking every existing event new (finding 6).
  - **When an event counts as seen:** when its card is rendered on `/student/online/`. That is
    `OnlineEventSeen(event, student, last_seen_at)`, one row per pair, written by one bulk upsert per page load,
    and only when a shown card was new or changed. The dashboard card shows the marks but doesn't clear them, so a
    parent who taps through still sees what changed.
  - **Queries:** the flags are subqueries in the existing events query, adding none. The write adds one, and only
    when needed.
- **D11, the sidebar badge.** «کلاس‌های آنلاین» shows a count of today's and upcoming events, not ended, that are new
  or changed for the student.
  - **How it's computed:** a lazy context value (`SimpleLazyObject`, like `blog_can_write`), read only in the
    student branch of the sidebar.
  - **Cost:** two queries (the current enrolment, then one count) on student pages that render the sidebar, and
    none elsewhere.
- **D12, the urgent banner offer [policy: N].**
  - **The checkbox:** «ساختن اطلاعیه‌ی فوری برای مخاطبان این رویداد» appears on the event form when the admin has
    `add_announcement`. It's acted on only if the time, link or status changed and the event starts within
    `ONLINE_URGENT_CHANGE_HOURS` (proposed **24**). In any other case it does nothing, and a message says why.
  - **The banner it creates, in the same transaction:**
    - level «فوری», linked to the event;
    - the event's audience (groups included);
    - shown from now until the event's end;
    - the text names what changed («زمان این کلاس تغییر کرد»), never a link or a secret.

### Opens and acknowledgements (§4, §5)

- **D13, the join view.** `/student/online/<id>/join/` records the open and then redirects.
  - **Which rules it checks:** the same function the card uses (audience, current enrolment, join window, status).
    Outside those rules it returns 404 and never redirects.
  - **Response headers:** `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.
  - **No personal link in our own URLs or logs.** Our own URL carries only the event id. Nothing the app logs
    contains the target.
  - **«آزمایش ورود»** goes through the same view with `?test=1`. That is checked against the credentials window and
    isn't counted as an open.
  - **What's stored:** `OnlineEventOpen(event, student, first_opened_at, last_opened_at, count)`, one row per pair.
    Updates use `F()`, with `get_or_create` on the unique pair for the first open.
- **D14, the open report** (Django admin, in Part A).
  - **Where it lives:** in the existing summary, breakdown and list page. Counts are «مخاطب · باز کرده · باز نکرده»,
    plus «بدون ردیف» for personal events.
  - **The list page:** a filter «باز کرده / باز نکرده», and «خروجی اکسل» exporting the current filters with
    names, codes, class, first and last open, and count.
  - **Who sees it:** the superuser, and staff with a new permission `online_classes.view_open_report` (granted by
    hand), always within their branches (audience-lists D1).
  - **The page says** «باز کردن لینک به معنی حضور در کلاس نیست».
- **D15, acknowledgement.** `Announcement.requires_ack` and `AnnouncementAck(announcement, student,
  acknowledged_at)`, unique per pair.
  - **On the banner:** «متوجه شدم» is a plain POST form, so it works without JS. While not acknowledged, the banner
    can't be closed.
  - **Pressing it acknowledges and, if the banner may be closed, also closes it** (one tap for a parent). An
    urgent banner stays, showing «تأیید شد», until its window ends.
  - **Order:** unacknowledged banners come right after urgent ones, so the cap can't hide them.
  - **The report:** the same summary and list page pattern, with «تأیید کرده / تأیید نکرده» and Excel. Permission:
    `online_classes.view_open_report` covers both reports.

### Part B (§6)

- **D16, the authoring area.** «کلاس‌های آنلاین من» lives in each role's shell (`panel_base`, as the blog's «نوشته‌های من»):
  `/online/manage/…` views in this app, using the same forms, `audience.py` and services as the admin.
  - **Teachers:** events only. The audience is classes of their active class subjects in the current year, with
    optional excluded students from those classes.
  - **Supervisors:** events and announcements. The audience is their `SupervisorScope` classes.
  - **Editing:** each edits and reports only on items they created and still own by these rules.
  - **Platforms** stay admin-only, chosen from the active ones.
- **D17 [policy], announcements by supervisors.** Proposed: they show without approval, but are limited to «اطلاع‌رسانی» and
  «مهم» (no «فوری»), with no image. The alternative is admin approval (a `pending` status and an admin queue).
- **D18 [policy], personal rows by teachers.** Proposed: teachers and supervisors may enter rows and import Excel
  for their own personal events, but never reveal (reveal stays `view_access_secret`, admin only).
- **D19 [policy], the director.** Proposed: yes, read-only and GET-only (ADR-020). Per-event open and acknowledgement
  counts by class, with the director's `?branch=` filter; no names list and no export. The alternative is not to
  show them.

## 2. Implementation outline

### Part A

- **Models and migrations** (`online_classes` 0003…, schema only, no data written):
  - **New models:** `StudentGroup`, `OnlineSeries` (an `AudienceTargets` subclass), `OnlineEventChange`,
    `OnlineEventSeen`, `OnlineEventOpen`, `AnnouncementAck`.
  - **`groups` M2M on `AudienceTargets`:** this adds tables for events, announcements and series.
  - **`OnlineEvent`:** `series`, `occurrence_date`, `detached`, `status_by_hand`, and `closure` (FK to
    `academic_calendar.CalendarEvent`, `SET_NULL`).
  - **`OnlineEventAccess`:** `event` becomes nullable, plus `series`, with the constraints in D3.
  - **`Announcement`:** `requires_ack`.
  - **New permission:** `view_open_report`.
- **audience.py:** the groups term, applied in both directions and in the branch rules. `access_rows(item)` (an
  occurrence's rows plus its series' rows, or a series' rows) replaces `_has_row` and the list page's subquery.
  `breakdown` and `students` take optional open and ack annotations, still one aggregate query.
- **Services:**
  - **`series.py`:** `sync_series(series)` and `sync_closures(start, end, year)`, both idempotent, under a row lock
    on the series.
  - **`changes.py`:** `record(event, before, after, user)` and `urgent_banner(...)`.
  - **`services.py`:** `record_open`, `acknowledge`, `mark_seen`.
- **`academic_calendar`:** the `closures_synced` signal, sent in `sync_cancelled_sessions`. No other change there.
- **Management command:** `sync_online_series`.
- **Admin:**
  - **Series:** fields, audience (mixin), «پیش‌نمایش تاریخ‌ها» on save (created, updated, deactivated, cancelled
    by closure, partly closed), occurrences list linked, rows, import.
  - **Groups:** the members picker and member list.
  - **Event page:** detached / back to series, the change log, the urgent checkbox, and open counts.
  - **Announcement page:** `requires_ack`, ack counts.
  - **List pages:** the open and ack filters and the Excel export.
- **Student side:**
  - the join view, and cards linking to it;
  - «جدید» and «تغییر کرد» marks;
  - the «متوجه شدم» form;
  - the sidebar badge (`online_classes.context_processors.unseen`).
- **Settings:** `ONLINE_NEW_DAYS` (7) and `ONLINE_URGENT_CHANGE_HOURS` (24), read in one place.

### Part B

Authoring views, forms and templates in `online_classes` (`authoring/`, permissions in `online_classes/permissions.py`),
sidebar items in the teacher and supervisor sidebars, report pages in each shell, and (if D19 is approved) one
director page. The detailed outline is written into this plan after Part A is merged.

## 3. Tests (Part A)

- **Series:**
  - generation is idempotent (a second sync changes nothing; the same for the command, with and without
    `--dry-run`);
  - weekday and date edges;
  - only future occurrences are created or changed; started ones stay as they were;
  - detached occurrences are left alone; «برگرداندن به سری» applies the series again;
  - dates that drop out are deactivated;
  - the academic-year range check.
- **Closures:**
  - create, edit, deactivate and import a closure, and check that occurrences follow it;
  - a partial closure keeps the occurrence and warns;
  - bell-scoped closures are ignored;
  - a status set by hand is never changed;
  - `academic_calendar` doesn't import `online_classes`;
  - a timetable change doesn't re-sync occurrences.
- **Rows:**
  - the occurrence-over-series rule;
  - the counts, list page, import and add page on a series;
  - reveal and re-encryption of series rows;
  - the constraints.
- **Groups:**
  - `visible_to` and `reached_enrollments` still agree over the target matrix, with groups added to it;
  - branch rules and forged ids;
  - the group page's size and query count don't grow with the number of students.
- **Changes and seen:**
  - each kind is recorded, with masking;
  - «جدید» and «تغییر کرد» marks;
  - the `ONLINE_NEW_DAYS` boundary;
  - one write per page, and none when nothing is new;
  - the badge's count and its fixed query cost;
  - the urgent banner offer inside and outside N hours, and without permission.
- **Opens:**
  - the join view checks every rule (audience, no enrolment, before the window, after the end, cancelled,
    postponed, personal with no row, info-only), and outside them gives a 404 with no redirect;
  - the test mode;
  - the counters;
  - no personal link in the HTML, in our URLs or in any log record;
  - the report's branch scope, permission and Excel.
- **Acknowledgements:**
  - can't dismiss before acknowledging; acknowledging is idempotent;
  - a 404 outside the audience;
  - the report.
- **Locked query counts:** each lock is updated with its reason and checked for the same count with 3 and 60
  students.
- **Runs:** the full suite on PostgreSQL and on SQLite, one at a time.

## 4. Verification and what I won't touch

- **Migrations:** `makemigrations --check`, then the migrations applied forwards and backwards on a scratch SQLite
  copy and on the test database. Each one is reversible. The `event` column becomes nullable without touching
  rows.
- **Browser check:** headless Chrome at 1280 px and 375 px on the series page, the group page, the event page, the
  list pages, the student online page and the dashboard.
- **What I won't touch:**
  - any `academic_calendar` behaviour beyond the one signal;
  - holiday sessions;
  - `student_info`;
  - the local Docker database and production;
  - existing rows of any kind.
- **Docs:** `docs/apps/online_classes.md`, `docs/apps/academic_calendar.md` (the signal), `docs/database.md` and
  `docs/database-mermaid.md`, a new ADR-028 (series, groups, change tracking, opens and acknowledgements),
  `docs/changelog.md`, and the report `docs/plans/2026-11-online-classes-phase2.md`.
- **Deploy notes in the report:** migrations, `collectstatic`, permissions to grant by hand, and briefing admins and
  families on «جدید» and «متوجه شدم».
