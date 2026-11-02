# Report: online classes and announcements, Phase 1 of 3

**State: committed on `feature/online-classes`, awaiting your check in the browser. Not merged, not pushed, not
deployed.** No migration has run outside the test databases and scratch SQLite copies. The plan is
`docs/plans/2026-11-online-classes-plan.md` on `main` (approved 2026-11-02 with five changes, `8200d05`).

## 1. Summary and reasoning

The admin can now schedule online classes and exams on any platform and write announcements. Students,
and in practice their parents, see them in the student panel: banners and a card on the dashboard, and
`/student/online/` with «امروز», «پیش‌رو» and «گذشته». The join button appears at the right moment, personal
credentials are encrypted at rest, and access rows can be imported from Excel. Nothing is sent to anyone,
and nothing is visible in the teacher, supervisor or director panels.

**Main choices:**
- One audience (abstract model plus one module) for events and announcements, read in both directions,
  with a test requiring the two directions to agree.
- States come from the clock: nothing is stored and no job runs.
- Secrets live in explicit `*_encrypted` columns with explicit read methods.

**Rejected alternatives:**
- A separate `Audience` table: the admin can't edit it inline from the foreign-key side, and prefill and
  duplicate are copies anyway.
- A field that decrypts on load: secrets could leak through `dumpdata`, admin history or logs.
- A redirect view for the join button: open tracking is out of scope, and Phase 3 can add it without
  changing the data.
- Browser storage for dismissals: banners would return on another device and siblings sharing a browser
  would be mixed up.
- Reusing `website.validators.validate_link`: it accepts `http://` and `//evil.com`.

## 2. Files changed

### New app `online_classes/`

| Files | What |
| --- | --- |
| `models/` (`audience`, `platform`, `event`, `access`, `announcement`), `migrations/0001_initial.py` | The tables |
| `audience.py` | The only reader of the targets |
| `selectors.py`, `services.py`, `views.py`, `urls.py` | Read side, writes, student pages |
| `crypto.py`, `validators.py` | Encryption, URL rules |
| `importer.py`, `import_template.py` | Excel import and template |
| `forms.py`, `admin.py` | Admin forms, filters, inline, actions, import and reveal pages |
| `management/commands/reencrypt_online_access.py` | Key rotation |
| `signals.py`, `apps.py` | Removal of replaced images |
| `templates/online_classes/*`, `templates/admin/online_classes/*` | Student fragments and page, admin pages |
| `static/online_classes/` | `css/online.css`, `js/online.js`, `admin/import.css` |
| `testing.py`, `tests/` | Factories and 210 tests |

### Shared code

| File | Change |
| --- | --- |
| `core/moments.py` (new) | `utc_now`, `to_utc`, `parse_jalali_datetime`, `format_jalali_datetime`, moved from the blog |
| `core/spreadsheet.py` (new) | Excel reading and text normalising, moved from the calendar importer |
| `blog/models/post.py`, `blog/forms.py` | Import from `core.moments`; behaviour unchanged |
| `academic_calendar/importer.py` | Uses `core.spreadsheet`; behaviour unchanged |
| `school/models/subject.py`, `class_subject.py` | `Subject.icon` holds the map; `ClassSubject.icon` delegates |

### Student panel

| File | Change |
| --- | --- |
| `student/views.py`, `dashboard.html` | Online block, banners, `?partial=1`, `never_cache` |
| `student/admin.py` | `search_fields`; branch-scoped results only for `online_classes` |
| `template/partials/sidebar.html` | «کلاس‌های آنلاین», with no added query |
| `core/querysets/student.py`, `student/selectors.py`, `student/tests.py` | The enrolment fix, commit `6deb38e` |

### Configuration

| File | Change |
| --- | --- |
| `teachlog/config/settings/base.py`, `development.py`, `production.py` | See §5 |
| `teachlog/urls.py` | Includes `online_classes.urls` under `student/` |
| `requirements.txt` | Pins `cryptography==46.0.3` |
| `.env.example` | `ONLINE_ACCESS_KEYS`, with the command to generate one |

### Docs

New `docs/apps/online_classes.md`; ADR-027; updates to `docs/apps/student.md`, `school.md`, `blog.md`,
`academic_calendar.md`, `docs/database.md`, `docs/database-mermaid.md`, `docs/changelog.md` and the command list in `CLAUDE.md`.

## 3. Models and migrations

`online_classes.0001_initial` adds 15 new tables and the `view_access_secret` permission: `OnlinePlatform`, `OnlineEvent`,
`OnlineEventAccess`, `Announcement`, `AnnouncementDismissal` and ten M2M tables for the audiences. **No existing table changes
and there is no data migration.** `docs/database.md` has the fields.

**Constraints:** `online_event_end_after_start`, `unique_online_access_per_student`, `online_access_has_a_way_in`,
`announcement_until_after_from`, `announcement_button_label_and_url`, `unique_dismissal_per_student`.

**Verified:** `makemigrations --check` reports no changes. On a scratch SQLite database, `migrate`, then `migrate online_classes
zero` (all the tables are gone), then `migrate` again. PostgreSQL applied it forward in the test database; the reverse ran on
SQLite only.

**Rollback:** `migrate online_classes zero` removes the tables and **everything in them, including entered credentials**. To
roll back without losing data, keep the tables and revert the code. The other changes need no rollback steps.

## 4. URLs, views and permissions

| URL | Who | Everyone else |
| --- | --- | --- |
| `GET /student/online/?tab=` | Student with a profile (`student_required`) | Logged out: login. Other roles and no profile: 403. Unknown tab: 404 |
| `POST /student/announcements/<id>/dismiss/` | The same, within audience and window | Outside them: 404. Urgent or non-dismissible: 403. GET: 405 |
| `GET /student/dashboard/` | Unchanged | Unchanged |
| Admin: platforms, events, rows, announcements | Superuser, or staff with the model permission | 403; non-staff go to the admin login |
| Admin: `<event>/access-import/`, `.../template/` | Change permission on an event wholly inside their branches, plus `add_onlineeventaccess` | No permission: 403. Outside their branches: 404. Whole-school for a branch admin: 403 |
| Admin: `<row>/reveal/` | `view_access_secret`, within their scope | No permission: 403. Outside their scope: 404 |

Branch-scoped admins (D23) **see** items touching their branches and whole-school items, and **change** only items wholly inside.
Teachers, supporters and the director have no access.

## 5. Settings

In `teachlog/config/settings/base.py`; change the value and restart.

| Setting | Default | Note |
| --- | --- | --- |
| `ONLINE_JOIN_LEAD_MINUTES` | 15 | Per-event override `join_lead_minutes` |
| `ONLINE_PAST_DAYS` | 14 | |
| `ONLINE_DASHBOARD_ITEMS` | 5 | |
| `ANNOUNCEMENT_MAX_VISIBLE` | 3 | |
| `ONLINE_ACCESS_IMPORT_MAX_ROWS` | 1000 | |
| `ONLINE_ACCESS_INLINE_MAX` | 100 | **Not in D25; added**, see §6 |
| `ONLINE_ACCESS_KEYS` | environment | Production raises `ImproperlyConfigured` if missing or invalid. Development has a fixed public key |

## 6. Decisions

### Approved

D1–D26 as recommended in the plan, with your five changes:

1. **D6:** grades 1–6, no fields of study, no `Track` now or later; recorded in the plan and `docs/apps/online_classes.md`. Student-facing
   text is short and plain enough for a parent to act on.
2. **D11:** per-event `credentials_lead_hours`, default 0; the personal link follows the same rule, and the join button appears only at
   the join window.
3. **D9:** a postponed event with no new time stays in «پیش‌رو» with «زمان جدید اعلام می‌شود» until an admin edits it; never «گذشته».
4. **D5:** done as the separate commit `6deb38e`.
5. **D14:** `reencrypt_online_access` (dry run by default, `--apply`). `docs/apps/online_classes.md` §6 covers generating, storing, backing up
   separately and rotating the key.

### Ambiguities I resolved

| Question | Choice | Why |
| --- | --- | --- |
| Function name | `audience.reached_enrollments`, not the plan's `students_of` | It returns enrolments, which the callers need |
| Events on the page with hundreds of rows | New `ONLINE_ACCESS_INLINE_MAX = 100` and a standalone «دسترسی‌های شخصی» list | Hundreds of inline rows pass Django's 1000-field POST limit and would make the event page impossible to save |
| A note-only row in the import | Allowed as an update of an existing row, refused as a new row | D8 says a note alone isn't a row, and the update can't create one |
| A personal event, student with no row, event has a link | The student does **not** get the event link | The message says to contact the school; the shared link isn't theirs by default |
| Banner of an event outside the student's audience | Shows its countdown, never a way in | D22 |
| Dashboard `?partial=1` | Returns only the card, not the banners | The card is what changes with the clock |
| Query lock | Measured after one warm-up request | The first request also fills site-wide caches |
| Who sees the rows list | Only rows of events wholly inside the admin's branches | D23: no rows on anything else |
| `updated_by` on rows | Set in `OnlineEventAccessForm.save` | One place for the inline and the row page |

## 7. Tests

**210 new tests** in `online_classes/tests/`, plus enrolment tests in `student/tests.py`:

| File | Covers |
| --- | --- |
| `test_audience.py` | The matrix in both directions, class and branch changes, enrolment states |
| `test_student_pages.py` | Tabs, boundaries with a mocked clock, links and secrets absent from the HTML, early credentials, postponed, dismissal, cap and order, every refused role, query locks |
| `test_validators.py` | `user@host`, `//`, domains and subdomains |
| `test_crypto.py` | Ciphertext in the database, rotation, unreadable rows, `reencrypt_online_access` |
| `test_importer.py` | Every error and warning, leading zeros, Persian digits, blank-keeps, all-or-nothing, row cap, file size, token expiry, nothing plain in the session, template safety |
| `test_admin.py` | Each refused role, branch scoping, masking, reveal and history, duplicate, clear, images, prefill, filters |

The new tests found three real bugs, all fixed:
- **Duplicate lost its audience.** The admin's list carries prefetched targets, so `set()` saw the original's rows and added nothing.
- **Inline rows had no `updated_by`.**
- **Staff with no permission got a 404, not a 403,** on the import page.

| Run | Result |
| --- | --- |
| Baseline, PostgreSQL, `main` 8200d05 | 1048 tests, OK |
| Branch, PostgreSQL, full | 1264 tests, OK (1048 + 216 new), before the last small admin, form and CSS changes |
| Branch, PostgreSQL, `online_classes`, final code | 210 tests, OK |
| Branch, SQLite, full | 1264 tests, OK, 1 skipped, on the final code |
| `makemigrations --check` | No changes |

**Browser, on a scratch database, in headless Chrome:**
- The dashboard and all three tabs at 1280 and 375 px, with JS on and off: no horizontal overflow, no JS errors, no request leaves the site.
- With JS: the countdown ticks, dismissing removes the banner and it stays gone after reload, reveal and copy work, and new-tab links carry `noopener noreferrer`.
- Admin event list and page, rows list, import, platform and announcement forms load at both widths. As usual in the admin, wide tables scroll inside their own box.
- The topbar's class label is cut off on a phone when the text is long. That's the existing shared header, which I didn't change.

## 8. Discrepancies between docs and code

**Fixed in this work:**
- `docs/apps/student.md` said `StudentProfile` has `school_class`, `enrollment_date` and `status` (they're on `StudentEnrollment`). Its sessions URL, dashboard query and admin were also out of date.

**Not fixed, outside this work:**
- `docs/apps/school.md` omits `Branch`, `SchoolClass.branch` and `Subject.color`, and gives `ClassSubject` a `teacher` field where the code uses `teacher_assignment`.
- `CLAUDE.md` says ADR-001…022, but the file reached ADR-026 before this work and now ADR-027.
- `docs/apps/student.md` §6 still describes some dashboard parts loosely (achievements are static text in the template).

## 9. Open questions and deploy actions

**Open questions:** none are blocking.

**Before you deploy, know these two:**
- A web container running production settings **won't start** without `ONLINE_ACCESS_KEYS`. That includes the local Docker one after a rebuild.
- If the key is lost, the entered secrets are gone. Back it up separately **before** anyone enters data.

**At deploy, in order. Nothing here has been done:**
1. Back up the database.
2. Generate the key and store it **separately from database backups** (`docs/apps/online_classes.md` §6).
3. Set `ONLINE_ACCESS_KEYS` in `.env`.
4. Rebuild the image for `cryptography`.
5. `migrate`: `online_classes.0001`, after the migrations already pending from earlier work (website 0003–0014, blog 0001–0002).
6. `collectstatic`.
7. In the admin, grant permissions by hand: the `online_classes` model permissions, `view_access_secret` only to those who should read
   passwords, and `student.view_studentprofile` for the student picker. Staff need `BranchAccess`.
8. Create the platforms, with short join help a parent can follow.

**Who to brief:** whoever enters events (a postponed event needs new moments and status back to «طبق برنامه»; announcement images are public), and parents, through
the school's usual channel, since nothing is sent by this system.
