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

| Field        | Description                 |
| ------------ | --------------------------- |
| username     | Unique login identifier     |
| role         | User role within the system |
| phone_number | User contact number         |
| avatar       | User profile image          |

### Relationships

```text
User
├── ClassSubject
├── Staff
└── StudentProfile
```

#### User → ClassSubject

A teacher can be assigned to multiple ClassSubjects.

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

Uses the ClassSubject model to associate teachers with educational assignments.

Relationship:

```text
User
↓
ClassSubject
```

---

## Important Business Rules

### Rule 1: Every User Must Have a Role

Every user account must have a defined role.

The role determines:

* Available dashboards
* Available features
* Access permissions

Current roles include:

* Teacher
* Supervisor
* Student

Future roles may include:

* Counselor
* Accountant
* IT Staff
* Administrator

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

Student
↓
Student Dashboard
```

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
