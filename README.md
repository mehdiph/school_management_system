# School Management System

A Django-based School Management System designed to streamline teaching activities, classroom management, academic scheduling, and student learning tracking.

The project focuses on providing a centralized platform for teachers, supervisors, and students to manage educational activities efficiently.

---

# Features

## Teacher Portal

* View assigned classes
* Record teaching sessions
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

* Monitor teaching activities
* Review recorded sessions
* Track class progress
* Generate educational reports

## Scheduling System

* Weekly schedules
* Support for Week 1 and Week 2 rotation schedules
* Daily timetable management
* Teacher and class schedule tracking

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

* database.md
* architecture-decisions.md
* changelog.md
* apps/*.md

---

# License

This project is intended for educational and school management purposes.
