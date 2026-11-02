"""
Reading the first sheet of an uploaded .xlsx: the part every Excel import
shares (``academic_calendar.importer``, ``online_classes.importer``). A file
is taken cell by cell as text; each importer validates the cells itself.
"""

import re
from datetime import date, datetime

from openpyxl import load_workbook

_SEPARATORS = re.compile(r"[,،;؛]")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class FileRejected(Exception):
    """The file as a whole cannot be read (not xlsx, wrong headers, too long...)."""


def cell_text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, (datetime, date)):
        # Excel turned "1405/07/12" into a (Gregorian) date: keep its digits.
        return f"{value.year:04d}/{value.month:02d}/{value.day:02d}"
    # ZWNJ is part of Persian words; only collapse ordinary whitespace.
    return re.sub(r"[ \t\r\n]+", " ", str(value)).strip()


def normalize(value):
    """For matching names: Arabic ي/ك -> Persian, digits -> Latin, no extra spaces."""

    return cell_text(value).replace("ي", "ی").replace("ك", "ک").translate(_DIGITS).strip()


def split_list(value):
    return [part.strip() for part in _SEPARATORS.split(normalize(value)) if part.strip()]


def read_rows(uploaded_file, columns, max_rows):
    """``[{column: text}, ...]`` from the first sheet; ``FileRejected`` when unreadable."""

    try:
        workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
    except Exception:
        raise FileRejected("فایل قابل خواندن نیست؛ فایل اکسل (xlsx) را با قالب دانلودشده بفرستید.")

    sheet = workbook.worksheets[0]
    rows = sheet.iter_rows(values_only=True)
    header = [cell_text(value) for value in next(rows, ())]
    while header and not header[-1]:
        header.pop()
    if header != columns:
        raise FileRejected(
            "ستون‌های فایل با قالب یکی نیست. ستون‌ها باید دقیقاً این‌ها باشند: "
            + "، ".join(columns)
        )

    data = []
    for values in rows:
        cells = {column: cell_text(value) for column, value in zip(columns, values)}
        data.append(cells)
    while data and not any(data[-1].values()):
        data.pop()
    if len(data) > max_rows:
        raise FileRejected(f"حداکثر {max_rows} ردیف در هر فایل مجاز است.")
    workbook.close()
    return data
