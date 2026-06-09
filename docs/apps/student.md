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

---

## 2. Database Models (`student/models/`)

### 2.1 StudentProfile (`student_profile.py`)
This model stores the primary biographical, enrollment, and administrative status information for each student.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `user` | `OneToOneField(AUTH_USER_MODEL)` | Maps directly to the authentication user. Relates back via `student_profile` and is restricted to `role='student'`. |
| `student_code` | `CharField(max_length=20)` | Unique registration code assigned to the student (e.g., "کد دانش آموزی"). |
| `school_class` | `ForeignKey(SchoolClass)` | Associated physical/logical class unit. Employs `PROTECT` on delete to avoid accidental removal of active student data. |
| `enrollment_date` | `jmodels.jDateField` | Date of registration using the Jalali calendar system. |
| `status` | `CharField` | Status selection from the `Status` text choices sub-class. |

#### Status Selection Options
*   `active` ("فعال")
*   `graduated` ("فارغ التحصیل")
*   `transferred` ("انتقالی")

*   **String Representation:** Returns the full name of the student's associated authentication user.

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
Renders the primary landing portal for authenticated students. It performs the following data queries:
*   **Profile Query:** Retrieves the student profile and active school class.
*   **Homework Query:** Queries the `SessionContent` database for up to five of the latest homework items. It targets sessions that match the student's `school_class` and filters out empty strings:
    ```python
    homeworks = (
        SessionContent.objects
        .filter(session__class_subject__school_class=school_class)
        .exclude(homework='')
        .select_related('session', 'session__class_subject', 'session__class_subject__subject')
        .order_by('-session__date')[:5]
    )
    ```
*   **Schedule Query:** Dynamically queries `ClassSchedule` for active classes scheduled for the current day. The query helper `get_today_schedule_day(date.today())` retrieves classes matching the correct day of the week, ordered by start time.

### 4.2 `sessions_list` View
Lists class subjects assigned to the student's standard school class. It uses `prefetch_related` on `'sessions'` and `'sessions__session_contents'` to optimize performance when rendering timeline structures.

### 4.3 `session_list_json` API Endpoint
A localized API view that returns JSON formatted list data for a specific subject. 
*   Filters `ClassSubject` matching the student's class and selected subject slug.
*   Iterates over the related sessions to build a standardized dictionary:
    ```python
    {
        'id': session.id,
        'label': f'جلسه {persian_filters.persian_ordinal(session.session_number)} - {persian_filters.persian_date(session.date)}',
        'title': session.session_contents.title,
        'content': session.session_contents.content
    }
    ```
*   Returns a `JsonResponse` payload, enabling the frontend to fetch session timelines via asynchronous AJAX calls.

---

## 5. URL Routing (`student/urls.py`)

```python
app_name = 'student'

urlpatterns = [
    path('dashboard/', views.student_dashboard, name='dashboard'),
    path('sessions/<slug:subject>', views.sessions_list, name='sessions'),
    path('api/sessions/<slug:subject>', views.session_list_json, name='session_list_json')
]
```

---

## 6. Frontend Presentation & Styling

The frontend components leverage modern, clean layouts designed to display dashboard blocks and interactive timelines.

### 6.1 `dashboard.html`
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

The student administrative panels are registered using basic Django model administrators:

```python
@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['get_full_name', 'school_class', 'enrollment_date', 'status']

    def get_full_name(self, obj):
        return f"{obj.user.get_full_name()}"
    get_full_name.short_description = 'نام و نام خانوادگی'
```

*   **`get_full_name` Helper:** Invokes `obj.user.get_full_name()` inside a list column to display the student's full name, resolving the nested authentication dependency.