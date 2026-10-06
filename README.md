# School Management System

A Django-based School Management System designed to streamline teaching activities, classroom management, academic scheduling, and student learning tracking.

The project focuses on providing a centralized platform for teachers, supervisors, students and the school director to manage educational activities efficiently.

---

# Features

## Teacher Portal

* View assigned classes
* Record teaching sessions (one per subject, date and bell)
* Weekly schedule by dated week: click a lesson to record that session; future, already-recorded and holiday slots say why they cannot be recorded
* Register session content
* Add homework assignments
* View teaching history
* Access class schedules
* Generate teaching reports

## Student Portal

* View today's and tomorrow's schedule in dashboard
* View last 5 homework in dashboard
* View weekly timetable
* Review recently taught topics
* Check homework assignments
* View school announcements

## Supervisor Portal

* Dashboard of the supervised classes and a "needs attention" list
* Per-class attendance review
* Training sessions: sessions recorded per teacher, subject and class, with filters, KPIs, progress against the weekly timetable (the same execution rate the director sees), a session timeline and session details
* Supervised teachers: each teacher's subjects, classes and session-recording activity, as cards or a table
* Everything is limited to the classes assigned to the supervisor

## Director Portal

* Read-only analytics for the school director («مدیر مدرسه») over both branches, with branch / grade filters and date presets on every page
* Dashboard: key figures with the change vs the previous period, the branches side by side, the academic calendar at a glance, and alerts (low attendance, unregistered lessons, missing attendance, calendar conflicts)
* Program execution: lessons the timetable expected vs held, cancelled and unregistered, drill-down to each class and subject, per teacher, and the same subject across classes
* Attendance: daily trend (holidays marked), comparison by branch, grade and class, students with the most absences
* Every metric is defined once in the `analytics` app, so the director and the supervisors see the same numbers
* Details: [docs/apps/director.md](docs/apps/director.md), [docs/apps/analytics.md](docs/apps/analytics.md)

## Scheduling System

* Weekly schedules
* Support for Week 1 and Week 2 rotation schedules
* Daily timetable management
* Teacher and class schedule tracking

## Academic Calendar

* Official holidays and unplanned closures (snow, air pollution), per branch, grade and bell
* Closed lessons become «تعطیل» sessions automatically: shown in every panel with their reason, never numbered or counted
* Quick closure form, conflicts page and Excel bulk import for the system admin
* Thursday and Friday are always non-working days
* Details: [docs/apps/academic_calendar.md](docs/apps/academic_calendar.md)

## Reporting System

* Class-based teaching reports
* Grade-based teaching reports
* PDF export support

---

# Core Domain Model

The educational structure is built around the `ClassSubject` entity.

A `ClassSubject` represents:

* A Class
* A Subject
* A Teacher

Example:

Grade 4 - Class A
+
Mathematics
+
Mr. Ahmadi

All teaching sessions, schedules, and reports are attached to a ClassSubject.

---

# User Roles

Current roles:

* Teacher
* Supervisor
* Student

The architecture is designed to support future roles such as:

* Counselor
* Accountant
* IT Staff
* Administrative Staff

---

# Main Applications

## Accounts

Responsible for:

* Authentication
* User management
* Role management

## Staff

Responsible for:

* Staff profiles
* Teacher profiles
* Personnel information

## School

Responsible for:

* Academic years
* Grades
* Classes
* Subjects
* Class assignments

## Teaching

Responsible for:

* Teaching sessions
* Session contents
* Homework management
* Teaching reports

## Schedule

Responsible for:

* Weekly schedules
* Rotational schedules
* Timetable management

## Student

Responsible for:

* Student profiles
* Student dashboard
* Academic information

## Supervisor

Responsible for:

* Supervisor profiles and their assigned classes
* Supervisor dashboard and attendance review
* Training sessions and supervised teachers pages
* Scoping every supervisor query to the assigned classes

---

# Technology Stack

* Python
* Django
* PostgreSQL
* HTML
* CSS
* JavaScript

---

# Project Status

The project is currently under active development.

Implemented modules:

* User Management
* Staff Management
* Teacher Profiles
* Academic Structure
* Session Management
* Teaching Reports
* Scheduling System
* Student Dashboard
* Supervisor Panel

Planned modules:

* Attendance Tracking
* Assessment Management
* Messaging System
* Parent Portal
* Advanced Analytics

---

# Documentation

Additional documentation can be found in the `docs/` directory.

Recommended documents:

* database.md and database-mermaid.md (ER diagram)
* architecture-decisions.md
* apps/academic_calendar.md (holidays, closures, the clickable weekly schedule)
* apps/analytics.md (every metric definition: expected slots, execution, attendance, content)
* apps/director.md (the director panel: pages, filters, alerts, access, performance)
* plans/director-dashboard-phase1.md (the director dashboard: final Phase 1 report, decisions and follow-ups)
* plans/director-dashboard.md (the director dashboard: plan and first implementation round)
* changelog.md
* apps/*.md

---

# License

This project is intended for educational and school management purposes.
