"""
Page data of the director panel.

Every number here comes from ``analytics`` (``engine.compute`` +
``metrics``): this module only decides *which* scope, window and grouping
a page shows, and turns the results into rows for the templates. Views
call one function per page and run no query of their own.

Bounded queries: each page loads its dimension tables once (current year,
branches, grades), the year's calendar events once (``Closures``), runs
the engine once over the union of the windows it needs (current range,
previous period, alert window) and adds a fixed number of aggregate
queries -- whatever the number of classes, sessions or records.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from academic_calendar import services as calendar
from analytics import engine, metrics, periods
from analytics.definitions import ABSENT, DELIVERED_STATUSES, LATE, rate, rounded
from analytics.scope import AnalyticsScope
from core.templatetags.jalali_tags import MONTHS, fa_digits, format_jalali
from attendance.models import Attendance
from school.models import AcademicYear, Branch, ClassSubject, Grade, SchoolClass
from staff.models import TeacherAssignment
from student.models.student_enrollment import StudentEnrollment

from .forms import custom_range_query

#: Alert thresholds: read from settings each time (so they can be
#: changed, and overridden in tests), with these defaults.
ALERT_DEFAULTS = {
    "DIRECTOR_ALERT_ATTENDANCE_RATE": 85,        # %, classes under it are listed
    "DIRECTOR_ALERT_UNREGISTERED_SLOTS": 3,      # teachers with at least this many
    "DIRECTOR_ALERT_WINDOW_TEACHING_DAYS": 7,    # both of the above look this far back
    "DIRECTOR_ALERT_ATTENDANCE_GRACE_DAYS": 1,   # held sessions older than this without attendance
}

#: How many items an alert card lists (the rest is behind its link).
ALERT_ITEMS = 5

#: The same-subject comparison marks a class this many held sessions (or
#: more) behind the class of its grade that held the most.
SUBJECT_GAP_WARNING = 2

TOP_ABSENTEES = 20
MISSING_ATTENDANCE_ITEMS = 50
UPCOMING_CLOSURE_DAYS = 30


def threshold(name):
    return getattr(settings, name, ALERT_DEFAULTS[name])


# ----------------------------------------------------------------------
# Dimensions
# ----------------------------------------------------------------------

@dataclass
class Dimensions:
    """What every page needs before it can read its filters (three queries)."""

    year: object
    branches: list
    grades: list

    @classmethod
    def load(cls):
        return cls(
            year=AcademicYear.objects.filter(is_current=True).order_by("-start_date").first(),
            branches=list(Branch.objects.filter(is_active=True).order_by("order", "id")),
            grades=list(Grade.objects.filter(is_active=True).order_by("level", "id")),
        )


def class_label(school_class):
    """"هفتم ۲": grade and section, in Persian digits (sections are often numbers)."""

    return fa_digits(f"{school_class.grade.name} {school_class.section}")


def teacher_name(teacher):
    user = teacher.staff.user
    return user.get_full_name() or user.username


def _units(dims, filters):
    branch_ids = [filters.branch.pk] if filters.branch else [b.pk for b in dims.branches]
    grade_ids = [filters.grade.pk] if filters.grade else [g.pk for g in dims.grades]
    return periods.units(filters.year, branch_ids, grade_ids)


def _closures(year):
    """The year's active events, loaded once per page."""

    return calendar.Closures.between(year.start_date, year.end_date, academic_year=year)


def _in_branch(branch):
    if branch is None:
        return None
    return lambda cs: cs.school_class.branch_id == branch.pk


def _in_scope(filters):
    """Class subjects in the filters' branch and grade."""

    def accept(cs):
        if filters.branch is not None and cs.school_class.branch_id != filters.branch.pk:
            return False
        if filters.grade is not None and cs.school_class.grade_id != filters.grade.pk:
            return False
        return True

    return accept


# ----------------------------------------------------------------------
# Head counts (students, classes, teachers): no history, no comparison
# ----------------------------------------------------------------------

def head_counts(year, grade=None):
    """
    ``{branch_id: {"students", "classes", "teachers"}, None: totals}``:
    students with an active enrollment in an active class of the year,
    active classes, and teachers with an active assignment teaching an
    active class subject of an active class (as the supervisor counts
    them). A teacher in both branches is one teacher in the total. Five
    queries.
    """

    class_q = Q(school_class__year=year, school_class__is_active=True)
    if grade is not None:
        class_q &= Q(school_class__grade=grade)

    enrollments = StudentEnrollment.objects.filter(
        class_q, status=StudentEnrollment.EnrollmentStatus.ACTIVE
    )
    teaching = ClassSubject.objects.filter(
        class_q, is_active=True,
        teacher_assignment__status=TeacherAssignment.AssignmentStatus.ACTIVE,
    )
    classes = SchoolClass.objects.filter(year=year, is_active=True)
    if grade is not None:
        classes = classes.filter(grade=grade)

    counts = defaultdict(lambda: {"students": 0, "classes": 0, "teachers": 0})

    for branch_id, n in (
        enrollments.order_by().values_list("school_class__branch")
        .annotate(n=Count("student", distinct=True))
    ):
        counts[branch_id]["students"] = n
    for branch_id, n in (
        teaching.order_by().values_list("school_class__branch")
        .annotate(n=Count("teacher_assignment__teacher", distinct=True))
    ):
        counts[branch_id]["teachers"] = n
    for branch_id, n in classes.order_by().values_list("branch").annotate(n=Count("id")):
        counts[branch_id]["classes"] = n

    counts[None] = {
        "students": enrollments.aggregate(n=Count("student", distinct=True))["n"],
        "classes": sum(c["classes"] for key, c in counts.items() if key is not None),
        "teachers": teaching.aggregate(n=Count("teacher_assignment__teacher", distinct=True))["n"],
    }
    return dict(counts)


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------

@dataclass
class Kpi:
    key: str
    title: str
    value: object                 # int count, or a rate (float) / None
    is_rate: bool = False
    previous: object = None
    delta: int | None = None      # percentage points vs the previous period
    note: str = ""

    @property
    def direction(self):
        if self.delta is None:
            return ""
        return "up" if self.delta > 0 else "down" if self.delta < 0 else "flat"


def _kpi_rate(key, title, current, previous, complete):
    value = getattr(current, key)
    kpi = Kpi(key=key, title=title, value=value, is_rate=True)
    if previous is None:
        kpi.note = "بدون دوره‌ی قبلی"
        return kpi
    kpi.previous = getattr(previous, key)
    if not complete:
        kpi.note = "داده‌ی دوره‌ی قبل کافی نیست"
    elif value is not None and kpi.previous is not None:
        kpi.delta = rounded(value) - rounded(kpi.previous)
    return kpi


@dataclass
class Alert:
    key: str
    title: str
    description: str
    count: int = 0
    items: list = field(default_factory=list)   # [{"label", "detail", "url"}]
    url: str = ""
    level: str = "warning"


def dashboard(dims, filters, as_of, urls):
    """
    Everything the dashboard shows. ``urls`` builds the drill-down links
    (``urls(page, query)``), so this module stays free of URL names.
    """

    year = filters.year
    today = timezone.localtime(as_of).date()
    closures = _closures(year)
    units = _units(dims, filters)

    # The comparison block shows every branch: the engine runs over all
    # of them, and the branch filter is applied when grouping.
    scope = AnalyticsScope.build(year, filters.start, filters.end, as_of=as_of, grade=filters.grade)
    previous = (
        None if scope.is_empty
        else periods.previous_period(year, scope.start, scope.end, closures, units)
    )
    window = periods.preceding_teaching_days(
        year, today + timedelta(days=1), threshold("DIRECTOR_ALERT_WINDOW_TEACHING_DAYS"), closures, units,
    )

    # One engine run over the year so far serves every window of the page
    # (the range, the previous period, the alert window) and the
    # year-to-date alerts (conflicts, sessions without attendance).
    hull = scope.with_range(year.start_date, today)
    result = engine.compute(hull, closures=closures)
    where = _in_branch(filters.branch)

    current = (
        metrics.Breakdown() if scope.is_empty
        else metrics.total(result, start=scope.start, end=scope.end, where=where)
    )
    before = (
        metrics.total(result, start=previous[0], end=previous[1], where=where) if previous else None
    )
    complete = bool(previous and previous[2])

    counts = head_counts(year, filters.grade)
    own = counts.get(filters.branch.pk if filters.branch else None, {})

    kpis = [
        Kpi("students", "دانش‌آموزان فعال", own.get("students", 0)),
        Kpi("classes", "کلاس‌ها", own.get("classes", 0)),
        Kpi("teachers", "معلمان", own.get("teachers", 0)),
        _kpi_rate("attendance_rate", "نرخ حضور", current, before, complete),
        _kpi_rate("execution_rate", "نرخ اجرای برنامه", current, before, complete),
        _kpi_rate("content_rate", "ثبت محتوا", current, before, complete),
    ]

    comparison = []
    for branch in dims.branches:
        breakdown = (
            metrics.Breakdown() if scope.is_empty
            else metrics.total(
                result, start=scope.start, end=scope.end,
                where=lambda cs, b=branch: cs.school_class.branch_id == b.pk,
            )
        )
        comparison.append({
            "branch": branch,
            "counts": counts.get(branch.pk, {"students": 0, "classes": 0, "teachers": 0}),
            "breakdown": breakdown,
            "is_selected": filters.branch is not None and filters.branch.pk == branch.pk,
        })

    return {
        "scope": scope,
        "current": current,
        "previous_period": previous,
        "kpis": kpis,
        "comparison": comparison,
        "calendar": calendar_summary(year, today, closures, units, filters),
        "alerts": alerts(dims, filters, result, window, today, urls),
        "teaching_days": len(periods.teaching_days(year, scope.start, scope.end, closures, units))
        if not scope.is_empty else 0,
    }


def _affects(event, filters):
    branches = {b.pk for b in event.branches.all()}
    grades = {g.pk for g in event.grades.all()}
    if filters.branch is not None and branches and filters.branch.pk not in branches:
        return False
    if filters.grade is not None and grades and filters.grade.pk not in grades:
        return False
    return True


def calendar_summary(year, today, closures, units, filters):
    """Teaching days so far / left, days lost to closures, and closures to come."""

    year_end = calendar.to_gregorian(year.end_date)
    upcoming = [
        event for event in closures.events(today, today + timedelta(days=UPCOMING_CLOSURE_DAYS))
        if _affects(event, filters)
    ]
    return {
        "elapsed": len(periods.teaching_days(year, year.start_date, today, closures, units)),
        "remaining": len(periods.teaching_days(year, today + timedelta(days=1), year_end, closures, units)),
        "lost": len(periods.closed_days(year, year.start_date, today, closures, units)),
        "upcoming": upcoming,
        "upcoming_days": UPCOMING_CLOSURE_DAYS,
    }


def alerts(dims, filters, result, window, today, urls):
    """The four alert cards, each linking to the page that explains it."""

    branch_id = filters.branch.pk if filters.branch else None
    grade_id = filters.grade.pk if filters.grade else None
    where = _in_branch(filters.branch)
    cards = []

    # 1. Classes with a low attendance rate over the last teaching days.
    rate_min = threshold("DIRECTOR_ALERT_ATTENDANCE_RATE")
    low = Alert(
        key="attendance",
        title="کلاس‌های با حضور پایین",
        description=f"نرخ حضور زیر {rate_min}٪ در {len(window)} روز آموزشی اخیر",
        level="danger",
    )
    by_teacher = {}
    if window:
        classes = {cs.school_class_id: cs.school_class for cs in result.class_subjects.values()}
        rows = metrics.breakdowns(result, metrics.by_class, start=window[0], end=window[-1], where=where)
        flagged = sorted(
            (
                (classes[class_id], b) for class_id, b in rows.items()
                if b.attendance_total and b.attendance_rate < rate_min
            ),
            key=lambda item: (item[1].attendance_rate, class_label(item[0])),
        )
        low.count = len(flagged)
        low.items = [
            {
                "label": class_label(school_class),
                "detail": f"{rounded(b.attendance_rate)}٪ · {b.absent} غیبت",
                "sub": school_class.branch.name,
                "url": urls("attendance", custom_range_query(
                    window[0], window[-1], branch=school_class.branch_id,
                    grade=school_class.grade_id, **{"class": school_class.pk},
                )),
            }
            for school_class, b in flagged[:ALERT_ITEMS]
        ]
        low.url = urls("attendance", custom_range_query(window[0], window[-1], branch=branch_id, grade=grade_id))

        # 2. Teachers with many unregistered slots in the same window.
        minimum = threshold("DIRECTOR_ALERT_UNREGISTERED_SLOTS")
        teachers = {cs.teacher_assignment.teacher_id: cs.teacher_assignment.teacher
                    for cs in result.class_subjects.values()}
        rows = metrics.breakdowns(result, metrics.by_teacher, start=window[0], end=window[-1], where=where)
        by_teacher = sorted(
            ((teachers[t], b) for t, b in rows.items() if b.unregistered >= minimum),
            key=lambda item: (-item[1].unregistered, teacher_name(item[0])),
        )
    unregistered = Alert(
        key="unregistered",
        title="معلمان با جلسات ثبت‌نشده",
        description=(
            f"حداقل {threshold('DIRECTOR_ALERT_UNREGISTERED_SLOTS')} زنگ ثبت‌نشده در "
            f"{len(window)} روز آموزشی اخیر"
        ),
        count=len(by_teacher),
    )
    if window:
        query = custom_range_query(window[0], window[-1], branch=branch_id, grade=grade_id, view="teachers")
        unregistered.url = urls("execution", query)
        unregistered.items = [
            {"label": teacher_name(teacher), "detail": f"{b.unregistered} زنگ", "url": unregistered.url}
            for teacher, b in by_teacher[:ALERT_ITEMS]
        ]
    cards += [low, unregistered]

    # 3. Held sessions still without attendance after the grace days, and
    # 4. sessions recorded in closed slots -- both over the year so far,
    # which ``result`` covers.
    cards.append(missing_attendance_alert(filters, result, urls))
    cards.append(conflicts_alert(filters, result, urls))
    return cards


def missing_attendance_alert(filters, result, urls):
    missing = missing_attendance_rows(result, result.scope, _in_branch(filters.branch), limit=ALERT_ITEMS)
    grace = threshold("DIRECTOR_ALERT_ATTENDANCE_GRACE_DAYS")
    card = Alert(
        key="missing_attendance",
        title="جلسات بدون حضور و غیاب",
        description=f"جلسه‌ی برگزارشده یا جبرانی که بیش از {grace} روز از آن گذشته و حضور و غیابی ندارد",
        count=missing["count"],
        url=urls("attendance", filters.query(period="year", date_from=None, date_to=None)) + "#missing",
    )
    for row in missing["rows"]:
        cs = row["class_subject"]
        card.items.append({
            "label": f"{cs.subject.name} · {row['class_label']}",
            "date": row["date"],
            "detail": "",
            "sub": row["teacher"],
            "url": card.url,
        })
    return card


def conflicts_alert(filters, result, urls):
    """
    Sessions in closed slots, from the engine run over the year so far:
    the same set ``academic_calendar.services.find_conflicts`` reports
    (same matching, same active events), in the filters' branch.
    """

    accept = _in_branch(filters.branch)
    conflicts = [
        row for row in conflict_rows(result)
        if accept is None or accept(row["class_subject"])
    ]
    card = Alert(
        key="conflicts",
        title="تداخل با تقویم آموزشی",
        description="جلسه‌ی ثبت‌شده در زنگی که تقویم آموزشی تعطیل کرده است",
        count=len(conflicts),
        url=urls("execution", filters.query(period="year", date_from=None, date_to=None)) + "#conflicts",
        level="danger",
    )
    for row in conflicts[:ALERT_ITEMS]:
        card.items.append({
            "label": f"{row['class_subject'].subject.name} · {row['class_label']}",
            "date": row["date"],
            "detail": row["event"].title,
            "sub": row["class_subject"].school_class.branch.name,
            "url": card.url,
        })
    return card


# ----------------------------------------------------------------------
# Drill-down (execution and attendance pages)
# ----------------------------------------------------------------------

LEVELS = ("branch", "grade", "class", "class_subject")


@dataclass
class DrillRow:
    key: object
    label: str
    sub: str
    breakdown: metrics.Breakdown
    query: str = ""               # the next level's query string; "" = deepest


def resolve_class(result, class_id):
    """``?class=`` -> a class of the scope (no query), or None."""

    for cs in result.class_subjects.values():
        if str(cs.school_class_id) == str(class_id):
            return cs.school_class
    return None


def drill_rows(dims, filters, result, school_class=None):
    """
    ``(level, rows)``: branches; with a branch, its grades; with a grade,
    its classes; with a class, its class subjects -- each row with its
    ``Breakdown`` and the query string of the level below.
    """

    groups = defaultdict(list)          # level key -> class subjects
    for cs in result.class_subjects.values():
        if school_class is not None and cs.school_class_id != school_class.pk:
            continue
        groups[cs.school_class_id].append(cs)

    if school_class is not None:
        level = "class_subject"
        data = metrics.breakdowns(result, metrics.by_class_subject,
                                  where=lambda cs: cs.school_class_id == school_class.pk)
        css = sorted(groups.get(school_class.pk, []), key=lambda cs: (cs.subject.name, cs.pk))
        rows = [
            DrillRow(cs.pk, cs.subject.name, teacher_name(cs.teacher_assignment.teacher),
                     data.get(cs.pk, metrics.Breakdown()))
            for cs in css if cs.is_active or cs.pk in data
        ]
        return level, rows

    if filters.grade is not None:
        level = "class"
        data = metrics.breakdowns(result, metrics.by_class)
        classes = {}
        for cs in result.class_subjects.values():
            if cs.school_class.is_active or cs.school_class_id in data:
                classes[cs.school_class_id] = cs.school_class
        rows = [
            DrillRow(c.pk, class_label(c), c.branch.name, data.get(c.pk, metrics.Breakdown()),
                     filters.query(**{"class": c.pk}))
            for c in sorted(classes.values(), key=lambda c: (c.branch.order, c.branch_id, c.section, c.pk))
        ]
        return level, rows

    if filters.branch is not None:
        level = "grade"
        data = metrics.breakdowns(result, metrics.by_grade)
        present = {cs.school_class.grade_id for cs in result.class_subjects.values()}
        rows = [
            DrillRow(g.pk, g.name, "", data.get(g.pk, metrics.Breakdown()), filters.query(grade=g.pk))
            for g in dims.grades if g.pk in present or g.pk in data
        ]
        return level, rows

    level = "branch"
    data = metrics.breakdowns(result, metrics.by_branch)
    rows = [
        DrillRow(b.pk, b.name, "", data.get(b.pk, metrics.Breakdown()), filters.query(branch=b.pk))
        for b in dims.branches
    ]
    return level, rows


def breadcrumbs(filters, school_class, urls, page):
    """The drill path: all branches > branch > grade > class."""

    crumbs = [{"label": "همه‌ی شعبه‌ها", "url": urls(page, filters.query(branch=None, grade=None))}]
    if filters.branch is not None:
        crumbs.append({"label": filters.branch.name, "url": urls(page, filters.query(grade=None))})
    if filters.grade is not None:
        crumbs.append({"label": filters.grade.name, "url": urls(page, filters.query())})
    if school_class is not None:
        crumbs.append({"label": class_label(school_class), "url": ""})
    crumbs[-1]["url"] = ""
    return crumbs


def _page_scope(filters, as_of):
    return AnalyticsScope.build(
        filters.year, filters.start, filters.end, as_of=as_of,
        branch=filters.branch, grade=filters.grade,
    )


# ----------------------------------------------------------------------
# Execution page
# ----------------------------------------------------------------------

EXECUTION_VIEWS = (
    ("breakdown", "به تفکیک شعبه، پایه و کلاس"),
    ("teachers", "به تفکیک معلم"),
    ("subjects", "مقایسه‌ی درس‌ها در یک پایه"),
)


def execution(dims, filters, as_of, view, class_id, urls):
    closures = _closures(filters.year)
    scope = _page_scope(filters, as_of)
    result = engine.compute(scope, closures=closures, with_attendance=False)
    school_class = resolve_class(result, class_id) if class_id else None

    data = {
        "scope": scope,
        "summary": metrics.total(
            result, where=(lambda cs: cs.school_class_id == school_class.pk) if school_class else None
        ),
        "teaching_days": 0 if scope.is_empty else len(
            periods.teaching_days(filters.year, scope.start, scope.end, closures, _units(dims, filters))
        ),
        "school_class": school_class,
        "conflicts": conflict_rows(result),
    }

    if view == "teachers":
        data["teacher_rows"] = teacher_rows(result)
    elif view == "subjects":
        data["subject_matrix"] = subject_matrix(result, filters) if filters.grade else None
    else:
        data["level"], data["rows"] = drill_rows(dims, filters, result, school_class)
        data["breadcrumbs"] = breadcrumbs(filters, school_class, urls, "execution")
    return data


def teacher_rows(result):
    """One row per teacher, worst execution rate first (no slots last)."""

    teachers, subjects = {}, defaultdict(set)
    for cs in result.class_subjects.values():
        teacher = cs.teacher_assignment.teacher
        teachers[teacher.pk] = teacher
        if cs.is_active:
            subjects[teacher.pk].add(f"{cs.subject.name} ({class_label(cs.school_class)})")

    data = metrics.breakdowns(result, metrics.by_teacher)
    rows = [
        DrillRow(pk, teacher_name(teacher), "، ".join(sorted(subjects[pk])), data[pk])
        for pk, teacher in teachers.items() if pk in data
    ]
    rows.sort(key=lambda row: (
        row.breakdown.execution_rate is None,
        row.breakdown.execution_rate if row.breakdown.execution_rate is not None else 0,
        -row.breakdown.unregistered,
        row.label,
    ))
    return rows


def subject_matrix(result, filters):
    """
    Held sessions per subject (rows) and class (columns) of one grade, to
    spot a class falling behind the others in the same subject. A cell
    ``SUBJECT_GAP_WARNING`` or more held sessions behind the best class of
    its row is marked.
    """

    data = metrics.breakdowns(result, lambda cs, day: (cs.subject_id, cs.school_class_id))
    subjects, classes = {}, {}
    for cs in result.class_subjects.values():
        if cs.is_active or (cs.subject_id, cs.school_class_id) in data:
            subjects[cs.subject_id] = cs.subject
            classes[cs.school_class_id] = cs.school_class
    classes = sorted(classes.values(), key=lambda c: (c.branch.order, c.branch_id, c.section, c.pk))

    rows = []
    for subject in sorted(subjects.values(), key=lambda s: (s.name, s.pk)):
        cells = [(c, data.get((subject.pk, c.pk))) for c in classes]
        best = max((cell.held for _, cell in cells if cell is not None), default=0)
        rows.append({
            "subject": subject,
            "best": best,
            "cells": [
                {
                    "school_class": school_class,
                    "breakdown": cell,
                    "gap": None if cell is None else best - cell.held,
                    "is_behind": cell is not None and best - cell.held >= SUBJECT_GAP_WARNING,
                }
                for school_class, cell in cells
            ],
        })
    return {"classes": classes, "rows": rows, "gap_warning": SUBJECT_GAP_WARNING}


def conflict_rows(result):
    rows = []
    for conflict in sorted(result.conflicts, key=lambda c: (c.date, c.bell.order)):
        cs = result.class_subjects[conflict.class_subject_id]
        rows.append({
            "date": conflict.date,
            "bell": conflict.bell,
            "class_subject": cs,
            "class_label": class_label(cs.school_class),
            "teacher": teacher_name(cs.teacher_assignment.teacher),
            "event": conflict.event,
            "status": conflict.session.status,
        })
    return rows


# ----------------------------------------------------------------------
# Attendance page
# ----------------------------------------------------------------------

def attendance(dims, filters, as_of, class_id, urls):
    closures = _closures(filters.year)
    scope = _page_scope(filters, as_of)
    result = engine.compute(scope, closures=closures)
    school_class = resolve_class(result, class_id) if class_id else None
    in_class = (lambda cs: cs.school_class_id == school_class.pk) if school_class else None
    units = _units(dims, filters)
    if school_class is not None:
        units = periods.units(filters.year, [school_class.branch_id], [school_class.grade_id])

    level, rows = drill_rows(dims, filters, result, school_class)
    return {
        "scope": scope,
        "teaching_days": 0 if scope.is_empty else len(
            periods.teaching_days(filters.year, scope.start, scope.end, closures, units)
        ),
        "summary": metrics.total(result, where=in_class),
        "school_class": school_class,
        "level": level,
        "rows": rows,
        "breadcrumbs": breadcrumbs(filters, school_class, urls, "attendance"),
        "trend": daily_trend(filters.year, scope, result, closures, units, in_class),
        "absentees": [] if scope.is_empty else top_absentees(scope, school_class),
        "absentee_limit": TOP_ABSENTEES,
        "missing": missing_attendance_rows(result, scope, in_class),
    }


def daily_trend(year, scope, result, closures, units, where=None):
    """
    One point per working day of the range: the attendance rate (None
    without records) and whether the scope was closed that day -- a
    closed day is marked, never plotted as zero.
    """

    if scope.is_empty:
        return {"points": [], "has_data": False}

    data = metrics.breakdowns(result, metrics.by_day, where=where)
    closed = set(periods.closed_days(year, scope.start, scope.end, closures, units))
    events = {}
    for day in closed:
        for event in closures.events(day, day):
            events.setdefault(day, event.title)

    days = sorted(
        {d for d in calendar.date_range(scope.start, scope.end) if not calendar.is_weekend(d)}
        | {d for d, b in data.items() if b.attendance_total}
    )
    points = []
    for day in days:
        breakdown = data.get(day, metrics.Breakdown())
        jalali = calendar.to_jalali(day)
        points.append({
            "date": day,
            "label": fa_digits(f"{jalali.day} {MONTHS[jalali.month - 1]}"),
            "title": format_jalali(day, with_weekday=True),
            "rate": rounded(breakdown.attendance_rate),
            "total": breakdown.attendance_total,
            "absent": breakdown.absent,
            "late": breakdown.late,
            "closed": day in closed,
            "closure": events.get(day, ""),
        })
    with_data = sum(1 for p in points if p["rate"] is not None)
    return {
        "points": points,
        "has_data": with_data > 0,
        "enough": with_data >= 2,
        "closed_days": sum(1 for p in points if p["closed"]),
        "chart": {
            "labels": [p["label"] for p in points],
            "titles": [p["title"] for p in points],
            "rates": [p["rate"] for p in points],
            "closed": [p["closed"] for p in points],
            "closures": [p["closure"] for p in points],
            "totals": [p["total"] for p in points],
            "absents": [p["absent"] for p in points],
            "lates": [p["late"] for p in points],
        },
    }


def top_absentees(scope, school_class=None, limit=TOP_ABSENTEES):
    """
    Students with the most absences in the range (count, then rate), over
    the records of delivered sessions of the scope. One query.
    """

    records = Attendance.objects.filter(
        session__status__in=DELIVERED_STATUSES,
        session__date__gte=calendar.to_jalali(scope.start),
        session__date__lte=calendar.to_jalali(scope.end),
        **scope.class_subject_filter("session__class_subject__"),
    )
    if school_class is not None:
        records = records.filter(session__class_subject__school_class=school_class)

    rows = (
        records.order_by()
        .values(
            "student_enrollment",
            "student_enrollment__student__user__first_name",
            "student_enrollment__student__user__last_name",
            "student_enrollment__student__user__username",
            "student_enrollment__school_class__grade__name",
            "student_enrollment__school_class__section",
            "student_enrollment__school_class__branch__name",
        )
        .annotate(
            total=Count("id"),
            absent=Count("id", filter=Q(status=ABSENT)),
            late=Count("id", filter=Q(status=LATE)),
        )
        .filter(absent__gt=0)
        .order_by("-absent", "-total", "student_enrollment")[:limit]
    )
    result = []
    for row in rows:
        name = " ".join(filter(None, (
            row["student_enrollment__student__user__first_name"],
            row["student_enrollment__student__user__last_name"],
        ))) or row["student_enrollment__student__user__username"]
        result.append({
            "name": name,
            "class_label": fa_digits(
                f"{row['student_enrollment__school_class__grade__name']} "
                f"{row['student_enrollment__school_class__section']}"
            ),
            "branch": row["student_enrollment__school_class__branch__name"],
            "total": row["total"],
            "absent": row["absent"],
            "late": row["late"],
            "absence_rate": rounded(rate(row["absent"], row["total"])),
        })
    return result


def missing_attendance_rows(result, scope, where=None, limit=MISSING_ATTENDANCE_ITEMS):
    """Delivered sessions of the range, past the grace days, without any record."""

    grace = threshold("DIRECTOR_ALERT_ATTENDANCE_GRACE_DAYS")
    before = scope.today - timedelta(days=grace)
    rows = []
    for row in result.sessions:
        if row.status not in DELIVERED_STATUSES or row.attendance_total or row.date >= before:
            continue
        cs = result.class_subjects[row.class_subject_id]
        if where is not None and not where(cs):
            continue
        rows.append({
            "date": row.date,
            "class_subject": cs,
            "class_label": class_label(cs.school_class),
            "teacher": teacher_name(cs.teacher_assignment.teacher),
            "status": row.status,
        })
    rows.sort(key=lambda r: (r["date"], r["class_label"]), reverse=True)
    return {"count": len(rows), "rows": rows[:limit], "limit": limit}
