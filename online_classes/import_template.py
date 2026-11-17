"""
The downloadable .xlsx template of one event's personal access import (see
``online_classes.importer``). Sheet «اطلاعات ورود» lists the event's audience
with empty access cells; no stored secret or username is ever written out.
Code columns are Text-formatted, so Excel doesn't drop leading zeros.
"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import audience
from .importer import (
    ACCESS_CODE, COLUMNS, NAME, NATIONAL_CODE, NOTE, PASSWORD, STUDENT_CODE, URL, USERNAME,
)

TEXT_COLUMNS = {STUDENT_CODE, NATIONAL_CODE, URL, USERNAME, PASSWORD, ACCESS_CODE}
WIDTHS = {STUDENT_CODE: 16, NATIONAL_CODE: 14, NAME: 26, URL: 40, USERNAME: 18, PASSWORD: 16, ACCESS_CODE: 14, NOTE: 30}
HEADER_FILL = PatternFill("solid", fgColor="FAEAD2")
#: Empty, Text-formatted rows below the audience, for students added by hand.
SPARE_ROWS = 20


def _write_text(sheet, row, column, value):
    """A cell that is always text: a name starting with «=» must not become a formula."""

    cell = sheet.cell(row=row, column=column, value=value)
    cell.data_type = "s"
    return cell


def build_template(event):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "اطلاعات ورود"
    sheet.sheet_view.rightToLeft = True
    sheet.freeze_panes = "A2"

    for index, title in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=1, column=index, value=title)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")
        sheet.column_dimensions[get_column_letter(index)].width = WIDTHS.get(title, 16)

    enrollments = list(audience.reached_enrollments(event))
    for number, enrollment in enumerate(enrollments, start=2):
        student = enrollment.student
        _write_text(sheet, number, COLUMNS.index(STUDENT_CODE) + 1, student.student_code or "")
        _write_text(sheet, number, COLUMNS.index(NATIONAL_CODE) + 1, student.user.national_code or "")
        _write_text(sheet, number, COLUMNS.index(NAME) + 1, student.user.get_full_name())

    last_row = len(enrollments) + 1 + SPARE_ROWS
    for index, title in enumerate(COLUMNS, start=1):
        if title in TEXT_COLUMNS:
            for row in range(2, last_row + 1):
                sheet.cell(row=row, column=index).number_format = "@"

    guide = workbook.create_sheet("راهنما")
    guide.sheet_view.rightToLeft = True
    guide.column_dimensions["A"].width = 100
    notes = [
        f"رویداد: {event.title}",
        "هر دانش‌آموز با کد دانش‌آموزی یا کد ملی شناخته می‌شود؛ «نام دانش‌آموز» فقط برای راهنمایی شماست.",
        "ردیفی که لینک، نام کاربری، رمز، کد و توضیحش خالی باشد نادیده گرفته می‌شود.",
        "در ارسال دوباره، خانه‌ی خالی مقدار ثبت‌شده را تغییر نمی‌دهد.",
        "لینک‌ها باید با https:// شروع شوند.",
        "اگر حتی یک ردیف خطا داشته باشد، هیچ ردیفی ثبت نمی‌شود.",
        "این فایل پس از پر شدن رمزها را دارد؛ آن را جایی نگذارید و پس از ثبت پاکش کنید.",
    ]
    for row, note in enumerate(notes, start=1):
        guide.cell(row=row, column=1, value=note)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
