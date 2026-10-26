# Architecture Decisions

This document records important architectural decisions made during the development of the School Management System.

The purpose of this document is to explain why certain design choices were made and to provide context for future development.

---

# ADR-001: Custom User Model

## Decision

A custom User model was implemented by extending Django's AbstractUser.

## Rationale

The system requires additional user-related information that is not provided by Django's default User model.

Examples:

* User roles
* Phone number
* Future profile extensions

Using a custom User model from the beginning avoids future migration complexity.

## Consequences

Benefits:

* Flexible authentication system
* Easier role management
* Better support for future modules

Trade-offs:

* Increased initial setup complexity

---

# ADR-002: Separation of User and Staff Information

## Decision

Staff-specific information is stored in a separate Staff model instead of the User model.

## Structure

User
→ Staff

## Rationale

Authentication information and personnel information have different responsibilities.

User should only contain:

* Authentication
* Authorization
* Basic identity

Staff should contain:

* Personnel code
* National code
* Employment information
* Contact information

This separation improves maintainability and follows the Single Responsibility Principle.

---

# ADR-003: Dedicated Teacher Profile

## Decision

Teacher-specific information is stored in TeacherProfile.

## Structure

User
→ Staff
→ TeacherProfile

## Rationale

Teachers require additional information that is not relevant to all staff members.

Examples:

* Education
* Field of study
* Teaching experience
* Homeroom teacher status

The architecture is designed to support future profile types:

* CounselorProfile
* AccountantProfile
* SupervisorProfile
* ITProfile

without modifying the Staff model.

---

# ADR-004: Student Profile Separation

## Decision

Student-specific information is stored in StudentProfile.

## Structure

User
→ StudentProfile

## Rationale

Students have different requirements from staff members.

Examples:

* Student code
* Enrollment information
* Class assignment

Keeping student information separate prevents unnecessary complexity in the User model.

---

# ADR-005: ClassSubject as the Core Educational Entity

## Decision

The system introduces a dedicated ClassSubject model.

## Structure

SchoolClass
+
Subject
+
Teacher

↓

ClassSubject

## Rationale

A direct relationship between classes and subjects is insufficient.

The system needs to support:

* Multiple teachers
* Session tracking
* Scheduling
* Reporting

All educational activities are attached to a ClassSubject.

## Consequences

Benefits:

* Clear educational structure
* Easier reporting
* Better scalability

This entity became the central component of the teaching system.

---

# ADR-006: Sessions Belong to ClassSubject

## Decision

Teaching sessions are attached to ClassSubject rather than SchoolClass.

## Structure

ClassSubject
→ SchoolSession

## Rationale

Sessions are related to a specific subject taught by a specific teacher.

Example:

Grade 4-A
Mathematics
Teacher A

must have different sessions from:

Grade 4-A
Science
Teacher B

Attaching sessions directly to SchoolClass would make this distinction impossible.

---

# ADR-007: Session Content Separation

## Decision

Educational content is stored in a dedicated SessionContent model.

## Structure

SchoolSession
→ SessionContent

## Rationale

Session metadata and educational content serve different purposes.

SchoolSession stores:

* Date
* Session number
* Status

SessionContent stores:

* Topic
* Activities
* Homework
* Notes

This separation improves readability and future extensibility.

---

# ADR-008: Weekly Schedule System

## Decision

Class schedules are stored separately in ClassSchedule.

## Structure

ClassSubject
→ ClassSchedule

## Rationale

Schedules represent recurring events while sessions represent actual teaching events.

Separating these concepts avoids duplication and improves data consistency.

---

# ADR-009: Support for Rotational Weeks

## Decision

The scheduling system supports three week types.

## Week Types

1 = Week One

2 = Week Two

3 = Both Weeks

## Rationale

Some schools use rotating schedules where Week One and Week Two differ.

The system must support:

* Fixed schedules
* Alternating schedules

without duplicating schedule records.

---

# ADR-010: Student Schedule Retrieval Through SchoolClass

## Decision

Students are not directly linked to ClassSchedule.

## Structure

Student
→ SchoolClass
→ ClassSubject
→ ClassSchedule

## Rationale

Schedules belong to classes, not individual students.

Creating a direct relationship would introduce redundant data and increase maintenance costs.

This design follows database normalization principles.

---

# ADR-011: Soft Activation Strategy

## Decision

Most educational entities include an is_active field.

## Rationale

Historical educational data should not be deleted.

Examples:

* Classes
* Subjects
* Assignments

can be deactivated while preserving historical records.

---

# ADR-012: Academic Year Isolation

## Decision

SchoolClass records belong to a specific AcademicYear.

## Structure

AcademicYear
→ SchoolClass

## Rationale

Educational data must be separated between academic years.

Benefits:

* Historical reporting
* Easier archiving
* Cleaner data organization

---

# ADR-013: Reports are generated through a shared BaseReportView.

## Reason:
* To guarantee identical business logic between HTML and PDF outputs and avoid duplicated report-generation code.

---

# ADR-014: Supervisor Data Is Scoped Through SupervisorScope

## Decision

Every supervisor query starts from `SupervisorScope` (`supervisor/selectors.py`): the classes assigned through `SupervisorClass` in the supervisor's branch and grade. The training sessions and supervised teachers pages use `supervised_class_subjects()`, the active class subjects of active classes.

## Rationale

* One place defines what a supervisor may see, so a view or template cannot bypass it.
* Filters only narrow an already scoped queryset; user input never widens it.
* Detail and fragment views use `get_object_or_404` on the scoped queryset, so records outside the scope are a 404 and their existence is not leaked.
* Filter options come from the same scope, so a foreign id is just an invalid choice.

---

# ADR-015: HTML Fragments for Progressive Enhancement

## Decision

Panels stay server-rendered (MVT). When JavaScript needs to load content (an expanded timeline row, the session drawer), it fetches the same URL with `?partial=1` and the view renders only the fragment template; without the parameter the view renders a full page that includes that fragment.

## Rationale

* Rendering logic stays in Django templates; there is no JSON API or client-side templating to keep in sync.
* Every enhanced link still works without JS, and can be opened in a new tab or shared.
* A query parameter (rather than a request header) keeps full-page and fragment responses on different URLs, so caches never mix them up.

---

# ADR-016: A Session Is Identified by Class Subject, Date and Bell

## Decision

`SchoolSession` has a nullable `bell` foreign key, and `(class_subject, date, bell)` is unique when the bell is set. It does not point at the `ClassSchedule` row it was recorded for.

## Rationale

* The same subject can be taught at two bells on one day; `(class_subject, date)` cannot tell those two sessions apart.
* Timetable rows are edited, moved and deleted during the year. A foreign key to them would either block those edits (`PROTECT`) or lose the session's slot (`SET_NULL`), while past sessions must stay intact.
* The date already gives the weekday and the rotation week, so date + bell is the slot. Bells are stable and soft-deactivated.

## Consequences

* Sessions recorded before the field existed have no bell. `backfill_session_bells` matches the unambiguous ones (dry run first); the rest count against their day's slots in bell order.
* Two bells of one subject on one day are two expected sessions everywhere (teacher week, supervisor "missing" list, coverage).

---

# ADR-017: Holidays Are Sessions With Their Own Status, From One Calendar Service

## Decision

A slot closed by a `CalendarEvent` gets a `SchoolSession` with the dedicated status `HL` (not `CD`), no session number, a link to the event and `is_auto_created = True`. All holiday logic lives in `academic_calendar.services`; panels only ask it (`Closures`, `get_slots`, `is_working_day`, ...). `SchoolSession.objects.counted()` (`status != HL`) is the single exclusion rule for counts.

## Rationale

* Teacher-entered `CD` sessions are numbered and counted; mixing the two would turn every count into a two-column condition that one query would eventually forget.
* A row per closed slot shows the reason wherever sessions are listed, without each page re-deriving the calendar.
* `is_auto_created` keeps cleanup away from anything a person created; held sessions found in closed slots are reported as conflicts, never overwritten.
* One service keeps the teacher page, the session form and the supervisor pages from ever disagreeing about a closure.

## Consequences

* Every write that can change which slots are closed (event save/deactivate/import, timetable and class subject changes) must re-sync; the admin, the import and `academic_calendar.signals` do.
* The sync is idempotent and can be re-run any time (`sync_calendar_sessions`).

---

# ADR-018: Session Numbers Follow Teaching Order

## Decision

Counted sessions of a class subject are renumbered 1..N in teaching order (date, then bell) on every save and delete, under a row lock on the class subject, in two phases so the unique `(class_subject, session_number)` constraint holds after each statement.

## Rationale

* Teachers record missed sessions from earlier days (the weekly schedule makes past slots clickable); refusing them, or numbering them out of order, would make numbers meaningless.
* Holidays take no number, so numbering stays continuous.

## Consequences

* A session number shown in the past can change when an earlier session is recorded or one is removed. Anything that needs a stable reference uses the session's id, not its number.

---

# ADR-019: Metrics Are Defined Once, in a Shared Analytics Layer

## Decision

Every school metric (expected slots, slot outcomes, execution rate, makeup coverage, content rate, attendance recorded / attendance rate) is computed by the `analytics` app: `AnalyticsScope` (what), `engine.compute` (one pass over slots and sessions) and `metrics.Breakdown` / `breakdowns()` (counts, rates, any grouping and date window). Rules that lower layers also need (`counted_q`, `missing_content_q`, `attendance_rate`, the registration grace) live in `analytics.definitions`, which imports no model. The legacy bell-less fallback is one function, `academic_calendar.services.match_sessions`. Panels choose a scope, a window and a grouping; they never re-derive a rule.

The supervisor's training-sessions coverage moved onto the engine, and its dashboard attendance rate onto the same formula, in the same change that added the director panel.

## Rationale

* The director and a supervisor looking at the same class must see the same number. Before, coverage was a count (every HD + JB session against the expected slots, which could pass 100%) and the attendance rate counted only «حاضر»; a second, slot-based definition for the director would have made two "truths".
* The fallback for sessions without a bell existed in three copies (calendar sync, supervisor «نیازمند پیگیری», teacher dashboard); a fourth would have drifted.
* Computing on the fly from aggregated queries keeps Phase 1 free of summary tables that would need their own invalidation; the engine runs a fixed number of queries whatever the data size, and pages lock their counts in tests.

## Consequences

* Execution is slot-based: only a session recorded in an expected slot makes it "held" (a JB session in a regular slot included); compensatory sessions elsewhere count as makeup, never as execution. Late counts as attended everywhere.
* A new metric or grouping is added to `analytics` and tested there; panels only display it.
* Cost grows with the range: a whole year means every slot and session of the year in memory and one grouped query over its attendance records (measured in `docs/apps/director.md` §8). Decided: a daily summary table per (day, class subject), **written by the engine itself** so the definitions stay single, with a command that recomputes sampled days live and reports mismatches — before Dey 1405 (`docs/apps/analytics.md` §8). *(October 2026, ADR-023: the director no longer has year-wide views, so the deadline is dropped; the table is built only if a page passes one second when measured in mid-Bahman 1405.)*

---

# ADR-020: The School Director Is a Role With a Read-Only Panel

## Decision

The director is `User.Roles.DIRECTOR` («مدیر مدرسه») with no profile model. `director.permissions.director_required` admits that role and superusers, sends everyone else to their own dashboard (the teacher / student pattern), and accepts only GET / HEAD. The panel has no form that writes and no link to an edit page. The system admin's role is relabelled «مدیر سامانه».

## Rationale

* The director sees both branches, so there is nothing to scope and nothing to store: a profile row would only be one more thing to forget to create.
* Writes belong to the system admin in the Django admin; a read-only panel cannot be misused to change data, and makes the separation visible.
* «مدیر» alone was ambiguous between the person who runs the school and the person who runs the system.

## Consequences

* The director is not staff (no Django admin) unless the system admin also makes them staff on purpose.
* Roles and `is_staff` stay independent, for the system admin too: «مدیر سامانه» does not imply staff access (decided October 2026); staff access is granted explicitly.
* `core.services.access` does not know the director: the panel uses its own `?branch=` filter over all active branches, never `request.branch`.

---

# ADR-021: Front-End Libraries Are Vendored, Never Loaded From a CDN

## Decision

Third-party CSS / JS / fonts are copied into `static/` (with their licence and a README stating the version, source and integrity) and served with the project's static files. No template loads anything from an external host. Chart.js 4.5.1 is vendored under `static/vendor/chartjs/`; Font Awesome 7.2 already was (`static/assets`), and the two student pages that also loaded Font Awesome 6.4 from cdnjs no longer do.

## Rationale

* External CDNs can be slow, unreliable or blocked for the school's users; a page that depends on one breaks for reasons outside the project.
* Vendored files are reviewed, versioned with the code, and cannot change under the project.

## Consequences

* Upgrades are deliberate: download, check the integrity against the registry, replace the files, update the README.
* Every chart has a table twin and pages work without JavaScript (ADR-015), so a missing script never hides data.

---

# ADR-022: Attendance Is Taken Daily by the Grade Supporter, Behind One Cutoff Service

## Decision

From `settings.ATTENDANCE_DAILY_START_DATE` (1 Aban 1405, 23 October 2026) attendance is **one sheet per class per day** (`DailyAttendanceSheet` / `DailyAttendance`), taken at 8:30 by the class's grade supporter (`SupervisorProfile` through `SupervisorScope`); superusers and staff admins with the permission of the class's branch may also take or correct it. Teachers no longer take attendance.

The per-session attendance (`Attendance`) is renamed `SessionAttendance` and **archived**: same table (`db_table` pinned), every row kept, no data converted, read-only in the app (view-only admin, read-only page, 403 for teachers from the cutoff on).

`attendance.services` is the only place that decides which source a date has: before the cutoff the archive (records of held and compensatory sessions), from it on the daily sheets. Every page, report and the analytics engine read attendance through it. Which days can have a sheet comes from the class's weekly timetable and the academic calendar (a day with at least one open lesson), the same rule as the engine's expected class-days.

## Rationale

* Some teachers teach every class and attendance is in fact taken once in the morning by the supporter, who follows absences up at once; a per-session record by each teacher no longer matches how the school works.
* Converting old session records into daily ones would invent data (which session's status is "the day's"?). Archiving keeps history exactly as recorded.
* A date setting rather than a hard-coded day lets the switch move if go-live slips, and lets tests place the cutoff inside their fixture.
* One reader of the cutoff keeps ADR-019's promise: the director and a supporter still see the same number.

## Consequences

* Daily attendance belongs to a class, not to a class subject or teacher: per-subject and per-teacher attendance exist only before the cutoff. Metrics group class-days only by class-level keys.
* Over a range that spans the cutoff, counts add missed sessions (before) and missed days (after); they are never converted.
* «غیبت موجه» exists only in daily attendance and is an absence in every rate.
* "Attendance recorded" means class-days with a sheet from the cutoff on; the director's list of missing attendance only lists class-days (archived gaps cannot be completed).
* The planned daily summary table (ADR-019) needs a per (day, class) part for daily attendance, if it is built (ADR-023).

---

# ADR-023: The Director Panel Shows Daily Attendance at a Glance; Execution Waits for بودجه‌بندی

## Decision

The director panel (October 2026) is reduced to **daily attendance**, presented for a reader who is not data-literate: plain Persian sentences with names («امروز ۲۳ دانش‌آموز غایب هستند (۵ نفر موجه)»), the classes that have not taken attendance with their supporter, today's absent students, students absent on several days, and a daily chart and class table for a period (today / this week / this month) and a branch. Percentages are secondary text only; there are no previous-period comparisons, deltas or technical terms; status colours are only green / yellow / red, always with words.

**Program execution is removed** from the panel (the execution page, execution / content rates, the per-teacher view, the same-subject comparison, conflicts, makeup) **until curriculum budgeting («بودجه‌بندی») exists**; `/director/execution/` redirects (302) to the home page. It will return on the existing `analytics` engine.

The panel computes no metric: everything comes from `attendance.services` (`class_day_statuses`, `student_tallies`, `get_absences`, …) and `supervisor.selectors.class_supervisors`, the functions the supporter's daily attendance page is built on. A class is due to take attendance on a day when its timetable has an open lesson (`planned_class_days`); today it is reported missing only once its first open bell has ended plus the engine's 15-minute grace (`analytics.definitions.slot_deadline`, now the one deadline rule the engine also uses).

## Rationale

* The Phase 1 panel (KPI cards, rates, drill-downs, alerts) answered questions a statistician would ask; the directors want to know who is absent today and whether every class has been checked.
* Execution compared classes with each other and with the timetable; without a plan of what should have been taught by when, a director cannot tell a good number from a bad one. بودجه‌بندی gives that baseline.
* Daily attendance, taken at 8:30 by the supporter (ADR-022), is the one figure that is fresh every morning and means the same to everyone.
* Reusing the supporter's functions keeps ADR-019's promise: the director and the supporter see the same classes as missing once the grace is over (tested), and the same absences.

## Consequences

* The pages read today and at most one month of daily sheets: a fixed, small number of queries and no year-long engine run. The daily summary table planned in ADR-019 is no longer needed for the director; its deadline (1 Dey 1405) is dropped in favour of a measurement in mid-Bahman 1405 (`docs/apps/analytics.md` §8).
* Archived per-session attendance is not shown on the director panel: every range starts at `ATTENDANCE_DAILY_START_DATE` at the earliest.
* For the first minutes of each school day, a supporter sees a class «ثبت نشده» while the director sees «هنوز وقت دارد»: the supporter acts at 8:30, the director is told only what is late.
* The label thresholds (`DIRECTOR_FREQUENT_ABSENCE_DAYS`, `DIRECTOR_CLASS_ABSENCE_YELLOW` / `_RED`) are school policy in settings, to be reviewed after the first month of real data.
* `analytics.periods.previous_period`, `preceding_teaching_days` and the per-teacher grouping keep their tests but have no page caller until execution returns.

---

# ADR-024: Public Form Submissions Are Stored, Rate-Limited in the Database, and Not Emailed by Default

## Decision

A form on the public website (first: «تماس با ما», `website:contact`) saves each submission as a row that staff read in the admin (`ContactMessage`), and sends no email unless a later decision adds it. Spam is held off in three layers, all server-side:

* a honeypot field hidden from people; when it is filled, the visitor sees the normal success message and nothing is saved;
* a signed render timestamp: submissions faster than `CONTACT_MIN_FILL_SECONDS` or older than `CONTACT_MAX_FORM_AGE_SECONDS` are refused;
* a rate limit counted on the stored rows themselves: `CONTACT_RATE_LIMIT` (3 per 10 minutes) per normalised mobile number **and** per device, and `CONTACT_DAILY_LIMIT` (50 per 24 hours) per device. Refused with HTTP 429; what the visitor typed is kept.

The "device" is an HMAC-SHA256 of the client IP keyed with `SECRET_KEY`; the raw IP is never stored. The client IP is read from the header named in `CLIENT_IP_HEADER` (from the environment: the CDN's client-IP header in production, nginx's `X-Real-IP` without a CDN), falling back to `REMOTE_ADDR`.

## Rationale

* No cache is configured and gunicorn's worker count comes from `WEB_CONCURRENCY`: a per-process cache would count each worker separately. Rows in PostgreSQL are shared by all workers and need no new service; two indexes keep the one aggregate query cheap.
* Iranian mobile carriers put many users behind one IP (CGNAT). The short window therefore also counts per mobile number, and the per-IP cap is only a daily ceiling, high enough for a school's real traffic from one carrier address.
* Email is not configured on the server, and a stored row cannot be lost in a spam folder.
* Keeping only an HMAC of the IP is enough for the limit and keeps one less piece of personal data about parents.

## Consequences

* `CLIENT_IP_HEADER` must name the CDN's header in production. If the origin can be reached without going through the CDN, that header can be forged and only the per-mobile limit holds; the origin should accept traffic from the CDN only.
* The office needs `website.view_contactmessage` (and `change_contactmessage` to tick «پیگیری شد») to read messages; permissions are granted by hand, never in migrations.
* Messages are kept until a superuser deletes them; there is no automatic retention period yet.

---

# ADR-025: Public Website Content Is Editorial, Never Computed From School Data

## Decision

Everything the public website states about the school (texts, numbers such as «۴۰۰+ دانش‌آموز», milestones, people, photos) is entered by hand in the admin and shown as typed. No public page counts or reads enrolments, staff, classes, attendance or any other school record to produce what it shows. First applied on «درباره ما» (`website:about`): `AboutFact.value` is free text, `AboutPerson.role` is typed, and seeded content that would read as a fact (milestones, numbers) is created inactive until the school fills it in.

Where a public item links to a school record for convenience, only named, documented fields follow it: `ContactLocation` shows its branch's name, address and phone; `AboutPerson` shows its staff member's first and last name; `LandingTeacher` (the teacher cards of the landing page and the «معلمان» page) shows its teacher's first and last name and, as a fallback specialty, the profile's `field_of_study`. A name never falls back to the username.

People are published one by one, on purpose: a teacher appears on a public page only when an admin ticks it for that page (`on_teachers_page`, `on_home`), and nobody is listed because they exist in the school's records. A card or person linked to someone who has left (inactive `Staff`) is hidden.

Photos of people are published only when uploaded for that purpose, never the account avatar (`AboutPerson`, and since the teachers page also `LandingTeacher`), and an uploaded photo of a person is re-encoded on save (`website/images.py`: upright, at most 900 px, a fresh JPEG), so no EXIF data such as a phone's GPS position is published. Without a photo, the name's first letter is shown.

Invented content presented as fact is not published either: the four made-up teachers the landing page was seeded with are deactivated (`website.0013`) unless an admin had already edited them.

## Rationale

* A public number is a claim to parents. It should say what the school decides to say, rounded and worded as it wants, not whatever a query happened to return that day (mid-year transfers, test accounts, inactive rows).
* Internal data stays internal: the public site can't leak counts, names or photos the school never chose to publish.
* Metrics with a definition belong to `analytics` (ADR-019) and to logged-in panels; the website is not one of them.

## Consequences

* The school must keep these figures up to date by hand; the admin help texts say so.
* A new public page (blog, registration) follows the same rule: content models, admin-edited, no queries into school apps beyond an explicit, documented fallback like the ones above.
* The About page's gallery and the other website images (slides, highlights) are not re-encoded yet; they are pictures of the school rather than portraits, and are a follow-up.
* The blog (ADR-026) follows the same editorial rule: the only school data it reads is an author's first and last name (as a fallback for the byline) and a teacher card the admin linked on purpose. An author's photo is one uploaded for the blog or the linked teacher card's photo, never the account avatar.

---

# ADR-026: Blog Authorship Is Granted per Section by the Website Admin; Post HTML Is Sanitized With an Allow-List

## Decision

The school blog (`blog` app, `/blog/`) is written by people the website admin names, one by one: a `BlogAuthor` row per person and an `AuthorSection` row per section they may write in, recording who granted it and when. Being an author is a grant on top of a role, not a role. A person **can write** only while their `BlogAuthor` is active, their account is active, their role is in `BLOG_AUTHOR_ROLES` (teacher, counselor, supervisor, director, system admin; never students), their `Staff` record, if any, is active, and the section is granted and active. `blog.permissions` is the only code that decides this.

Authors write in an authoring area, «نوشته‌های من» (`/blog/write/`), rendered in their own panel's shell; they are not made staff and never use the Django admin. The director writes there too, so the director panel itself stays read-only and GET-only (ADR-020). **Editors** («ویراستار وبلاگ») are staff with `blog.publish_post` and work in the admin for all sections; there are no per-section editors yet.

A post moves through draft → submitted → published (now or at a future time) → archived, only through `blog.services`, each step under a row lock that checks the state it starts from. Submitting needs the author's privacy acknowledgement; publishing needs the editor to tick every line of the review checklist. "Public" is one queryset rule, `Post.objects.public()`: published, `published_at` reached, section active. There is no scheduler.

Post bodies are written in Trix (vendored, ADR-021) and stored as HTML that `blog/content.py` reshapes and then sanitizes with an `nh3` allow-list, on every save and again when shown: a fixed set of tags; links only to http(s), mailto, relative paths and anchors, with `rel="noopener noreferrer"`; images only from `MEDIA_URL` + `blog/`, uploaded through the blog and re-encoded without metadata. No script, style, iframe, event handler, `style` or `class` attribute survives. The public blog pages also send a strict Content-Security-Policy. The editor's image upload is the blog's one JSON endpoint.

## Rationale

* Counselors, the main writers of «مشاوره», have no panel; making teachers and counselors staff would give them the admin, which was built for the system admin (ADR-020: roles and `is_staff` are independent).
* A grant per section keeps least privilege: a teacher who writes for «پرورشی» can't publish in «مشاوره».
* A rich-text body is the first public HTML not escaped by the template engine. An allow-list in `Post.save()` covers every path (authoring area, admin, shell, tests); sanitizing again on render covers rows written any other way; the CSP stops a script even if the sanitizer had a bug.
* `bleach` is deprecated; `nh3` (the Rust `ammonia` sanitizer) is maintained, MIT and a pure wheel.
* Without a scheduler, a status flip at a set time would need a job someone must run; comparing `published_at` with the clock in one queryset needs nothing.

## Consequences

* Authors, sections and the «ویراستار وبلاگ» group's permissions are set up by hand in the admin; no migration grants anything (as in ADR-024).
* An author whose role or employment changes stops writing at once; their published posts stay public with their byline. `BlogAuthor.user` is `PROTECT`: a user with an author row can't be deleted.
* Images uploaded into a draft are served from `/media/` like every upload: their names are random and unguessable, but not secret.
* What an author can format is limited on purpose (paragraphs, two heading levels, lists, quotes, links, images); colours, fonts and embeds are not possible.
* The body pipeline parses HTML with `tinyhtml5`, already pinned in `requirements.txt` for WeasyPrint.

---

# Future Architectural Directions

Planned modules:

* Assessment Management
* Parent Portal
* Notification System
* Messaging System
* Financial Management
* School Analytics
* Curriculum Plan (بودجه‌بندی): planned lessons per subject, grade and year, so supervisors can compare recorded sessions with the plan automatically (proposal in `docs/apps/supervisor.md`)
* Program execution on the director panel, back after بودجه‌بندی and built on the existing `analytics` engine (ADR-023, `docs/apps/director.md` §8)

Future development should follow the same principles:

* Separation of concerns
* Explicit relationships
* Reusable domain entities
* Normalized database design
