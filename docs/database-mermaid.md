# Database ER Diagram

The school-domain tables and their relations, as Mermaid. Prose descriptions of each model are in [database.md](database.md); the academic calendar's rules are in [apps/academic_calendar.md](apps/academic_calendar.md).

* Dates (`jdate`) are `django_jalali` `jDateField`s: stored in Gregorian, shown in Jalali.
* The website CMS tables (`website` app: site settings, landing page, menus, contact page, contact messages, about page and teachers page) and Django's own tables are left out. The contact, about and teachers tables are described in [database.md](database.md#public-website-contact-page); their links into the school domain are `ContactLocation.branch` → `Branch`, `AboutPerson.staff` → `Staff` and `LandingTeacher.teacher` → `TeacherProfile` (all optional, `SET_NULL`).
* Every table also has an `id` primary key (not repeated below except where it helps).
* The blog's tables (`blog` app) are drawn separately at the end: they link into the domain through `BlogAuthor.user` → `User` and the optional `BlogAuthor.teacher_card` → `LandingTeacher`.

```mermaid
erDiagram
    User ||--o| Staff : "has"
    User ||--o| StudentProfile : "has"
    User ||--o| SupervisorProfile : "has"
    User ||--o{ LoginActivity : "logs in"
    Staff ||--o| TeacherProfile : "is a teacher"
    Staff ||--o{ BranchAccess : "may see"
    Branch ||--o{ BranchAccess : ""

    TeacherProfile ||--o{ TeacherAssignment : "assigned"
    Branch ||--o{ TeacherAssignment : ""
    AcademicYear ||--o{ TeacherAssignment : ""

    AcademicYear ||--o{ SchoolClass : ""
    Grade ||--o{ SchoolClass : ""
    Branch ||--o{ SchoolClass : ""

    SchoolClass ||--o{ ClassSubject : "teaches"
    Subject ||--o{ ClassSubject : ""
    TeacherAssignment ||--o{ ClassSubject : "taught by"

    ClassSubject ||--o{ ClassSchedule : "timetable slots"
    Bell ||--o{ ClassSchedule : ""

    ClassSubject ||--o{ SchoolSession : "sessions"
    Bell |o--o{ SchoolSession : "slot bell"
    CalendarEvent |o--o{ SchoolSession : "cancelled by"
    SchoolSession ||--o| SessionContent : "content"
    SchoolSession ||--o{ SessionAttendance : "archive (before the cutoff)"

    AcademicYear ||--o{ CalendarEvent : ""
    CalendarEvent }o--o{ Branch : "scope: branches (empty = all)"
    CalendarEvent }o--o{ Grade : "scope: grades (empty = all)"
    CalendarEvent }o--o{ Bell : "scope: bells (empty = whole day)"
    User |o--o{ CalendarEvent : "created_by"

    StudentProfile ||--o{ StudentEnrollment : ""
    SchoolClass ||--o{ StudentEnrollment : ""
    AcademicYear ||--o{ StudentEnrollment : ""
    StudentEnrollment ||--o{ SessionAttendance : ""
    SchoolClass ||--o{ DailyAttendanceSheet : "one per day"
    User ||--o{ DailyAttendanceSheet : "taken_by"
    DailyAttendanceSheet ||--o{ DailyAttendance : "records"
    StudentEnrollment ||--o{ DailyAttendance : ""
    User |o--o{ DailyAttendance : "updated_by"

    SupervisorProfile ||--o{ SupervisorClass : "supervises"
    SchoolClass ||--o{ SupervisorClass : ""
    Branch |o--o{ SupervisorProfile : ""
    Grade ||--o{ SupervisorProfile : ""

    User {
        string username UK
        string role "teacher / student / supervisor / admin / director ..."
        string phone_number
        string national_code UK
        bool must_change_password
        image avatar
    }
    LoginActivity {
        int user_id FK
        datetime created_at
        string ip_address
        string browser
        string os
        string session_key
    }
    Staff {
        int user_id FK "one-to-one"
        string personnel_code UK
        string gender
        jdate birth_date
        jdate hire_date
        bool is_active
    }
    BranchAccess {
        int staff_id FK
        int branch_id FK
        bool is_default
    }
    TeacherProfile {
        int staff_id FK "one-to-one"
        string education
        string field_of_study
        int teaching_experience
    }
    TeacherAssignment {
        int teacher_id FK
        int branch_id FK
        int academic_year_id FK
        jdate hire_date
        jdate end_date
        string status "active / transferred / terminated / leave"
    }
    Branch {
        string name UK
        string code UK "used by the calendar Excel import"
        int order
        bool is_active
    }
    AcademicYear {
        string title
        jdate start_date
        jdate end_date
        bool is_current
        bool is_active
    }
    Grade {
        string name
        int level UK
        bool is_active
    }
    Subject {
        string name
        string slug
        string color "#rrggbb"
        bool is_active
    }
    SchoolClass {
        int year_id FK
        int grade_id FK
        int branch_id FK
        string section "unique per branch, year, grade"
        bool is_active
    }
    ClassSubject {
        int school_class_id FK
        int subject_id FK
        int teacher_assignment_id FK
        jdate start_date "teaching window"
        jdate end_date
        bool is_active
    }
    Bell {
        string title
        int order UK
        time start_time
        time end_time
        bool is_active
    }
    ClassSchedule {
        int class_subject_id FK
        int day_of_week "0=Sat .. 4=Wed (5=Thu legacy only)"
        int week_type "1=week one, 2=week two, 3=both"
        int bell_id FK
    }
    CalendarEvent {
        int academic_year_id FK
        string title
        string event_type "official / unplanned"
        jdate start_date
        jdate end_date "check: end >= start"
        text description
        int created_by_id FK "nullable"
        datetime created_at
        datetime updated_at
        bool is_active "soft delete"
    }
    SchoolSession {
        int class_subject_id FK
        jdate date
        int bell_id FK "nullable (legacy rows); unique (class_subject, date, bell)"
        int session_number "nullable: NULL exactly when status = HL; unique per class_subject"
        string status "HD held / CD cancelled / JB compensatory / HL holiday"
        int calendar_event_id FK "nullable: the holiday's reason"
        bool is_auto_created "created by the calendar sync"
        datetime created_at
    }
    SessionContent {
        int session_id FK "one-to-one"
        string title
        text content
        text activity
        text homework
        text notes
    }
    StudentProfile {
        int user_id FK "one-to-one"
        string student_code UK
    }
    StudentEnrollment {
        int student_id FK
        int academic_year_id FK "unique per student"
        int school_class_id FK
        jdate enrollment_date
        string status
    }
    SessionAttendance {
        int session_id FK "never an HL session"
        int student_enrollment_id FK "unique per session"
        string status "present / absent / late"
        text description
        datetime created_at
    }
    DailyAttendanceSheet {
        int school_class_id FK "unique with date"
        jdate date
        int taken_by_id FK
        datetime created_at
    }
    DailyAttendance {
        int sheet_id FK "unique with student_enrollment"
        int student_enrollment_id FK
        string status "present / absent / late / excused"
        text description
        int updated_by_id FK "nullable"
        datetime updated_at
    }
    SupervisorProfile {
        int user_id FK "one-to-one"
        int branch_id FK
        int grade_id FK
    }
    SupervisorClass {
        int supervisor_id FK
        int school_class_id FK "unique per supervisor"
    }
```

## Blog

```mermaid
erDiagram
    User ||--o| BlogAuthor : "may be"
    LandingTeacher |o--o{ BlogAuthor : "optional public card"
    BlogAuthor ||--o{ AuthorSection : "may write in"
    Section ||--o{ AuthorSection : ""
    User |o--o{ AuthorSection : "granted by"
    Section ||--o{ Category : "has"
    Section ||--o{ Post : ""
    Category |o--o{ Post : ""
    BlogAuthor ||--o{ Post : "writes"
    Post }o--o{ Tag : "tagged"
    Post ||--o{ PostImage : "inline images"
    User |o--o{ Post : "reviewed by"

    BlogAuthor {
        int user_id FK "one-to-one, PROTECT"
        string display_name
        string slug "unique"
        int teacher_card_id FK "nullable, SET_NULL"
        bool show_profile
        bool is_active
    }
    AuthorSection {
        int author_id FK "unique with section"
        int section_id FK
        int granted_by_id FK "nullable"
        datetime granted_at
    }
    Section {
        string title
        string slug "unique"
        string paper
        bool is_active
    }
    Category {
        int section_id FK
        string slug "unique per section"
        bool is_active
    }
    Tag {
        string name
        string key "unique"
        string slug "unique"
        bool is_active
    }
    Post {
        int section_id FK "PROTECT"
        int category_id FK "nullable, PROTECT"
        int author_id FK "PROTECT"
        string slug "unique"
        text body "sanitized HTML"
        string status "draft / submitted / published / archived"
        datetime published_at "required when published"
        int reviewed_by_id FK "nullable"
    }
    PostImage {
        int post_id FK "CASCADE"
        string image
        int uploaded_by_id FK "nullable"
    }
```

| Table | Constraint | Meaning |
| --- | --- | --- |
| `Post` | `blog_published_post_has_date` | `status = 'published'` ⇒ `published_at IS NOT NULL` |
| `Category` | `blog_unique_category_slug_per_section` | one slug per section |
| `AuthorSection` | `blog_unique_author_section` | one grant per author and section |

## Academic calendar constraints at a glance

| Table | Constraint | Meaning |
| --- | --- | --- |
| `CalendarEvent` | `calendar_event_end_after_start` | `end_date >= start_date` |
| `SchoolSession` | `unique_session_number_per_class_subject` | numbers are unique per class subject (NULLs never collide) |
| `SchoolSession` | `unique_session_per_slot` | one session per `(class_subject, date, bell)` when `bell` is set |
| `SchoolSession` | `session_number_only_when_counted` | `status = 'HL'` ⇔ `session_number IS NULL` |

## Attendance constraints at a glance

| Table | Constraint | Meaning |
| --- | --- | --- |
| `DailyAttendanceSheet` | `unique_daily_attendance_sheet_per_class_day` | one sheet per `(school_class, date)` |
| `DailyAttendance` | `unique_daily_attendance_per_sheet` | one record per `(sheet, student_enrollment)` |
| `SessionAttendance` | `unique_attendance_per_session` | one record per `(session, student_enrollment)`; table `attendance_attendance` (archive, read-only) |
