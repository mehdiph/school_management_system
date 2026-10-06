# Director App

## 1. Purpose

The panel of the school director («مدیر مدرسه»): one person who oversees **both branches** and manages the school through statistics. It is **read-only** (ADR-020): the director never creates or edits data — that is the system admin's job in the Django admin — and no page here has a form that writes or a link to an edit page.

Phase 1 has three pages: a dashboard, program execution, and attendance. Every number comes from the shared analytics layer (`docs/apps/analytics.md`, ADR-019), so the director and the supervisors see the same figure for the same class.

Branch comparison is first-class: every page has a branch filter (all / each branch), and the dashboard shows the branches side by side.

---

## 2. Access

| Who | Gets |
| --- | --- |
| A user with role `director` («مدیر مدرسه») | every page |
| A superuser | every page |
| Logged out | redirect to the login page (`?next=`) |
| Any other role (teacher, student, supervisor, accountant, counselor, IT, services, system admin), staff or not | redirect to their own dashboard (`accounts.utils.role_dashboard`), the teacher / student panel pattern |
| Any method other than GET / HEAD | 405 |

`director/permissions.py`: `director_required` (and `is_director`). No profile row is needed: the director sees every active branch. After login the director lands on `/director/`; the sidebar shows the director menu (also to a superuser browsing these pages).

**Creating or assigning the director:** in the Django admin, add or open the user and set «نقش» to «مدیر مدرسه». No staff flag, group or permission is needed (and the director should not be staff unless they also administer data). The Excel user import does not create directors.

---

## 3. Pages

| URL | Name | Content |
| --- | --- | --- |
| `/director/` | `director:dashboard` | KPI cards, alerts, branches side by side, academic calendar |
| `/director/execution/` | `director:execution` | expected slots and what happened to them |
| `/director/attendance/` | `director:attendance` | attendance rate trend, comparison, absentees |

### 3.1 Filters (every page)

A plain GET form above everything it scopes (`director/forms.py`), so every view is a link and works without JavaScript:

* **Presets** (links): today, this week (from Saturday), **this Jalali month (the default every page opens with)**, since the start of the academic year. The year-to-date view is the slowest late in the year (§8), so it is a choice rather than what every visit pays for (`director.forms.DEFAULT_PERIOD`).
* **Custom range**: two Jalali dates (typed in any digits, or picked with the project's persian-datepicker). The inputs always show the range in effect; dates that differ from the selected preset make the range custom. A range is clamped to the academic year and to today; a range entirely in the future shows an empty state.
* **Branch** (all / each active branch) and **grade** (all / each active grade).
* Invalid input (an impossible date, an end before the start, an unknown branch) is reported above the filters and not applied; the page still renders.
* The sidebar links and every drill-down link keep the filters.

Page-specific parameters: `view` (execution: `breakdown`, `teachers`, `subjects`) and `class` (a class drill-down on execution / attendance; a class outside the scope is ignored).

### 3.2 Dashboard

* **KPI cards**: active students (distinct students with an active enrollment in an active class of the year), classes (active classes), teachers (with an active assignment teaching an active class subject of an active class — as the supervisor counts them), and the **attendance**, **execution** and **content** rates (definitions in §4).
  * The three rates show the change vs the **previous period** of as many teaching days, in percentage points with ↑ / ↓ and a sign (never color alone). When that period is incomplete (start of the year) the card says «داده‌ی دوره‌ی قبل کافی نیست»; a range starting on the first day of the year (this month, in Mehr) has «بدون دوره‌ی قبلی».
  * The three counts have **no change indicator**: enrollments and assignments keep no status history, so "how many last month" cannot be answered faithfully (Phase 2, §9).
* **Alerts** (§5): four cards, each with its count, up to five items and a link to the page that explains it.
* **Branches side by side**: for each active branch (whatever the branch filter; the selected one is highlighted), in the same range and grade: students, classes, teachers, attendance / execution / content rates, unregistered slots, slots lost to closures.
* **Academic calendar**: teaching days elapsed (up to and including today) and remaining in the year (known closures already taken out), days lost to closures so far, and the closures of the next 30 days with their scope (branches, grades, bells) — for the selected branch / grade.

### 3.3 Execution

* Summary cards: execution rate (held of expected), unregistered and teacher-cancelled slots, slots lost to closures, makeup coverage (compensatory sessions for the slots lost to closures and cancellations). A note counts sessions outside the timetable and conflicts when there are any.
* **Breakdown** (default view): a table per level — branches; with a branch, its grades; with a grade, its classes; with a class (`?class=`), its class subjects (subject and teacher) — each row with expected, held, cancelled, unregistered, execution rate (with a bar: under 60% red, under 85% amber, level also spelled out for screen readers), lost to closures, compensatory, makeup coverage, and a total row. A breadcrumb goes back up.
* **By teacher** (`?view=teachers`): the same columns per teacher, lowest execution rate first.
* **Same subject across classes** (`?view=subjects`, needs a grade): held sessions per subject (rows) and class of the grade (columns), "held of expected"; a class **2 or more held sessions behind** the best class of its row is marked.
* **Conflicts**: sessions recorded in slots the calendar closed, in the range (the system admin resolves them).

### 3.4 Attendance

* Summary cards: attendance rate, absences, late rate, attendance recorded (delivered sessions with records).
* **Daily attendance rate**: one point per working day of the range. Closure days (no unit of the scope open) are a gray band with the event's title in the tooltip — **never plotted as zero**; days without records are gaps. Chart.js (vendored, ADR-021), RTL (time runs right to left, the axis on the right), Persian digits, crosshair tooltip. The same data is always in a table («جدول روزانه»), open by default and folded once the chart has drawn — so the page works without JavaScript. Fewer than two days with data: no chart, the table only. No data: an empty state.
* **Comparison** by branch → grade → class → class subject (like the execution breakdown): attendance rate, records, absences, late (and late rate), attendance recorded.
* **Most absences**: up to 20 students with the most absences in the range (count, then records), with their class, absence rate and lateness. No student detail page in Phase 1.
* **Sessions without attendance** (`#missing`): delivered sessions of the range older than the grace (§5) with no record at all.

---

## 4. Metric definitions

The definitions live in `docs/apps/analytics.md` §3 (and in code in `analytics`); in short:

| Metric | Formula |
| --- | --- |
| Teaching days | Saturday–Wednesday of the academic year, minus the days on which every (branch, grade) of the scope is closed for the whole day |
| Expected slots | timetable slots (`get_slots`, never Thursday) minus slots an active event closes; a slot of today only once its bell ended + 15 min |
| Held / cancelled / unregistered | the expected slot holds an HD (or JB) session / a CD session / nothing; bell-less legacy sessions fill the day's free slots in bell order |
| Execution rate | held ÷ expected slots |
| Lost to closures | number of HL sessions (shown apart) |
| Compensatory | JB sessions that fill no expected slot |
| Makeup coverage | compensatory ÷ (HL + teacher-cancelled) |
| Content rate | HD + JB sessions with a `SessionContent` row ÷ HD + JB sessions |
| Attendance recorded rate | HD + JB sessions with ≥ 1 attendance record ÷ HD + JB sessions |
| Attendance rate | (records − absent) ÷ records, on HD + JB sessions (late = attended) |
| Previous period | as many teaching days, immediately before the range |

A rate with nothing to divide by is «—».

---

## 5. Alerts and thresholds

Read from settings at request time (`director.selectors.threshold`), with these defaults. To change one, set it in `teachlog/config/settings/*.py`:

| Setting | Default | Used by |
| --- | --- | --- |
| `DIRECTOR_ALERT_ATTENDANCE_RATE` | `85` | classes whose attendance rate is **under** this % |
| `DIRECTOR_ALERT_UNREGISTERED_SLOTS` | `3` | teachers with **at least** this many unregistered slots |
| `DIRECTOR_ALERT_WINDOW_TEACHING_DAYS` | `7` | the window of both alerts above: the last N teaching days up to today |
| `DIRECTOR_ALERT_ATTENDANCE_GRACE_DAYS` | `1` | sessions without attendance are listed once their date is more than this many days ago |

| Alert | Rule | Links to |
| --- | --- | --- |
| کلاس‌های با حضور پایین | classes with records in the window and an attendance rate under the threshold, lowest first | the attendance page for that class, over the window |
| معلمان با جلسات ثبت‌نشده | teachers with ≥ threshold unregistered slots in the window, most first | execution, by teacher, over the window |
| جلسات بدون حضور و غیاب | HD / JB sessions of the year so far, dated before today − grace days, with no attendance record | the attendance page's list, for the year |
| تداخل با تقویم آموزشی | sessions in slots an active event closes (`find_conflicts`, the year so far) | the execution page's conflicts, for the year |

The alerts follow the branch and grade filters, never the date range (each has its own window), so they always say "now".

The thresholds are **global** (the same for both branches) in Phase 1. Per-branch thresholds can be added later — for example a `{branch code: value}` setting, or a small model the system admin edits — read through `director.selectors.threshold`, which every alert already goes through.

---

## 6. Structure

| File | Role |
| --- | --- |
| `director/permissions.py` | `director_required` |
| `director/forms.py` | `DirectorFilterForm` → `DirectorFilters` (with `query()` for links) |
| `director/selectors.py` | page data: `Dimensions`, `dashboard`, `execution`, `attendance`, alerts, drill-down rows, head counts, top absentees |
| `director/views.py` | three GET views: read the request, call one selector, render |
| `director/templatetags/director_tags.py` | `percent`, `signed`, `rate_level`, `bar` |
| `director/templates/director/` | `_layout.html` (header, filters, empty states), the three pages, partials |
| `director/static/director/` | `css/director.css`, `js/filters.js` (date picker), `js/attendance_chart.js` |

The pages reuse the supervisor panel's components (stat cards, filter bar, cards, tables, badges, empty states, coverage bars) and add only `director.css`. Layout: six KPI cards in one row on a wide screen, three on a tablet, two on a phone; tables become cards on narrow screens (`data-label`).

---

## 7. Queries

Every page runs a **fixed number of queries**, whatever the number of classes, sessions or records (`director/tests.py`, `QueryCountTests`, locked):

| Page | Queries | Of which |
| --- | --- | --- |
| Dashboard | 23 | 7 overhead (session, user, branch middleware, footer) + 3 dimensions (year, branches, grades) + 4 the year's events + 4 engine (class subjects, slots, sessions, attendance tallies) + 5 head counts |
| Execution (any view) | 17 | overhead, dimensions, events, engine without attendance (3) |
| Attendance | 19 | overhead, dimensions, events, engine (4) + 1 top absentees |

The dashboard runs the engine once over the **year so far**: that one run serves the selected range, the previous period, the alert window, and the year-to-date alerts (its conflicts are exactly `find_conflicts`' and its sessions without attendance need no extra query).

---

## 8. Performance (synthetic full year, PostgreSQL)

### 8.1 Measurements

Synthetic year (`seed.py` in the implementation report): 2 branches × 3 grades × 7 classes = 42 classes, 12 subjects and 30 timetable slots a week per class (504 class subjects), 1,260 students; 47,880 expected slots, 43,924 sessions (85% held, 5% cancelled, 10% unregistered, compensatory sessions on Thursdays), 33,749 contents, **1,038,480 attendance records**; nine closures (Nowruz, a branch-only and a partial-day closure among them) and a conflict. Times are the median of 5 full requests (view + template) through Django's test client, on an 8-core laptop with PostgreSQL 16 in Docker on the same machine, "now" pinned to the end of the year (25 Khordad 1406):

| Page | Filters | Time | Queries |
| --- | --- | --- | --- |
| Dashboard | year so far | 1.8 s | 23 |
| Dashboard | this month / this week | 1.6 s / 1.5 s | 23 |
| Dashboard | year, one branch | 1.8 s | 23 |
| Execution | year, whole school | 1.3 s | 17 |
| Execution | year, one branch + grade | 0.28 s | 17 |
| Execution | year, by teacher | 1.4 s | 17 |
| Execution | year, same subject (one grade) | 0.48 s | 17 |
| Execution | this month | 0.55 s | 17 |
| Attendance | year, whole school | 2.7 s | 19 |
| Attendance | year, one class | 1.7 s | 19 |
| Attendance | this month / this week | 0.88 s / 0.60 s | 19 |

The same data, "now" moved through the year (whole school, year so far):

| As of | Dashboard | Execution | Attendance |
| --- | --- | --- | --- |
| 15 Aban (≈ 1.5 months) | 0.70 s | 0.61 s | 0.92 s |
| 15 Dey (≈ 3.5 months) | 1.03 s | 0.82 s | 1.45 s |
| 15 Esfand (≈ 5.5 months) | 1.32 s | 0.94 s | 1.89 s |
| 25 Khordad (end of year) | 1.82 s | 1.28 s | 2.68 s |

Before optimization the end-of-year figures were 7.7 s / 3.2 s / 5.0 s: most of the time went into converting jDateField values into `jdatetime` objects (whose constructor queries the locale), into a join that aggregated a million attendance records, and into recomputing the calendar conflicts. See the implementation report for what changed.

The cost grows **linearly with the days elapsed**: the engine looks at every expected slot of the range (≈ 48k for a whole school year) in Python, and the attendance page groups every record of the range (≈ 1M) twice (per session and per student). Narrow scopes (a branch and grade, a month, a week) stay well under a second all year.

### 8.2 Decision

The current timings are accepted for Phase 1, with two measures:

* every page opens on **this Jalali month** (`director.forms.DEFAULT_PERIOD`); "since the start of the academic year" stays a preset;
* a **daily summary table** (one row per day and class subject, written by the same engine, refreshed nightly and on writes to past days) ships **before 1 Dey 1405 (22 December 2026)**, with a management command that recomputes a sample of days with the live engine and reports any mismatch. Specification: `docs/apps/analytics.md` §8.

No cache was added.

---

## 9. Phase 2 follow-ups

Designed for, not built:

* **Status history for enrollments and assignments** (when a student left, when a teacher's assignment ended), so the student / teacher counts can be compared with the previous period and enrollment / dropout analytics become possible.
* Teacher detail page and recording discipline (late recording, content quality).
* Supervisor overview (a supervisor's classes as a scope: `AnalyticsScope(class_subjects=...)` already supports it).
* Day / bell absence patterns, consecutive absences (must skip holiday sessions), a student detail page.
* Exports (PDF / Excel) and a weekly email digest — both can reuse `director.selectors` unchanged.
* **Daily summary table with its verification command** — before **1 Dey 1405 (22 December 2026)** (§8.2, `docs/apps/analytics.md` §8).
* **Academic-year selector** — before the **1406–1407 academic year starts (Mehr 1406, September 2027)**. Phase 1 always shows the current year (`AcademicYear.is_current`), so when the new year becomes current the director loses sight of 1405–1406. `AnalyticsScope` already takes the year as a parameter; the filter form and `Dimensions` need a year field (validated against existing years), and the head counts / alerts must follow the selected year.
* Per-branch alert thresholds (§5).
