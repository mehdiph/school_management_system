"""
Excel import of one event's personal access rows (admin «ورود از اکسل» on the
event page), on the calendar importer's pattern.

Flow: ``read_rows`` (the raw cells) -> ``validate`` (every row, every problem,
nothing written) -> the admin shows a preview with passwords masked -> on
confirmation ``validate`` runs again on the same cells and, only when no row
has an error, ``services.save_access_import`` writes them all (all or nothing).

Between preview and confirmation the cells hold passwords, so the session keeps
one encrypted token of them that expires, never the cells (``seal`` / ``unseal``,
D16). The uploaded file isn't kept. No message echoes a link or a secret.

A row is matched by student code or national code. A student outside the event's
audience is a warning, not an error (D17). A row with no access data is skipped,
so a partly filled template works, and a blank cell keeps what is stored (D18).
"""

import json
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError

from core import spreadsheet
from core.services import access
from core.spreadsheet import FileRejected, normalize
from student.models.student_enrollment import StudentEnrollment
from student.models.student_profile import StudentProfile

from . import audience, crypto
from .models import OnlineEventAccess
from .validators import validate_https_url

STUDENT_CODE = "کد دانش‌آموزی"
NATIONAL_CODE = "کد ملی"
NAME = "نام دانش‌آموز"
URL = "لینک"
USERNAME = "نام کاربری"
PASSWORD = "رمز عبور"
ACCESS_CODE = "کد دسترسی"
NOTE = "توضیح"

COLUMNS = [STUDENT_CODE, NATIONAL_CODE, NAME, URL, USERNAME, PASSWORD, ACCESS_CODE, NOTE]

MASK = "••••••"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
PREVIEW_SECONDS = 30 * 60

_MAX_USERNAME = OnlineEventAccess._meta.get_field("username").max_length
_MAX_NOTE = OnlineEventAccess._meta.get_field("note").max_length


@dataclass
class ImportRow:
    number: int                 # the spreadsheet row number (header = 1)
    student_code: str = ""
    national_code: str = ""
    student: StudentProfile = None
    url: str = ""
    username: str = ""
    password: str = ""
    access_code: str = ""
    note: str = ""
    is_update: bool = False
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def link_display(self):
        """The host only: a personal link can be a login in itself."""

        try:
            return urlsplit(self.url).hostname or MASK
        except ValueError:
            return MASK

    @property
    def password_display(self):
        return MASK if self.password else ""

    @property
    def access_code_display(self):
        return MASK if self.access_code else ""


@dataclass
class ImportPlan:
    event: object
    rows: list
    skipped: int = 0

    @property
    def errors(self):
        return [row for row in self.rows if row.errors]

    @property
    def warnings(self):
        return [row for row in self.rows if row.warnings]

    @property
    def rows_to_save(self):
        return self.rows

    @property
    def new_count(self):
        return sum(1 for row in self.rows if not row.is_update)

    @property
    def update_count(self):
        return sum(1 for row in self.rows if row.is_update)

    @property
    def is_valid(self):
        return bool(self.rows) and not self.errors


def read_rows(uploaded_file):
    if uploaded_file.size > MAX_UPLOAD_BYTES:
        raise FileRejected("حجم فایل نباید بیشتر از ۵ مگابایت باشد.")
    return spreadsheet.read_rows(uploaded_file, COLUMNS, settings.ONLINE_ACCESS_IMPORT_MAX_ROWS)


def seal(event, user, rows, filename):
    """The preview's cells as one encrypted token, tied to this event and this admin."""

    return crypto.encrypt(json.dumps({"event": event.pk, "user": user.pk, "rows": rows, "filename": filename}))


def unseal(token, event, user):
    """``(rows, filename)``, or ``None`` when the preview has expired or belongs to someone else."""

    try:
        data = json.loads(crypto.decrypt(token or "", ttl=PREVIEW_SECONDS) or "null")
    except crypto.DecryptionFailed:
        return None
    if not data or data["event"] != event.pk or data["user"] != user.pk:
        return None
    return data["rows"], data["filename"]


def _student_lookup(raw_rows):
    """Loads every student the file names in two queries, not one per row."""

    student_codes = {normalize(cells.get(STUDENT_CODE, "")) for cells in raw_rows} - {""}
    national_codes = {_national(cells.get(NATIONAL_CODE, "")) for cells in raw_rows} - {""}
    students = StudentProfile.objects.select_related("user")
    by_code = {s.student_code: s for s in students.filter(student_code__in=student_codes)}
    by_national = {s.user.national_code: s for s in students.filter(user__national_code__in=national_codes)}
    return by_code, by_national


def _national(value):
    """Excel drops leading zeros from a number: pad a national code back to 10 digits."""

    text = normalize(value)
    return text.zfill(10) if text.isdigit() else text


def validate(raw_rows, event, acting_user):
    """``raw_rows`` -> ``ImportPlan``: every row parsed, with every problem found. Writes nothing."""

    by_code, by_national = _student_lookup(raw_rows)
    named_ids = {s.pk for s in by_code.values()} | {s.pk for s in by_national.values()}
    branch_of = dict(
        StudentEnrollment.objects.current()
        .filter(student__in=named_ids)
        .values_list("student_id", "school_class__branch_id")
    )
    in_audience = set(audience.reached_enrollments(event).values_list("student_id", flat=True))
    existing = set(OnlineEventAccess.objects.filter(event=event).values_list("student_id", flat=True))
    allowed = None if acting_user.is_superuser else set(access.get_accessible_branch_ids(acting_user))
    domains = event.platform.allowed_domains if event.platform_id else ""

    rows, seen, skipped = [], {}, 0
    for number, cells in enumerate(raw_rows, start=2):
        row = ImportRow(
            number=number,
            student_code=normalize(cells.get(STUDENT_CODE, "")),
            national_code=_national(cells.get(NATIONAL_CODE, "")),
            url=cells.get(URL, ""),
            username=cells.get(USERNAME, ""),
            password=cells.get(PASSWORD, ""),
            access_code=cells.get(ACCESS_CODE, ""),
            note=cells.get(NOTE, ""),
        )
        has_way_in = bool(row.url or row.username or row.password or row.access_code)
        if not has_way_in and not row.note:
            skipped += 1
            continue
        rows.append(row)

        if not row.student_code and not row.national_code:
            row.errors.append("کد دانش‌آموزی یا کد ملی لازم است.")
        by_student_code = by_code.get(row.student_code) if row.student_code else None
        by_national_code = by_national.get(row.national_code) if row.national_code else None
        if row.student_code and by_student_code is None:
            row.errors.append(f"دانش‌آموزی با کد دانش‌آموزی «{row.student_code}» پیدا نشد.")
        if row.national_code and by_national_code is None:
            row.errors.append(f"دانش‌آموزی با کد ملی «{row.national_code}» پیدا نشد.")
        if by_student_code and by_national_code and by_student_code.pk != by_national_code.pk:
            row.errors.append("کد دانش‌آموزی و کد ملی این ردیف مال دو دانش‌آموز مختلف است.")
        row.student = by_student_code or by_national_code

        if row.student is not None:
            student_id = row.student.pk
            row.is_update = student_id in existing
            if allowed is not None and branch_of.get(student_id) not in allowed:
                row.errors.append("این دانش‌آموز در شعبه‌های شما نیست.")
            if student_id in seen:
                row.errors.append(f"این دانش‌آموز در ردیف {seen[student_id]} همین فایل هم آمده است.")
            else:
                seen[student_id] = number
            if student_id not in in_audience:
                row.warnings.append("این دانش‌آموز جزو مخاطبان این رویداد نیست؛ تا وقتی جزو مخاطبان نشود چیزی نمی‌بیند.")
            if not has_way_in and not row.is_update:
                row.errors.append("فقط «توضیح» کافی نیست؛ لینک، نام کاربری، رمز یا کد لازم است.")

        if row.url:
            try:
                validate_https_url(row.url, domains)
            except ValidationError as error:
                row.errors.extend(error.messages)
        if len(row.username) > _MAX_USERNAME:
            row.errors.append(f"نام کاربری نباید بیشتر از {_MAX_USERNAME} حرف باشد.")
        if len(row.note) > _MAX_NOTE:
            row.errors.append(f"توضیح نباید بیشتر از {_MAX_NOTE} حرف باشد.")

    if not rows:
        raise FileRejected("فایل هیچ ردیفی با اطلاعات ورود ندارد.")
    return ImportPlan(event=event, rows=rows, skipped=skipped)
