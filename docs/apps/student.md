# Student App Documentation

The `student` application manages student records, profiles, and dashboard interfaces. It bridges user accounts with educational resources, schedules, and curriculum tasks.

---

## 1. System Architecture & Context integration

The `student` app provides the main interface for users categorized under the `'student'` role. It manages how students interact with their class schedules, view academic progress, and check homework tasks.

### Context Processor (`student/context_processors.py`)
To ease template rendering across various school directories, the app defines a global context processor, `student_info`. When registered in Django's settings, it injects student-related context into active template contexts:

*   **Logic:**
    *   Checks if the user is authenticated and possesses the `'student'` role.
    *   If matched, returns the user instance under the variable key `student` and the student's associated class under `school_class`.
    *   If not matched, returns an empty dictionary.
    *   A user with the `'student'` role but no `StudentProfile` row also gets an empty dictionary, so every page still renders (the topbar shows «دانش‌آموز» without a class). The student pages themselves refuse that user with a 403 (`student.decorators.student_required`).

---

## 2. Database Models (`student/models/`)

### 2.1 StudentProfile (`student_profile.py`)
One row per student, whatever the year.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `user` | `OneToOneField(AUTH_USER_MODEL)` | The login. Relates back via `student_profile`; restricted to `role='student'`. |
| `student_code` | `CharField(max_length=20)` | Unique registration code («کد دانش آموزی»). |

### 2.2 StudentEnrollment (`student_enrollment.py`)
One row per student per academic year: `student`, `academic_year`, `school_class`, `enrollment_date`, `status`, `created_at`. A class change edits this row.

### 2.3 Which enrolment a page uses (`student/selectors.py`)
*   **`current_enrollment(profile)`** decides what a student receives right now (online classes, announcements): active, current year, active class of an active branch; the newest wins if two years are flagged current; otherwise `None`. A student who left or hasn't re-enrolled receives nothing.
*   **`panel_enrollment(profile)`** is what the student's own pages show (timetable, homework, sessions): the newest year's, in any status, or `None`.

---

## 3. Custom Template Tags & Filters (`student/templatetags/`)

The application includes a specialized template filter utility set (`persian_filters.py`) to convert numbers and dates into localized Persian textual representations.

### 3.1 `persian_ordinal`
Converts positive integer inputs (representing session or class numbers) into ordinal Persian descriptive words.
*   **1–19 Range Mapping:** Handled by a static lexicon lookup (e.g., `1` becomes `'اول'`, `10` becomes `'دهم'`).
*   **Decade Markers:** Exact decametric values (20, 30, ..., 100) are converted directly (e.g., `20` becomes `'بیستم'`).
*   **Compound Values:** Combines factors using standard Persian joining syntax (e.g., `21` results in `'بیست و یکم'`).
*   **Fallback:** Returns the string value of the input if parsing fails or bounds are exceeded.

### 3.2 `persian_date`
Converts standard datetime objects or formatted Jalali date strings into a localized textual representation (e.g., converting a Jalali date like `1405-03-10` into `'10 خرداد 1405'`).

---

## 4. Views and Controller Logic (`student/views.py`)

### 4.1 `student_dashboard` View
Renders the primary landing portal for authenticated students. `never_cache`, because the online card can hold personal links. A student with no enrolment gets an empty state, not an error.
*   **Enrolment:** `panel_enrollment` gives the class.
*   **Online block:** `online_classes.selectors.dashboard_block` gives the banners and the card, at most four queries (see [online_classes.md](online_classes.md)). `?partial=1` returns just the card, for the JS refresh (ADR-015).
*   **Today and tomorrow:** `get_classes_for_day(school_class, date)`.
*   **Homework:** up to five latest `SessionContent` rows of the class with non-empty homework.

### 4.2 `sessions_list` View
Lists the class subjects of the class from `panel_enrollment` (none for a student with no enrolment). It uses `prefetch_related` on `'sessions'` and `'sessions__session_contents'` to optimize performance when rendering timeline structures. Each class subject is annotated with `session_count`, which **excludes holiday sessions** (status `HL`, see [academic_calendar.md](academic_calendar.md)).

### 4.3 `session_list_json` API Endpoint
A localized API view that returns JSON formatted list data for a specific subject. 
*   Filters `ClassSubject` matching the student's class and selected subject slug.
*   Iterates over the related sessions (newest first, by date then bell) and builds one dictionary per session with `_session_json`:
    ```python
    {
        'id': session.id,
        'label': 'جلسه سوم - ۱۲ مهر ۱۴۰۵ · زنگ ۲',   # «تعطیل - <date> · <bell>» for a holiday
        'title': '<content title>',                  # «تعطیل: <event>» for a holiday
        'content': '<content text>',
        'is_holiday': False,                         # True: the page shows it hatched, with no number
        'reason': '',                                # the calendar event's title for a holiday
    }
    ```
*   Sessions without content no longer raise: they get «بدون عنوان» and an empty content.
*   Returns a `JsonResponse` payload, enabling the frontend to fetch session timelines via asynchronous AJAX calls.

---

## 5. URL Routing (`student/urls.py`)

```python
app_name = 'student'

urlpatterns = [
    path('dashboard/', views.student_dashboard, name='dashboard'),
    path('sessions/', views.sessions_list, name='sessions'),
    path('api/sessions/<slug:subject>', views.session_list_json, name='session_list_json')
]
```

The online pages are also under `/student/` but belong to `online_classes` (`/student/online/`, `/student/announcements/<id>/dismiss/`).

---

## 6. Frontend Presentation & Styling

The frontend components leverage modern, clean layouts designed to display dashboard blocks and interactive timelines.

### 6.1 `dashboard.html`
*   **Announcements and online card:** the banners on top, then the «کلاس‌ها و آزمون‌های آنلاین» card after the hero (templates in `online_classes`).
*   **Hero Section:** Welcomes the student and displays their avatar image.
*   **Achievements Panel:** Lists gamification statistics, such as learning streaks or homework completed status badges.
*   **Today's Classes:** Uses conditional structures to display today's lessons or an alternative message if there are no classes scheduled.
*   **Quick Actions:** Link buttons built on static vector layouts to direct users to tasks, weekly schedules, profile adjustments, and educational sessions.

### 6.2 `session_list.html`
*   **Search and Filter Panel:** Dropdowns allow the student to filter records by subject or select specific dates.
*   **Asynchronous Timeline Rendering:** Contains an HTML `<template>` element with the ID `subject-sessions-template`. This template is used by the frontend JavaScript (`session_list.js`) to dynamically generate and insert session cards into the DOM when a user interacts with the top-level cards.

### 6.3 Style System (`student/static/student/css/`)
*   **`dashboard.css`:** Uses CSS Grid layouts (`grid-2-col` and `homework-section`) to organize card-based interfaces. Media queries adjust the card structures for mobile displays.
*   **`session_list.css`:** Uses a relative vertical line system (`.timeline-line` and `.timeline-node`) to render timelines on the right side of session information blocks.

---

## 7. Admin Interface Integration (`student/admin.py`)

*   **`StudentProfileAdmin`:** `list_display = ['get_full_name']`, and `search_fields` on name, student code and national code, which the online classes pickers need. In `get_search_results`, results are limited to the admin's branches only when the autocomplete request comes from `online_classes`, so the existing pages don't change.
*   **`StudentEnrollmentAdmin`:** branch-scoped, listing student, class, branch, status, date and year.
