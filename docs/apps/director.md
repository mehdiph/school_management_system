# Director App

## 1. Purpose

The panel of the school director («مدیر مدرسه»): one person who oversees **both branches**. It answers one question at a glance: **who is not in school, and has every class taken its attendance?** It is built on the daily attendance the grade supporters take at 8:30 (ADR-022, `docs/apps/attendance.md`).

Directors are mostly not data-literate, so the panel speaks in **plain Persian sentences with names** («امروز ۲۳ دانش‌آموز غایب هستند (۵ نفر موجه)»), not in rates. Percentages appear only as small secondary text; there are no deltas, arrows or technical terms (ADR-023).

It is **read-only** (ADR-020): the director never creates or edits data — that is the system admin's job in the Django admin — and no page has a form that writes or a link to an edit page.

**Program execution is deferred.** Phase 1 (October 2026) also had an execution page (expected slots held, per-teacher view, same-subject comparison, conflicts, makeup) and KPI cards with previous-period comparison. They were removed in October 2026: comparing classes has no baseline until curriculum budgeting («بودجه‌بندی») exists. Execution returns after بودجه‌بندی, on the existing `analytics` engine (§8).

---

## 2. Access

| Who | Gets |
| --- | --- |
| A user with role `director` («مدیر مدرسه») | every page |
| A superuser | every page |
| Logged out | redirect to the login page (`?next=`) |
| Any other role (teacher, student, supervisor, accountant, counselor, IT, services, system admin), staff or not | redirect to their own dashboard (`accounts.utils.role_dashboard`), the teacher / student panel pattern |
| Any method other than GET / HEAD | 405 |

`director/permissions.py`: `director_required` (and `is_director`). No profile row is needed: the director sees every active branch. After login the director lands on `/director/`; the sidebar shows the director menu («وضعیت امروز», «حضور و غیاب»), also to a superuser browsing these pages.

**Creating or assigning the director:** in the Django admin, add or open the user and set «نقش» to «مدیر مدرسه». No staff flag, group or permission is needed (and the director should not be staff unless they also administer data). The Excel user import does not create directors.

---

## 3. Pages

| URL | Name | Content |
| --- | --- | --- |
| `/director/` | `director:dashboard` | today: sentences, classes without attendance, today's absent students, this month's frequent absences, the next holiday |
| `/director/attendance/` | `director:attendance` | a period (default this month): absent students per day, the classes table, frequent absences with each student's days |
| `/director/execution/` | `director:execution` | **302** to `/director/` (keeping a valid `?branch=`), behind `director_required`. Temporary on purpose: the page comes back (§8) and browsers cache a 301 |

### 3.1 Filters

A plain GET form (`director/forms.py`), so every view is a link and works without JavaScript:

* **Branch** (`?branch=`, every page): all branches or one. An unknown branch is reported above the page («… همه‌ی شعبه‌ها نمایش داده شده است») and not applied.
* **Period** (`?period=`, the attendance page only): «امروز», «این هفته» (from Saturday), «این ماه» (the Jalali month, **the default**). Links that keep the branch.
* Nothing else: no grade, no custom range, no «از ابتدای سال». An old link carrying `period=year` / `custom`, `date_from`, `grade`, `class` or `view` opens this month without an error.
* **Daily attendance only.** A period is clamped to the days from `ATTENDANCE_DAILY_START_DATE` (1 Aban 1405), the academic year and today (`forms.daily_range`, built on `attendance.services.split_range`). When the cutoff cut days off the start, a note says so; a period entirely before it shows an empty state. Archived per-session attendance never appears on these pages.
* The sidebar links keep the branch (`director_query`).

### 3.2 Home (`/director/`): today

1. **Today in sentences** (one card):
   * «امروز X دانش‌آموز غایب هستند (Y نفر موجه)» — absent = «غایب» + «غیبت موجه», the excused count always beside it («هیچ‌کدام موجه نیست» when 0); «امروز هیچ دانش‌آموزی غایب نیست» when none; «هنوز حضور و غیاب هیچ کلاسی ثبت نشده است» before the first sheet (never "0 absent").
   * «Z نفر تأخیر داشتند» as a secondary line (late is attended, never an absence).
   * «حضور و غیاب A از B کلاس ثبت شده است» with a green «همه ثبت شده» or a red «n کلاس ثبت نشده».
   * «n کلاس هنوز وقت دارد» (neutral) for classes still within their grace (§4).
   * A partial closure: «n کلاس امروز تعطیل است (<event>)».
   * **A day off** — Thursday / Friday («امروز پنج‌شنبه است؛ مدرسه تعطیل است»), every lesson of the scope closed («امروز تعطیل است: <event>»), or a weekday without lessons («امروز کلاسی در برنامه نیست») — replaces the sentences, adds «روز کلاسی بعدی: <date>» (the first day within 14 days with an open lesson) and hides sections 2 and 3.
   * Before daily attendance starts: «حضور و غیاب روزانه از <date> شروع می‌شود».
2. **Classes without attendance today**: each class past its grace without a sheet, with its supporter(s) («پشتیبان: …», or «پشتیبان ندارد») and a red «ثبت نشده».
3. **Today's absent students**, grouped by class in school order, each class a `<details>` (open when there are three classes or fewer): name, status («غایب» red, «غیبت موجه» yellow) and the supporter's description; late students on a secondary line («با تأخیر: …»).
4. **Frequent absences this month** (§3.4), also on a day off.
5. **Next holiday**, one line: the first calendar event starting after today within 60 days for the selected branch, with «(بخشی از کلاس‌ها)» when it closes only some grades, bells or branches.

### 3.3 Attendance (`/director/attendance/`): a period

* **Sentences**: absent days in the period (excused among them), late as a secondary line, and how many times a class's daily attendance was not taken.
* **Absent students per day**: one bar per working day (Saturday–Wednesday). A day the calendar closed for every class is a gray band with the event's title, **never a zero**; a day with lessons but no sheet yet is a gap; a weekday without lessons is «کلاسی نبود» in the table. Chart.js (vendored, ADR-021), RTL (time runs right to left, the axis on the right), Persian digits, a tooltip per day (absent, excused, late, classes not recorded). The same numbers are always in a table («جدول روزانه»), open by default and folded once the chart has drawn, so the page works without JavaScript. Fewer than two days with sheets: the table only.
* **Classes**: class (and branch), supporter(s), absent days with the excused count and an **absence label**, and a **recording label** (§5). No drill-down below the class.
* **Frequent absences** (§3.4). On «امروز» the list asks for a longer period instead.

### 3.4 Frequent absences and a student's days

Students absent (absent or excused) on at least `DIRECTOR_FREQUENT_ABSENCE_DAYS` days of the period (this month on the home page), most days first, with their class, the number of days and how many were excused; late days are mentioned apart. Each row is a `<details>` that opens onto the student's absent, excused and late days with the weekday, the status and the supporter's description (`attendance.services.get_absences` over the listed students). There is no separate student page or URL.

---

## 4. Definitions

Every count comes from `attendance.services` (§6); this app adds no metric rule.

| Term on the page | Rule |
| --- | --- |
| Absent | «غایب» + «غیبت موجه» (`analytics.definitions.ABSENCE_STATUSES`); one daily record = one day |
| Late | «تأخیر»: attended; only ever shown on its own line |
| A class should take attendance on a day | its weekly timetable has at least one lesson that day that the calendar did not close (`planned_class_days`) — the same rule as the sheet page and the engine's expected class-days. Thursday, Friday and days without lessons never count |
| Not recorded («ثبت نشده») | such a day without a sheet: a past day at once; **today only once the class's first open bell has ended plus 15 minutes** (`analytics.definitions.slot_deadline`, the engine's grace). Until then «هنوز وقت دارد» |
| Recorded | the class has a sheet that day (even before its grace, and whatever the timetable says now) |

`attendance.services.class_day_statuses` applies these rules. Tests pin it to the supervisor's overview (without the grace) and to the engine's expected class-days, so the director and the supporters see the same thing once the grace is over. Before it, a supporter's page already shows «ثبت نشده» while the director's shows «هنوز وقت دارد»: the supporter acts at 8:30, the director is only told about what is late.

---

## 5. Settings (labels and thresholds)

Read on each request through `director.selectors.threshold`; set in `teachlog/config/settings/base.py` (override in `development.py` / `production.py` if needed) and restart.

| Setting | Value | Used by |
| --- | --- | --- |
| `DIRECTOR_FREQUENT_ABSENCE_DAYS` | `3` | frequent absences: at least this many absent days in the period |
| `DIRECTOR_CLASS_ABSENCE_YELLOW` | `5` (%) | absence label from «نیاز به توجه» |
| `DIRECTOR_CLASS_ABSENCE_RED` | `10` (%) | absence label from «غیبت زیاد» |

| Label | Green | Yellow | Red |
| --- | --- | --- | --- |
| Absences (a class's absent days ÷ its records in the period) | under 5%: «وضعیت خوب» | 5% to under 10%: «نیاز به توجه» | 10% or more: «غیبت زیاد» |
| Recording | «همه ثبت شده» | — | «n روز ثبت نشده» |

A class without records has no absence label («—»); one still in time today is «هنوز وقت دارد», one without lessons in the period «کلاسی نداشته» (plain text, no colour). The percentage is shown only as small text beside the label.

**The 5% / 10% thresholds and the 3 days are a school policy chosen without real data. Review them after the first month of daily attendance (end of Aban 1405).** They are global for both branches.

---

## 6. Structure

| File | Role |
| --- | --- |
| `director/permissions.py` | `director_required` |
| `director/forms.py` | `DirectorFilterForm` → `DirectorFilters` (period, branch, the clamped range); `daily_range` |
| `director/selectors.py` | page data: `Dimensions`, `home`, `attendance_page`, `absent_by_class`, `frequent_absentees`, `daily_points`, `class_rows`, `absence_level` |
| `director/views.py` | two GET views and the execution redirect: read the request, call one selector, render |
| `director/templates/director/` | `_layout.html` (header, filters, no-year state), `home.html`, `attendance.html`, partials `_filters`, `_frequent`, `_status` |
| `director/static/director/` | `css/director.css`, `js/attendance_chart.js` |

Shared functions used (owned elsewhere):

| Function | Owner | Used for |
| --- | --- | --- |
| `class_day_statuses` | `attendance.services` | which classes were due, recorded, missing, pending or closed, with each sheet's counts |
| `planned_class_days` | `attendance.services` | the next school day on a day off |
| `student_tallies` | `attendance.services` | frequent absences |
| `get_absences` | `attendance.services` | today's absent students; a student's days (with a queryset of enrollments) |
| `split_range`, `daily_start`, `is_daily` | `attendance.services` | clamping to daily attendance |
| `class_supervisors` | `supervisor.selectors` | the supporters of a class, by `SupervisorScope`'s rule (assigned, same branch and grade), active users only |
| `Closures`, `date_range`, `is_weekend` | `academic_calendar.services` | holidays and the next holiday |
| `periods.period_range`, `definitions.rate` | `analytics` | the presets, the absence share |

The pages reuse the supervisor panel's components (cards, tables that become cards on a phone, badges, pills, empty states) and add `director.css`: 18px text (17px on a phone), wider spacing, tap targets of at least 48px, the sentence card, and the expandable lists.

---

## 7. Queries

Every page runs a **fixed number of queries**, whatever the number of classes, students or records (`director/tests.py`, `QueryCountTests`, locked):

| Page | Queries | Of which |
| --- | --- | --- |
| Home (school day) | 20 | 7 overhead (session, user and its three profile look-ups, the footer's two) + year, branches, classes + the calendar (1 + 3 prefetches) + this month's student tallies and the frequent absentees' days + today's timetable, sheets, supporters and absences |
| Attendance | 19 | overhead, year, branches, classes + timetable, calendar (1 + 3), sheets, supporters, student tallies, the frequent absentees' days |

On a day off the home page skips the supporters and today's absences and adds one timetable query for the next school day (Thursday and Friday need no timetable query for today). Queries that have nothing to read (no absences today, nobody frequently absent, no events) are skipped.

Home reads today and the current month only; the attendance page at most a month. Both are cheap all year (one grouped query over at most a month of daily sheets), so they need no precomputed table (`docs/apps/analytics.md` §8).

---

## 8. Follow-ups

* **Program execution returns after curriculum budgeting («بودجه‌بندی»)**, built on the existing `analytics` engine (`engine.compute`, `metrics.breakdowns`, `periods.previous_period` — all kept and tested). Without a plan of lessons per subject and grade there is no baseline to compare classes against; with one, "taught vs planned" becomes meaningful to a director. The Phase 1 design (execution rate, per-teacher view, same-subject comparison, conflicts, makeup coverage) is in `docs/plans/director-dashboard-phase1.md`.
* **Review the label thresholds** (§5) after the first month of real data.
* **Measure in mid-Bahman 1405** (`docs/apps/analytics.md` §8): the supervisor's training sessions page ("since the start of the year") and this panel's attendance page ("this month") on the production server; the daily summary table is built only if a page passes 1 second.
* **Academic-year selector** — before the **1406–1407 academic year starts (Mehr 1406, September 2027)**: the panel always shows the current year (`AcademicYear.is_current`).
* Per-branch thresholds, if the branches turn out to differ: read through `director.selectors.threshold`, which every label already goes through.
* Exports (PDF / Excel) and a weekly digest can reuse `director.selectors` unchanged.

---

## 9. Tests

* `director/tests.py`: the home page on a school day (sentences, no technical terms), before and after the grace, missing classes with and without a supporter, today's absent students by class with late apart, everything recorded; Thursday, Friday, a full and a partial closure, a weekday without lessons, before daily attendance starts, the next holiday (partial) and none, no data, no current year; the branch filter (one branch, an unknown one, links keeping it); frequent absences at and around the threshold and a student's days; the attendance page (the month clamped at the cutoff with a note, archived records never mixed in, a period before the cutoff, the presets and old parameters, daily points with a holiday never zero, a day without a sheet as a gap, class rows and labels, still in time / no lessons); the label thresholds and their settings; the execution redirect; locked query counts.
* `director/test_access.py`: who may open each page, the redirect guarded the same way, GET only, the sidebar without the execution link.
* `attendance/test_class_days.py`: `class_day_statuses` (grace, partial closure, full closure, no lessons, Thursday / Friday, past days, clamping) and its agreement with the supervisor's overview and the engine; `planned_class_days` with preloaded closures; readers with a queryset of enrollments; `class_supervisors`.
