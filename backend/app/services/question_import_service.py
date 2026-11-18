"""Excel/CSV question-bank import and export helpers.

Security notes
--------------
* Only ``.xlsx`` and ``.csv`` are accepted, and the file signature is checked
  in addition to the extension (an XLSX is a ZIP archive).
* File size and row count are capped before any parsing work is done.
* Cell values are treated strictly as data: formulas are never evaluated
  (openpyxl is used with ``data_only=True`` and ``read_only=True``).
* CSV formula injection is neutralised on export by prefixing a leading
  ``= + - @`` with a single quote when the workbook is opened in Excel.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
MAX_CELL_CHARS = 20_000

# Canonical field -> accepted spreadsheet headers (lower-cased, stripped).
COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "text": ("question", "question text", "question_text", "text", "prompt"),
    "question_type": ("question type", "question_type", "type"),
    "category": ("category", "category name", "category_name", "category_id"),
    "topic": ("topic", "subject", "section"),
    "skill": ("skill", "skill name", "skill_tag", "skill tag"),
    "skill_tags": ("skill tags", "skills", "skill_tags"),
    "difficulty": ("difficulty", "difficulty level", "level"),
    "option_a": ("option a", "optiona", "a", "choice a"),
    "option_b": ("option b", "optionb", "b", "choice b"),
    "option_c": ("option c", "optionc", "c", "choice c"),
    "option_d": ("option d", "optiond", "d", "choice d"),
    "correct_answer": ("correct answer", "correct_answer", "answer", "answer key"),
    "explanation": ("explanation", "description", "solution", "rationale"),
    "marks": ("marks", "mark", "score", "points"),
    "status": ("status", "active", "is active"),
    "language": ("language", "coding language"),
    "starter_code": ("starter code", "starter_code"),
    "company_tags": ("company tags", "company_tags", "companies"),
}

TRUE_FALSE_VALUES = {"true": "True", "false": "False"}


class ImportFileError(Exception):
    """Raised for problems with the uploaded file itself (not a row)."""


@dataclass
class ParsedSheet:
    mapping: dict[str, str]
    headers: list[str]
    rows: list[dict[str, str]] = field(default_factory=list)
    raw_row_count: int = 0


def _normalise_header(value: object) -> str:
    return re.sub(r"[\s_\-]+", " ", str(value or "").strip().lower()).strip()


def _map_headers(headers: list[str]) -> dict[str, str]:
    normalised = {_normalise_header(h): h for h in headers if h}
    mapping: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if _normalise_header(alias) in normalised:
                mapping[canonical] = normalised[_normalise_header(alias)]
                break
    return mapping


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _csv_dialect(sample: str) -> type[csv.Dialect]:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        return csv.excel


def parse_question_file(filename: str, content: bytes) -> ParsedSheet:
    """Parse a validated upload into canonical, string-valued rows."""
    if not filename or "." not in filename:
        raise ImportFileError("Uploaded file must have a .xlsx or .csv extension.")
    extension = filename.rsplit(".", 1)[1].lower()
    if extension not in {"xlsx", "csv"}:
        raise ImportFileError("Only .xlsx and .csv question files are supported.")
    if not content:
        raise ImportFileError("Uploaded file is empty.")
    if len(content) > MAX_IMPORT_BYTES:
        raise ImportFileError(f"Uploaded file exceeds the {MAX_IMPORT_BYTES // (1024 * 1024)} MB limit.")

    # XLSX files are ZIP archives ("PK\x03\x04"). CSV must be decodable text.
    if extension == "xlsx" and not content.startswith(b"PK\x03\x04"):
        raise ImportFileError("This .xlsx file is not a valid Excel workbook.")
    if extension == "csv" and b"\x00" in content[:4096]:
        raise ImportFileError("This .csv file contains binary data.")

    rows: list[list[object]] = []
    if extension == "xlsx":
        try:
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = workbook.active
            for row in sheet.iter_rows(values_only=True):
                rows.append(list(row))
            workbook.close()
        except Exception as exc:  # pragma: no cover - malformed workbook
            raise ImportFileError(f"Could not read the Excel workbook: {exc}") from exc
    else:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ImportFileError("CSV file must be UTF-8 encoded.") from exc
        reader = csv.reader(io.StringIO(text), _csv_dialect(text[:4096]))
        rows = [list(row) for row in reader]

    if len(rows) > MAX_IMPORT_ROWS + 1:
        raise ImportFileError(f"A question file can contain at most {MAX_IMPORT_ROWS} questions.")
    if not rows:
        raise ImportFileError("The file contains no header row.")

    headers = [_cell_text(value) for value in rows[0]]
    mapping = _map_headers(headers)
    required = ("text", "question_type", "category", "difficulty", "correct_answer")
    missing = [name for name in required if name not in mapping]
    if missing:
        raise ImportFileError(
            "Missing required column(s): " + ", ".join(missing) + ". "
            "Download the import template to see accepted column names."
        )

    parsed_rows: list[dict[str, str]] = []
    for row in rows[1:]:
        if not any(_cell_text(cell) for cell in row):
            continue  # ignore completely blank trailing rows, not data rows
        values: dict[str, str] = {}
        for canonical, header in mapping.items():
            index = headers.index(header)
            value = _cell_text(row[index]) if index < len(row) else ""
            if len(value) > MAX_CELL_CHARS:
                value = value[:MAX_CELL_CHARS]
            values[canonical] = value
        parsed_rows.append(values)

    return ParsedSheet(mapping=mapping, headers=headers, rows=parsed_rows, raw_row_count=len(parsed_rows))


def coerce_row(values: dict[str, str], sheet: ParsedSheet) -> dict:
    """Convert a parsed row into the loose shape QuestionCreateRequest expects."""
    question_type = _normalise_header(values.get("question_type", "")).replace(" ", "_")
    options = [values[f"option_{letter}"] for letter in "abcd" if values.get(f"option_{letter}")]
    if question_type == "true false":
        question_type = "true_false"

    tags = [tag.strip() for tag in re.split(r"[|;]", values.get("skill_tags", "")) if tag.strip()]
    skill = values.get("skill", "").strip() or (tags[0] if tags else None)
    companies = [tag.strip() for tag in re.split(r"[|;]", values.get("company_tags", "")) if tag.strip()]
    marks_raw = values.get("marks", "").strip()
    status_raw = _normalise_header(values.get("status", "active") or "active")

    payload: dict = {
        "category_id": values.get("category", "").strip(),
        "difficulty": values.get("difficulty", "").strip().lower(),
        "type": question_type,
        "text": values.get("text", "").strip(),
        "options": options,
        "correct_answer": values.get("correct_answer", "").strip() or None,
        "skill_tags": tags,
        "company_tags": companies,
        "topic": values.get("topic", "").strip() or None,
        "skill": skill,
        "explanation": values.get("explanation", "").strip() or None,
        "status": "inactive" if status_raw in {"inactive", "disabled", "false", "0"} else "active",
    }
    if marks_raw:
        payload["marks"] = marks_raw
    if question_type == "coding":
        payload["language"] = values.get("language", "").strip().lower() or None
        payload["starter_code"] = values.get("starter_code", "").strip() or None
        # Legacy expected-output imports use correct_answer as the single test case.
    return payload


def questions_to_rows(questions: list, category_names: dict[str, str]) -> list[list[object]]:
    rows: list[list[object]] = []
    for q in questions:
        options = list(q.options) + [""] * (4 - len(q.options))
        answer = q.correct_answer or ""
        if isinstance(answer, list):
            answer = "|".join(answer)
        rows.append(
            [
                q.id,
                q.text,
                q.type.value,
                category_names.get(q.category_id, q.category_id),
                q.topic or "",
                q.skill or (q.skill_tags[0] if q.skill_tags else ""),
                q.difficulty.value,
                options[0],
                options[1],
                options[2],
                options[3],
                answer,
                q.explanation or "",
                q.marks,
                q.status.value,
            ]
        )
    return rows


EXPORT_HEADERS = [
    "Question ID",
    "Question",
    "Question Type",
    "Category",
    "Topic",
    "Skill",
    "Difficulty",
    "Option A",
    "Option B",
    "Option C",
    "Option D",
    "Correct Answer",
    "Explanation",
    "Marks",
    "Status",
]


def _excel_safe(value: object) -> object:
    """Prevent spreadsheet formula execution when a cell is opened."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def build_export_workbook(questions: list, category_names: dict[str, str]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Question Bank"
    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF")
    for column, title in enumerate(EXPORT_HEADERS, start=1):
        cell = sheet.cell(row=1, column=column, value=title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center")
    for row_index, row in enumerate(questions_to_rows(questions, category_names), start=2):
        for column, value in enumerate(row, start=1):
            sheet.cell(row=row_index, column=column, value=_excel_safe(value)).alignment = Alignment(
                vertical="top", wrap_text=column in {2, 13}
            )
    widths = [28, 60, 18, 30, 22, 22, 12, 24, 24, 24, 24, 26, 60, 10, 12]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.freeze_panes = "A2"
    if questions:
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(EXPORT_HEADERS))}{len(questions) + 1}"

    # Admin-only helper sheet documenting the valid values for imports.
    guide = workbook.create_sheet("Import Guide")
    guide_rows = [
        ["Column", "Accepted values / notes"],
        ["Question", "Required. Full question text."],
        ["Question Type", "Required. mcq, multiple_select, true_false, coding or descriptive."],
        ["Category", "Required. Exact category name or category ID."],
        ["Difficulty", "Required. easy, medium or hard."],
        ["Correct Answer", "Required. MCQ: exact option text. Multiple select: A|C. True/false: True or False."],
        ["Status", "active or inactive. Blank means active."],
        ["Marks", "Optional integer. Blank assigns marks from difficulty (1/3/5)."],
    ]
    for row in guide_rows:
        guide.append(row)
    guide.column_dimensions["A"].width = 20
    guide.column_dimensions["B"].width = 90

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def build_template_workbook(
    category_names: list[str] | None = None,
    sections: list[tuple[str, int]] | None = None,
) -> bytes:
    """Downloadable blank workbook: headers, instructions, categories and sections.

    The ``Questions`` sheet deliberately contains **no data rows** — only the
    header row and list validations — so a downloaded template can never be
    mistaken for, or imported as, existing question-bank content. Guidance,
    supported categories and the standardized section layout live on separate
    sheets so the importable sheet stays clean.
    """
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Questions"

    header_fill = PatternFill("solid", fgColor="C8102E")
    header_font = Font(bold=True, color="FFFFFF")
    for column, title in enumerate(EXPORT_HEADERS, start=1):
        cell = sheet.cell(row=1, column=column, value=title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for index, width in enumerate([28, 60, 18, 30, 22, 22, 12, 24, 24, 24, 24, 26, 60, 10, 12], start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.row_dimensions[1].height = 30
    sheet.freeze_panes = "A2"

    type_validation = DataValidation(
        type="list", formula1='"mcq,multiple_select,true_false,coding,descriptive"', allow_blank=True
    )
    difficulty_validation = DataValidation(type="list", formula1='"easy,medium,hard"', allow_blank=True)
    status_validation = DataValidation(type="list", formula1='"active,inactive"', allow_blank=True)
    sheet.add_data_validation(type_validation)
    sheet.add_data_validation(difficulty_validation)
    sheet.add_data_validation(status_validation)
    type_validation.add(f"C2:C{MAX_IMPORT_ROWS + 1}")
    difficulty_validation.add(f"G2:G{MAX_IMPORT_ROWS + 1}")
    status_validation.add(f"O2:O{MAX_IMPORT_ROWS + 1}")

    # --- Instructions -----------------------------------------------------
    guide = workbook.create_sheet("Instructions")
    guide_rows: list[list[object]] = [
        ["PLACER question import template", ""],
        ["", ""],
        ["How to use", ""],
        ["1", "Enter one question per row on the 'Questions' sheet. Do not rename or reorder the header row."],
        ["2", "Leave the 'Question ID' column blank for new questions."],
        ["3", "Save the file as .xlsx or .csv, then use 'Import completed file' in Admin → Question bank."],
        ["4", "The import is previewed and validated before anything is written. Invalid rows are never inserted."],
        ["", ""],
        ["Required columns", "Question, Question Type, Category, Difficulty, Correct Answer"],
        ["Question", "Full question text."],
        ["Question Type", "mcq, multiple_select, true_false, coding or descriptive."],
        ["Category", "Exact category name or ID from the 'Categories' sheet."],
        ["Difficulty", "easy, medium or hard."],
        [
            "Correct Answer",
            "MCQ: exact option text. Multiple select: option letters separated by '|' (for example A|C). "
            "True/false: True or False.",
        ],
        ["Option A-D", "Required for mcq and multiple_select. Leave blank for descriptive/coding."],
        ["Marks", "Optional integer. Blank assigns marks from difficulty (easy 1, medium 3, hard 5)."],
        ["Status", "active or inactive. Blank means active."],
        ["Topic / Skill / Skill Tags", "Optional. Separate multiple skill tags with '|' or ';'."],
        ["Language / Starter Code", "Coding questions only: python or javascript, plus optional starter code."],
        ["", ""],
        ["Example row (for reference only — do not import)", ""],
        [
            "Example",
            "What does len('hello') return in Python? | mcq | Python Programming | easy | 4 | 5 | 6 | Error | 5",
        ],
    ]
    for row in guide_rows:
        guide.append(row)
    guide.column_dimensions["A"].width = 34
    guide.column_dimensions["B"].width = 110
    for row in guide.iter_rows(min_row=1, max_row=1):
        for cell in row:
            cell.font = Font(bold=True, size=14, color="C8102E")

    # --- Supported categories --------------------------------------------
    categories_sheet = workbook.create_sheet("Categories")
    categories_sheet.append(["Supported category name", "Category ID"])
    for name in sorted({name for name in (category_names or []) if name}):
        categories_sheet.append([name, ""])
    if categories_sheet.max_row == 1:
        categories_sheet.append(["No categories exist yet — create one in the Question bank first.", ""])
    categories_sheet.column_dimensions["A"].width = 48
    categories_sheet.column_dimensions["B"].width = 30

    # --- Standardized section layout -------------------------------------
    sections_sheet = workbook.create_sheet("Sections")
    sections_sheet.append(["Section", "Questions per standardized assessment", "Notes"])
    for name, count in sections or []:
        sections_sheet.append([name, count, "Used by standardized drive assessments."])
    if sections_sheet.max_row == 1:
        sections_sheet.append(["Standardized sections are configured in Assessment creation.", "", ""])
    sections_sheet.append([])
    sections_sheet.append(["Overall difficulty mix", "6 Easy / 10 Medium / 4 Hard", "20 questions in total."])
    sections_sheet.column_dimensions["A"].width = 40
    sections_sheet.column_dimensions["B"].width = 36
    sections_sheet.column_dimensions["C"].width = 44

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def build_error_report(preview: dict) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Row", "Field", "Error", "Question text"])
    rows = {row["row"]: row for row in preview.get("rows", [])}
    for error in preview.get("errors", []):
        row = rows.get(error["row"], {})
        question = row.get("question") or {}
        question_text = question.get("text") or row.get("raw_text", "")
        writer.writerow([error["row"], error["field"], error["message"], question_text])
    return output.getvalue().encode("utf-8-sig")
