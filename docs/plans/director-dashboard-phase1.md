# Director Dashboard, Phase 1: Final Report

Branch `director-dashboard`, 15 commits on top of `main` (`9bc6065`), **not pushed**. A read-only analytics panel for the school director over both branches, built on a new shared analytics layer that the supervisor panel now uses too.

Reference documentation: `docs/apps/director.md` (the panel), `docs/apps/analytics.md` (every metric definition, the engine, the summary-table follow-up), ADR-019 to ADR-021. The first-round report, with the Step 0 findings, is `docs/plans/director-dashboard.md`.

---

## 1. What was delivered

* **Director role and access.** `User.Roles.DIRECTOR` («مدیر مدرسه»); the system admin's role relabelled «مدیر سامانه». `/director/` is open to the director and superusers only; everyone else goes to their own dashboard, logged-out users to the login page; GET / HEAD only.
* **Dashboard.** KPI cards (active students, classes, teachers; attendance, execution and content rates with the change vs the previous period of as many teaching days), both branches side by side, the academic calendar (teaching days elapsed / remaining, days lost, closures in the next 30 days) and four alerts (low attendance, unregistered slots, sessions without attendance, conflicts with the calendar), each linking to its drill-down.
* **Execution page.** Expected slots held / cancelled by the teacher / unregistered, lost to closures, compensatory sessions, makeup coverage; drill-down branch → grade → class → class subject; per teacher; the same subject across the classes of a grade; the conflicts.
* **Attendance page.** Daily rate (Chart.js, vendored) with closure days marked, never zero, and a table twin; comparison by branch → grade → class → class subject; students with the most absences; sessions without attendance.
* **Filters** on every page as GET parameters (linkable, work without JS): presets, custom Jalali range, branch, grade. **Pages open on this Jalali month.**
* **`analytics` app**: the single definition of every metric (ADR-019), used by the director panel and by the supervisor's progress, compensatory count and attendance rate.
* **Supervisor panel**: «پیشرفت» is now the shared execution rate, with the number of compensatory sessions next to it; the attendance rate counts late as attended.
* **No external CDN** anywhere in the HTML (ADR-021).

---

## 2. Commits

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
| `496a8db` | Document the director panel and the analytics layer |
| `7b7b67a` | Open every director page on this Jalali month |
| `ed733d4` | Show compensatory sessions next to the supervisor's progress |
| `53b0acb` | Delete the datepicker package's demo pages |
| (last) | Record the Phase 1 decisions and follow-ups |

---

## 3. Migrations

One: **`accounts/0004_director_role`** — `AlterField` on `User.role` choices (adds `director` «مدیر مدرسه», relabels `admin` «مدیر سامانه»). `sqlmigrate` shows no SQL: nothing changes in the database. No other model changed.

## 4. Creating or assigning the director

Django admin (as the system admin) → **Users** → add or open the user → **نقش** = «مدیر مدرسه» → save. No staff flag, group or permission is needed; the role and `is_staff` stay independent (for the system admin too). The director logs in at `/auth/login/` and lands on `/director/`.

---

## 5. Metric definitions as implemented

All in `analytics` (`docs/apps/analytics.md` §3); every metric takes a date range, an optional branch and an optional grade, and only considers dates up to today.

| Metric | Implemented as |
| --- | --- |
| Teaching days | Saturday–Wednesday of the academic year on which at least one (branch, grade) of the scope is not closed for the whole day; a branch closure removes the day for that branch only; bell-limited closures never remove a day |
| Expected slots | `get_slots` (never Thursday/Friday; active class subjects of active classes, on their dates, active bells, rotation week) minus slots an active event closes; a slot of **today** counts once its bell ended + 15 minutes; a slot holding a stale holiday row is treated as closed |
| Slot outcome | sessions matched with `match_sessions` over all slots (the legacy count fallback: a bell-less session fills the day's first free slot in bell order); **held** = HD or JB in the slot, **cancelled** = CD, **unregistered** = none; a non-holiday session in a closed slot is a conflict |
| Execution rate | held ÷ expected |
| Lost to closures | HL sessions (separate, never in expected) |
| Compensatory | JB sessions that fill no expected slot |
| Makeup coverage | compensatory ÷ (HL + teacher-cancelled) |
| Content rate | HD + JB with a `SessionContent` row ÷ HD + JB (no homework rate: the field is required and «ندارد» is typed when there is none) |
| Attendance recorded rate | HD + JB with ≥ 1 record ÷ HD + JB |
| Attendance rate | (records − absent) ÷ records on HD + JB sessions — **late counts as attended**, everywhere; late rate shown separately |
| Previous period | as many teaching days, immediately before the range; incomplete → no arrow |
| Also shown | HD/CD sessions outside the timetable (legacy), conflicts |

---

## 6. Decisions

| Topic | Decision |
| --- | --- |
| Other roles on `/director/` | redirect to their own dashboard |
| "Present" | not absent (present + late), unified everywhere incl. the supervisor |
| JB in an expected slot | held, not makeup |
| Content denominator | HD + JB (the supervisor's rule) |
| Student / teacher count cards | no change indicator (no status history) |
| `admin` label | «مدیر سامانه»; role and `is_staff` stay independent |
| Charts | Chart.js 4.5.1 vendored, table fallback |
| Supervisor coverage | moved onto the engine in Phase 1 |
| **Performance** | current timings accepted; **default range = this Jalali month**; daily summary table + verification command **before Dey 1405**; no cache |
| Supervisor «پیشرفت» change | supervisors will be informed; the **compensatory count is shown next to it** (shared engine) |
| Alert thresholds | global for now; per-branch possible later |
| Datepicker demo pages | deleted |
| Academic-year selector | not now; before the 1406–1407 year starts |

Implementation decisions (details in the first-round report, §11): an `analytics` app with no models and a `director` app for the panel; `match_sessions` extracted; `count_open_slots` and `delivered_count` removed; the period filter is a hidden field driven by preset links (edited dates make a custom range, without JS); the dashboard runs the engine once over the year so far and derives every window and the year-to-date alerts from it; alerts follow branch / grade but not the date range; the engine checks closures before "today, not over yet", so its conflicts are exactly `find_conflicts'`.

---

## 7. Supervisor panel: what changed for supervisors

| Where | Before | Now |
| --- | --- | --- |
| Dashboard «نرخ حضور دانش‌آموزان» | present ÷ all records (late lowered it), every session | (records − absent) ÷ records of HD + JB sessions: rises by the share of late records (≈ 3 points in the synthetic data); records on cancelled sessions no longer count |
| Training sessions «پیشرفت» | every HD + JB session of the range ÷ open expected slots (could pass 100%) | expected slots held by a session **in that slot** ÷ open expected slots (≤ 100%); today's slots once their bell ended + 15 min |
| Training sessions, under «پیشرفت» | — | **«n جلسه‌ی جبرانی»**: compensatory sessions made up outside the timetable (Thursday, a free bell), for every row, timetable or not — make-up work stays visible |

Sessions recorded on days without a slot, at bells outside the timetable, or in closed slots no longer raise «پیشرفت». On data recorded through the current session form (bell required, HD/CD only in timetable slots) the old and new rates differ only by compensatory sessions outside the slots — now shown next to it — and today's pending slots.

---

## 8. External CDN references

* Removed: Font Awesome 6.4 from cdnjs on the student dashboard and session list (the vendored 7.2 has every icon they use).
* Deleted: the persian-datepicker package's demo pages (`dist/*.html`: bootstrapcdn, code.jquery.com) and font sample page (`assets/IRANSans.html`: fontiran.com).
* Result: **no HTML file in the project references an external host**; the only remaining URLs in CSS / JS are licence comments. Chart.js 4.5.1 is vendored (tarball sha512 matched the npm registry; source map kept for manifest storage).

---

## 9. Performance

Synthetic full year on PostgreSQL 16 (Docker, same 8-core laptop): 42 classes, 504 class subjects, 1,260 students, 47,880 expected slots, 43,924 sessions, 1,038,480 attendance records, nine closures; median of 5 full requests (view + template).

**Queries per page are fixed whatever the data size** (locked in tests): dashboard 23, execution 17, attendance 19; supervisor training sessions +3 for progress and compensatory sessions.

Whole school, "since the start of the year" (no longer the default):

| As of | Dashboard | Execution | Attendance |
| --- | --- | --- | --- |
| 15 Aban 1405 | 0.70 s | 0.61 s | 0.92 s |
| 15 Dey 1405 | 1.03 s | 0.82 s | 1.45 s |
| 15 Esfand 1405 | 1.32 s | 0.94 s | 1.89 s |
| 25 Khordad 1406 | 1.82 s | 1.28 s | 2.68 s |

End of year, narrower views: execution for one branch + grade 0.28 s, one month 0.55 s; attendance one month 0.88 s, one week 0.60 s; dashboard one month 1.6 s (it always reads the year so far for its year-to-date alerts). The first version was 7.7 / 3.2 / 5.0 s at the end of the year; commit `66ead90` cut it without changing a number (dates read as plain `DATE` instead of `jdatetime` objects, unused Jalali fields deferred, per-row bounds computed once, events indexed by day, attendance tallies as a separate grouped aggregate, one engine run on the dashboard).

**Accepted for Phase 1.** Follow-up (§10): the daily summary table before Dey 1405.

---

## 10. Follow-ups (with deadlines)

| Follow-up | Deadline | Where specified |
| --- | --- | --- |
| **Daily summary table** per (day, class subject), written by the engine, refreshed nightly and on writes to past days, **with a management command that recomputes a sample of days with the live engine and reports every mismatch** (non-zero exit) | **before 1 Dey 1405 (22 December 2026)** | `docs/apps/analytics.md` §8 |
| **Academic-year selector** on the director pages | **before the 1406–1407 academic year starts (Mehr 1406, September 2027)** | `docs/apps/director.md` §9 |
| Status history for enrollments and assignments (counts comparison, enrollment / dropout analytics) | Phase 2 | `docs/apps/director.md` §9 |
| Per-branch alert thresholds | when needed | `docs/apps/director.md` §5 |
| Teacher detail and recording discipline, supervisor overview, day / bell absence patterns, consecutive absences, student detail, exports (PDF / Excel), weekly email digest | Phase 2 | `docs/apps/director.md` §9 |

---

## 11. Tests

* New: `analytics/tests.py` (30), `director/test_access.py` (7), `director/tests.py` (35) — every metric definition in the brief, conflicts equal to `find_conflicts`, alerts at and around their thresholds, access for every role, the default month range, formatting, and **locked query counts that do not grow with data**. Supervisor: compensatory count with and without a timetable, the attendance rate with late and cancelled sessions, coverage on the slot rule.
* Full suite on PostgreSQL after the last code commit: see §11.1. The `analytics` and `director` suites also pass on SQLite.
* Browser check (headless Chrome on a seeded copy; 1280 / 820 / 390 px): no horizontal page scroll, the chart renders, no console errors apart from the site's missing favicon; the supervisor page shows the compensatory count under «پیشرفت».

### 11.1 Final run

`POSTGRES_HOST=localhost python manage.py test` on PostgreSQL, after the last code commit (`53b0acb`): **631 tests, 630 pass**. The one error is `scheduling.tests.WeeklyScheduleServiceTests.test_invalid_color_in_database_never_reaches_style`, which fails the same way on `main` (it writes more than 7 characters into `Subject.color` `varchar(7)`; it passes on SQLite). Baseline on `main`: 555 tests, the same single error.

---

## 12. Open questions

None blocking. Two notes:

1. The timings above come from a laptop with the database on the same machine; it is worth re-measuring the year-wide views on the production server before Dey, to size the summary-table deadline precisely.
2. The supervisor announcement could quote §7 of this report (what changed and why the progress may drop where make-up work used to count).
