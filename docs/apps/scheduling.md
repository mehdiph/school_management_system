# Scheduling App

## Purpose

The Scheduling app is responsible for managing the weekly timetable of educational assignments.

It provides the temporal structure of the educational system by defining when each class is taught.

The application supports both standard weekly schedules and rotating schedules based on Week One and Week Two patterns.

This module serves as the scheduling foundation for teacher dashboards, student dashboards, and future attendance tracking features.

---

## Responsibilities

* Manage class schedules
* Define teaching time slots
* Support weekly timetables
* Support rotating week schedules
* Prevent schedule conflicts
* Provide scheduling information for dashboards
* Define the temporal structure of educational activities

---

## Models

### ClassSchedule

Represents a scheduled teaching slot for a specific educational assignment.

A schedule belongs to a ClassSubject and determines:

* Day of the week
* Week type
* Start time
* End time

### Main Fields

| Field       | Description             |
| ----------- | ----------------------- |
| class_room  | Associated ClassSubject |
| day_of_week | Teaching day            |
| week_type   | Week rotation type      |
| start_time  | Class start time        |
| end_time    | Class end time          |
| created_at  | Creation timestamp      |

---

### DayChoices

Supported teaching days.

| Value | Day       |
| ----- | --------- |
| 0     | Saturday  |
| 1     | Sunday    |
| 2     | Monday    |
| 3     | Tuesday   |
| 4     | Wednesday |
| 5     | Thursday  |

---

### WeekTypeChoices

Supported scheduling modes.

| Value | Meaning    |
| ----- | ---------- |
| 1     | Week One   |
| 2     | Week Two   |
| 3     | Both Weeks |

---

## Relationships

```text
ClassSubject
↓
ClassSchedule
```

A single ClassSubject may have multiple schedule entries.

Examples:

```text
Grade 4 - Mathematics
↓
Saturday 08:00
Monday 10:00
```

---

## Validation Rules

### Time Validation

End time must always be later than start time.

Invalid example:

```text
08:30 → 08:00
```

Valid example:

```text
08:00 → 08:45
```

---

### Teacher Conflict Detection

The system prevents a teacher from being assigned to overlapping classes.

Example:

```text
Teacher A

Math
Saturday
08:00 - 09:00

Science
Saturday
08:30 - 09:15
```

This configuration is not allowed because the teacher cannot be present in two classes simultaneously.

---

### Week-Aware Conflict Detection

Conflict checking respects week rotation rules.

Examples:

#### Allowed

```text
Math
Saturday
Week One

Science
Saturday
Week Two
```

No conflict exists because the classes occur on different weeks.

---

#### Not Allowed

```text
Math
Saturday
Week One

Science
Saturday
Both Weeks
```

A conflict exists because "Both Weeks" includes Week One.

---

## Views

This application currently does not contain any views.

The Scheduling app acts as a domain module and provides scheduling data to other applications.

Scheduling information is primarily consumed by:

* Core dashboard
* Student dashboard
* Reporting system

---

## URL Structure

This application currently does not expose public URLs.

```text
No URLs Defined
```

---

## Relationships With Other Apps

### School

Uses:

* ClassSubject

Relationship:

```text
ClassSubject
↓
ClassSchedule
```

The scheduling system is built directly on top of the educational assignment structure.

---

### Core

Provides schedule information for:

* Today's classes
* Teacher dashboard
* Daily teaching workflow

---

### Student

Provides schedule information for:

* Student dashboard
* Weekly timetable
* Daily class view

---

### Report

Provides schedule information for future timetable and workload reports.

---

## Important Business Rules

### Rule 1: Every Schedule Must Belong To A ClassSubject

Schedules should never exist independently.

A schedule only makes sense when attached to a specific:

```text
Class
+
Subject
+
Teacher
```

represented by ClassSubject.

---

### Rule 2: Teachers Cannot Have Overlapping Classes

A teacher cannot teach two classes at the same time.

The system automatically validates scheduling conflicts before saving.

This is one of the most important integrity rules in the scheduling system.

---

### Rule 3: Rotating Weeks Are First-Class Citizens

The scheduling system must support schools that use alternating weekly timetables.

Supported patterns:

* Week One
* Week Two
* Both Weeks

This functionality is a core feature and not an optional extension.

---

### Rule 4: Schedules Represent Planned Activities

Schedules define planned teaching activities.

Actual teaching activities are recorded elsewhere.

Relationship:

```text
ClassSchedule
→ Planned Activity

SchoolSession
→ Actual Activity
```

A schedule does not guarantee that a class was actually held.

---

### Rule 5: Scheduling Data Is Shared Across The System

Schedule information is used by multiple modules.

Examples:

* Teacher dashboard
* Student dashboard
* Reporting
* Future attendance tracking

Changes to scheduling logic should be made carefully.

---

## Common Workflow

### Schedule Creation Workflow

```text
Administrator
↓
Select ClassSubject
↓
Select Day
↓
Select Week Type
↓
Select Time Range
↓
Conflict Validation
↓
Schedule Saved
```

---

### Teacher Dashboard Workflow

```text
Teacher Login
↓
Current Day Detection
↓
Current Week Detection
↓
Schedule Filtering
↓
Today's Classes Display
```

---

### Student Dashboard Workflow

```text
Student Login
↓
Student Class Detection
↓
Current Day Detection
↓
Schedule Retrieval
↓
Today's Timetable Display
```

---

### Week Rotation Workflow

```text
Current Date
↓
Week Type Calculation
↓
Schedule Filtering
↓
Week-Specific Classes
```

---

## Future Improvements

### Timetable Features

* Weekly timetable view
* Monthly calendar view
* Academic calendar integration

### Schedule Management

* Drag-and-drop timetable editor
* Bulk schedule creation
* Schedule duplication tools

### Conflict Detection

* Classroom conflict detection
* Grade-level conflict detection
* Resource conflict detection

### Attendance Integration

* Automatic attendance sessions
* Schedule-based attendance tracking

### Notifications

* Upcoming class reminders
* Schedule change notifications
* Teacher alerts

### Advanced Scheduling

* Special event schedules
* Exam schedules
* Temporary timetable overrides
* Holiday-aware scheduling

### Analytics

* Teacher workload analysis
* Classroom utilization reports
* Schedule optimization suggestions

---

## Notes

The Scheduling app provides the temporal layer of the educational system.

While educational content is managed through teaching sessions, scheduling determines when those activities are expected to occur.

The separation between scheduling and teaching activities allows the system to distinguish between planned and actual educational events, improving flexibility and reporting accuracy.
