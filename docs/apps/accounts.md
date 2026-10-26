# Accounts App

## Purpose

The Accounts app is responsible for authentication and user management.

This app was intentionally separated from profile-related applications to keep authentication logic independent from business-specific user information.

The goal is to provide a centralized authentication system while allowing other applications to extend user information through dedicated profile models.

---

## Responsibilities

* User authentication
* User login and logout
* User role management
* User identity management
* Access control foundation
* User account extension support

---

## Models

### User

The custom user model used throughout the system.

It extends Django's authentication system and serves as the central identity entity for all users.

### Main Fields

| Field                | Description                 |
| -------------------- | --------------------------- |
| username             | Unique login identifier     |
| role                 | User role within the system (`User.Roles`) |
| phone_number         | User contact number         |
| national_code        | National code, unique; the single copy (Staff no longer has one). Null only for legacy and superuser accounts |
| must_change_password | Set for accounts created with a known password (the Excel import); `ForcePasswordChangeMiddleware` sends the user to change it first |
| avatar               | User profile image (never shown on the public site, ADR-025) |

### Relationships

```text
User
├── Staff ── TeacherProfile ── TeacherAssignment ── ClassSubject
├── StudentProfile
├── SupervisorProfile
└── BlogAuthor (blog app)
```

#### User → ClassSubject (indirect)

A user never links to a ClassSubject directly: a teacher's `Staff` row has a
`TeacherProfile`, whose `TeacherAssignment`s (one per branch and year) carry the
ClassSubjects they teach.

#### User → Staff

A staff member profile extends a User account.

#### User → StudentProfile

A student profile extends a User account.

---

## Views

### login_form

Displays and processes the login form.

#### Responsibilities

* Display login page
* Validate submitted credentials
* Authenticate registered users
* Redirect users based on their role
* Start authenticated sessions

#### User Flow

```text
User
↓
Login Form
↓
Authentication
↓
Role Detection
↓
Dashboard Redirect
```

---

### auth_logout

Logs the user out of the system.

#### Responsibilities

* Terminate user session
* Remove authentication data
* Redirect to login page

---

## URL Structure

```text
/auth/login/
/auth/logout/
```

---

## Relationships With Other Apps

### Staff

Uses the Staff model to store personnel information.

Relationship:

```text
User
↓
Staff
```

---

### Student

Uses the StudentProfile model to store student-specific information.

Relationship:

```text
User
↓
StudentProfile
```

---

### School

ClassSubject associates teachers with what they teach, through their staff record.

Relationship:

```text
User
↓
Staff → TeacherProfile → TeacherAssignment
↓
ClassSubject
```

---

### Blog

A `BlogAuthor` row (one per user, created by the website admin) lets a person write in
the school blog (ADR-026, `docs/apps/blog.md`). Being an author is a grant on top of a
role, not a role.

---

## Important Business Rules

### Rule 1: Every User Must Have a Role

Every user account must have a defined role.

The role determines:

* Available dashboards
* Available features
* Access permissions

Current roles (`User.Roles`):

* Teacher (`teacher`)
* Supervisor (`supervisor`, «پشتیبان» / grade supporter): oversees the classes assigned through `SupervisorClass` (one grade, one branch) and, since 1 Aban 1405, takes their **daily attendance** (`docs/apps/attendance.md`). Teachers no longer take attendance.
* Student (`student`)
* School director (`director`, «مدیر مدرسه»): one person who oversees both branches through the read-only director panel (`docs/apps/director.md`). No profile row: the role alone gives access.
* System admin (`admin`, «مدیر سامانه»): enters and edits the data in the Django admin. Relabelled from «مدیر» in October 2026 so it cannot be confused with the director.
* Accountant, counselor, IT and services staff: roles exist, no panel of their own yet. A counselor who is a blog author writes in «نوشته‌های من» (`/blog/write/`), in the `base.html` shell with only that sidebar item.

To make someone the director: in the Django admin, open the user (or add one) and set «نقش» to «مدیر مدرسه». No staff flag, group or permission is needed; do not make them staff unless they also administer data.

---

### Rule 2: Authentication Data Must Remain Separate

Authentication information must remain inside the Accounts app.

Profile-specific information must not be stored directly in the User model.

Examples:

Store in User:

* Username
* Password
* Role
* Phone Number

Store in Profile Models:

* Personnel Code
* Student Code
* Education Information
* Employment Information

---

### Rule 3: Dashboard Access Is Role-Based

After successful authentication, users must be redirected according to their role.

Examples:

```text
Teacher
↓
Teacher Dashboard

Supervisor
↓
Supervisor Dashboard

Director
↓
Director Panel (/director/: today's attendance)

Student
↓
Student Dashboard
```

Roles without a dashboard (`accounts.utils.role_dashboard`): staff users go to the
Django admin; otherwise a user who can write in the blog goes to «نوشته‌های من»
(`blog:write`, blog plan D7); everyone else to the public home page.

---

### Rule 4: User Is the Single Source of Identity

All system users must originate from the User model.

Neither Staff nor StudentProfile should be used for authentication.

Authentication always happens through User.

---

## Common Workflow

### Teacher Login Workflow

```text
Teacher
↓
Login Page
↓
Authentication
↓
Role Verification
↓
Teacher Dashboard
↓
Teaching Activities
```

---

### Student Login Workflow

```text
Student
↓
Login Page
↓
Authentication
↓
Role Verification
↓
Student Dashboard
↓
Homework & Schedule Access
```

---

### Supervisor Login Workflow

```text
Supervisor
↓
Login Page
↓
Authentication
↓
Role Verification
↓
Supervisor Dashboard
↓
Monitoring Activities
```

---

## Future Improvements

### Authentication

* Password reset functionality
* Email verification
* Two-factor authentication (2FA)
* Login activity tracking

### User Management

* User registration form
* User profile settings
* Avatar upload management
* Account activation workflow

### Security

* Login attempt limiting
* Suspicious activity detection
* Session management dashboard

### Role Management

* Permission groups
* Fine-grained access control
* Dynamic role assignment

### Administration

* User audit logs
* Account status management
* Bulk user import/export

---

## Notes

The Accounts app is intentionally kept lightweight.

Its primary responsibility is identity and authentication management.

Business-specific information should always be implemented in dedicated profile applications such as:

* Staff
* Student

This approach improves maintainability, scalability, and separation of concerns.
