# Director panel: daily attendance at a glance

**Status:** committed on branch `feature/director-daily-attendance`, merged into `main` (`--no-ff`) and pushed on 23 October 2026 (1 Aban 1405); **not deployed** (deploy needs `collectstatic`, no migration).

---

## 0. The approved plan

The plan as approved on 23 October 2026 (1 Aban 1405), with the final D-decisions. Sections 1–9 below are the work report.

### 0.1 Why

The director panel was too complex for its users (mostly older, not data-literate). The execution part (execution page, rates, per-teacher view, same-subject comparison, conflicts, makeup) is removed: comparing classes has no baseline until curriculum budgeting («بودجه‌بندی») exists. Attendance stays, rebuilt around the daily attendance the grade supporters take at 8:30 (ADR-022), and presented as plain Persian sentences with names.

### 0.2 Risks found while reading

1. **Supervisor vs director "missing" for about 45 minutes each morning.** The supervisor's overview shows a class «ثبت نشده» as soon as it has an open lesson today; the director lists it only after the first open bell + 15 minutes (the engine's grace). After the grace both agree. *Decision: keep the supervisor as it is; the director's neutral «هنوز وقت دارد» state is right.*
2. The grace rule existed only in `analytics.engine._deadline` (per slot); `planned_class_days` kept no bell times. Hence D1.
3. A class can have several supporters (`SupervisorClass` is unique per supporter and class), and `SupervisorScope` also requires the supporter's branch and grade to match the class.
4. The `DIRECTOR_ALERT_*` "settings" were never in the settings files: they were defaults in `director/selectors.py`, while `docs/apps/director.md` §5 said "set it in settings". *Decision: fix that statement in the docs work.*
5. Today (1 Aban 1405) is a Friday and the cutoff day itself: until go-live "this month" is a single closed day, so the empty states must read well.
6. `analytics.periods.previous_period` / `preceding_teaching_days` and `metrics.by_teacher` lose their only page caller. They stay, unchanged and tested, for when execution returns.

### 0.3 Final D-decisions

| # | Decision |
| --- | --- |
| **D1** | **Shared functions.** `attendance.services.planned_class_days`: same output, built on a private helper that also keeps the end of each day's earliest open bell. **New** `attendance.services.class_day_statuses(start, end, classes, as_of)`: per (class, day) recorded (with counts) / missing / pending / closed (with the event); pending = today before the first open bell + 15 min. `analytics.engine._deadline` moves unchanged into `analytics.definitions.slot_deadline` (the engine imports it: one deadline rule). `attendance.services` readers accept a queryset of `StudentEnrollment` (one query for the listed students' days). **New** `supervisor.selectors.class_supervisors(class_ids)`: each class's supporters by `SupervisorScope`'s rule. Reused as they are: `split_range`, `student_tallies`, `class_day_tallies`, `get_absences`. **Supervisor identical:** none of its views, selectors or templates change; existing supervisor / attendance / analytics tests run unchanged; new tests pin `class_day_statuses` to the supervisor's overview (ignoring the grace) and to the engine's expected class-days without a sheet. |
| **D2** | "Days without attendance" is computed by `attendance.services`, not an engine run (the engine would load every session of the month to learn which classes were due); the agreement test keeps one definition. |
| **D3** | Past days have no grace: a planned open day without a sheet is missing. Today is "pending" until the first open bell + 15 min; a pending class counts among "B classes" but is not listed as missing. |
| **D4** | Responsible supporter = `SupervisorClass` under `SupervisorScope`'s rule (same branch and grade), active users only; several are joined with «، »; none → «پشتیبان ندارد». |
| **D5** | **Two separate labels** on the classes table, each with words. Absences (absent + excused days ÷ records in the range): under 5% green «وضعیت خوب», 5% to under 10% yellow «نیاز به توجه», 10% or more red «غیبت زیاد» (`DIRECTOR_CLASS_ABSENCE_YELLOW = 5`, `DIRECTOR_CLASS_ABSENCE_RED = 10`; the percentage only as small text). Days without attendance: 0 green «همه ثبت شده», 1+ red «n روز ثبت نشده». A class with neither records nor due days: plain «کلاسی نداشته». **The 5 / 10 thresholds are a school policy: start with them and review them after the first month of real data** (recorded in `docs/apps/director.md`). |
| **D6** | Frequent absence: `DIRECTOR_FREQUENT_ABSENCE_DAYS = 3` absent days (absent + excused) in the range; this month on the home page. On «امروز» the attendance page asks for a longer period instead. |
| **D7** | Late is only ever a secondary line («Z نفر تأخیر داشتند», «با تأخیر: …» under each class); never an absence, never in a label. |
| **D8** | Home on a holiday: Thursday / Friday → «امروز پنجشنبه است؛ مدرسه تعطیل است»; every planned lesson closed → «امروز تعطیل است: <event>»; a weekday without planned lessons → «امروز کلاسی در برنامه نیست»; a partial closure is a school day with one line «n کلاس امروز تعطیل است (<event>)». Next school day: the first day within 14 days with an open lesson. Next holiday: one line, the first event starting after today within 60 days for the selected branch, with «(بخشی از کلاس‌ها)» when it closes only some grades or bells. |
| **D9** | Home: `?branch=` only. Attendance: `?period=today|week|month&branch=`, default month. A range is clamped to max(cutoff, start of year)..today, with a note when the cutoff cut it. Grade, custom range, «از ابتدای سال», the date picker and the old `view` / `class` / `grade` parameters are gone; an old link opens this month without an error. An invalid branch is ignored with a message. |
| **D10** | `/director/execution/` → **302** to `/director/` (keeping a valid `branch`), still behind `director_required`. Not 301: execution returns later and browsers cache a 301. The sidebar link is removed. |
| **D11** | A student's days: an expandable `<details>` row in the frequent-absence list (both pages): date with weekday, status, the supporter's description, for absent / excused / late. One `get_absences` query; no new page or URL. |
| **D12** | Chart: bars of absent students per day (Saturday–Wednesday); a holiday is a gray band with the event, never zero; a day with lessons but no sheet is a gap «ثبت نشده»; a weekday without lessons «بدون کلاس». Table twin open by default, folded once the chart drew. Vendored Chart.js. |
| **D13** | Removed: execution page and view, KPI cards, alerts, branch comparison, calendar summary, grade / class drill-down, previous period, the year-long engine run, the filter form's grade / dates, `filters.js`, `director_tags`, the partials `_execution_table`, `_attendance_table`, `_rate`, `_breadcrumbs`, and the tests of only those. `analytics` stays as it is apart from D1. |
| **D14** | **The daily summary table is no longer needed for now.** Drop the 1 Dey 1405 deadline and record the trigger instead: **in mid-Bahman 1405, measure on the production server the supervisor's training sessions page ("since the start of the year") and the director's attendance page ("this month"); build the table (design in `docs/apps/analytics.md` §8) only if a page passes 1 second.** |
| **D15** | Presentation: 18px base text inside `.director`, generous spacing, tap targets ≥ 48px; status words in green «ثبت شده» / red «ثبت نشده» / neutral «هنوز وقت دارد»; «هنوز حضور و غیابی ثبت نشده است» rather than "0 absent"; the branch name beside each class when both branches are shown. |

### 0.4 Wireframes (as planned)

**Home `/director/`**

```
┌ امروز، شنبه ۳ آبان ۱۴۰۵                     [همه‌ی شعبه‌ها ▾]┐
│ امروز ۲۳ دانش‌آموز غایب هستند (۵ نفر موجه).                 │
│ ۴ نفر تأخیر داشتند.                                (کم‌رنگ) │
│ حضور و غیاب ۱۸ از ۲۱ کلاس ثبت شده است.                       │
│ ۲ کلاس امروز تعطیل است (اردوی پایه‌ی هفتم).     (اگر باشد) │
├─ کلاس‌هایی که حضور و غیاب امروزشان ثبت نشده (۳) ────────────┤
│ هشتم ۲ · شعبه‌ی ۱      پشتیبان: خانم احمدی     [ثبت نشده]   │
│ نهم ۱ · شعبه‌ی ۲       پشتیبان ندارد            [ثبت نشده]   │
├─ دانش‌آموزان غایب امروز ──────────────────────────────────┤
│ ▸ هفتم ۱ · ۳ غایب (۱ موجه)                                   │
│ ▾ هشتم ۳ · ۲ غایب                                            │
│     علی رضایی      غایب       «تماس گرفته شد، بیمار است»     │
│     سارا محمدی     غیبت موجه  «نامه‌ی پزشک»                  │
│     با تأخیر: مریم کریمی (۸:۴۵)                     (کم‌رنگ) │
├─ غیبت‌های پرتکرار این ماه (۳ روز یا بیشتر) ─────────────────┤
│ ▸ رضا اکبری · نهم ۲ · ۵ روز غایب (۲ موجه)                    │
├──────────────────────────────────────────────────────────┤
│ تعطیلی بعدی: چهارشنبه ۱۳ آبان، روز دانش‌آموز                  │
└──────────────────────────────────────────────────────────┘
Holiday: «امروز تعطیل است: تاسوعا. روز کلاسی بعدی: شنبه ۱۰ آبان.»
(the missing and today's-absent sections are hidden).
```

**Attendance `/director/attendance/`**

```
┌ حضور و غیاب   [امروز][این هفته][(این ماه)]   [همه‌ی شعبه‌ها ▾]┐
│ ۱ آبان تا ۲۰ آبان ۱۴۰۵   (note when the cutoff clamped it)  │
├─ تعداد دانش‌آموزان غایب در هر روز ─────────────────────────┤
│  bars per day, holidays as gray bands, gaps «ثبت نشده»       │
│  ▸ جدول روزانه: روز | غایب | موجه | تأخیر | کلاس بدون ثبت      │
├─ کلاس‌ها ──────────────────────────────────────────────────┤
│ کلاس | پشتیبان | روزهای غیبت + label | ثبت حضور و غیاب + label │
├─ غیبت‌های پرتکرار در این بازه ──────────────────────────────┤
│ ▸ name · class · ۴ روز غایب (۱ موجه)  → expands to the days    │
└──────────────────────────────────────────────────────────┘
```

### 0.5 Not touched

No models, migrations or data rows; no supervisor view, selector or template (only the new lookup function); no change in engine behaviour; no production or Docker database; nothing committed until asked.

---

## 1. Summary and reasoning

The director panel now answers one question at a glance: **who is not in school, and has every class taken its attendance?** It shows two pages built only on the supporters' daily attendance (ADR-022):

* **Home `/director/`** (today, one branch or all): today in plain sentences («امروز ۷ دانش‌آموز غایب هستند (۱ نفر موجه)», late on its own line, «حضور و غیاب ۹ از ۱۲ کلاس ثبت شده است»); the classes without attendance once their grace is over, with their supporter or «پشتیبان ندارد»; today's absent students by class with the supporter's description; this month's frequent absences with each student's days; the next holiday. A day off (Thursday / Friday, a closure, no lessons) says why and when school is next open.
* **Attendance `/director/attendance/`** (today / this week / this month, default month; branch): absent students per day as bars (holidays a gray band, never zero) with a table version, a classes table with two worded labels, frequent absences.

Program execution (page, rates, per-teacher, same-subject comparison, conflicts, makeup), KPI cards, previous-period comparison, drill-downs, alerts and the year-long engine run are gone; `/director/execution/` redirects (302) home. Execution comes back after بودجه‌بندی on the existing engine (ADR-023, `docs/apps/director.md` §8).

The panel holds no metric rule. The new rule it needed — *which classes were due to take attendance on a day, and when today's absence of a sheet becomes "missing"* — lives in `attendance.services.class_day_statuses`, built from `planned_class_days` and `class_day_tallies` (the supervisor's functions) and the engine's grace (`analytics.definitions.slot_deadline`). Tests pin it to both existing answers: the supervisor's overview and the engine's expected class-days.

**Rejected alternatives**

* *Run `analytics.engine.compute` for a month and read `result.class_days`.* It has the grace built in, but loads every class subject, slot **and session** of the month to answer a question about sheets; the request asked to drop the engine run. The agreement test gives the same guarantee of one definition.
* *Reuse the supervisor's `SupervisorAttendanceSelector.overview`.* Scoped to one supervisor, one day, and without the grace; widening it would have changed the supervisor panel (out of scope).
* *A separate student page for a student's days.* An expandable row needs no new URL (so no id to guard), one query for all listed students, and works without JavaScript.
* *One combined green / yellow / red label per class.* Mixing "many absences" and "attendance not taken" in one colour hides which problem it is; two labels, each in words (D5).
* *301 for the execution redirect.* Browsers cache it indefinitely, and the page is to come back (D10).

## 2. Files changed / added

**Shared layer (no behaviour change for the supervisor or `analytics`)**

| File | Change |
| --- | --- |
| `analytics/definitions.py` | `slot_deadline(day, end_time)`: a bell's end + the registration grace (moved from the engine) |
| `analytics/engine.py` | `_deadline` calls `slot_deadline`; unused imports removed |
| `attendance/services.py` | `_planned` (planned days + each day's first open deadline); `planned_class_days(…, closures=None)` same output; `ClassDay` + `class_day_statuses`; `_target` accepts a queryset of `StudentEnrollment` |
| `supervisor/selectors.py` | `class_supervisors(class_ids)`, by `SupervisorScope`'s rule (read-only, not used by the supervisor panel) |
| `teachlog/config/settings/base.py` | `DIRECTOR_FREQUENT_ABSENCE_DAYS`, `DIRECTOR_CLASS_ABSENCE_YELLOW`, `DIRECTOR_CLASS_ABSENCE_RED` |
| `template/partials/sidebar.html` | director menu: «وضعیت امروز», «حضور و غیاب»; the «اجرای برنامه» link removed |

**Director app**

| File | Change |
| --- | --- |
| `director/forms.py` | rewritten: period (today / week / month) + branch; `daily_range` clamps to the cutoff, year and today |
| `director/selectors.py` | rewritten: `home`, `attendance_page`, `absent_by_class`, `frequent_absentees`, `daily_points`, `class_rows`, `absence_level`, `threshold` |
| `director/views.py` | `dashboard`, `attendance`, `execution` (302 redirect) |
| `director/templates/director/_layout.html`, `attendance.html`, `partials/_filters.html` | rewritten |
| `director/templates/director/home.html`, `partials/_frequent.html`, `partials/_status.html` | new |
| `director/static/director/css/director.css` | rewritten (larger type, 48px targets, sentence card, expandable lists) |
| `director/static/director/js/attendance_chart.js` | rewritten: bars of absent students, holiday bands |
| **Deleted** | `dashboard.html`, `execution.html`, `partials/_rate.html`, `_execution_table.html`, `_attendance_table.html`, `_breadcrumbs.html`, `templatetags/director_tags.py` (+ `__init__.py`), `static/director/js/filters.js` |

**Tests**

| File | Change |
| --- | --- |
| `attendance/test_class_days.py` | new (15 tests) |
| `director/tests.py` | rewritten (39 tests) |
| `director/test_access.py` | the redirect guarded like the pages; the sidebar has no execution link |

**Docs**: `docs/apps/director.md` (rewritten), `docs/architecture-decisions.md` (ADR-023; notes on ADR-019 / ADR-022; future directions), `docs/apps/analytics.md` (§1, §3, §5, §6, §8), `docs/apps/attendance.md` (§4, §5, §8, §9), `docs/apps/supervisor.md`, `docs/apps/academic_calendar.md`, `docs/apps/accounts.md`, `docs/changelog.md`, this report.

## 3. Models and migrations

**None.** No model, field or table changed; `makemigrations --check --dry-run`: "No changes detected". No data row was touched. Rollback: revert the branch (code and docs only).

## 4. URLs, views and permissions

| URL | View | Who | Others |
| --- | --- | --- | --- |
| `/director/` | `dashboard` | role `director`, superusers | logged out → login; any other role (staff or not) → their own dashboard; non-GET/HEAD → 405 |
| `/director/attendance/` | `attendance` | same | same |
| `/director/execution/` | `execution` → **302** `/director/` (keeps a numeric `branch`) | same | same |

Unchanged rules (ADR-020): `director_required`, read-only, no forms that write. Query parameters: `branch` (both pages), `period` (attendance). The director still never uses `request.branch`.

## 5. Settings

| Setting | Value | Meaning | To change |
| --- | --- | --- | --- |
| `DIRECTOR_FREQUENT_ABSENCE_DAYS` | `3` | «غیبت‌های پرتکرار»: at least this many absent days (absent + excused) in the period | edit `teachlog/config/settings/base.py` (or override in `production.py`) and restart |
| `DIRECTOR_CLASS_ABSENCE_YELLOW` | `5` | % of a class's records absent from which it is «نیاز به توجه» | same |
| `DIRECTOR_CLASS_ABSENCE_RED` | `10` | % from which it is «غیبت زیاد» | same |
| `ATTENDANCE_DAILY_START_DATE` | unchanged | every director range starts there at the earliest | `docs/apps/attendance.md` §6 |

**Review the three values after the first month of real data** (end of Aban 1405). Read through `director.selectors.threshold` only. The former `DIRECTOR_ALERT_*` values existed only as defaults in `director/selectors.py` and are gone with it.

Constants in code (not policy): the next school day is looked for within 14 days, the next holiday within 60 (`director/selectors.py`).

## 6. Decisions

The approved D-items are in §0.3. Resolved during implementation, consistently with the code:

* **The home page's frequent-absence list also shows on a day off** (only "missing" and "today's absent students" are hidden): Friday is when a director might look at the week.
* **«همه‌ی شعبه‌ها»** rather than «هر دو شعبه» in the branch select, so the label stays true if a branch is added.
* **The class table keeps school order** (branch, grade, section) rather than worst-first: a director looks for a class by name; the labels carry the attention.
* **Today's pending classes**: they count in "B classes" and are named in a neutral line «n کلاس هنوز وقت دارد»; in the classes table a class whose only due day is today, before its grace, is «هنوز وقت دارد» (no colour).
* **A sheet on a day without lessons** (the timetable changed after it was taken) counts as recorded, as on the supervisor's overview.
* **Old links**: an unknown `period` (`year`, `custom`) silently opens this month (no error), and `grade` / `class` / `view` / dates are ignored — they come from bookmarks of the Phase 1 panel, not from a mistake of the reader. An unknown `branch` is still reported.
* **Status colours**: «غایب» red, «غیبت موجه» yellow (the supervisor panel uses blue for excused; the director panel is limited to green / yellow / red), late as plain secondary text.

## 7. Tests

**Baseline (`main`, PostgreSQL, before any change):** 689 tests, only the known error `scheduling.tests.WeeklyScheduleServiceTests.test_invalid_color_in_database_never_reaches_style`.

**Branch (PostgreSQL, full suite):** 700 tests, the same single known error and nothing else. The net +11 is the Phase 1 director tests removed and the new director / attendance tests added. The four apps touched (`director`, `attendance`, `analytics`, `supervisor`) also pass on SQLite: 255 tests, OK. `makemigrations --check --dry-run`: no changes.

New coverage (all in the request's list):

| Requirement | Tests |
| --- | --- |
| absent + excused, late apart | `HomeSchoolDayTests.test_today_in_sentences`, `test_todays_absent_students_by_class_late_apart`, `FrequentAbsenceTests.test_a_students_days`, `AttendancePageTests.test_daily_points_…`, `test_class_rows` |
| clamping at the cutoff | `AttendancePageTests.test_the_month_is_clamped_to_the_cutoff_with_a_note`, `test_archived_per_session_records_never_mix_in`, `test_a_period_entirely_before_the_cutoff_is_empty`, `ClassDayStatusTests.test_the_range_is_clamped_…` |
| classes due today (open lesson, full / partial closure, no lessons, Thursday / Friday, grace) | `ClassDayStatusTests` (7 tests), `HomeGraceTests`, `HomeHolidayTests` |
| missing classes with and without a supporter | `HomeSchoolDayTests.test_missing_classes_with_and_without_a_supporter`, `ClassSupervisorsTests` (inactive, wrong grade / branch) |
| frequent-absence threshold at and around its value | `FrequentAbsenceTests.test_at_the_threshold`, `test_around_the_threshold` |
| home on a school day, a holiday, Thursday / Friday, no data | `HomeSchoolDayTests`, `HomeHolidayTests`, `HomeEmptyTests` |
| branch filter | `BranchFilterTests` |
| a student's absences | `FrequentAbsenceTests.test_a_students_days` |
| execution redirect | `ExecutionRedirectTests`, `test_access` |
| supervisor numbers unchanged | `ClassDayStatusTests.test_agrees_with_the_supervisors_overview`, `test_agrees_with_the_engines_expected_class_days`; the existing supervisor / attendance / analytics tests unchanged |
| query counts | `QueryCountTests` (home 20, attendance 19, the same with 1 or 4 extra classes) |

Removed with the code they tested: the Phase 1 `DashboardTests`, `AlertTests`, `ExecutionTests`, `AttendancePageTests` (rates, drill-down, trend of rates), `FormattingTests` (`director_tags`), `FilterTests` (custom ranges, year preset), and the old `QueryCountTests`.

**Browser check** (headless Chrome, scratch SQLite database outside the repo with 12 classes in two branches, nine school days of sheets, a past closure and an upcoming partial one, "now" pinned to Monday 11 Aban 1405 10:00): both pages at 1280 px and at 375 px (in a 375 px frame), with all `<details>` opened too. No horizontal scroll (`.app-shell` scroll width = client width) on the home page, the attendance page (month and today) and the home page for one branch. Fixes that came out of it: the branch selector sat at the far end on the home page (now at the start when there are no period pills); the class name and branch were pushed apart in the phone cards of the classes table; «٪ از روزها» became «٪ غیبت».

## 8. Discrepancies between docs and code

* `docs/apps/director.md` §5 said the `DIRECTOR_ALERT_*` thresholds were "set in `teachlog/config/settings/*.py`"; they were never in the settings files, only defaults in `director/selectors.py`. Corrected (the new thresholds are in `base.py`).
* `docs/apps/supervisor.md` said the training sessions' «پیشرفت» is "the same number the director dashboard shows" and «جبرانی» "the director's"; no longer true until execution returns. Corrected.
* `docs/apps/analytics.md` pointed to `docs/apps/director.md` §8 for the Phase 1 measurements; that section is gone from the rewritten doc, the measurements are in `docs/plans/director-dashboard-phase1.md`. Corrected.
* `.claude/skills/teachlog-workflow/SKILL.md` was clean when this work started and shows as modified in the working tree since; this work did not change it and leaves it as it is (not part of this change).

## 9. Open questions and manual actions

* **Deploy:** no migration; `collectstatic` is needed (new CSS / JS, deleted `filters.js`). Nothing to set up in the admin. Supporters should be assigned to every class (`SupervisorClass`): a class without one shows «پشتیبان ندارد» on the director's home page.
* **Brief the director:** the panel is now "today" and "attendance"; execution is gone until بودجه‌بندی; a class appears as «ثبت نشده» only 15 minutes after its first lesson ends.
* **Review after the first month** (end of Aban 1405): `DIRECTOR_FREQUENT_ABSENCE_DAYS`, `DIRECTOR_CLASS_ABSENCE_YELLOW` / `_RED`.
* **Mid-Bahman 1405:** measure on the production server the supervisor's training sessions page ("since the start of the year") and the director's attendance page ("this month"); build the daily summary table only if one passes 1 second (`docs/apps/analytics.md` §8).
* **Unchanged follow-up:** the academic-year selector before Mehr 1406.
