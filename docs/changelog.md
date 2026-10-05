# [0.1.0] - 2026-02-07

## Added

### Teacher Dashboard

- Each day schedule
- Submit sessions
- Get Report from sessions

# [0.2.0] - 2026-06-07

### Student Dashboard

- Weekly schedule page
- Subject-based session history
- Homework overview

### Documentation

- README
- Database documentation
- Architecture decisions document

# [Unreleased]

## Added

### Supervisor Panel

- Training sessions page (جلسات آموزشی): sessions per teacher, subject and class, with GET filters (academic year, teacher, subject, class, Jalali date range with week / month / year shortcuts, status), KPI cards, sorting, pagination and progress against the weekly timetable
- Session timeline per class subject, expandable in the table or as its own page, marking sessions without content and long gaps
- Session detail in a drawer or as its own page, with content, homework, activity, notes and attendance counts
- Supervised teachers page (معلمان من): cards or table, search, subject / year filters, sorting, session statistics and an inactivity marker, linking to the teacher's sessions
- Database index on `SchoolSession(class_subject, date)`

## Changed

- Supervisor pages redirect logged-out users to the login page instead of returning 403

### Documentation

- `docs/apps/supervisor.md`, ADR-014 and ADR-015
