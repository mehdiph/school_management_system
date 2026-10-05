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
