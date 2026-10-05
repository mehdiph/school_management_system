# Database Documentation

## Overview

The database is designed around the educational workflow of a school management system.

The core educational entity is **ClassSubject**, which represents the relationship between a school class, a subject, and a teacher. Teaching sessions, schedules, and reports are built on top of this entity.

### Main Domains

The database is divided into the following domains:

* User Management
* Staff Management
* Student Management
* Academic Structure
* Scheduling
* Teaching Sessions
* Academic Calendar

The full entity relationship diagram (Mermaid) is in [database-mermaid.md](database-mermaid.md).

---

# Entity Relationship Overview

```text
AcademicYear
    └── SchoolClass
            ├── StudentProfile
            └── ClassSubject
                    ├── ClassSchedule ── Bell
                    └── SchoolSession ── Bell (slot), CalendarEvent (holiday reason)
                            └── SessionContent

AcademicYear
    └── CalendarEvent ── Branches / Grades / Bells (scope; empty = all)

User
 ├── Staff
 │      └── TeacherProfile
 │
 └── StudentProfile
```

---

# User Management

## User

Represents all authenticated users in the system.

### Purpose

Provides authentication and authorization capabilities.

### Key Fields

| Field        | Description             |
| ------------ | ----------------------- |
| username     | Unique login identifier |
| email        | User email              |
| role         | System role             |
| phone_number | Contact number          |

### Relationships

* One User may have one Staff profile.
* One User may have one Student profile.
* One User may teach multiple ClassSubjects.

---

# Staff Management

## Staff

Stores general personnel information.

### Purpose

Acts as the base profile for all school employees.

### Key Fields

| Field          | Description                    |
| -------------- | ------------------------------ |
| personnel_code | Internal personnel identifier  |
| national_code  | National identification number |
| hire_date      | Employment start date          |
| gender         | Personnel gender               |

### Relationships

* One-to-One with User.
* One-to-One with TeacherProfile.

---

## TeacherProfile

Stores teacher-specific information.

### Purpose

Extends Staff with educational and teaching details.

### Key Fields

| Field               | Description           |
| ------------------- | --------------------- |
| education           | Highest degree        |
| field_of_study      | Academic major        |
| teaching_experience | Years of experience   |
| is_homeroom_teacher | Homeroom teacher flag |

### Relationships

* One-to-One with Staff.

---

# Academic Structure

## AcademicYear

Represents a school academic year.

### Purpose

Allows separation of data between different school years.

### Key Fields

| Field      | Description         |
| ---------- | ------------------- |
| title      | Academic year title |
| start_date | Start date          |
| end_date   | End date            |
| is_current | Current active year |

### Relationships

* One AcademicYear contains many SchoolClasses.

---

## Grade

Represents a school grade level.

### Examples

* Grade 1
* Grade 2
* Grade 3

### Key Fields

| Field | Description |
| ----- | ----------- |
| name  | Grade name  |
| level | Grade order |

### Relationships

* One Grade contains many SchoolClasses.

---

## SchoolClass

Represents an actual classroom.

### Examples

* Grade 4 - A
* Grade 5 - B

### Key Fields

| Field   | Description   |
| ------- | ------------- |
| section | Class section |
| year    | Academic year |
| grade   | Grade         |

### Relationships

* Belongs to one Grade.
* Belongs to one AcademicYear.
* Contains many Students.
* Contains many ClassSubjects.

---

## Subject

Represents school subjects.

### Examples

* Mathematics
* Science
* Computer Studies

### Key Fields

| Field | Description             |
| ----- | ----------------------- |
| name  | Subject name            |
| slug  | URL-friendly identifier |

### Relationships

* One Subject may be assigned to many ClassSubjects.

---

## ClassSubject

### Core Entity

This is the most important educational entity in the system.

Represents:

```text
School Class
+
Subject
+
Teacher
```

### Example

```text
Grade 4 - A
+
Mathematics
+
Mr. Ahmadi
```

### Purpose

Provides a central entity for:

* Scheduling
* Teaching sessions
* Reporting
* Student tracking

### Relationships

* Belongs to one SchoolClass.
* Belongs to one Subject.
* Belongs to one Teacher (User).
* Has many SchoolSessions.
* Has many ClassSchedules.

---

# Scheduling

## ClassSchedule

Stores weekly timetable information.

### Purpose

Defines when a ClassSubject is taught.

### Key Fields

| Field       | Description  |
| ----------- | ------------ |
| day_of_week | Teaching day |
| start_time  | Start time   |
| end_time    | End time     |
| week_type   | Week pattern |

### Week Types

| Value | Meaning    |
| ----- | ---------- |
| 1     | Week One   |
| 2     | Week Two   |
| 3     | Both Weeks |

### Relationships

* Belongs to one ClassSubject.

---

# Teaching Sessions

## SchoolSession

Represents a teaching session.

### Purpose

Stores each lesson of a ClassSubject in one **slot**: a date and a bell. The same subject can be taught twice on one day (two bells), and each is its own session.

### Key Fields

| Field           | Description |
| --------------- | ----------- |
| date            | Session date |
| bell            | The slot's bell (nullable: only sessions recorded before the field existed have none; see `backfill_session_bells`) |
| session_number  | Number in teaching order (date, then bell); NULL for holidays |
| status          | Session status |
| calendar_event  | For a holiday: the CalendarEvent that closed the slot |
| is_auto_created | Created by the calendar sync, not by a teacher |

### Status Values

| Value | Meaning      |
| ----- | ------------ |
| HD    | Held         |
| JB    | Compensatory |
| CD    | Cancelled    |
| HL    | Holiday (تعطیل): created by the academic calendar, never numbered or counted |

### Relationships

* Belongs to one ClassSubject.
* Belongs to one Bell (optional).
* Belongs to one CalendarEvent (holidays only).
* Has one SessionContent.

### Constraints and Indexes

* `session_number` is unique per ClassSubject (NULLs never collide).
* `unique_session_per_slot`: one session per `(class_subject, date, bell)` when the bell is set.
* `session_number_only_when_counted` (check): `status = 'HL'` if and only if `session_number` is NULL.
* Index `school_session_cs_date_idx` on `(class_subject, date)`: the supervisor pages read one ClassSubject's sessions in a date range and its first/last session date, which the unique constraint (`class_subject, session_number`) does not cover.

### Numbering

Counted sessions are renumbered 1..N in teaching order on every save/delete, so recording a missed past session shifts the later numbers. Use `SchoolSession.objects.counted()` for anything that counts sessions. See [apps/academic_calendar.md](apps/academic_calendar.md).

---

# Academic Calendar

## CalendarEvent

A closure of (part of) the school: an official holiday or an unplanned closure.

### Key Fields

| Field        | Description |
| ------------ | ----------- |
| academic_year | The year it belongs to |
| title        | Shown as the reason everywhere |
| event_type   | `official` (تعطیل رسمی) / `unplanned` (تعطیلی غیرمنتظره) |
| start_date, end_date | Range (Thursday/Friday inside it have no effect) |
| branches, grades, bells | Scope; empty = all (bells empty = the whole day) |
| created_by   | The admin who entered it |
| is_active    | Soft delete: events are never deleted |

### Relationships

* Belongs to one AcademicYear.
* Many-to-many with Branch, Grade and Bell (scope).
* Has many holiday SchoolSessions (`sessions`).

### Constraints

* `calendar_event_end_after_start`: `end_date >= start_date`.
* Index `calendar_event_range_idx` on `(academic_year, is_active, start_date, end_date)`.

Rules, sync and admin: [apps/academic_calendar.md](apps/academic_calendar.md).

---

## SessionContent

Stores educational content of a session.

### Purpose

Records what happened during a lesson.

### Key Fields

| Field    | Description          |
| -------- | -------------------- |
| title    | Session title        |
| content  | Teaching content     |
| activity | Classroom activities |
| homework | Assigned homework    |
| notes    | Additional notes     |

### Relationships

* One-to-One with SchoolSession.

---

# Student Management

## StudentProfile

Stores student-specific information.

### Purpose

Extends User with educational data.

### Key Fields

| Field           | Description        |
| --------------- | ------------------ |
| student_code    | Student identifier |
| enrollment_date | Enrollment date    |
| status          | Student status     |

### Relationships

* One-to-One with User.
* Belongs to one SchoolClass.

---

# Supervision

## SupervisorProfile

Represents a supervisor (پشتیبان).

### Key Fields

| Field  | Description                          |
| ------ | ------------------------------------ |
| user   | One-to-one with User                 |
| branch | Branch the supervisor works in       |
| grade  | Grade the supervisor oversees        |

## SupervisorClass

Assigns a SchoolClass to a supervisor.

### Rules

* Unique per supervisor and class.
* The class must belong to the supervisor's grade and branch.

### Relationships

* Belongs to one SupervisorProfile.
* Belongs to one SchoolClass.
* Defines everything a supervisor may see (see `docs/apps/supervisor.md`).

---

# Design Decisions

## Why ClassSubject Exists

Instead of directly connecting:

```text
SchoolClass → Subject
```

the system introduces:

```text
SchoolClass → ClassSubject ← Teacher
```

This allows:

* Multiple teachers per grade
* Independent schedules
* Session tracking
* Subject-level reporting

---

## Why SessionContent Is Separate

Session metadata and educational content are separated.

```text
SchoolSession
    ↓
SessionContent
```

Benefits:

* Cleaner design
* Easier future extensions
* Better reporting capabilities

---

# Future Expansion

The database architecture is designed to support future modules:

* Attendance Tracking
* Student Assessment
* Parent Portal
* Messaging System
* Financial Management
* School Announcements
* Advanced Analytics


