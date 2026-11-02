# Plan: online classes and exams, and announcements in the student panel (Phase 1 of 3)

Status: **waiting for approval.** No code has been written. After approval, work goes on
`feature/online-classes`, created from `main`. Nothing on that branch is committed until
you ask.

Items marked **[policy]** are school decisions. Every other D-item is a technical choice,
and I give a recommendation for each. Answer «تأیید» to accept them all, or name the ones
to change. **D6 is the one question I can't answer from the code.**

## 1. Findings, risks and surprises

Most important first.

1. **The importer pattern would put passwords in the session table in plain form.** The
   calendar import keeps the raw cells in `request.session` between preview and
   confirmation. `SESSION_ENGINE` isn't set, so these are database sessions, which are
   signed but not encrypted. Copied as it is, the pattern would write every student's
   password to `django_session`, even if the access table is encrypted. See D16.
2. **There is no single "current enrolment".** The student code picks it three ways:
   - `student_dashboard` uses `enrollments.all()[0]`, which is the newest year in any
     status, and **raises a 500 when a student has no enrolment**.
   - `sessions_list` and `session_list_json` use `enrollments.get()`, which **raises a 500
     as soon as a student has two years**, so every returning student at the 1406 rollover.
   - `student_info` uses active enrolments, current year first.

   `AcademicYear.is_current` also has no unique constraint. The audience rule needs one
   definition, and the dashboard must agree with it. See D4 and D5.
3. **No field of study exists (verified).** `Grade` has `name` and `level`, and
   `SchoolClass` has `year`, `grade`, `branch` and `section`. The only «رشته» in the code is
   `TeacherProfile.field_of_study`, which is about the teacher. `Grade.level` is unique, so
   «دهم ریاضی» and «دهم تجربی» can't be two grades at the same level. The local data can't
   settle this: SQLite has grades 1–6 and a test row, and the Docker database has only
   «اول». See D6.
4. **"Info only" events have no platform.** The brief lists platform as a field of every
   event, but an in-school exam has none. See D8.
5. **Personal rows often have no link of their own.** Many exams give everyone one URL with
   a personal username and password. If a row has credentials and no link, the join button
   needs somewhere to go. See D8.
6. **Moments compare wrongly on SQLite.** `django_jalali` stores datetimes as text with
   their own offset, the bug the blog already fixed (ADR-026, `MOMENT_FIELDS`, `utc_now`).
   Event and announcement moments need the same treatment or the suite will disagree
   between the two databases. I'll move those two helpers to `core/moments.py` and have the
   blog import them, with no change to blog behaviour.
7. **`website.validators.validate_link` isn't strict enough to reuse.** It accepts `http://`
   and `//evil.com`, which passes as a "local" path. This feature gets its own single
   validator (D13).
8. **Student autocomplete needs work.** `StudentProfileAdmin` has no `search_fields`, so
   `autocomplete_fields` fails its system check. It also isn't branch-scoped, so a branch
   admin could search students of other branches. See D23.
9. **Excel drops leading zeros.** A national code stored as a number loses them
   (`0012345678` becomes `12345678`), and the calendar importer's `_text` keeps that number.
   The template formats these columns as Text, and the importer pads national codes back to
   10 digits.
10. **Logos become JPEGs.** `website.images.reencode` flattens transparency onto white. I'll
    show logos on a white rounded tile so this doesn't look wrong on the panel's cards.
11. **Images are public.** `/media/` is served by nginx without a login, under random names
    (the same limit ADR-026 records). Announcement images must not carry private content.
    The admin help text will say so. No secret is ever stored as a file.
12. **`cryptography` isn't a project dependency.** It's in `.venv` (46.0.3) only because of
    an unpinned `pyHanko`. It has to be pinned in `requirements.txt` (D14).
13. **Small inherited details:**
    - The calendar's row cap is a constant in code. This feature uses a setting, as you
      asked, and the calendar stays as it is.
    - `website/signals.py` removes replaced image files, and the new image fields need the
      same cleanup.
    - The student pages have no locked query counts yet, so this adds the first.

## 2. Decisions to confirm

### Structure

**D1. One new app, `online_classes`.** Announcements live in it too, because they link to
events and share the audience code.

| Model | Persian label | Why this name |
|---|---|---|
| `OnlinePlatform` | پلتفرم آنلاین | |
| `OnlineEvent` | کلاس یا آزمون آنلاین | "Online" keeps it apart from `SchoolSession` and `CalendarEvent` |
| `OnlineEventAccess` | دسترسی شخصی | One student's link or credentials |
| `Announcement` | اطلاعیه | |
| `AnnouncementDismissal` | | Only if D20 is approved as recommended |

Student URLs (namespace `online_classes`):
- `/student/online/?tab=today|upcoming|past`
- `POST /student/announcements/<id>/dismiss/`

**D2. The audience is an abstract model plus one module.** `AudienceTargets` holds
`is_whole_school`, `branches`, `grades`, `classes`, `students` and `excluded_students`.
`online_classes/audience.py` is the only code that reads them, in both directions:
- `visible_to(queryset, enrolment)`: the items one student sees.
- `students_of(item)`: the students an item reaches (admin count, missing rows, template).

A test runs both over a matrix of targets and requires them to agree. Phase 2's custom
groups become one more M2M and one more term here, with no change to callers.

I rejected a separate `Audience` table with a foreign key. It would allow sharing, but the
Django admin can't edit it inline from the FK side, and you asked for prefill and duplicate
as copies anyway.

**D3. Audience semantics.** As you prefer, nothing selected means nobody.

```
shown = whole school
        OR the student is listed
        OR the student's class is listed
        OR (a branch or grade is selected
            AND the student's branch matches, if any branches are selected
            AND the student's grade matches, if any grades are selected)
then remove excluded students (exclusion always wins)
```

| Selected | Who sees it |
|---|---|
| Nothing | Nobody; the admin gets a warning on save |
| Whole school | Everyone with a current enrolment |
| Branch: مرکزی | All of that branch |
| Grade: هفتم | Grade 7 in all branches |
| Branch: مرکزی + grade: هفتم | Grade 7 in that branch only (AND) |
| Branch + grade + class ۸-الف | The row above, plus that class (OR) |
| Any of these + excluded student | The same, minus that student |

Branch and grade narrow each other, so "grade 7 in this branch" needs no class list. Pure OR
can't express that. It also matches how `CalendarEvent` scopes work, except that empty means
nobody here. Classes and students add to the result.

The form refuses "whole school" with other positive targets, and a student who is both
listed and excluded. The event page shows the resulting student count.

**D4. Who counts as enrolled.** One function, `student.selectors.current_enrollment(profile)`:
status active, in the `is_current` year, in an active class of an active branch. If two years
are flagged as current, the newest wins. A student without one sees nothing, even if listed by
name, so someone who left or hasn't re-enrolled gets no links. A class change edits the same
row (one row per student per year), so it takes effect on the next page load.

**D5. Fix the enrolment crashes on this branch.** Recommended: yes, as a separate commit.
- The dashboard no longer returns a 500 for a student with no enrolment; it shows an empty
  state.
- `sessions_list` and `session_list_json` no longer fail for a student with two years.
- The two leftover `print` calls in the dashboard view go.

I'm already changing this view, and the sessions page would otherwise break for every
returning student at rollover. A student whose only active enrolment is in an old year keeps
seeing that class's timetable and homework as they do today, but gets no online items.

**D6. [policy, question for you] Does the school have fields of study?** If tracks exist,
each is presumably its own class («دهم ریاضی الف»). Recommended: **no schema change in
Phase 1**. The admin ticks the classes of a track, and a mixed-track group waits for Phase 2's
custom groups.

If you need "all of ریاضی" as one tick, the addition is a `Track` model, a `SchoolClass.track`
FK and one more audience term. None of it reworks Phase 1, but it does change `school`, so it
deserves its own decision. Tell me if tracks exist and how the classes are named.

**D7. No `academic_year` on events or announcements.** Their moments already place them in
time, and audiences resolve against the current enrolment. The class picker offers only
current-year active classes. Old items fall out through the past window (D10) and their
display windows.

### Events

**D8. [policy] Platform and link rules by access mode.**

| Mode | Platform | Event link | Join button goes to |
|---|---|---|---|
| Shared | Required | Required | The event link |
| Personal | Required | Optional | The row's link, else the event link |
| Info only | Optional | Not allowed | No button |

A personal row must have a link, username, password or access code; a note alone isn't a row.
If a student has credentials but neither a row link nor an event link exists, the page shows
the credentials with no button.

**D9. Time states and tabs.** One queryset and one `state_at(now)` in `selectors.py`; nothing
is stored and no job runs.

| Tab | Contains |
|---|---|
| امروز | Not ended, and starts by the end of today (Tehran), live first |
| پیش‌رو | Starts after today |
| گذشته | Ended within the last N days (D10), newest first |

- Cancelled and postponed events stay in their tab with a badge and note, with no button and
  no credentials. The note is required for those two statuses.
- A postponed event with a new time is edited: new moments, back to scheduled.
- A postponed event with no new time moves to گذشته when its old end passes.
- `is_active=False` is the separate soft delete, which hides the event. There's no hard delete
  for events.

**D10. [policy] Timing defaults, all in settings.**
- Join opens **15 minutes** before the start (`ONLINE_JOIN_LEAD_MINUTES`, with a per-event
  override).
- Past items stay visible for **14 days** (`ONLINE_PAST_DAYS`).

**D11. [policy] When credentials appear.** Recommended: **the same window as the join button**
for personal links, usernames, passwords and codes. They're sent to the browser only during
that window, so an exam password can't be passed around days earlier.

The «لینک شما هنوز ثبت نشده؛ با مدرسه تماس بگیرید» message shows **at all times**, including
for upcoming events, so a student can act before the exam. Students with a row see «دسترسی شما
ثبت شده است» until the window opens.

**D12. Direct links, no redirect view.** The button is a plain
`<a target="_blank" rel="noopener noreferrer">`, as you specified. Open tracking is out of
scope, and Phase 3 can add a redirect without changing the data.
- The URL isn't in the page before the window opens.
- The countdown uses seconds sent by the server, not the phone's clock, which is often wrong.
- At zero, JS fetches `?partial=1` (ADR-015) to get the button.
- Without JS the page shows the time and a refresh link.

**D13. One validator, `online_classes/validators.py`.**
- Links must be https with a host and no `user@host` form, so
  `https://skyroom.online@evil.com` is refused. If the platform lists domains, the host must
  match one exactly or be a subdomain of one.
- Announcement buttons also accept internal paths: `/…`, but never `//…` or `/\…`.
- Models, forms and the importer all call it. Templates check again when rendering, so a bad
  row written another way can't produce a dangerous link.

Colours reuse `school.colors` (`hex_color_validator`, `safe_hex`).

**Subject.** The event has both optional FKs, `subject` and `class_subject`. Setting
`class_subject` fills `subject`. The icon map moves from `ClassSubject.icon` to `Subject.icon`,
and `ClassSubject.icon` delegates to it.

### Access

**D14. [policy] Encrypt personal secrets at rest.** Recommended: **yes.** These are children's
accounts, and database dumps and backups travel further than the server.
- **Encrypted:** password, access code and the personal link, because a personal link is often
  a login in itself. **Plain:** username and note.
- **Method:** `cryptography` Fernet through `MultiFernet`. Key list in the environment,
  `ONLINE_ACCESS_KEYS`; the first encrypts and all decrypt, which allows rotation.
- **Storage:** explicit `*_encrypted` columns with explicit read methods, not a field that
  decrypts on every load. Secrets can't leak through `dumpdata`, `__str__`, admin history or
  logs.
- **Production** refuses to start without a key, like `SECRET_KEY`. Development and tests use a
  fixed non-secret key.

**The cost: if the key is lost, the secrets are gone.** The key must be backed up separately
from the database, and recovery means re-importing the file. A row that can't be decrypted
shows «با مدرسه تماس بگیرید» and logs an error; it never returns a 500.

**D15. [policy] Who sees passwords in the admin.** Recommended:
- New permission `online_classes.view_access_secret`, granted by hand. Superusers have it
  automatically.
- Everywhere, secrets show as `••••••`: lists, change pages, inlines and the import preview.
- A holder clicks «نمایش» on one row, on a server-checked page. The click is written to Django's
  admin history (who, which row, when).
- Without the permission, staff can still **enter or replace** a secret but can't read it. A
  blank field keeps the current value.

**D16. Encrypt the import preview.** The session stores one Fernet token of the rows, not the
raw cells, with a 30-minute expiry. It's cleared on confirmation or when the page reloads.
Uploaded files aren't kept.

**D17. [policy] An imported row for a student outside the audience.** Recommended: **a warning,
highlighted in the preview, with the row still saved.** Audiences change, and such a row does
nothing unless the student joins the audience, because the audience check always runs first.
The highlight still catches a mistyped code that matched the wrong person.

These remain **errors**, which block the whole file:
- unknown student
- a student outside the admin's branches
- a duplicate student in the file
- two codes in a row that point to different students
- a link that fails validation

**D18. Import details.** It follows the calendar pattern: generated template, per-row preview,
all-or-nothing confirmation with a second validation.
- **Template.** Generated per event and prefilled with its audience: student code, national code
  and name (for reference), then link, username, password, access code and note. Existing secrets
  are never exported.
- **Empty rows.** A row with no access data is skipped and stays on the "no row" list, so a
  partly filled template works.
- **Re-import.** Updates the student's existing row, and **blank cells keep their current value**,
  so a file with only corrected passwords can't wipe links. The preview counts new and updated
  rows.
- **Limits.** `ONLINE_ACCESS_IMPORT_MAX_ROWS = 1000`, and uploads are limited to 5 MB.
- **Concurrency.** Confirmation locks the event row. `(event, student)` is unique in the database.
- **Shared code.** The file reading and text normalising move from `academic_calendar.importer` to
  `core/spreadsheet.py`. Calendar behaviour stays the same, and its tests guard that.

**D19. [policy] How long personal rows are kept.** Recommended: **until someone deletes them**; no
automatic purge, because there's no scheduler. An admin action, «حذف دسترسی‌های شخصی», clears the
rows of selected ended events. Tell me if you'd rather have a fixed retention period.

### Announcements

**D20. [policy] Dismissal.** Recommended: **remembered on the server, per student**
(`AnnouncementDismissal`). Browser storage would bring dismissed banners back on another device and
would mix up siblings who share a browser. It's a plain POST form, so it works without JS, and JS
only removes the banner in place. The server refuses non-dismissible or urgent announcements, and
announcements outside the student's audience.

If an announcement is later raised to urgent, it shows again despite an earlier dismissal.

**D21. [policy] Order and the cap.** `ANNOUNCEMENT_MAX_VISIBLE = 3`. Order: **urgent first**, then
pinned, then priority, then newest. Without urgent first, three pinned info banners could hide an
urgent one, so this is a small addition to "highest priority first". Dismissed banners don't use up
the cap.

**D22. Link to an event.**
- «ساختن اطلاعیه» on the event page opens the add form prefilled with title, display window (now until
  the event ends) and audience. **It's a copy:** later changes to the event's audience don't follow.
- The banner shows a countdown, or the event's cancelled or postponed status.
- It never exposes the event's link or credentials; the only button is the announcement's own.

Both display moments are required, so no banner runs forever. The body is plain text rendered with
autoescape and `linebreaksbr`. The image is `<picture>` with the optional mobile version, at most
1600 px, using the title as alt text.

### Admin

**D23. Branch-scoped admins (non-superusers),** as in the calendar:
- They can't tick "whole school".
- They need at least one target inside their branches, and a grade alone needs a branch too, because
  a grade alone covers every branch.
- Classes, students and excluded students must be inside their branches.
- They **see** items that touch their branches and whole-school items, and **change** only items
  wholly inside their branches. On anything else they get no access rows and no reveal.
- `StudentProfileAdmin` gets `search_fields` (name, student code, national code). Results are
  branch-scoped only when the autocomplete comes from these new fields, so its existing pages don't
  change.
- Staff need `student.view_studentprofile` for the autocomplete. This goes in the deploy notes.

Filters: date, derived state, type, platform, branch and grade. The branch and grade filters include
whole-school items and items that reach them through a class.

**D24. Duplicate creates a hidden copy.** The copy has the audience but no access rows, its title gets
«(کپی)», its status returns to scheduled, and it starts with `is_active=False`. Otherwise it would
appear to students at once with the old time. The admin sets the new time and activates it.

### Settings and records

**D25. Settings in `base.py`:** `ONLINE_JOIN_LEAD_MINUTES`, `ONLINE_PAST_DAYS`, `ONLINE_DASHBOARD_ITEMS`
(5), `ANNOUNCEMENT_MAX_VISIBLE`, `ONLINE_ACCESS_IMPORT_MAX_ROWS`, `ONLINE_ACCESS_KEYS` (from the
environment, with an entry in `.env.example` and the command to generate a key).

**D26. A new ADR-027** records D2–D4, D11 and D14–D16.

## 3. Data model (all new tables)

`AudienceTargets` (abstract) is defined in D2. Moments are `jDateTimeField`, saved in UTC.

| Model | Fields |
|---|---|
| `OnlinePlatform` | `name` (unique), `logo`, `color`, `join_help`, `support_contact`, `support_url`, `allowed_domains` (one per line), `is_active`, timestamps |
| `OnlineEvent` | `title`, `event_type` (class, exam, meeting, other), `platform`, `subject`, `class_subject`, `start_at`, `end_at`, `description`, `status`, `status_note`, `access_mode`, `join_url`, `join_lead_minutes`, `is_active`, `created_by`, `updated_by`, timestamps |
| `OnlineEventAccess` | `event`, `student`, `url_encrypted`, `username`, `password_encrypted`, `access_code_encrypted`, `note`, `updated_by`, timestamps |
| `Announcement` | `title`, `body`, `image`, `image_mobile`, `button_label`, `button_url`, `level`, `visible_from`, `visible_until`, `priority`, `is_pinned`, `is_dismissible`, `event`, `is_active`, `created_by`, `updated_by`, timestamps |
| `AnnouncementDismissal` | `announcement`, `student`, `dismissed_at` |

Database constraints:
- end after start on events, and until after from on announcements
- `(event, student)` and `(announcement, student)` unique
- an access row has at least one of link, username, password or code
- a button has both label and URL, or neither

Indexes on `(is_active, start_at, end_at)` and `(is_active, visible_from, visible_until)`.

**Room for Phases 2 and 3, none of it built now:**

| Later need | How it's added |
|---|---|
| Custom groups | One M2M on `AudienceTargets`, one term in `audience.py` |
| Teacher or supervisor authoring | `created_by` and `class_subject` already exist |
| Open tracking | A redirect view and a new table |
| Recurring events | A nullable `series` FK |

## 4. Implementation outline

**Models and migrations.** `online_classes.0001_initial`, schema and the new permission only. No
existing table changes and no data migration.

**Services and selectors.**
- `audience.py`, `crypto.py`, `validators.py`
- `selectors.py`: event cards, tabs, dashboard block, visible announcements
- `services.py`: duplicate, dismiss, save import
- `importer.py`, `import_template.py`
- image cleanup signals
- `student/selectors.py` for D4

**Student panel, in the panel's current design** (`dashboard.css` cards, colours and Font Awesome).
- **Dashboard:** the announcement area at the top, then a «کلاس‌ها و آزمون‌های آنلاین» card with the
  platform logo, time, status and join button. If the student needs credentials, a link leads to the
  page that shows them.
- **`/student/online/`:** three tabs that are real links, with platform help and support contact on
  each item.
- **On the phone:** a full-width join button at least 48 px tall, with no horizontal overflow at
  375 px.
- **Secrets:** masked inside `<details>`, so reveal works without JS. JS adds the copy button. Pages
  showing secrets send `Cache-Control: no-store`.
- **Sidebar:** one new item, with no added query.

**Query budget.** At most **4 extra queries** on the dashboard and on the page, however many events,
audience rows or access rows exist:
1. the enrolment
2. the events (audience checked with `EXISTS`, platform and subject joined)
3. the student's access rows
4. the announcements (dismissals checked with `EXISTS`, dashboard only)

The page itself will have a locked total.

**Admin.**
- Platforms; announcements; events with the access inline
- Import, template download and the secret reveal page
- Read-only «دانش‌آموزان بدون ردیف» on the event page, with the count and list
- Duplicate action

**Tests** (`online_classes/tests/`, on both databases):
- audience matrix in both directions (D3), and class or branch change taking effect at once
- enrolment states: none, old year, withdrawn, inactive class, two years
- time boundaries with a mocked clock: exactly at window open, start and end, tab edges, Tehran midnight
- link and secret absent from the HTML before the window, after the end and when cancelled
- URL validator, including `user@host`, `//`, wrong domain and subdomain rules
- encryption: ciphertext in the database, key rotation, undecryptable row, nothing plain in the session
  during import
- importer: every error and warning, leading zeros, Persian digits, blank-keeps, all-or-nothing, row cap
- admin: each refused role and each branch-scoping rule, masked output, reveal permission and history
- dismissal: other student's audience, urgent, non-dismissible, repeat POST, no-JS flow
- cap and order; query locks with small and large data
- student page access: logged out, teacher, supervisor, director, staff, no profile

**Docs.**
- New `docs/apps/online_classes.md`
- Updates to `docs/apps/student.md`, `docs/database.md`, `docs/database-mermaid.md`, ADR-027,
  `docs/changelog.md`
- Report in `docs/plans/2026-11-online-classes.md`

**Order of work:**
1. Baseline on `main`
2. Enrolment fix
3. Models, audience, validators and crypto
4. Admin and import
5. Student panel
6. Docs and full runs

## 5. Verification

- **Baseline:** full PostgreSQL suite on `main` before branching, compared with the branch at the end,
  plus the app tests on SQLite.
- **Migrations:** `makemigrations --check`, then forward and reverse on the test database and a scratch
  SQLite copy.
- **Browser:** headless checks of the dashboard, the page and the masked secrets at 1280 and 375 px, on a
  scratch database, with JS on and off.

## 6. What I will not touch

- Production or the local Docker database. Nothing gets migrated there without asking.
- Existing rows of any table.
- Calendar, attendance and analytics behaviour. This feature adds no metric.
- The teacher, supervisor and director panels. Nothing is visible there in Phase 1.
- Anything on your out-of-scope list: recurring events, custom groups, tracking and reports,
  acknowledgements, authoring outside the admin, archives, platform APIs, parents, and all notifications.

## 7. Deploy notes (for the report; nothing is deployed by this work)

1. Back up the database, and **store the new key separately from the backup**.
2. Set `ONLINE_ACCESS_KEYS` in `.env`. Production won't start without it.
3. Rebuild the image for `cryptography`.
4. Run `migrate` (`online_classes.0001`, after the migrations already pending from earlier work) and
   `collectstatic`.
5. Grant permissions by hand, including `view_access_secret` and `student.view_studentprofile`.
6. Create the platforms.

## 8. Docs that disagree with the code (found so far; will go in the report)

- `docs/apps/student.md` says `StudentProfile` has `school_class`, `enrollment_date` and `status`. Those are
  on `StudentEnrollment`. Its URL list and dashboard query are also out of date.
- `docs/apps/school.md` omits `Branch`, `SchoolClass.branch` and `Subject.color`, and gives `ClassSubject` a
  `teacher` field where the code uses `teacher_assignment`.
- `CLAUDE.md` says ADR-001…022, but the file goes up to ADR-026.
