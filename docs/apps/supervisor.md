# Supervisor App

## Purpose

The Supervisor app is the panel of the "پشتیبان": a staff member who oversees a set of classes of one grade in one branch. It shows what the teachers of those classes actually recorded (sessions, content, attendance) so the supervisor can follow up, and compare progress with the curriculum plan (بودجه‌بندی).

Everything in it is read-only: no page here changes data.

---

## Models

### SupervisorProfile

| Field  | Description                                  |
| ------ | -------------------------------------------- |
| user   | One-to-one with the supervisor's `User`      |
| branch | The branch the supervisor works in           |
| grade  | The grade (پایه) the supervisor oversees     |

### SupervisorClass

Assigns a `SchoolClass` to a supervisor (unique per supervisor and class). `clean()` only accepts classes of the supervisor's own grade and branch.

---

## Access and Scope

### `require_supervisor` (`supervisor/permissions.py`)

Every supervisor view uses this decorator:

* Logged-out users are redirected to the login page (like `teacher_required` / `student_required`).
* Users without a `SupervisorProfile`, or whose selected branch is not the supervisor's branch, get 403.
* The view gets `request.supervisor`.

### `SupervisorScope` (`supervisor/selectors.py`)

The single source of truth for "what may this supervisor see". All page selectors build on it, and views never query models directly.

| Method                            | Returns                                                                 |
| --------------------------------- | ----------------------------------------------------------------------- |
| `classes()`                       | Classes assigned via `SupervisorClass`, in the supervisor's branch and grade |
| `class_subjects()`                | All class subjects of those classes                                     |
| `supervised_class_subjects(year)` | Active class subjects of active classes, optionally in one academic year |
| `supervised_sessions()`           | Sessions of `supervised_class_subjects()`                               |
| `academic_years()`                | Years the supervisor has classes in, plus the current year              |
| `sessions()`, `attendance()`, `teachers()`, `student_enrollments()` | Used by the dashboard and attendance pages |

Rules:

* Every queryset is restricted to the scope inside the selector, never through user-supplied parameters.
* Detail and fragment views look their object up with `get_object_or_404` on a scoped queryset, so anything outside the scope is a **404** (its existence is not leaked).
* Filter dropdown options (years, teachers, subjects, classes) also come from the scope. An id outside it is an invalid choice: the form shows a Persian error and the filter is not applied.

---

## Pages

| URL                                                  | Name                     | View                     |
| ---------------------------------------------------- | ------------------------ | ------------------------ |
| `/supervisor/`                                       | `dashboard`              | `dashboard`              |
| `/supervisor/attention/`                             | `attention_list`         | `attention_list`         |
| `/supervisor/attendance/`                            | `attendance`             | `attendance`             |
| `/supervisor/sessions/`                              | `sessions`               | `training_sessions`      |
| `/supervisor/sessions/class-subject/<pk>/timeline/`  | `class_subject_timeline` | `class_subject_timeline` |
| `/supervisor/sessions/<pk>/`                         | `session_detail`         | `session_detail`         |
| `/supervisor/teachers/`                              | `teachers`               | `supervised_teachers`    |

The sidebar items «جلسات آموزشی» and «معلمان من» (`template/partials/sidebar.html`) link to the last two pages. «جلسات آموزشی» stays active on the timeline and session detail pages.

### Academic calendar (holidays)

Holiday sessions (status `HL`, created by the academic calendar for closed slots) are **never counted** here and closed slots are **never expected** (all through `academic_calendar.services`; see [academic_calendar.md §8.3](academic_calendar.md#83-supervisor)):

* **Dashboard / «نیازمند پیگیری»**: a scheduled slot is matched to a session by class subject + date + **bell**, so two bells of one subject are two expected sessions; a legacy session without a bell covers the day's first uncovered bell. Closed slots, Thursdays and Fridays are never reported missing nor counted in «امروز». Statistics, recent sessions and the attendance page's latest session skip holidays.
* **Training sessions**: counts, KPIs, first/last dates and coverage exclude holidays; a sortable «تعطیل» column shows each class subject's sessions cancelled by closures. The timeline shows holidays in place (no number, the event as the reason) and measures gaps between counted sessions only.
* **Teachers**: session count and last activity ignore holidays.

There is no consecutive-absence feature in this panel yet (follow-up: it must ignore holiday sessions).

---

### Training Sessions — جلسات آموزشی (`sessions/`)

Shows how many sessions each teacher recorded for each subject in each class, when, and what was taught.

**Filters** (`SessionFilterForm`, a GET form, so links are shareable):

| Parameter                 | Meaning                                                              |
| ------------------------- | -------------------------------------------------------------------- |
| `academic_year`           | Defaults to the current year                                          |
| `teacher`                 | `TeacherProfile` id. The supervised teachers page links here with `?teacher=<id>&academic_year=<id>` |
| `subject`, `school_class` | Narrow the rows                                                       |
| `date_from`, `date_to`    | Jalali dates, `1405/07/01` or `1405-07-01`, Persian or ASCII digits   |
| `range`                   | Shortcut links: `week` (Saturday..Friday), `month` (Jalali month), `year` (the academic year). Turned into `date_from`/`date_to` by the form |
| `status`                  | `HD` / `CD` / `JB` (holidays are not a status filter: they have their own column) |
| `sort`                    | `teacher`, `subject`, `class`, `sessions`, `empty`, `holidays`, `first_date`, `last_date`; prefix `-` for descending |
| `page`                    | 20 rows per page                                                      |

Invalid values never break the page: the field shows its error and is ignored.

**KPI cards** (for the current filters): recorded sessions, teachers, sessions without content, date of the last recorded session.

**Summary table**: one row per supervised `ClassSubject` (teacher × subject × class), including class subjects with no session at all:

* recorded sessions, sessions without content, **holidays** («تعطیل»: sessions the academic calendar cancelled), first and last session date;
* **progress against the timetable**: held + compensatory sessions compared with the slots the weekly timetable planned (both weeks of the rotation, one per bell) from the class subject's start, or `date_from`, up to today or `date_to`, **without slots an active calendar event closed and without Thursdays/Fridays** (`academic_calendar.services.count_open_slots`). Shown as "n از m · x٪" with a bar: under 60% is red, under 85% amber. Rows without timetable slots show «برنامه‌ی هفتگی ندارد».

"Without content" means a session with no `SessionContent` row, **excluding cancelled and holiday sessions**. Holiday sessions are never counted as recorded sessions.

**Timeline**: «جلسات» on a row expands it and loads the class subject's sessions (with the active date range and status) as a vertical timeline, in teaching order (date, then bell). Holidays appear in place with «بدون شماره» and their reason; gaps are measured between counted sessions only. Each item shows the number, Jalali date and weekday, status badge, title, the start of the content (two lines), and markers for homework / activity / notes. Sessions without content and gaps longer than `SUPERVISOR_SESSION_GAP_WARNING_DAYS` (default 14) between consecutive sessions are highlighted. Without JS the button is a link to the full timeline page.

**Session detail**: a session title opens a drawer from the left with the full content, homework, activity, notes and attendance counts (total / present / absent / late, no student list). Without JS it is a full page.

---

### Supervised Teachers — معلمان من (`teachers/`)

A supervised teacher is a `TeacherProfile` with at least one active class subject in the supervisor's active classes in the selected academic year. The assignment status is not checked, so past years still list their teachers.

**Filters** (`TeacherFilterForm`): `q` (name or personnel code; auto-submitted after typing stops), `subject`, `academic_year`, `sort` (`name`, `sessions`, `-sessions`, `last_activity`, `-last_activity`), `view` (`cards` or `table`), `page` (12 per page).

Each teacher shows: avatar, name, personnel code, education / field of study, subject and class chips (only within the scope), recorded sessions, sessions without content, and the last session as relative time («۳ روز پیش»). In the current year, a teacher whose last session is older than `SUPERVISOR_INACTIVITY_WARNING_DAYS` (default 7), or who has none, is flagged.

Statistics only count the teacher's sessions in the supervisor's classes (and the selected subject). «مشاهده‌ی جلسات» opens the training sessions page filtered on that teacher, year and subject.

---

## Selectors

| Class                          | Used by                                              |
| ------------------------------ | ---------------------------------------------------- |
| `SupervisorDashboardSelector`  | Dashboard, attention list                            |
| `SupervisorAttendanceSelector` | Attendance page                                      |
| `SupervisorSessionsSelector`   | Training sessions page, timeline, session detail     |
| `SupervisorTeachersSelector`   | Supervised teachers page                             |

`SupervisorSessionsSelector`:

* `summary_rows(filters)`: annotated rows (`session_count`, `empty_count`, `delivered_count`, `first_date`, `last_date`) via `Count(filter=Q(...))`, `Min`, `Max`.
* `kpis(filters)`: one `aggregate()`.
* `attach_coverage(rows, filters)`: expected sessions and coverage for one page of rows (one query for their timetable slots, then `scheduling.utils.count_scheduled_occurrences`).
* `timeline(class_subject, filters)`: loads only the session fields, the title and the first 240 characters of the content (`Substr`), never the full texts.
* `detail_sessions()` / `timeline_class_subjects()`: the scoped querysets the views pass to `get_object_or_404`.

`SupervisorTeachersSelector.teachers()` applies the scope in a single `filter()` before `annotate()`, so the aggregates only run over the in-scope class subjects (Django reuses that join). `decorate()` adds the chips with one more query.

Filters reach the selectors as a `SessionFilters` dataclass of already-validated, in-scope values.

---

## Fragments (HTML partials)

The timeline and detail views render either a full page or, with `?partial=1`, only their fragment. The page JS fetches the fragment and inserts it, so all rendering stays in Django templates (no JSON API).

| Template                                         | Rendered by                                     |
| ------------------------------------------------ | ----------------------------------------------- |
| `partials/_session_timeline.html`                | Timeline fragment, and inside `session_timeline.html` |
| `partials/_session_detail.html`                  | Drawer fragment, and inside `session_detail.html` |
| `partials/_teacher_card.html`                    | Cards view of the teachers page                 |
| `partials/_teacher_activity.html`                | Last-session marker (cards and table)           |
| `partials/_session_status_badge.html`            | Status as colour + icon + text                  |
| `partials/_filter_field.html`                    | Labelled filter field with its errors           |
| `partials/_pagination.html`                      | Previous / next, keeping every other GET parameter (`{% querystring %}`) |
| `partials/_session_drawer.html`                  | The drawer shell, loading and error templates   |

Template filter: `{% load supervisor_tags %}` → `relative_days` («امروز», «دیروز», «۳ روز پیش», «۲ هفته پیش», …).

---

## Static Files

| File                         | Purpose                                                                 |
| ---------------------------- | ----------------------------------------------------------------------- |
| `css/panel.css`              | Shared: filter bar, cards, tables that become stacked cards on phones, chips, pagination, loading/error |
| `css/sessions.css`           | Coverage bar, expandable rows, timeline, drawer, session detail          |
| `css/teachers.css`           | Teacher card grid and inactivity marker                                  |
| `js/session_drawer.js`       | `SupervisorPartials.load()` (loading indicator, error + retry) and the session drawer (Esc, focus trap, focus returns to the link) |
| `js/sessions.js`             | Expandable rows, Jalali date pickers, year change re-submits             |
| `js/teachers.js`             | Debounced search submit, selects submit on change                         |

The pages also load `dashboard.css` and `attendance.css` for the existing badges, buttons, stat cards, pills and empty states, and the project's persian-datepicker from `teaching/static`.

All JS is progressive enhancement: every page works with plain links and GET forms.

---

## Settings

| Setting                               | Default | Meaning                                                    |
| ------------------------------------- | ------- | ---------------------------------------------------------- |
| `SUPERVISOR_INACTIVITY_WARNING_DAYS`  | 7       | Days without a recorded session before a teacher is flagged |
| `SUPERVISOR_SESSION_GAP_WARNING_DAYS` | 14      | Gap between two sessions marked as long on the timeline    |

Both are optional and read with `getattr(settings, ...)`.

---

## Performance

* No N+1 queries: related objects are joined with `select_related`, statistics are annotations, chips and timetable slots are one query per page.
* `SchoolSession` has an index on `(class_subject, date)` (`teaching` migration `0003`) for the per-class-subject date-range reads.
* Query counts are locked in `supervisor/test_training_sessions.py` (`QueryCountTests`). Every request costs 9 queries of shared overhead (session, user, profiles, branch middleware, sidebar context). On top of that: sessions page 8, teachers page 5, timeline and detail fragments 2 each.

---

## Tests

* `supervisor/tests.py`: dashboard, attention list and attendance pages, `SupervisorScope`.
* `supervisor/test_training_sessions.py`: access (login redirect, 403), scoping (404 outside the scope, filter options), counts, filters (dates, Persian digits, invalid input, range shortcuts, academic year, `?teacher=`), sorting and paging, partial vs full rendering, query counts.
* `supervisor/test_calendar.py`: missing sessions per bell (and the legacy fallback), closed slots never missing or scheduled, coverage without holidays, the holiday column and KPI, the timeline with holidays.

---

## Known Limitations

* Coverage uses the current timetable for the whole range; a timetable changed mid-year is applied retroactively to the expected count.
* Inactive class subjects and classes are hidden. When a subject is reassigned mid-year (the old class subject is deactivated), the previous teacher's sessions no longer appear.
* There is no curriculum-plan model yet, so the comparison with بودجه‌بندی is manual (see below).

---

## Future Improvements

### Curriculum Plan (بودجه‌بندی)

```python
class CurriculumPlan(models.Model):          # one per subject × grade × year
    academic_year = FK(AcademicYear)
    grade = FK(Grade)
    subject = FK(Subject)
    # unique (academic_year, grade, subject)

class CurriculumPlanItem(models.Model):
    plan = FK(CurriculumPlan, related_name="items")
    order = PositiveIntegerField()
    title = CharField()                       # chapter / lesson
    planned_sessions = PositiveSmallIntegerField(default=1)
    target_week = PositiveSmallIntegerField(null=True)   # academic week (scheduling.utils)
    # unique (plan, order)

# optional: SessionContent.plan_items = M2M(CurriculumPlanItem)
```

With teachers tagging each session with the plan items it covered, the timeline could show "planned for week N, taught in week M" and the summary table could show the share of the plan covered instead of the share of timetabled sessions.

### Other

* A holiday calendar, to make the expected session count exact.
* Searchable teacher / class selects for supervisors with many classes.
