# Staff App Documentation

The `staff` application handles the database structure and management interface for school employees. It separates general employment records from teacher-specific pedagogical credentials using a layered One-to-One model design.

---

## 1. Architectural Overview

The application organizes employee data into two primary relational tiers:
1.  **General Staff Layer (`Staff`):** Contains administrative, contact, and employment details common to all individuals employed by the school (e.g., administrators, teachers, support staff).
2.  **Specialized Profile Layer (`TeacherProfile`):** Extends the base staff record with academic and professional teaching background details, restricted strictly to users with a teaching role.

Persian (Jalali) dates for employee milestones (birth dates, hire dates) and metadata timestamps are managed via the `django-jalali` library.

---

## 2. Database Models (`staff/models/`)

### 2.1 Staff (`staff.py`)
Stores core identity and employment details for all employees. It links directly to Django's user model.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `user` | `OneToOneField(AUTH_USER_MODEL)` | Unique mapping to the authentication user record. Relates back as `staff_profile`. |
| `personnel_code` | `CharField(max_length=20)` | Unique employee identification code (e.g., "کد پرسنلی"). |
| `national_code` | `CharField(max_length=10)` | Unique national identification number (e.g., "کد ملی"). |
| `gender` | `CharField(choices=Gender)` | Employee gender. Options: `male` ("مرد") or `female` ("زن"). |
| `birth_date` | `jmodels.jDateField` | Employee date of birth (Jalali calendar). Optional. |
| `hire_date` | `jmodels.jDateField` | Employment commencement date (Jalali calendar). |
| `address` | `TextField` | Residential address. Optional. |
| `emergency_phone` | `CharField(max_length=15)` | Primary emergency contact number. Optional. |
| `is_active` | `BooleanField` | Status flag denoting active employment status. Defaults to `True`. |
| `created_at` | `jmodels.jDateTimeField` | Record creation timestamp. |
| `updated_at` | `jmodels.jDateTimeField` | Record modification timestamp. |

*   **Ordering:** Records are ordered alphabetically by the linked user's first name and last name.
*   **String Representation:** Returns the full name of the linked user via `user.get_full_name()`.

---

### 2.2 TeacherProfile (`teacher_profile.py`)
Maintains teaching-specific credentials. This profile is only applicable to staff members who perform active teaching duties.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `staff` | `OneToOneField(Staff)` | One-to-one link to the parent `Staff` record. Relates back as `teacher_profile`. |
| `education` | `CharField(max_length=255)` | Highest educational degree attained (e.g., "مدرک تحصیلی"). Optional. |
| `field_of_study` | `CharField(max_length=255)` | Area of academic specialization (e.g., "رشته تحصیلی"). Optional. |
| `teaching_experience` | `PositiveIntegerField` | Accumulated years of teaching experience. Defaults to `0`. |
| `is_homeroom_teacher` | `BooleanField` | Designates if the teacher acts as a fixed class homeroom teacher ("معلم ثابت"). Defaults to `True`. |
| `created_at` | `jmodels.jDateTimeField` | Record creation timestamp. |
| `updated_at` | `jmodels.jDateTimeField` | Record modification timestamp. |

*   **Role Constraint:** The relational field `staff` is restricted using Django's `limit_choices_to` dictionary:
    ```python
    limit_choices_to={'user__role': 'teacher'}
    ```
    This ensures that only staff members whose linked authentication user account has the role designation of `'teacher'` can have an associated `TeacherProfile` record.
*   **String Representation:** Returns the full name of the teacher through the parent staff and user objects.

---

## 3. Data Flow and Relationships

The diagram below illustrates the hierarchical database relationship from the authentication model down to the teacher's profile:

```
[ Django User Model ] (with 'role' field)
         │
         ▼ (One-to-One via 'staff_profile')
   [ Staff Model ] (General employee data)
         │
         ▼ (One-to-One via 'teacher_profile', limited to user__role='teacher')
[ TeacherProfile Model ] (Credentials and experience)
```

By decoupling these profiles, the system supports other staff roles (such as IT, accountants, or librarians) under the core `Staff` model without requiring empty or irrelevant academic fields on those records.

---

## 4. Administration Interface (`staff/admin.py`)

The Django Admin configuration handles registration and standard tabular configurations for both models.

```python
@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ['user', 'personnel_code', 'national_code', 'emergency_phone']

@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ['staff', 'education', 'teaching_experience']
```

### Admin Configuration Properties
*   **`StaffAdmin`:**
    *   **List Display:** Shows user identity, unique personnel code, national ID code, and primary emergency contact number in the overview list table.
*   **`TeacherProfileAdmin`:**
    *   **List Display:** Highlights the corresponding staff member, their educational qualification level, and their registered teaching experience in years.