# Architecture Decisions

This document records important architectural decisions made during the development of the School Management System.

The purpose of this document is to explain why certain design choices were made and to provide context for future development.

---

# ADR-001: Custom User Model

## Decision

A custom User model was implemented by extending Django's AbstractUser.

## Rationale

The system requires additional user-related information that is not provided by Django's default User model.

Examples:

* User roles
* Phone number
* Future profile extensions

Using a custom User model from the beginning avoids future migration complexity.

## Consequences

Benefits:

* Flexible authentication system
* Easier role management
* Better support for future modules

Trade-offs:

* Increased initial setup complexity

---

# ADR-002: Separation of User and Staff Information

## Decision

Staff-specific information is stored in a separate Staff model instead of the User model.

## Structure

User
→ Staff

## Rationale

Authentication information and personnel information have different responsibilities.

User should only contain:

* Authentication
* Authorization
* Basic identity

Staff should contain:

* Personnel code
* National code
* Employment information
* Contact information

This separation improves maintainability and follows the Single Responsibility Principle.

---

# ADR-003: Dedicated Teacher Profile

## Decision

Teacher-specific information is stored in TeacherProfile.

## Structure

User
→ Staff
→ TeacherProfile

## Rationale

Teachers require additional information that is not relevant to all staff members.

Examples:

* Education
* Field of study
* Teaching experience
* Homeroom teacher status

The architecture is designed to support future profile types:

* CounselorProfile
* AccountantProfile
* SupervisorProfile
* ITProfile

without modifying the Staff model.

---

# ADR-004: Student Profile Separation

## Decision

Student-specific information is stored in StudentProfile.

## Structure

User
→ StudentProfile

## Rationale

Students have different requirements from staff members.

Examples:

* Student code
* Enrollment information
* Class assignment

Keeping student information separate prevents unnecessary complexity in the User model.

---

# ADR-005: ClassSubject as the Core Educational Entity

## Decision

The system introduces a dedicated ClassSubject model.

## Structure

SchoolClass
+
Subject
+
Teacher

↓

ClassSubject

## Rationale

A direct relationship between classes and subjects is insufficient.

The system needs to support:

* Multiple teachers
* Session tracking
* Scheduling
* Reporting

All educational activities are attached to a ClassSubject.

## Consequences

Benefits:

* Clear educational structure
* Easier reporting
* Better scalability

This entity became the central component of the teaching system.

---

# ADR-006: Sessions Belong to ClassSubject

## Decision

Teaching sessions are attached to ClassSubject rather than SchoolClass.

## Structure

ClassSubject
→ SchoolSession

## Rationale

Sessions are related to a specific subject taught by a specific teacher.

Example:

Grade 4-A
Mathematics
Teacher A

must have different sessions from:

Grade 4-A
Science
Teacher B

Attaching sessions directly to SchoolClass would make this distinction impossible.

---

# ADR-007: Session Content Separation

## Decision

Educational content is stored in a dedicated SessionContent model.

## Structure

SchoolSession
→ SessionContent

## Rationale

Session metadata and educational content serve different purposes.

SchoolSession stores:

* Date
* Session number
* Status

SessionContent stores:

* Topic
* Activities
* Homework
* Notes

This separation improves readability and future extensibility.

---

# ADR-008: Weekly Schedule System

## Decision

Class schedules are stored separately in ClassSchedule.

## Structure

ClassSubject
→ ClassSchedule

## Rationale

Schedules represent recurring events while sessions represent actual teaching events.

Separating these concepts avoids duplication and improves data consistency.

---

# ADR-009: Support for Rotational Weeks

## Decision

The scheduling system supports three week types.

## Week Types

1 = Week One

2 = Week Two

3 = Both Weeks

## Rationale

Some schools use rotating schedules where Week One and Week Two differ.

The system must support:

* Fixed schedules
* Alternating schedules

without duplicating schedule records.

---

# ADR-010: Student Schedule Retrieval Through SchoolClass

## Decision

Students are not directly linked to ClassSchedule.

## Structure

Student
→ SchoolClass
→ ClassSubject
→ ClassSchedule

## Rationale

Schedules belong to classes, not individual students.

Creating a direct relationship would introduce redundant data and increase maintenance costs.

This design follows database normalization principles.

---

# ADR-011: Soft Activation Strategy

## Decision

Most educational entities include an is_active field.

## Rationale

Historical educational data should not be deleted.

Examples:

* Classes
* Subjects
* Assignments

can be deactivated while preserving historical records.

---

# ADR-012: Academic Year Isolation

## Decision

SchoolClass records belong to a specific AcademicYear.

## Structure

AcademicYear
→ SchoolClass

## Rationale

Educational data must be separated between academic years.

Benefits:

* Historical reporting
* Easier archiving
* Cleaner data organization

---

# ADR-013: Reports are generated through a shared BaseReportView.

## Reason:
* To guarantee identical business logic between HTML and PDF outputs and avoid duplicated report-generation code.

---

# ADR-014: Supervisor Data Is Scoped Through SupervisorScope

## Decision

Every supervisor query starts from `SupervisorScope` (`supervisor/selectors.py`): the classes assigned through `SupervisorClass` in the supervisor's branch and grade. The training sessions and supervised teachers pages use `supervised_class_subjects()`, the active class subjects of active classes.

## Rationale

* One place defines what a supervisor may see, so a view or template cannot bypass it.
* Filters only narrow an already scoped queryset; user input never widens it.
* Detail and fragment views use `get_object_or_404` on the scoped queryset, so records outside the scope are a 404 and their existence is not leaked.
* Filter options come from the same scope, so a foreign id is just an invalid choice.

---

# ADR-015: HTML Fragments for Progressive Enhancement

## Decision

Panels stay server-rendered (MVT). When JavaScript needs to load content (an expanded timeline row, the session drawer), it fetches the same URL with `?partial=1` and the view renders only the fragment template; without the parameter the view renders a full page that includes that fragment.

## Rationale

* Rendering logic stays in Django templates; there is no JSON API or client-side templating to keep in sync.
* Every enhanced link still works without JS, and can be opened in a new tab or shared.
* A query parameter (rather than a request header) keeps full-page and fragment responses on different URLs, so caches never mix them up.

---

# ADR-016: A Session Is Identified by Class Subject, Date and Bell

## Decision

`SchoolSession` has a nullable `bell` foreign key, and `(class_subject, date, bell)` is unique when the bell is set. It does not point at the `ClassSchedule` row it was recorded for.

## Rationale

* The same subject can be taught at two bells on one day; `(class_subject, date)` cannot tell those two sessions apart.
* Timetable rows are edited, moved and deleted during the year. A foreign key to them would either block those edits (`PROTECT`) or lose the session's slot (`SET_NULL`), while past sessions must stay intact.
* The date already gives the weekday and the rotation week, so date + bell is the slot. Bells are stable and soft-deactivated.

## Consequences

* Sessions recorded before the field existed have no bell. `backfill_session_bells` matches the unambiguous ones (dry run first); the rest count against their day's slots in bell order.
* Two bells of one subject on one day are two expected sessions everywhere (teacher week, supervisor "missing" list, coverage).

---

# ADR-017: Holidays Are Sessions With Their Own Status, From One Calendar Service

## Decision

A slot closed by a `CalendarEvent` gets a `SchoolSession` with the dedicated status `HL` (not `CD`), no session number, a link to the event and `is_auto_created = True`. All holiday logic lives in `academic_calendar.services`; panels only ask it (`Closures`, `get_slots`, `is_working_day`, ...). `SchoolSession.objects.counted()` (`status != HL`) is the single exclusion rule for counts.

## Rationale

* Teacher-entered `CD` sessions are numbered and counted; mixing the two would turn every count into a two-column condition that one query would eventually forget.
* A row per closed slot shows the reason wherever sessions are listed, without each page re-deriving the calendar.
* `is_auto_created` keeps cleanup away from anything a person created; held sessions found in closed slots are reported as conflicts, never overwritten.
* One service keeps the teacher page, the session form and the supervisor pages from ever disagreeing about a closure.

## Consequences

* Every write that can change which slots are closed (event save/deactivate/import, timetable and class subject changes) must re-sync; the admin, the import and `academic_calendar.signals` do.
* The sync is idempotent and can be re-run any time (`sync_calendar_sessions`).

---

# ADR-018: Session Numbers Follow Teaching Order

## Decision

Counted sessions of a class subject are renumbered 1..N in teaching order (date, then bell) on every save and delete, under a row lock on the class subject, in two phases so the unique `(class_subject, session_number)` constraint holds after each statement.

## Rationale

* Teachers record missed sessions from earlier days (the weekly schedule makes past slots clickable); refusing them, or numbering them out of order, would make numbers meaningless.
* Holidays take no number, so numbering stays continuous.

## Consequences

* A session number shown in the past can change when an earlier session is recorded or one is removed. Anything that needs a stable reference uses the session's id, not its number.

---

# Future Architectural Directions

Planned modules:

* Attendance Tracking
* Assessment Management
* Parent Portal
* Notification System
* Messaging System
* Financial Management
* School Analytics
* Curriculum Plan (بودجه‌بندی): planned lessons per subject, grade and year, so supervisors can compare recorded sessions with the plan automatically (proposal in `docs/apps/supervisor.md`)

Future development should follow the same principles:

* Separation of concerns
* Explicit relationships
* Reusable domain entities
* Normalized database design
