# Director Dashboard, Phase 1: Plan and Implementation Report

Branch `director-dashboard` (not pushed). Read-only analytics panel for the school director over both branches. Reference documentation: `docs/apps/director.md` (the panel) and `docs/apps/analytics.md` (every metric definition).

---

## 1. Step 0 findings (before any code)

1. **Roles and access.** No director role existed. `User.Roles` had student, teacher, supervisor, accountant, counselor, it, services and `admin` («مدیر», used for the system admin). There are no groups or permissions; each panel's decorator checks the role plus a profile. Two patterns: `teacher_required` / `student_required` redirect other roles to their own dashboard (`accounts.utils.role_dashboard`), `require_supervisor` returns 403.
2. **Reusable logic.**
   * `academic_calendar.services` already had `get_slots`, `Closures`, `get_events`, `is_working_day`, `get_week_type`. There was no `closures_for`; the equivalent is `Closures.between`.
   * The legacy "count fallback" (a bell-less session fills the day's first free slot in bell order) existed in **three copies**: `academic_calendar.services._plan`, `SupervisorDashboardSelector.attention_items`, `core.selectors._today_lessons`.
   * The supervisor's "missing content" Q, "counted" Q and the present/absent/late aggregate (three copies) were private to `supervisor/selectors.py`.
   * The supervisor's coverage was count-based: every HD + JB session of the range ÷ open expected slots (`count_open_slots`), which could pass 100%.
   * `report/selectors.py` and `core/selectors.py` had nothing metric-like to generalize.
   * `find_conflicts` loaded every session of the year with six joins.
3. **Attendance statuses**: `present`, `absent`, `late`; there is no "excused". The supervisor's `present_rate` counted `present` only.
4. **SessionContent**: `title`, `content`, `homework` (required), `activity`, `notes` (optional). "Has content" in the supervisor panel = a `SessionContent` row exists; "missing content" applies to non-CD, non-HL sessions (HD and JB). A homework rate is not meaningful: `homework` is required and teachers write «ندارد».
5. **Charts**: no chart library vendored (jQuery and persian-datepicker only). Recommended Chart.js 4 vendored.
6. **Legacy bell-less sessions**: coverage simply counted them; slot-level code used the fallback above.
7. **Templates**: `base.html` + `partials/sidebar.html` (switching on the role); the supervisor panel's components (stat cards, filter bar, cards, tables, badges, empty states) in `supervisor/static/supervisor/css/`; `fa_digits`, `jalali_date`, `to_persian` filters; GET filter forms that never break a page; query-count tests with `assertNumQueries`.

## 2. Decisions (approved)

1. Other roles visiting `/director/` are redirected to their own dashboard (teacher / student pattern).
2. **Attendance rate = not absent (present + late)**, lateness shown separately, **unified everywhere** including the supervisor's `present_rate`.
3. A JB session in an expected open slot counts as **held**, not as makeup.
4. Content rate denominator: **HD + JB**, the supervisor's missing-content rule.
5. **No change indicators** on the student / class / teacher count cards; "status history for enrollments / assignments" recorded as a Phase 2 follow-up.
6. `admin` relabelled **«مدیر سامانه»**, checked everywhere the label appears.
7. **Chart.js 4, vendored**, with a table fallback.
8. **Supervisor coverage migrated to the analytics engine in this phase.**
9. Font Awesome vendored for the student templates (separate commit); every external CDN reference reported.

## 3. Commits

| Commit | Summary |
| --- | --- |
| `e20fc1b` | Load Font Awesome from the vendored copy on the student pages |
| `97497db` | Share the slot-matching, content and attendance rules across panels (no behaviour change) |
| `02714dd` | Count late as attended in the supervisor's attendance rate |
| `957856b` | Add the director role and the director panel's access control |
| `4f8f67f` | Add the analytics engine: expected slots, outcomes and rates |
| `3d75f20` | Compute the supervisor's coverage with the analytics engine |
| `fdf719a` | Vendor Chart.js 4.5.1 under static/vendor |
| `c62df77` | Add the director panel: dashboard, execution and attendance pages |
| `66ead90` | Cut the analytics engine's cost on a full school year |
| `479b63c` | Polish the director pages after a look in the browser |
| (last) | Document the director panel and the analytics layer |

The three pages share one selectors module, so they landed in one commit rather than one per page.

## 4. Migrations

One: `accounts/0004_director_role` — `AlterField` on `User.role` choices (adds `director` «مدیر مدرسه», relabels `admin` «مدیر سامانه»). `sqlmigrate` shows **no SQL** (no-op on the database). No other model changed.

## 5. How to create or assign the director

In the Django admin (as the system admin): **Users** → add or open the user → **نقش** = «مدیر مدرسه» → save. No staff flag, group or permission is needed (do not make the director staff unless they also administer data). They log in at `/auth/login/` (any role in the login dropdown; the role field is not checked) and land on `/director/`. A superuser can also open `/director/` directly.

## 6. Metric definitions as implemented

All in `analytics` (`docs/apps/analytics.md` §3). Every metric takes a date range, an optional branch and an optional grade, and only considers dates up to today.

| Metric | Implemented as |
| --- | --- |
| Teaching days | Saturday–Wednesday of the academic year on which at least one (branch, grade) of the scope is not closed for the whole day. A branch closure removes the day for that branch only; bell-limited closures never remove a day. |
| Expected slots | `get_slots` (never Thursday/Friday, active class subjects of active classes on their dates, active bells, rotation week) minus slots an active event closes. **Correction to the brief:** a slot of *today* counts only once its bell ended + 15 minutes (the grace of «نیازمند پیگیری»), otherwise the morning dashboard would report every afternoon lesson as unregistered. A slot holding a stale holiday row is treated as closed. |
| Slot outcome | sessions matched with `match_sessions` over all slots (closed included, like the calendar sync): held = HD **or JB** in the slot; teacher-cancelled = CD; unregistered = none (bell-less legacy sessions fill the day's free slots in bell order). A non-holiday session in a closed slot is a conflict, not held. |
| Execution rate | held ÷ expected |
| Lost to closures | number of HL sessions in range (separate) |
| Compensatory | JB sessions that fill **no** expected slot (decision 3) |
| Makeup coverage | compensatory ÷ (HL + teacher-cancelled) |
| Content rate | HD + JB sessions with a `SessionContent` row ÷ HD + JB sessions; **no homework rate** (not supported by the data) |
| Attendance recorded rate | HD + JB sessions with ≥ 1 record ÷ HD + JB sessions |
| Attendance rate | (records − absent) ÷ records, on HD + JB sessions; late rate reported separately |
| Previous period | the same number of teaching days immediately before the range; marked incomplete (no arrow) when the year began too recently |
| Also reported | HD/CD sessions outside the timetable (legacy), conflicts |

## 7. Supervisor numbers that change

| Where | Before | After |
| --- | --- | --- |
| Dashboard «نرخ حضور دانش‌آموزان» | `present ÷ all records` (late lowered it), records of every session | `(records − absent) ÷ records` of HD + JB sessions. Rises by the share of late records (in the synthetic data, about 3 points); records on cancelled sessions no longer count |
| Training sessions «پیشرفت» | every HD + JB session of the range ÷ open expected slots (could pass 100%) | expected slots held by a session recorded **in that slot** ÷ open expected slots (≤ 100%) |

Coverage differences, case by case: sessions recorded on days without a timetable slot or at bells outside the timetable no longer count (legacy data — the session form refuses new ones); JB sessions on Thursdays or at free bells no longer raise it (they are makeup); sessions in closed slots no longer count; today's slots not yet over plus 15 minutes are not expected yet; a legacy bell-less session still fills one slot. On data recorded through the current session form (bell required, HD/CD only in timetable slots), the two definitions differ only by compensatory sessions recorded outside slots and by today's pending slots. The supervisor test that pinned the old number (`test_coverage_against_the_timetable`, sessions on non-slot days = 100%) was rewritten for the slot rule. The page runs 3 queries for coverage instead of 2.

## 8. External CDN references

* Fixed: `student/templates/student/dashboard.html` and `session_list.html` loaded Font Awesome 6.4 from cdnjs; the vendored Font Awesome 7.2 (`static/assets`, already loaded by `base.html`) has every icon they use, so the links were removed.
* Remaining, harmless: `teaching/static/teaching/js/datepicker/package/dist/*.html` (the datepicker package's own demo pages: bootstrapcdn and code.jquery.com) and `.../assets/IRANSans.html` (a font sample page with links to fontiran.com). They are static demo files that no template includes; they are copied by `collectstatic` but never loaded by a page. They could be deleted from the vendored package.
* No other template, CSS or JS file references an external host.

## 9. Performance

**Synthetic full year** (seeded by a scratch script, not committed): 2 branches × 3 grades × 7 classes = 42 classes, 504 class subjects (30 slots a week per class), 1,260 students, 47,880 expected slots, 43,924 sessions, 33,749 contents, **1,038,480 attendance records**, nine closures and a conflict. PostgreSQL 16 in Docker on an 8-core laptop; median of 5 full requests (view + template) via Django's test client; "now" pinned to the end of the year.

| Page (whole school unless noted) | First version | Shipped | Queries |
| --- | --- | --- | --- |
| Dashboard, year so far | 7.7 s | **1.8 s** | 23 |
| Dashboard, this week | 4.7 s | 1.5 s | 23 |
| Execution, year | 3.2 s | **1.3 s** | 17 |
| Execution, year, one branch + grade | 0.58 s | 0.28 s | 17 |
| Execution, this month | 1.2 s | 0.55 s | 17 |
| Attendance, year | 5.0 s | **2.7 s** | 19 |
| Attendance, this week | 1.1 s | 0.60 s | 19 |

Same data, "now" moved through the year (whole school, year so far): dashboard 0.70 s (15 Aban) → 1.03 s (15 Dey) → 1.32 s (15 Esfand) → 1.82 s (end of year); execution 0.61 → 0.82 → 0.94 → 1.28 s; attendance 0.92 → 1.45 → 1.89 → 2.68 s. Full tables: `docs/apps/director.md` §8.

**What was optimized** (commit `66ead90`, same results): sessions read with the date cast to a plain `DATE` (each `jDateField` value otherwise becomes a `jdatetime` object whose constructor queries the locale — the biggest single cost); unused Jalali fields of joined rows deferred; `get_slots` converts each timetable row's bounds once (not per day) and builds `NamedTuple` slots; `Closures` indexes events by day; attendance tallies as a separate grouped aggregate (2× faster on 1M records); the dashboard's conflicts and missing-attendance alerts come from its one engine run instead of a second calendar pass.

**Verdict, as the brief asks:** query counts are bounded and locked, and narrow views stay well under a second all year, but the **year-wide whole-school views pass ~1 s around Dey and reach 1.3–2.7 s by the end of the year**. The cost is linear in the days elapsed (every expected slot and every attendance record of the range is looked at); further micro-optimization would gain perhaps 30%, not an order of magnitude. Today (Mehr, two weeks into the year) every page is well under a second. **Proposal, not built** (`docs/apps/director.md` §8.2): a daily rollup table per (day, class subject) written by the same engine, refreshed nightly and on the writes that change a past day — every page under ~0.3 s all year, with the definitions still in one place. A short-TTL cache is the stopgap alternative. This needs your decision (§12).

## 10. Tests

* New: `analytics/tests.py` (30 tests: every metric definition — HL excluded from expected slots; CD vs unregistered; JB not expected but counted in makeup coverage, and JB in an expected slot counted as held; Thursday never expected; branch-specific and partial closures; two bells on one day; the legacy count fallback with one and two bell-less sessions; future dates and today's not-yet-ended slots excluded; conflicts equal to `find_conflicts`; content / attendance rates; teaching days; previous period complete / pushed back / incomplete; presets), `director/test_access.py` (7: every role, staff or not, logged out, superuser, read-only methods, login redirect, labels), `director/tests.py` (34: KPIs, previous-period comparison, branch comparison, calendar summary, empty states, all four alerts at and around their thresholds with `override_settings`, execution drill-down / teachers / subject matrix, attendance trend with closure days, absentees, filters, formatting, and **locked query counts that do not grow with data**).
* Changed: supervisor `test_coverage_against_the_timetable` (rewritten for the slot rule), the sessions-page query count (+1), two exact-dict assertions (`rate` key), `academic_calendar/test_counts` (`delivered_count` removed), `accounts/test_profile` (text).
* Full suite on PostgreSQL: see §10.1.

### 10.1 Final run

`POSTGRES_HOST=localhost python manage.py test` on PostgreSQL, after the last code commit: **628 tests, 627 pass**. The one error is `scheduling.tests.WeeklyScheduleServiceTests.test_invalid_color_in_database_never_reaches_style`, which fails the same way on `main` before this branch (it writes more than 7 characters into `Subject.color` `varchar(7)`; it passes on SQLite). Baseline on `main`: 555 tests, the same single error. The `analytics` and `director` suites also pass on SQLite.

## 11. Decisions made during implementation

* A new `analytics` app (no models) holds the definitions; the `director` app holds only access, filters, page assembly and templates (ADR-019, ADR-020). `analytics.definitions` imports no model so `core.querysets` can use it.
* `match_sessions` extracted into `academic_calendar.services`; `_plan` now loads only sessions on closure/holiday days; `find_conflicts` / `_plan` accept the caller's `Closures`; `count_open_slots` removed (replaced by the engine).
* The period filter is a hidden field driven by preset links, not a select: dates equal to the preset keep it, edited dates make the range custom — so a no-JS user can never end up in a stale custom range.
* The dashboard runs the engine once over the union of its windows (range, previous period, alert window) and groups in Python; the branch comparison is computed from the same run.
* Alerts follow the branch / grade filters but not the date range (each has its own window), so they always describe "now".
* The conflicts alert covers the year so far and links to the execution page's conflicts table (the director has no admin access).
* Three UI texts that sent users to «مدیر مدرسه» / «مدیر» to change data (profile, timetable bells, class assignment) now name «مدیر سامانه».
* The supervisor's coverage help text and footnote were corrected (the footnote said holidays were not considered, which was already wrong).
* Chart: one series (no legend box), closure days as a neutral band with their own tooltip and key, crosshair tooltip, Persian digits, RTL axis; the brand primary passed the palette validator against the white surface. The app is light-only, so is the chart.
* Chart.js's source map is vendored too, so a future switch to a manifest static storage cannot fail on its `sourceMappingURL`.
* The engine checks closures before "today, not over yet", so its conflicts are exactly `find_conflicts`' (tested); the dashboard therefore runs the engine once over the year so far and derives every window and the year-to-date alerts from it (23 queries).
* Checked in a real browser (headless Chrome on a seeded copy, 1280 / 820 / 390 px): no horizontal page scroll, the chart renders, no console errors (apart from the site's missing favicon). Fixed from that pass: a rate's color band now follows the rounded value it shows, signed numbers are isolated so the minus stays in front of the digits in RTL, class sections use Persian digits.

## 12. Open questions

1. **Performance (§9):** approve the daily rollup table (recommended, before Dey) or a short-TTL cache as a stopgap — or accept the current times for now?
2. **Execution vs coverage history:** supervisors will see «پیشرفت» drop where it used to count off-slot sessions (§7). Should the changelog be announced to supervisors, or should the old number be shown alongside for a transition period?
3. **Alert thresholds:** 85% attendance / 3 unregistered slots / 7 teaching days / 1 grace day are the brief's defaults; are they right for both branches, or should they differ per branch?
4. **The `admin` role and staff:** the relabel is cosmetic; should the system admin role also imply `is_staff` (today they are independent)?
5. **Datepicker demo pages** (§8): delete the unused demo HTML from the vendored datepicker package?
6. **Academic-year selector:** Phase 1 always shows the current year; is looking at a past year needed before Phase 2?
