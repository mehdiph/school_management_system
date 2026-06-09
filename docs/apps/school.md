# School App

This document provides a technical overview and documentation for the Django `school` application, which forms a core component of the school management system. The application handles academic years, educational grades, subjects, physical/logical classes, and the assignment of subjects and teachers to classes.

---

## 1. Architectural Overview

The `school` app is designed to manage the structural hierarchy of an educational institution. It organizes data around five relational database models and integrates Persian (Jalali) date handling using the `django-jalali` library.

### Core Features
*   **Academic Lifecycle Management:** Tracks active and current academic years.
*   **Educational Structure Hierarchy:** Manages class grades (e.g., Grade 1, Grade 2) and individual class divisions (sections).
*   **Subject Registry:** Maintains a catalog of taught subjects.
*   **Teacher Assignments (Class Subjects):** Bridges classes, subjects, and teachers under specified validity dates.
*   **Teacher-Specific Dashboards:** Displays filtered and grouped lists of class assignments for authenticated teaching staff.

---

## 2. Database Models (`school/models/`)

The database architecture is split into modular files under the `school/models/` directory.

### 2.1 AcademicYear (`academic_year.py`)
Represents a school calendar year. 

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `title` | `CharField(max_length=50)` | Name of the academic year (e.g., "1402-1403"). |
| `start_date` | `jmodels.jDateField` | Start date of the academic period (Jalali). |
| `end_date` | `jmodels.jDateField` | End date of the academic period (Jalali). |
| `is_current` | `BooleanField` | Designates if this is the active school year. |
| `is_active` | `BooleanField` | Designates if the record is enabled. |

### 2.2 Grade (`grade.py`)
Defines the educational levels within the school.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `name` | `CharField(max_length=255)` | Name of the grade (e.g., "پایه هفتم"). |
| `level` | `IntegerField` | Numeric level used for ordering (must be unique). |
| `created_at` | `jmodels.jDateTimeField` | Automatic timestamp of record creation. |
| `is_active` | `BooleanField` | Status indicator for the grade. |

### 2.3 Subject (`subject.py`)
Represents the curriculum topics.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `name` | `CharField(max_length=255)` | Name of the subject (e.g., "ریاضی"). |
| `slug` | `SlugField(max_length=255)` | URL-friendly identifier. |
| `created_at` | `jmodels.jDateTimeField` | Record creation timestamp. |
| `is_active` | `BooleanField` | Status indicator for the subject. |

### 2.4 SchoolClass (`school_class.py`)
Represents a distinct class unit assigned to a grade and academic year.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `year` | `ForeignKey(AcademicYear)` | Linked academic year. Cascade on delete. |
| `grade` | `ForeignKey(Grade)` | Linked educational grade. Cascade on delete. |
| `section` | `CharField(max_length=255)` | Section identifier (e.g., "الف", "101"). |
| `created_at` | `jmodels.jDateTimeField` | Creation timestamp. |
| `is_active` | `BooleanField` | Status indicator. |

*   **String Representation:** Returns `"{grade.name} - {section}"`.

### 2.5 ClassSubject (`class_subject.py`)
The junction model associating a class, a subject, and a teacher.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `school_class` | `ForeignKey(SchoolClass)` | Associated class. Linked via `related_name='class_subjects'`. |
| `subject` | `ForeignKey(Subject)` | Associated subject. |
| `teacher` | `ForeignKey(User)` | Assigned teacher user model instance. |
| `start_date` | `jmodels.jDateField` | Course teaching start date. |
| `end_date` | `jmodels.jDateField` | Course teaching end date. |
| `created_at` | `jmodels.jDateTimeField` | Record creation timestamp. |
| `is_active` | `BooleanField` | Status indicator. |

*   **Constraints:** `teacher` field is limited using `limit_choices_to={'role': 'teacher'}`.
*   **Icon Helper Property:** A helper `@property` named `icon` evaluates `self.subject.name` and returns an associated FontAwesome icon class string (defaults to `'fa-book'`).

---

## 3. Forms & Validation (`school/forms.py`)

### `SchoolClassForm`
A Django `ModelForm` used to create or edit `SchoolClass` records.

*   **Queryset Overrides:** Inside `__init__`, the dropdown fields `year` and `grade` are restricted to objects where `is_active=True`.
*   **Validation Logic (`clean_section`):** 
    Checks for duplicates in the database prior to saving. The validation logic ensures that the combination of `year`, `grade`, and `section` is unique:
    ```python
    exists = SchoolClass.objects.filter(year=year, grade=grade, section=section).exists()
    if exists:
        raise forms.ValidationError('این نام کلاس قبلاً ثبت شده است')
    ```
    *Developer Note:* The current implementation of `clean_section` retrieves instances via `Grade.objects.get(name=...)` and `AcademicYear.objects.get(title=...)`. In standard Django ModelForms, `self.cleaned_data['grade']` and `self.cleaned_data['year']` already return the model instances themselves.

---

## 4. Views and Controller Logic (`school/views.py`)

### 4.1 `class_list` View (Teacher Portal)
Retrieves class subject entries assigned to the currently authenticated teacher.

*   **Access Control:** Protected by `@login_required`.
*   **Database Optimization:** Uses `select_related` on `'school_class'`, `'school_class__grade'`, `'school_class__year'`, and `'subject'` to minimize SQL execution overhead.
*   **Filtering:** Filters results using `grade` and `subject` URL query parameters.
*   **Context Variables:** Passes current `grades`, `subjects`, and selected filter IDs back to the template to preserve form selection states.

### 4.2 `class_create` View
Renders and processes `SchoolClassForm` to create new classes.
*   Redirects to the class list page upon successful creation.
*   Implements Django's `messages` framework to return success or error notifications to the end user.

### 4.3 `class_update` View
Handles updates to existing `SchoolClass` instances based on primary key lookup (`pk`). Uses `get_object_or_404` for secure operations.

---

## 5. URL Routing (`school/urls.py`)

All paths within this application reside under the `'school'` namespace.

```python
urlpatterns = [
    path('class/create/', views.class_create, name='class_create'),
    path('class/<int:pk>/update/', views.class_update, name='class_update'),
    path('classes/', views.class_list, name='class_list'),
]
```

---

## 6. Frontend Presentation & Styling

The frontend components leverage custom CSS and Django template engines to structure data displays.

### 6.1 `class_list.html`
*   **Grouping Logic:** Uses the Django template tag `{% regroup class_subjects by school_class.grade as grade_list %}`. This groups class items under corresponding grade headers.
*   **Action Triggers:** Displays an action link pointing to `teaching:session_list` (from the sister app `teaching`), allowing teachers to view sessions directly.
*   **Empty States:** Renders contextual illustrations/text when no classes match active search filters or when a teacher has no assignments.

### 6.2 `class_list.css`
Contains targeted layout styling for class groupings.
*   **Grid System:** The class lists are styled via a grid layout (`grid-template-columns: 1fr 3fr 2fr`) separating Class Division, Subject Name, and Action buttons.
*   **Responsiveness:** Implements media queries targeting screens smaller than `768px`. The layout shifts to a single-column block format with stacked elements for touch interfaces.

---

## 7. Django Admin Integration (`school/admin.py`)

The Django administration panel configuration is defined in `school/admin.py`.

*   **Custom Admin Registrations:** `AcademicYear`, `Grade`, `Subject`, `SchoolClass`, and `ClassSubject` are registered using their respective admin customizer classes.
*   **Jalali Date Filtering:** Where appropriate, fields are integrated with `django_jalali.admin` elements.
*   **Editable Lists:** Fields such as `is_active` and `is_current` can be changed directly within list views (`list_editable`).
*   **Search and Filter Setup:** Includes deep lookups such as `school_class__section` and `teacher__username` to aid administration in high-volume environments.