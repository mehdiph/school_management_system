# Report App

## Purpose

The Report app is responsible for generating educational reports for teachers.

It provides both web-based and PDF-based reports that help teachers review teaching activities, session history, and educational progress across classes and grades.

The application is designed around a reusable reporting architecture where different report types share a common PDF and HTML rendering mechanism.

---

## Responsibilities

* Generate class-based reports
* Generate grade-based reports
* Display educational reports in HTML format
* Export reports as PDF documents
* Aggregate teaching session information
* Provide educational progress visibility
* Support academic-year-based reporting

---

## Models

This application does not contain any database models.

The Report app is a service-oriented application that retrieves data from other educational modules and transforms it into human-readable reports.

---

## Views

### BaseReportView

Base view responsible for rendering reports.

This view provides a common reporting mechanism used by all report implementations.

#### Responsibilities

* Generate HTML reports
* Generate PDF reports
* Load report templates
* Render report context
* Convert HTML reports to PDF documents

#### Output Modes

##### HTML Mode

When the request does not contain:

```text
?format=pdf
```

the report is rendered as a standard web page.

##### PDF Mode

When the request contains:

```text
?format=pdf
```

the report is rendered as a PDF document.

#### Purpose

The main purpose of this class is to eliminate duplicate reporting logic and provide a reusable reporting foundation.

---

### ReportsView

Main educational reporting view.

This view generates educational reports based on user-selected filters.

#### Responsibilities

* Process report filters
* Retrieve academic year data
* Retrieve class data
* Retrieve teaching session data
* Generate class-level reports
* Generate grade-level reports
* Produce HTML output
* Produce PDF output

#### Supported Report Types

### Class Report

Displays detailed teaching information for a specific class.

Information may include:

* Subjects
* Teachers
* Sessions
* Teaching content
* Homework
* Session dates

#### Example

```text
Grade 4 - Class A

Mathematics
Session 1
Session 2
Session 3

Science
Session 1
Session 2
```

---

### Grade Report

Displays a summarized educational view across all classes within a grade.

Information may include:

* Number of classes
* Number of sessions
* Subject coverage
* Educational activity overview

#### Example

```text
Grade 4

Class A
12 Sessions

Class B
14 Sessions

Class C
10 Sessions
```

---

## URL Structure

```text
/report/all/
```

---

## Relationships With Other Apps

### School

Used for retrieving academic structure information.

Models used:

* AcademicYear
* Grade
* SchoolClass
* ClassSubject

Responsibilities:

* Academic year filtering
* Grade filtering
* Class filtering

---

### Teaching

Used for retrieving teaching activities.

Models used:

* SchoolSession
* SessionContent

Responsibilities:

* Session retrieval
* Teaching content retrieval
* Homework retrieval
* Educational progress reporting

---

## Important Business Rules

### Rule 1: Reports Must Be Academic-Year Aware

All reports should be generated within the context of a selected academic year.

Educational data from different academic years must not be mixed.

This ensures reporting accuracy and historical consistency.

---

### Rule 2: Reports Are Read-Only

The reporting system must never modify educational data.

Reports should only:

* Read data
* Aggregate data
* Present data

All educational modifications must occur through dedicated operational modules.

---

### Rule 3: PDF and HTML Must Share The Same Data Source

HTML reports and PDF reports must be generated from the same dataset.

This guarantees consistency between on-screen reports and exported documents.

Example:

```text
HTML Report
=
PDF Report
```

Only the presentation format should differ.

---

### Rule 4: Class Reports Are Detailed

Class reports should provide detailed educational information.

Examples:

* Session dates
* Lesson topics
* Activities
* Homework

Class reports are intended for operational review and teaching analysis.

---

### Rule 5: Grade Reports Are Aggregated

Grade reports should focus on educational summaries rather than individual session details.

The purpose is to provide a broader educational overview.

---

### Rule 6: Reports Must Respect User Permissions

Teachers should only access reports related to their own assigned classes.

Future supervisor and administrator reports may have broader visibility.

---

## Common Workflow

### Class Report Workflow

```text
Teacher
↓
Open Reports Page
↓
Select Academic Year
↓
Select Grade
↓
Select Class
↓
Generate Report
↓
Review Results
↓
Export PDF (Optional)
```

---

### Grade Report Workflow

```text
Teacher
↓
Open Reports Page
↓
Select Academic Year
↓
Select Grade
↓
Generate Grade Report
↓
Review Educational Summary
↓
Export PDF (Optional)
```

---

### PDF Export Workflow

```text
Report Request
↓
Data Collection
↓
Template Rendering
↓
HTML Generation
↓
PDF Conversion
↓
Download PDF
```

---

## Future Improvements

### Reporting Features

* Subject-based reports
* Teacher performance reports
* Student progress reports
* Academic activity summaries

### Advanced Filters

* Date range filtering
* Subject filtering
* Teacher filtering
* Session status filtering

### Analytics

* Teaching activity charts
* Monthly statistics
* Subject coverage analysis
* Teaching workload analysis

### Export Options

* Excel export
* CSV export
* Printable reports
* Scheduled report generation

### Supervisor Reports

Future versions may include:

* Teacher monitoring reports
* Classroom activity reports
* Academic performance dashboards

### School-Wide Reports

* Annual educational reports
* Grade comparison reports
* Curriculum coverage reports

---

## Notes

The Report app follows a service-oriented design.

It owns no educational data itself and instead consumes data from educational modules to generate meaningful reports.

The BaseReportView acts as the foundation of the reporting architecture and ensures consistent behavior across all report types.

Future reporting features should extend the existing reporting framework rather than implementing separate reporting mechanisms.
