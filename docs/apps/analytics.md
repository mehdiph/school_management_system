# Analytics App

## 1. Purpose

`analytics` is where the school's metrics are **defined, once**. It has no models, URLs or templates: it is a layer of selectors that the panels call. The director panel (`docs/apps/director.md`) is built entirely on it, and the supervisor's training sessions page computes its «پیشرفت» column with it, so the director and a supervisor always see the same number for the same class subject.

If a number shown somewhere is "execution", "makeup coverage", "content rate", "attendance rate" or "attendance recorded", it comes from here. A panel that needs a new grouping or window asks `analytics.metrics.breakdowns`; it never re-derives a rule (ADR-019).

| Module | What it holds |
| --- | --- |
| `analytics/definitions.py` | The shared rules with no model import (usable from `core.querysets`): statuses, `counted_q`, `delivered_q`, `has_content_q`, `missing_content_q`, `rate`, `attendance_rate`, `REGISTRATION_GRACE_MINUTES` |
| `analytics/scope.py` | `AnalyticsScope`: year, date range (clamped), optional branch / grade / class subjects, and the moment it is computed `as_of` |
| `analytics/engine.py` | `compute(scope)`: expected slots, what happened in each, every session of the scope |
| `analytics/metrics.py` | `Breakdown` (counts + rates) and `breakdowns(result, key, start=, end=, where=)` |
| `analytics/periods.py` | Teaching days, closed days, the previous period, the date presets |

Lower-level rules it relies on, owned elsewhere:

* `SchoolSession.objects.counted()`: a session counts unless it is a holiday (`HL`) — ADR-017.
* `academic_calendar.services.get_slots`, `Closures`, `match_sessions` — `docs/apps/academic_calendar.md`.
* `AttendanceQuerySet.delivered()` / `.status_counts()` (`core/querysets/teaching.py`) use `analytics.definitions`, so a plain queryset count and the engine agree (tested).

---

## 2. Scope

`AnalyticsScope.build(year, start=None, end=None, *, as_of=None, branch=None, grade=None, class_subjects=None)`

* `start` / `end` default to the academic year; both are clamped to the year **and to `as_of`'s date**: no metric ever looks at the future. `start > end` (a range entirely in the future) is an empty scope (`is_empty`); pages show an empty state for it.
* `as_of` defaults to now (Asia/Tehran). `as_of_for(day)` gives the end of that day for a day other than today (used by selectors built for a fixed date, and by tests).
* `class_subjects` restricts the scope to those class subjects (the supervisor's page rows).
* `class_subject_filter(prefix)` turns the scope into `ClassSubject` lookups for any related model.

---

## 3. Metric definitions

All metrics take a date range, an optional branch and an optional grade, and only consider dates up to today.

### 3.1 Teaching days

> A **teaching day** is a working day (Saturday to Wednesday) of the academic year on which at least one unit of the scope — a (branch, grade) pair — is **not closed for the whole day**.

* Thursday and Friday are never teaching days.
* A closure of one branch removes the day from that branch's teaching days only. With every branch selected, a day is lost only when every branch (and grade) is closed.
* A closure limited to some bells never removes a day (its slots are still removed from the expected slots).
* **Days lost to closures** = working days of the range that are not teaching days (`periods.closed_days`).

### 3.2 Expected slots

> **Expected slots** = the timetable's slots in the range (`get_slots`) minus the slots an active calendar event closes.

* A slot is `(class subject, date, bell)`: two bells of one subject on one day are two slots.
* `get_slots` never returns Thursday or Friday (a legacy Thursday timetable row is ignored), and only active class subjects of active classes, on the dates the class subject is taught (`start_date`..`end_date`), with an active bell, in the right rotation week.
* A slot of **today** is expected only once its bell has ended **plus 15 minutes** (`REGISTRATION_GRACE_MINUTES`, the same grace the supervisor's «نیازمند پیگیری» list gives). Until then it is "pending": neither expected nor reported, and a session already recorded in it is ignored by the slot counts (it still counts as delivered).
* A slot holding a holiday row that no active event closes any more (the event changed and the sync has not run yet) is treated as closed: not expected, and its `HL` row is counted as lost.

### 3.3 Slot outcome

Recorded sessions are matched to slots with `academic_calendar.services.match_sessions`, over **all** slots of the range (closed ones included), exactly as the calendar sync does:

* a session with a bell fills its own slot;
* a legacy session without a bell fills that day's first slot (in bell order) that no session with a bell fills — several of them in number order (the **count fallback**).

Each **expected** slot then gets one outcome:

| Outcome | Rule |
| --- | --- |
| **held** | the slot holds an `HD` session — or a `JB` session: a compensatory session recorded in a regular slot means the class met there, so the slot is held and the session is **not** counted as makeup |
| **cancelled by the teacher** | the slot holds a `CD` session |
| **unregistered** | no session fills the slot |

A non-holiday session in a **closed** slot is a **conflict**: the slot is not expected, the session is not "held", and it is listed (it still counts as delivered for content and attendance, because it was taught).

### 3.4 Counts and rates

`Breakdown` adds up slot outcomes and sessions; its properties are the rates. A rate is `None` (shown as «—») when its denominator is 0.

| Name | Formula |
| --- | --- |
| `expected` | open expected slots (3.2) |
| `held`, `cancelled`, `unregistered` | expected slots by outcome (3.3); they add up to `expected` |
| **execution rate** | `held / expected` |
| `lost_to_closures` | `HL` sessions in the range (each is one slot an event closed); shown apart, never part of `expected` |
| `compensatory` | `JB` sessions that fill no expected slot (made up elsewhere — e.g. on a Thursday or at a free bell) |
| **makeup coverage** | `compensatory / (lost_to_closures + cancelled)` |
| `outside_timetable` | `HD` / `CD` sessions that fill no slot (legacy data; the session form refuses them now); shown apart |
| `conflicts` | non-holiday sessions in closed slots |
| `delivered` | `HD` + `JB` sessions in the range, whatever slot they are in |
| **content rate** | delivered sessions **with a `SessionContent` row** / delivered. The same "has content" rule as the supervisor's «بدون محتوا» (a missing row on a `CD` or `HL` session is expected and never counted) |
| **attendance recorded rate** | delivered sessions with at least one attendance record / delivered |
| **attendance rate** | `(records − absent) / records`, over the records of **delivered** sessions: present **and late** count as attended |
| late rate | `late / records` (reported separately; late is still attended) |

There is no homework rate: `SessionContent.homework` is required and teachers write «ندارد» when there is none, so a filled field says nothing.

### 3.5 Comparison with the previous period

> The **previous period** of a range is the same number of **teaching days** (3.1, for the same branch / grade) immediately before it.

* "This week" with a holiday in it is compared with as many real school days before it, not with seven calendar days.
* When the academic year started too recently to have that many teaching days before the range, the previous period is **incomplete**: the director dashboard shows «داده‌ی دوره‌ی قبل کافی نیست» instead of an arrow. A range starting on the first day of the year has no previous period at all.
* Rates are compared in percentage points (the rounded current minus the rounded previous rate).

### 3.6 Date presets (`periods.period_range`)

| Preset | Range |
| --- | --- |
| `today` | today |
| `week` | Saturday of this week .. today |
| `month` | the 1st of this **Jalali** month .. today (the director panel's default) |
| `year` | the start of the academic year .. today |
| `custom` | the typed Jalali dates |

---

## 4. Engine (`engine.compute`)

One pass, a fixed number of queries whatever the data size:

1. the scope's `ClassSubject` rows with subject, class, grade, branch and teacher joined (1 query; skipped when the caller passes them in);
2. the expected slots (`get_slots`, 1 query);
3. the active events (`Closures`, 1 query + 3 prefetches when there are events; skipped when the caller passes them in);
4. every session of the scope in the range as plain rows, with `has_content` (an `EXISTS` subquery) and the date cast to a plain `DATE` (a `jDateField` value would become a `jdatetime` object, whose constructor queries the locale) (1 query);
5. unless `with_attendance=False`, the attendance tallies per session (`total`, `absent`, `late`): a separate grouped aggregate over the records, about twice as fast as joining them to the sessions (1 query).

`get_slots` and `load_class_subjects` defer the Jalali date/time fields of the joined rows that nobody reads (`academic_calendar.services.UNUSED_JALALI_FIELDS`) for the same reason.

Each session row gets a `role`: it `fills` an expected slot, is a `conflict`, is `pending` (today's slot not over yet), or `""` (fills no slot). `metrics.Breakdown.add_session` reads that role to classify compensatory and outside-timetable sessions.

`metrics.breakdowns(result, key, start=None, end=None, where=None)` groups the result by `key(class_subject, day)`: `by_school`, `by_branch`, `by_grade`, `by_class`, `by_class_subject`, `by_teacher`, `by_day`, or any function (the director's same-subject matrix uses `(subject, class)`). `start` / `end` narrow it to a window — one engine run over the union of the windows a page needs (current range, previous period, alert window) serves all of them.

---

## 5. Who uses it

| Caller | What |
| --- | --- |
| Director panel | every KPI, table, alert and the attendance trend |
| Supervisor training sessions | «پیشرفت نسبت به برنامه» = execution rate per class subject, and «n جلسه‌ی جبرانی» = `compensatory` beside it (`attach_coverage`) |
| Supervisor dashboard | «نرخ حضور دانش‌آموزان» = `Attendance...delivered().status_counts()["rate"]` (same formula) |
| Supervisor «بدون محتوا» counts, teachers page | `missing_content_q`, `counted_q` |

---

## 6. Performance

Measured on PostgreSQL with a synthetic full year (42 classes, 48k slots, 44k sessions, 1M attendance records): `engine.compute` over the whole year takes about 1.5 s (slots 0.6 s, sessions + tallies 0.4 s, the per-slot pass the rest); see `docs/apps/director.md` §8 for the pages and the proposal to precompute past days.

---

## 7. Tests

`analytics/tests.py` pins every definition: two bells are two slots, held / cancelled / unregistered, the legacy count fallback (one and two bell-less sessions), Thursday never expected, future dates and today's not-yet-ended slots excluded, closed slots and holiday rows, a branch-only closure, a partial (bell) closure, conflicts, a holiday row left on a reopened slot, compensatory sessions outside and inside expected slots, makeup coverage, outside-timetable sessions, content / attendance rates (late attended, cancelled sessions excluded), the queryset and the engine agreeing, groupings and windows, teaching days per branch, the previous period (complete, pushed back by a closure, incomplete) and the presets.

---

## 8. Follow-up: daily summary table (required before Dey 1405)

**Status:** decided, not built. Phase 1 computes everything on the fly; the year-wide whole-school views are acceptable today (Mehr) but grow linearly with the days elapsed. The director pages open on "this Jalali month" to keep the default view fast; "since the start of the year" remains a preset.

**Deadline:** in production before **1 Dey 1405 (22 December 2026)**, when the year-wide dashboard passes one second on a school of the measured size.

### 8.1 Why: measured cost of the live engine

Synthetic full year on PostgreSQL (42 classes, 504 class subjects, 47,880 expected slots, 43,924 sessions, 1,038,480 attendance records; median of 5 full requests, view + template; details in `docs/apps/director.md` §8). Whole school, range = since the start of the academic year:

| As of | Dashboard | Execution | Attendance |
| --- | --- | --- | --- |
| 15 Aban 1405 (≈ 1.5 months) | 0.70 s | 0.61 s | 0.92 s |
| 15 Dey 1405 (≈ 3.5 months) | 1.03 s | 0.82 s | 1.45 s |
| 15 Esfand 1405 (≈ 5.5 months) | 1.32 s | 0.94 s | 1.89 s |
| 25 Khordad 1406 (end of year) | 1.82 s | 1.28 s | 2.68 s |

Narrow views stay fast all year (end of year: one branch + grade 0.28 s, one month 0.55–0.88 s, one week 0.60 s). The cost is the per-slot pass over every expected slot of the range and the grouping of every attendance record of the range; it is linear in the days elapsed.

### 8.2 What to build

* A table with one row per **(day, class subject)** for past days, holding exactly the counts of a `Breakdown` (expected, held, cancelled, unregistered, lost to closures, compensatory, outside the timetable, conflicts, delivered, with content, with attendance, records, absent, late).
* **Written by `engine.compute` itself** (run per day or per range, grouped `by_class_subject` and by day), so there is still only one definition of every metric. Pages sum the stored rows for past days and compute **only today** live; `metrics.breakdowns` keeps its interface (a `Breakdown` per group), so the director and supervisor pages do not change.
* Kept fresh by a nightly rebuild **and** by marking (day, class subject) dirty on every write that can change a past day: session create / edit / delete (and the renumbering it triggers), content and attendance saves, the calendar sync (events, imports, deactivation), timetable and class subject changes. Teachers record missed sessions for past days, so a nightly rebuild alone would show stale numbers for up to a day.
* Lists that need individual sessions (conflicts, sessions without attendance, top absentees) keep their targeted queries.

### 8.3 Required: a verification command

The table must ship with a management command (e.g. `verify_daily_summary`) that:

* picks a **sample of past days** (random, plus the most recent days and any day touched by a calendar event; `--days N`, `--from/--to`, `--all`),
* recomputes those days with the **live engine**,
* compares every count per (day, class subject) with the stored rows, and
* **reports every mismatch** (day, class subject, field, stored vs live) and exits non-zero when there is one, so it can run on a schedule and alert.

It is the guarantee that the precomputed numbers still mean what `analytics` defines; tests must also assert that a rebuilt table equals the live engine on the fixture data.

### 8.4 Not chosen

A short-TTL cache of page data: the first request stays slow, the numbers lag, and it needs a shared cache backend (the project uses Django's per-process default).
