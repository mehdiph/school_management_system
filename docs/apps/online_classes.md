# Online classes and announcements (`online_classes`)

Phase 1 of 3. The admin schedules online classes and exams and writes announcements; students, and
in practice their parents, see them in the student panel. There is no sending of any kind (no SMS,
email or push), no tracking and no platform API. The rules are in ADR-027; the plan is
`docs/plans/2026-11-online-classes-plan.md`.

**No fields of study (D6).** The school has grades 1–6 and no fields of study. There is no `Track`
model and no schema for one, now or in later phases. Audiences target branches, grades, classes and
students.

**Written for parents.** Parents usually use the panel on behalf of a primary-school child. Everything
a student page says (help, empty states, «لینک شما هنوز ثبت نشده؛ با مدرسه تماس بگیرید») stays short and
plain: say what to do next, with no technical words. Keep this when adding text.

## 1. Models

| Model | Persian label | Notes |
| --- | --- | --- |
| `OnlinePlatform` | پلتفرم آنلاین | Name, logo, colour, join help, support, allowed domains. Data, never code: nothing is hard-coded for a platform |
| `OnlineEvent` | کلاس یا آزمون آنلاین | Audience, moments, status, access mode, join link, leads |
| `OnlineEventAccess` | دسترسی شخصی | One student's link and credentials for one event; secrets encrypted |
| `Announcement` | اطلاعیه | A banner at the top of the dashboard; plain text |
| `AnnouncementDismissal` | | One student closed one banner |

`AudienceTargets` is the abstract base of `OnlineEvent` and `Announcement`. Moments (`start_at`, `end_at`,
`visible_from`, `visible_until`) are `jDateTimeField`s saved in UTC and compared with `core.moments.utc_now()`,
because on SQLite `django_jalali` stores text with its own offset.

Events are never hard-deleted; `is_active=False` hides one. Announcements can be deleted.

## 2. Audience (`audience.py`)

The only code that reads the target fields, in both directions:

- `visible_to(queryset, enrollment)`: what one student sees (`EXISTS` subqueries, no per-row query).
- `reached_enrollments(item)`: who an item reaches (the admin's counts and lists, missing rows, the import). One
  query: the targets are subqueries on the through tables, not lists read first.
- `breakdown(item, branch_ids=None, event=None)`: the admin's per-class counts in **one aggregate query**, ordered by
  grade level, section, then branch. Totals are summed from the class rows. With a personal `event`, it also counts
  students without an access row (`~EXISTS`); rows of students outside the audience aren't counted. `branch_ids=None`
  means every branch (a superuser).
- `students(item, branch_ids=None, event=None)`: the list page's queryset, with each enrolment's access row id as a
  subquery annotation.

A test runs both over a matrix of targets and requires them to agree.

```
shown = whole school
        OR the student is listed
        OR the student's class is listed
        OR (a branch or grade is selected
            AND the student's branch matches, if any branches are selected
            AND the student's grade matches, if any grades are selected)
then remove excluded students (exclusion always wins)
```

Nothing selected means nobody, and the admin gets a warning on save. Branch and grade narrow each other;
classes and students add to the result. The form refuses «کل مدرسه» with other positive targets, and a
student both listed and excluded.

**Who counts as enrolled:** `student.selectors.current_enrollment(profile)`: status active, in the
`is_current` year, in an active class of an active branch; if two years are flagged current, the newest wins.
A student without one sees nothing, even if listed by name. A class change takes effect on the next page load.

## 3. Time rules

Nothing is stored and no job runs; `OnlineEvent.state_at(now)` and the queryset's `in_tab` decide.

| Tab | Contains |
| --- | --- |
| امروز | Not ended, and starts by the end of today (Tehran), live first |
| پیش‌رو | Starts after today, plus every postponed event whatever its stored moments, listed last |
| گذشته | Ended within `ONLINE_PAST_DAYS`, newest first; never a postponed event |

| Status | Shows |
| --- | --- |
| Scheduled | Time, countdown, button in its window |
| Cancelled | Badge and note, no button or credentials; follows the clock through the tabs |
| Postponed | «زمان جدید اعلام می‌شود» in place of a time, note, no button or credentials; stays in پیش‌رو until an admin enters new moments and sets it back to scheduled. The admin's state filter finds forgotten ones |

| Moment | Rule |
| --- | --- |
| Join button opens | `start - join lead` (`join_lead_minutes`, else `ONLINE_JOIN_LEAD_MINUTES`) |
| Credentials open | The earlier of the join window and `start - credentials_lead_hours`; never later than the button |
| Both close | At the end of the event, or at once when it's cancelled or postponed |

`credentials_lead_hours` (default 0, at most 168) is for personal events only; the form refuses it elsewhere,
and a shared link waits for the join window regardless. It never moves the join button. While credentials are
open and the button isn't, the link appears as a small «آزمایش ورود» link beside them. Credentials and links are
sent to the browser only while open: they are not in the HTML before that.

| Access mode | Platform | Event link | The button goes to |
| --- | --- | --- | --- |
| Shared | Required | Required | The event link |
| Personal | Required | Optional | The row's link, else the event link |
| Info only | Optional | Not allowed | No button |

A student with no row on a personal event sees «لینک شما هنوز ثبت نشده؛ با مدرسه تماس بگیرید» at all times, and
never the event link. A personal row needs a link, username, password or code; a note alone isn't a row.

The countdown ticks from seconds sent by the server, not the phone's clock. At the next change (credentials
open, join opens, the event ends) `online.js` fetches `?partial=1` (ADR-015). Without JS the page shows the time
and a refresh link. Buttons are plain `<a target="_blank" rel="noopener noreferrer">`, with no redirect view.

## 4. Student pages

| URL | View | Notes |
| --- | --- | --- |
| `/student/online/?tab=today\|upcoming\|past` | `online_classes:online_page` | `student_required`, `never_cache`; `?partial=1` returns the list |
| `POST /student/announcements/<id>/dismiss/` | `online_classes:dismiss_announcement` | CSRF-protected; 403 for urgent or non-dismissible, 404 outside the student's audience; idempotent; works without JS |
| `/student/dashboard/` | `student:dashboard` | Banners on top, then the card (`ONLINE_DASHBOARD_ITEMS` items); `?partial=1` returns the card |

Secrets are masked inside `<details>`, so reveal works without JS; JS adds the copy button. Everything comes from
`selectors.py`: four queries at most for the block (enrolment, events, the student's access rows, announcements),
whatever the data. The page's total is locked in `test_student_pages.py`.

**Banners:** `ANNOUNCEMENT_MAX_VISIBLE` at once; urgent first, then pinned, priority, newest. Dismissed banners
don't use up the cap. Urgent ones can't be closed, and one raised to urgent later shows again despite an earlier
dismissal. A linked event gives the banner a countdown or the event's cancelled or postponed status, but never
its link or credentials. Images are public under `/media/` like every upload, so they must not carry private
content; the admin's help text says so.

## 5. Validators (`validators.py`)

Links must be https with a plain-ASCII host and no `user@host` form, so `https://skyroom.online@evil.com` is
refused. If the platform lists domains, the host must match one or be a subdomain of one. Announcement buttons also
accept internal paths (`/…`, never `//…` or `/\…`). Models, forms and the importer all call this, and templates
check again when rendering (`safe_https_url`, `safe_button_url`, `OnlinePlatform.safe_support_url`), so a bad row
written another way can't produce a dangerous link.

**Invisible marks are removed, not refused** (2026-11). Staff copy links out of Persian messengers, which add
direction marks the admin can't see. `clean_url` runs before every check:

- it trims surrounding whitespace;
- it removes bidi controls and zero-width characters everywhere in the link: U+200B, U+200E/F, U+202A–E, U+2066–9,
  U+FEFF and the Arabic letter mark U+061C;
- it removes ZWNJ (U+200C) from the scheme and host only, keeping it in the path, query and fragment, where Persian
  slugs use it.

The cleaned link is what's stored and what's rendered. This applies to the event's `join_url`, the personal
access `url` (admin form and Excel import), the platform's `support_url` and announcement buttons. The models clean
in `clean_fields`, before the field validators run. A host that still isn't plain ASCII after cleaning is refused
(«دامنه‌ی لینک باید با حروف انگلیسی باشد»), so Persian-script (IDN) domains aren't accepted. Their punycode form
(`xn--…`) is ASCII and passes. A trailing dot in the host (`skyroom.online.`) and the port don't matter when
comparing domains.

**Allowed domains** (`OnlinePlatform.allowed_domains`, one per line; commas and semicolons also separate). On save
(`OnlinePlatform.clean_fields`, so the admin and any `full_clean()` agree), each line is normalised:

- invisible characters (ZWNJ and ZWJ included) and surrounding spaces are removed;
- the scheme, `user@`, path, query, fragment, port, trailing dot, leading `*.` and leading `www.` are removed;
- Persian/Arabic digits become Latin and `۔ ٫ 。 ．` become `.`;
- the line is lower-cased, and duplicates are dropped.

A line that still isn't an ASCII hostname is refused, and each bad line is named in the error. If any line is
refused, the text is kept as typed so the admin can fix it.

`www` is not special when matching: a domain covers itself and every subdomain, and `www.example.com` is stored as
`example.com`. Entering either one accepts `example.com`, `www.example.com` and `class.example.com`. Matching
normalises when it reads too (`split_domains`), so rows saved before this fix (e.g. `www.skyroom.online`) work
without being re-saved. Unusable old lines are ignored when matching.

When a link's host isn't allowed, the error names the host it read and lists the platform's domains: «دامنه‌ی
این لینک (example.com) جزو دامنه‌های مجاز این پلتفرم نیست. دامنه‌های مجاز: skyroom.online (و زیردامنه‌هایشان).»
The same message appears in the event admin, the access rows and the import preview.

## 6. Personal secrets and the key

The password, access code and personal link are encrypted with Fernet (`crypto.py`) in `*_encrypted` columns, read
only through `OnlineEventAccess.read_secrets()`. The username and note are plain. Secrets can't leak through
`dumpdata`, `__str__`, admin history or logs. A row that can't be decrypted shows «با مدرسه تماس بگیرید» and logs an
error without its value; it never returns a 500.

`ONLINE_ACCESS_KEYS` is a comma-separated list in the environment: the first key encrypts, all decrypt. Production
refuses to start without a valid one. Development and tests use a fixed public key.

**If the key is lost, the secrets are gone.** Recovery means importing the files again.

### Generate

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the output in `.env` as `ONLINE_ACCESS_KEYS=<key>`, then restart.

### Store and back up

- Keep a copy in the school's password manager or another place only the system admin can open.
- **Back it up separately from database backups.** A dump together with its key exposes every secret, which is
  exactly what encryption prevents. Don't put the key in the database backup, its folder, the repository or a
  message.
- Check after a restore that an old row still opens, by pressing «نمایش» on one.

### Rotate

Do this on a schedule you choose, and at once if the key may have leaked or someone who held it leaves.

1. Generate a new key and put it **first**: `ONLINE_ACCESS_KEYS=<new>,<old>`. Restart. New writes use it; old rows still
   open.
2. Dry run: `python manage.py reencrypt_online_access`. It reports how many rows it would rewrite and writes nothing.
3. `python manage.py reencrypt_online_access --apply`. It works in batches under row locks and doesn't change
   `updated_by` or `updated_at`. A second run rewrites nothing.
4. If it lists rows no key can open, **stop and don't remove any key.** It exits with an error for that reason. Find
   the missing key, or delete those rows and import them again.
5. When it reports the old key is safe to remove: back up the new key, set `ONLINE_ACCESS_KEYS=<new>`, restart.

The command prints counts and row ids only, never a secret. If the key leaked, also replace the passwords themselves
on the platforms: an old database backup can still be opened with the leaked key.

## 7. Excel import

Event page → «ورود اطلاعات شخصی از اکسل» (`importer.py`, `import_template.py`; file reading is `core/spreadsheet.py`,
shared with the calendar importer).

- **Template:** per event, prefilled with its audience; student code, national code and name for reference, then link,
  username, password, access code and note. Existing secrets are never exported. Codes are Text cells, and names can't
  run as formulas.
- **Matching:** by student code or national code, with Persian digits accepted and lost leading zeros restored.
- **Errors block the whole file:** unknown student, a student outside the admin's branches, a duplicate student in the
  file, two codes pointing to different students, a bad link, an over-long value, a note alone on a new row.
- **A warning, still saved:** a student outside the audience, highlighted in the preview. Such a row does nothing unless
  the student joins the audience.
- **Skipped:** rows with no access data, so a partly filled template works.
- **Preview:** the totals; then only the rows with an error or a warning, one by one (masked); then the rows without
  errors counted per class (new and update) in a collapsed block. Valid rows are never listed one by one. The class
  comes with the branch in the same query, so the preview's query count doesn't grow with the file.
- **Re-import:** updates the student's row, and blank cells keep the stored value.
- **Preview:** masked. The session holds one encrypted token of the rows, tied to the admin and the event, expiring after
  30 minutes; it is cleared on confirmation or reload. The file isn't kept.
- **Confirmation:** validates again, locks the event row and saves everything or nothing.
- **Limits:** `ONLINE_ACCESS_IMPORT_MAX_ROWS` rows and 5 MB. No message ever repeats a link or secret.

## 8. Admin

| Who | May |
| --- | --- |
| Superuser | Everything, including «کل مدرسه» and reveal |
| Staff with the model permissions and `BranchAccess` | **See** items that touch their branches and whole-school items; **change** only items wholly inside their branches. Can't tick «کل مدرسه»; need one target in their branches; a grade needs a branch. Classes, students and exclusions must be theirs. On anything else: no access rows and no reveal |
| Staff without the permission | 403 |
| Teachers, supporters, the director, students | Nothing; no admin access |

- **Secrets:** `••••••` everywhere: lists, inlines, row pages, the import preview. A holder of
  `online_classes.view_access_secret` (granted by hand) presses «نمایش» on one row; the page only shows on POST, sends
  `no-store`, and the click goes to the admin history without the value. Without it, staff can enter or replace a secret but
  not read it; a blank field keeps the stored value. A row's student can't be changed after creation.
- **«چه کسانی می‌بینند»** (event and announcement change pages, `_audience_report.html`): one line of counts, and nothing
  per student.
  - **The line:** «N دانش‌آموز مخاطب»; for a personal event also «… با ردیف دسترسی · … بدون ردیف».
  - **Below it:** a per-class table in a `<details>` element, closed by default (no JS), with one row per class.
  - **Links:** each number opens the list page, filtered by class and/or access.
  - **Branch scope:** a non-superuser sees counts of their branches only, under «فقط دانش‌آموزان شعبه‌های شما». This
    includes whole-school items they can view but not change.
  - **Queries:** a fixed number whatever the audience size (locked in tests: event page 25, announcement page 19).
- **Student list page** (`<event or announcement>/<id>/students/`, `audience_students.html`):
  - **Access:** the same as the item's page. It needs view or change permission on the model, and an item outside the
    admin's items is a 404.
  - **Rows:** names of the admin's branches only, 100 per page.
  - **Search:** first and last name, student code and national code (Persian digits work). The national code is
    searchable but never shown.
  - **Filters:** class (only the audience's classes) and, for personal events, «همه / با ردیف / فقط بدون ردیف».
  - **Without JS:** plain GET forms and links. Pages keep the filters.
  - **Access rows:** for a personal event, the column names what a row holds («لینک، رمز»), never a value. For admins
    who may change the event, it links to the row's page. A student without a row gets «افزودن ردیف» if the admin also
    has `add_onlineeventaccess`.
  - **Queries:** a fixed number (locked: 18).
- **Adding one row** (`onlineeventaccess/add/?event=&student=&next=`): the access row add page exists only for a
  personal event given in `?event=` that the admin may change. Otherwise it's a 403, or a 404 for an unknown or shared
  event, and the rows list has no add button.
  - **Student:** prefilled; it must be in the event's audience and the admin's branches, without an existing row,
    whatever is posted.
  - **Return:** after saving or adding, the admin goes back to `next` only if it's a path on this site to that event's
    list page. Anything else gets Django's default redirect. «ذخیره و ادامه» stays on the row.
- **Event page:** the summary above, a blank inline row for adding by hand (existing rows are **never** listed there:
  they're edited from the list page or «دسترسی‌های شخصی»), template, import and «ساختن اطلاعیه».
- **Actions:** duplicate (a hidden copy with the audience, no rows, status back to scheduled, «(کپی)» in the title), and
  «حذف دسترسی‌های شخصی» for ended events (asks first, needs the delete permission). Rows are kept until someone deletes them;
  there is no automatic purge.
- **«ساختن اطلاعیه»:** the add form prefilled with title, window (now until the event ends) and audience. It's a copy: later
  changes to the event's audience don't follow.
- **Filters:** date, state (including «به‌تعویق‌افتاده، بدون زمان جدید»), type, platform, branch, grade. Branch and grade include
  whole-school items and items reaching them through a class.
- **Images:** re-encoded to JPEG through `website.images`; no SVG. Logos sit on a white tile because JPEG flattens transparency.
- **Student pickers** (`pickers.py`): «دانش‌آموزان», «دانش‌آموزان مستثنا» and an access row's student are select2
  autocomplete widgets backed by this app's own view (`…/onlineevent/student-autocomplete/`), never one checkbox per
  student. Branches, grades and classes stay checkboxes.
  - **Results:** students with a current enrolment, in the admin's branches (superuser: every branch). Searchable by
    name, student code and national code, and labelled «name · code · class · branch».
  - **Who can ask:** only this app's student fields; staff need `student.view_studentprofile` (or change).
  - **Form validation:** the form's queryset is the same set plus the students already selected on the item, so a
    forged id is "not a valid choice", and `targets_problems` checks branches again.

## 9. Settings (`base.py`)

| Setting | Default | Meaning |
| --- | --- | --- |
| `ONLINE_JOIN_LEAD_MINUTES` | 15 | Join opens this long before the start; events can override |
| `ONLINE_PAST_DAYS` | 14 | How long ended items stay in «گذشته» |
| `ONLINE_DASHBOARD_ITEMS` | 5 | Items in the dashboard's card |
| `ANNOUNCEMENT_MAX_VISIBLE` | 3 | Banners shown at once |
| `ONLINE_ACCESS_IMPORT_MAX_ROWS` | 1000 | Rows in one Excel file |
| `ONLINE_ACCESS_KEYS` | environment | See §6 |

## 10. Later phases

Not built: custom groups (one M2M on `AudienceTargets`, one term in `audience.py`), teacher or supervisor authoring, open
tracking (a redirect view and a table), recurring events (a nullable `series` FK).
