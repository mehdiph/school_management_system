# Teaching App Documentation

The `teaching` application manages the cataloging, logging, and editing of class sessions and their corresponding curricular contents. It tracks lesson schedules, class activities, homework assignments, and teacher logs.

---

## 1. System Role & Curricular Coupling

The `teaching` app acts as the record-keeper for lesson execution. While the `school` app defines *what* is assigned to whom (teacher, subject, class), the `teaching` app logs *when* and *what* was actually covered. 

Every scheduled class has a parent record (`SchoolSession`) documenting when it occurred and its status, which is linked to a detailed description record (`SessionContent`) containing the textual data of the lesson.

---

## 2. Database Models (`teaching/models/`)

### 2.1 SchoolSession (`school_session.py`)
Documents an individual class meeting occurrence.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `class_subject` | `ForeignKey(ClassSubject)` | Associated assignment. Employs `DO_NOTHING` on delete. Relates back via `sessions`. |
| `date` | `jmodels.jDateField` | Date of the session in the Jalali calendar system. |
| `session_number` | `IntegerField` | Sequential index number of the session within the term. |
| `status` | `CharField(max_length=2)` | Operational status of the session. |
| `created_at` | `jmodels.jDateTimeField` | Record creation timestamp. |

#### Session Status Choices (`Status`)
*   `JB`: Compensatory ("جبرانی")
*   `CD`: Canceled ("کنسل شده")
*   `HD`: Held ("برگزار شده") - *Default*

*   **Ordering:** Ordered descending by date (`-date`) and session number (`-session_number`).
*   **String Representation:** Returns `"{class_subject} - جلسه {session_number}"`.

---

### 2.2 SessionContent (`session_content.py`)
Holds the detailed curricular contents and tasks assigned during a specific session.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `session` | `OneToOneField(SchoolSession)` | Unique link to the parent session. Relates back via `session_contents`. |
| `title` | `CharField(max_length=255)` | Short topic title (e.g., "جمع اعداد چند رقمی"). |
| `content` | `TextField` | Description of the topics and concepts taught. |
| `activity` | `TextField` | Interactive exercises performed in-class. |
| `homework` | `TextField` | Home assignments given to the students. |
| `notes` | `TextField` | Teacher notes regarding student performance. |
| `created_at` | `jmodels.jDateTimeField` | Record creation timestamp. |

*   **Ordering:** Ordered descending by creation date (`-created_at`).
*   **String Representation:** Returns `"{session} - {title}"`.

> **Note on Naming Consistency:** 
> In `models/session_content.py`, the One-to-One relationship specifies `related_name='session_contents'`. In `views.py` (`update_session`), the update lookup accesses this model as `session.sessioncontent`. Ensure consistency in code extensions to avoid `AttributeError` exceptions.

---

## 3. Forms & Input Constraints (`teaching/forms.py`)

### 3.1 `SchoolSessionForm`
*   **Active Assignment Enforcement:** Under the `__init__` constructor, the `class_subject` queryset is restricted to active classes and active subjects using optimization lookups:
    ```python
    self.fields['class_subject'].queryset = ClassSubject.objects.filter(
        is_active=True,
        school_class__is_active=True
    ).select_related('school_class', 'subject', 'teacher')
    ```
*   **Validation Rules:** `class_subject`, `date`, and `session_number` are strictly set as required fields.

### 3.2 `SessionContentForm`
*   Implements placeholders and styling adjustments for Textarea fields (e.g., setting the rows attribute to `4` for curriculum content, and `3` for notes and homework).
*   Enforces `title` as a required field.

---

## 4. Views and Transaction Logic (`teaching/views.py`)

The views implement optimizations and transaction blocks to handle double-form submissions and database reads.

### 4.1 `school_session_form` (Session Creation)
Processes the simultaneous submission of `SchoolSessionForm` and `SessionContentForm`.

*   **Atomic Transactions:** Wraps database saves inside a `transaction.atomic()` block. If the creation of either `SchoolSession` or `SessionContent` fails, the transaction is rolled back to maintain database integrity:
    ```python
    with transaction.atomic():
        session = session_form.save()
        content = content_form.save(commit=False)
        content.session = session
        content.save()
    ```
*   **Session Number Auto-Increment:** On standard `GET` requests, it queries the specified `ClassSubject`, finds the highest existing `session_number`, and automatically populates the form with the next integer value:
    ```python
    last_session = SchoolSession.objects.filter(class_subject=class_subject).order_by('-session_number').first()
    next_number = (last_session.session_number + 1) if last_session else 1
    ```

### 4.2 `update_session` View
Loads existing instances of `SchoolSession` and `SessionContent` to update them inside a unified interface.

### 4.3 `session_list` View
Lists all sessions recorded under a specific `ClassSubject`.
*   **N+1 Query Prevention:** Explicitly prefetches relational fields to minimize query roundtrips:
    ```python
    sessions = SchoolSession.objects.filter(
        class_subject_id=class_subject_id,
        class_subject__is_active=True,
    ).select_related(
        'class_subject__school_class__grade',
        'class_subject__subject',
        'class_subject__teacher',
        'session_contents'
    ).order_by('-date', '-session_number')
    ```

---

## 5. URL Routing (`teaching/urls.py`)

All patterns are registered under the `'teaching'` namespace:

```python
app_name = 'teaching'

urlpatterns = [
    path('session/<int:class_subject_id>', views.school_session_form, name='session_form'),
    path('sessions/<int:class_subject_id>', views.session_list, name='session_list'),
    path('update_session/<int:session_id>/', views.update_session, name='update_session'),
]
```

---

## 6. Frontend Assets & Templates

The app relies on external date pickers and CSS definitions to manage Persian dates and schedule tables.

### 6.1 Jalali Datepicker Integration
The creation and update interfaces load a localized date picker (`persian-datepicker.js` and its stylesheet dependency). This script maps the standard input field to a Persian calendar widget, handling date translation before the form is submitted.

### 6.2 Styling System (`session_list.css`)
*   **Badges:** Styles the operational status of sessions visually:
    *   `.status-held` ("برگزار شده"): Light green background.
    *   `.status-canceled` ("لغو شد"): Light red background.
    *   `.status-makeup` ("جبرانی"): Light yellow background.
*   **Hover States:** Includes fluid transitions for grid cells on larger monitors, converting rows to block sections on mobile viewport widths.

---

## 7. Admin Customization (`teaching/admin.py`)

The Django administration panel uses two custom configurations:

### 7.1 `SchoolSessionAdmin`
*   **Hierarchy Filter:** Implements `JDateFieldListFilter` to allow filtering by Jalali dates.
*   **Inline Editing:** Allows administrators to modify session statuses (`status`) directly on the list grid without opening individual records.
*   **Deep Lookups:** The search bar searches across the database using deep relations:
    ```python
    search_fields = (
        'class_subject__subject__name',
        'class_subject__school_class__section',
        'class_subject__teacher__username',
        ...
    )
    ```

### 7.2 `SessionContentAdmin`
*   Provides structured fieldsets to organize textual input fields into distinct sections: "اطلاعات جلسه" (Session Information), "محتوای درسی" (Lesson Content), and "تکلیف و یادداشت" (Homework and Notes).