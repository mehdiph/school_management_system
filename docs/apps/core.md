# Core App

## Purpose

The Core app is responsible for the teacher dashboard and serves as the main entry point for teachers after authentication.

Originally, this application was created when the project was intended to be relatively small, which is why the generic name "Core" was chosen.

Its primary purpose is to provide teachers with quick access to the most important educational information and daily activities.

---

## Responsibilities

* Display teacher dashboard
* Show today's classes
* Display assigned classes
* Display recorded teaching sessions
* Provide quick access to educational activities
* Generate educational reports
* Provide an overview of teaching progress

---

## Models

This application does not contain any database models.

The Core app acts as an orchestration layer that aggregates information from multiple applications and presents it through a unified dashboard.

---

## Views

### dashboard

Main teacher dashboard.

#### Responsibilities

* Retrieve the current academic year
* Retrieve active class assignments for the logged-in teacher
* Retrieve today's scheduled classes
* Filter classes based on the current day
* Filter classes based on week rotation rules
* Display teaching-related information
* Provide quick access to frequently used actions

#### Data Sources

The dashboard combines data from:

* AcademicYear
* ClassSubject
* ClassSchedule
* SchoolSession

#### Filtering Logic

Classes are filtered using:

* Logged-in teacher
* Active class assignments
* Active classes
* Current academic year
* Current day of week
* Current week type

Example:

```text
Teacher
↓
Assigned ClassSubjects
↓
Today's Schedule
↓
Week Type Filter
↓
Dashboard Display
```

---

## URL Structure

```text
/core/dashboard/
```

---

## Relationships With Other Apps

### School

Used to retrieve educational structure information.

Models used:

* AcademicYear
* SchoolClass
* ClassSubject

Responsibilities:

* Current academic year detection
* Assigned classes retrieval
* Educational hierarchy

---

### Teaching

Used to retrieve teaching session information.

Models used:

* SchoolSession
* SessionContent

Responsibilities:

* Session history
* Teaching progress
* Educational reports

---

### Scheduling

Used to retrieve schedule information.

Models used:

* ClassSchedule

Responsibilities:

* Daily schedule retrieval
* Week rotation support
* Timetable filtering

---

## Important Business Rules

### Rule 1: Dashboard Must Only Show Active Assignments

Teachers should only see active educational assignments.

Inactive classes, inactive subjects, or inactive assignments must not appear on the dashboard.

This prevents outdated educational data from affecting daily operations.

---

### Rule 2: Dashboard Is Restricted To The Current Academic Year

Only assignments belonging to the currently active academic year should be displayed.

Historical data should be accessed through dedicated reporting pages rather than the dashboard.

This keeps the dashboard focused and relevant.

---

### Rule 3: Daily Schedule Must Respect Week Rotation

The dashboard must respect the scheduling system.

Schedules are filtered according to:

* Current day
* Current week type

Supported week types:

* Week One
* Week Two
* Both Weeks

This ensures teachers only see classes that are actually scheduled for the current day.

---

### Rule 4: Dashboard Should Prioritize Actionable Information

The dashboard is intended to support daily teaching activities.

Information displayed should help teachers answer:

* What classes do I have today?
* What should I teach today?
* Which sessions need to be recorded?
* Which reports should I review?

The dashboard should avoid displaying unnecessary historical data.

---

### Rule 5: Dashboard Must Be Fast

The dashboard is the most frequently visited page in the system.

Queries should be optimized using:

* select_related()
* prefetch_related()

to reduce database load and improve response times.

---

## Common Workflow

### Daily Teacher Workflow

```text
Teacher Login
↓
Dashboard
↓
Today's Classes
↓
Select Class
↓
Teach Session
↓
Record Session
↓
Assign Homework
↓
Review Progress
```

---

### Session Registration Workflow

```text
Teacher Dashboard
↓
Assigned Class
↓
Session List
↓
Create Session
↓
Record Session Content
↓
Add Homework
↓
Save Session
```

---

### Reporting Workflow

```text
Teacher Dashboard
↓
Reports Section
↓
Select Class
↓
Select Date Range
↓
Generate Report
↓
Review Results
```

---

## Future Improvements

### Dashboard Enhancements

* Personalized dashboard widgets
* Teaching statistics
* Weekly progress indicators
* Educational performance summaries

### Notifications

* Upcoming class reminders
* Missing session alerts
* Homework review notifications

### Productivity Tools

* Quick session creation
* Frequently used classes shortcut
* Recently accessed sessions

### Analytics

* Teaching activity charts
* Monthly teaching summaries
* Subject-based statistics
* Classroom performance indicators

### Calendar Integration

* Monthly calendar view
* Upcoming classes overview
* Academic event tracking

### Supervisor Features

Future versions may reuse parts of the dashboard architecture to provide:

* Teaching activity monitoring
* Teacher performance insights
* Educational oversight tools

---

## Notes

The Core app intentionally contains minimal business logic.

Its main responsibility is to aggregate information from multiple applications and present it through a teacher-focused dashboard.

Educational data ownership remains within the dedicated domain applications:

* School
* Teaching
* Scheduling

This approach improves separation of concerns and keeps the dashboard lightweight and maintainable.
