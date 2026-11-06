"""
Tool: Build Print Pack
Repeat each ARC / demand notice once per person (applicant, co-applicants,
guarantors) with an optional extra office set. Builds one print-ready PDF
and a checklist Excel from an allocation sheet + notice PDF/Word.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
import threading
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pypdf import PdfReader, PdfWriter
from window_fit import fit_to_screen, add_run_footer, add_primary_run_button

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Build_Print_Pack")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#30d158", "green": "#30d158",
    "red": "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#0a2414", "mid": "#0f3a20", "bdr": "#145c30"}

EXCEL_EXTS = {".xlsb", ".xlsx", ".xlsm", ".xls"}
PDF_EXT = ".pdf"
WORD_EXT = ".docx"


@dataclass
class Person:
    role: str
    name: str


@dataclass
class Case:
    sr: str
    reference: str
    agreement: str
    borrower: str
    people: list[Person] = field(default_factory=list)


@dataclass
class Notice:
    case: Case
    start: int  # first PDF page, 0-based
    end: int  # page after the last page, 0-based

    @property
    def page_count(self) -> int:
        return self.end - self.start

    @property
    def source_label(self) -> str:
        first = self.start + 1
        last = self.end
        if first == last:
            return str(first)
        return f"{first}-{last}"


class PackError(Exception):
    """User-facing build failure."""


def get_output_dir() -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def cell_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.strftime("%d-%b-%Y")
    return str(value).replace("\xa0", " ").strip()


def norm_header(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def compact_ref(text: str) -> str:
    text = text.upper()
    for ch in ("\u2019", "\u2018", "`", "\u2032", "\u02bc"):
        text = text.replace(ch, "'")
    return re.sub(r"\s+", "", text)


def compact_name(text: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def reference_on_page(page_text: str, reference: str) -> bool:
    token = compact_ref(reference)
    if not token:
        return False
    hay = compact_ref(page_text)
    start = 0
    while True:
        found = hay.find(token, start)
        if found < 0:
            return False
        before = hay[found - 1:found]
        after = hay[found + len(token):found + len(token) + 1]
        before_ok = not before or not before.isalnum()
        if token[-1].isdigit():
            after_ok = not after or not after.isdigit()
        else:
            after_ok = not after or not after.isalpha()
        if before_ok and after_ok:
            return True
        start = found + 1


def parse_table(rows: list[list[str]]) -> list[Case] | None:
    header_at = None
    columns: dict[str, int] = {}
    co_apps: dict[int, int] = {}
    guarantors: dict[int, int] = {}

    for index, row in enumerate(rows[:20]):
        found_ref = None
        found_name = None
        found_agreement = None
        found_sr = None
        found_co: dict[int, int] = {}
        found_guar: dict[int, int] = {}
        for col, raw in enumerate(row):
            header = norm_header(raw)
            if not header:
                continue
            if header in {"reference no", "reference number", "ref no", "ref number"}:
                found_ref = col
            elif header in {"name", "applicant name", "borrower", "borrower name"}:
                if found_name is None or header == "name":
                    found_name = col
            elif header in {"agreement no", "agreement number", "agreement"}:
                found_agreement = col
            elif header in {"sr no", "serial no", "s no", "sr"}:
                found_sr = col
            else:
                co_match = re.fullmatch(r"co app(?:licant)? (\d+)", header)
                guar_match = re.fullmatch(r"guarantor (\d+)", header)
                if co_match:
                    number = int(co_match.group(1))
                    found_co.setdefault(number, col)
                elif guar_match:
                    number = int(guar_match.group(1))
                    found_guar.setdefault(number, col)
        if found_ref is not None and found_name is not None:
            header_at = index
            columns = {"reference": found_ref, "name": found_name}
            if found_agreement is not None:
                columns["agreement"] = found_agreement
            if found_sr is not None:
                columns["sr"] = found_sr
            co_apps = found_co
            guarantors = found_guar
            break

    if header_at is None:
        return None

    cases: list[Case] = []
    seen: dict[str, int] = {}
    for offset, row in enumerate(rows[header_at + 1:], start=header_at + 2):
        def value(key: str) -> str:
            col = columns.get(key)
            if col is None or col >= len(row):
                return ""
            return row[col]

        reference = value("reference")
        if not reference:
            continue
        key = compact_ref(reference)
        if key in seen:
            raise PackError(
                f"Reference {reference} is on Excel rows {seen[key]} and {offset}. "
                "Each reference has to appear once."
            )
        seen[key] = offset

        people: list[Person] = []
        borrower = value("name")
        if borrower:
            people.append(Person("Applicant", borrower))
        for number in sorted(co_apps):
            col = co_apps[number]
            name = row[col].strip() if col < len(row) else ""
            if name:
                people.append(Person(f"Co-applicant {number}", name))
        for number in sorted(guarantors):
            col = guarantors[number]
            name = row[col].strip() if col < len(row) else ""
            if name:
                people.append(Person(f"Guarantor {number}", name))
        if not people:
            raise PackError(
                f"Reference {reference} (Excel row {offset}) has no applicant, "
                "co-applicant, or guarantor."
            )

        cases.append(
            Case(
                sr=value("sr") or str(len(cases) + 1),
                reference=reference,
                agreement=value("agreement"),
                borrower=borrower or people[0].name,
                people=people,
            )
        )

    if not cases:
        raise PackError("The Excel file has a header row, but no notice rows under it.")
    return cases


def read_excel(path: Path) -> list[Case]:
    try:
        import win32com.client
    except ImportError as exc:
        raise PackError("pywin32 is required. pip install pywin32") from exc

    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    workbook = None
    try:
        workbook = excel.Workbooks.Open(str(path.resolve()), 0, True)
        parsed = None
        sheet_names = []
        for sheet in workbook.Worksheets:
            sheet_names.append(str(sheet.Name))
            used = sheet.UsedRange
            values = used.Value
            if values is None:
                continue
            nrows = used.Rows.Count
            ncols = used.Columns.Count
            if nrows == 1 and ncols == 1:
                table = [[cell_str(values)]]
            elif nrows == 1:
                table = [[cell_str(cell) for cell in values]]
            else:
                table = [[cell_str(cell) for cell in row] for row in values]
            found = parse_table(table)
            if found is not None:
                parsed = found
                break
        if parsed is None:
            raise PackError(
                "Could not find columns named Reference No. and Name in "
                + path.name
                + ". Sheets: "
                + ", ".join(sheet_names)
            )
        return parsed
    except PackError:
        raise
    except Exception as exc:
        raise PackError(
            f"Excel could not open {path.name}. Close the file if it is open, then run again.\n{exc}"
        ) from exc
    finally:
        if workbook is not None:
            try:
                workbook.Close(False)
            except Exception:
                pass
        try:
            excel.Quit()
        except Exception:
            pass


def export_word_to_pdf(docx_path: Path, pdf_path: Path, log_fn=None) -> None:
    if log_fn:
        log_fn(f"Creating PDF from {docx_path.name}…")
    try:
        import win32com.client
    except ImportError as exc:
        raise PackError("pywin32 is required for Word → PDF. pip install pywin32") from exc

    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    document = None
    try:
        document = word.Documents.Open(str(docx_path.resolve()), False, True)
        document.ExportAsFixedFormat(str(pdf_path.resolve()), 17)
    except Exception as exc:
        raise PackError(f"Word could not create a PDF from {docx_path.name}.\n{exc}") from exc
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        try:
            word.Quit()
        except Exception:
            pass
    if not pdf_path.exists():
        raise PackError(f"Word did not create a PDF for {docx_path.name}.")


def load_pdf(path: Path) -> tuple[PdfReader, list[str]]:
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise PackError(f"Could not read {path.name}.\n{exc}") from exc
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise PackError(
                f"{path.name} is password protected. Open it without a password and run again."
            ) from exc
    texts = [(page.extract_text() or "") for page in reader.pages]
    if not texts:
        raise PackError(f"{path.name} has no pages.")
    return reader, texts


def ref_line(text: str) -> str:
    for line in text.splitlines():
        if re.search(r"\bREF\s*:", line, re.IGNORECASE):
            return " ".join(line.split())
    squashed = " ".join(text.split())
    return squashed[:180] if squashed else "(blank page)"


def split_notices(texts: list[str], cases: list[Case]) -> list[Notice]:
    by_key = {compact_ref(case.reference): case for case in cases}
    ref_pages = [
        index for index, text in enumerate(texts)
        if re.search(r"\bREF\s*:", text, re.IGNORECASE)
    ]

    starts: dict[str, int] = {}
    if ref_pages:
        for index in ref_pages:
            matches = [case for case in cases if reference_on_page(texts[index], case.reference)]
            snippet = ref_line(texts[index])
            if len(matches) != 1:
                if not matches:
                    raise PackError(
                        f"Page {index + 1} looks like a notice, but its reference "
                        f"is not in the Excel file.\n{snippet}"
                    )
                names = ", ".join(case.reference for case in matches)
                raise PackError(
                    f"Page {index + 1} matches more than one Excel reference ({names}).\n{snippet}"
                )
            key = compact_ref(matches[0].reference)
            if key in starts:
                raise PackError(
                    f"Reference {matches[0].reference} is on page {starts[key] + 1} "
                    f"and again on page {index + 1}."
                )
            starts[key] = index
        missing = [case.reference for case in cases if compact_ref(case.reference) not in starts]
        if missing:
            preview = ", ".join(missing[:12])
            more = "" if len(missing) <= 12 else f" (+{len(missing) - 12} more)"
            raise PackError(
                "These Excel references were not found on a notice page:\n"
                + preview
                + more
                + "\nThe Excel reference has to be printed on the first page of that notice."
            )
    else:
        for case in cases:
            pages = [
                index for index, text in enumerate(texts)
                if reference_on_page(text, case.reference)
            ]
            if not pages:
                raise PackError(
                    f"Could not find reference {case.reference} in the notice file. "
                    "The reference has to be printed on the first page of that notice."
                )
            starts[compact_ref(case.reference)] = pages[0]

    if len(starts) != len(by_key):
        raise PackError("The notice file and the Excel file do not have the same references.")

    ordered = sorted(starts.items(), key=lambda item: item[1])
    first_page = ordered[0][1]
    if first_page > 0 and any(texts[index].strip() for index in range(first_page)):
        raise PackError(
            f"The notice file has text on {first_page} page(s) before the first notice. "
            "Those pages were not matched to the Excel file."
        )

    notices: list[Notice] = []
    for position, (key, start) in enumerate(ordered):
        end = ordered[position + 1][1] if position + 1 < len(ordered) else len(texts)
        if end <= start:
            raise PackError(f"Reference {by_key[key].reference} has no pages.")
        notices.append(Notice(case=by_key[key], start=start, end=end))
    return notices


def check_names(notices: list[Notice], texts: list[str]) -> None:
    problems: list[str] = []
    for notice in notices:
        blob = compact_name("\n".join(texts[notice.start:notice.end]))
        for person in notice.case.people:
            token = compact_name(person.name)
            if len(token) < 3 or token not in blob:
                problems.append(f"  {notice.case.reference}: {person.role} — {person.name}")
    if problems:
        shown = "\n".join(problems[:20])
        extra = f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else ""
        raise PackError(
            "These Excel names were not found on the matching notice. "
            "Use the Excel and the notice file from the same batch.\n"
            + shown
            + extra
        )


def sets_for(case: Case, extra_copy: bool) -> list[Person]:
    people = list(case.people)
    if extra_copy:
        people.append(Person("Office copy", "Do not post. Keep this set for your file."))
    return people


def page_span(start: int, end: int) -> str:
    if start == end:
        return str(start)
    return f"{start}-{end}"


def build_print_pdf(
    reader: PdfReader,
    notices: list[Notice],
    extra_copy: bool,
    output_path: Path,
) -> int:
    writer = PdfWriter()
    set_plan = [(notice, sets_for(notice.case, extra_copy)) for notice in notices]
    total_sheets = sum(notice.page_count * len(sets) for notice, sets in set_plan)

    for notice, sets in set_plan:
        for _person in sets:
            for index in range(notice.start, notice.end):
                writer.add_page(reader.pages[index])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("wb") as handle:
            writer.write(handle)
    except PermissionError as exc:
        raise PackError(
            f"Could not write {output_path.name}. Close it if it is open in a PDF viewer, then run again."
        ) from exc

    written = len(PdfReader(str(output_path)).pages)
    if written != total_sheets:
        raise PackError(f"The print file has {written} pages, but it should have {total_sheets}.")
    return written


def write_checklist(
    path: Path,
    notices: list[Notice],
    extra_copy: bool,
    notice_path: Path,
    excel_path: Path,
) -> None:
    workbook = Workbook()
    notices_sheet = workbook.active
    notices_sheet.title = "Notices"
    sets_sheet = workbook.create_sheet("Sets")

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F4E79")
    office_fill = PatternFill("solid", fgColor="F8E6E8")
    wrap = Alignment(wrap_text=True, vertical="top")

    notice_headers = [
        "Sr", "Reference", "Agreement No.", "Borrower", "People", "Names",
        "Extra office copy", "Sets", "Notice pages", "Source pages", "Print file pages",
    ]
    set_headers = [
        "Sr", "Reference", "Agreement No.", "Borrower", "Set", "Sets",
        "Role", "Name", "Source pages", "Print file pages",
    ]

    def write_headers(sheet, headers):
        sheet.append(headers)
        for col, _header in enumerate(headers, start=1):
            cell = sheet.cell(1, col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(vertical="center")
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
        sheet.row_dimensions[1].height = 22

    write_headers(notices_sheet, notice_headers)
    write_headers(sets_sheet, set_headers)

    cursor = 1
    for notice in notices:
        sets = sets_for(notice.case, extra_copy)
        block = notice.page_count * len(sets)
        print_range = page_span(cursor, cursor + block - 1)
        names = "; ".join(f"{person.role}: {person.name}" for person in notice.case.people)
        notices_sheet.append(
            [
                notice.case.sr,
                notice.case.reference,
                notice.case.agreement,
                notice.case.borrower,
                len(notice.case.people),
                names,
                "Yes" if extra_copy else "No",
                len(sets),
                notice.page_count,
                notice.source_label,
                print_range,
            ]
        )
        for number, person in enumerate(sets, start=1):
            set_end = cursor + notice.page_count - 1
            row = [
                notice.case.sr,
                notice.case.reference,
                notice.case.agreement,
                notice.case.borrower,
                number,
                len(sets),
                person.role,
                person.name,
                notice.source_label,
                page_span(cursor, set_end),
            ]
            sets_sheet.append(row)
            if person.role == "Office copy":
                for col in range(1, len(row) + 1):
                    sets_sheet.cell(sets_sheet.max_row, col).fill = office_fill
            cursor = set_end + 1

    for sheet in (notices_sheet, sets_sheet):
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = wrap
        for column in sheet.columns:
            letter = get_column_letter(column[0].column)
            width = 14
            for cell in column:
                if cell.value is not None:
                    width = max(width, min(48, len(str(cell.value)) + 2))
            sheet.column_dimensions[letter].width = width

    info = workbook.create_sheet("Files", 0)
    info["A1"] = "Notice file"
    info["B1"] = notice_path.name
    info["A2"] = "Excel file"
    info["B2"] = excel_path.name
    info["A3"] = "Extra office copy"
    info["B3"] = "Yes" if extra_copy else "No"
    info["A4"] = "Print"
    info["B4"] = (
        "Whole file, one side of the paper, actual size. Each notice is already "
        "repeated once per person, plus the office set when that option is on. "
        "The checklist is the log of who each set is for."
    )
    for r in range(1, 5):
        info.cell(r, 1).font = Font(bold=True)
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 88

    try:
        workbook.save(path)
    except PermissionError as exc:
        raise PackError(
            f"Could not write {path.name}. Close it if it is open in Excel, then run again."
        ) from exc


def run_build(
    excel_path: Path,
    notice_path: Path,
    out_dir: Path,
    extra_copy: bool,
    log_fn,
    progress_fn,
) -> dict:
    log_fn(f"Excel   → {excel_path.name}")
    log_fn(f"Notices → {notice_path.name}")
    log_fn(f"Office  → {'Yes (extra set)' if extra_copy else 'No'}")
    log_fn(f"Output  → {out_dir}\n")
    progress_fn(0.05)

    log_fn("Reading Excel…")
    cases = read_excel(excel_path)
    log_fn(f"  {len(cases):,} cases (references)")
    progress_fn(0.20)

    with tempfile.TemporaryDirectory() as temp_dir:
        if notice_path.suffix.lower() == WORD_EXT:
            pdf_path = Path(temp_dir) / (notice_path.stem + ".pdf")
            export_word_to_pdf(notice_path, pdf_path, log_fn)
        else:
            pdf_path = notice_path

        log_fn("Reading notice PDF…")
        reader, texts = load_pdf(pdf_path)
        log_fn(f"  {len(texts):,} pages")
        progress_fn(0.40)

        log_fn("Matching references to pages…")
        notices = split_notices(texts, cases)
        progress_fn(0.55)

        log_fn("Checking names on notices…")
        check_names(notices, texts)
        progress_fn(0.65)

        excel_order = [compact_ref(case.reference) for case in cases]
        pdf_order = [compact_ref(notice.case.reference) for notice in notices]
        if excel_order != pdf_order:
            log_fn("⚠ Print file follows notice-file order (not Excel row order).")

        total_sets = 0
        log_fn("")
        for notice in notices:
            count = len(sets_for(notice.case, extra_copy))
            total_sets += count
            extra = " + office" if extra_copy else ""
            log_fn(
                f"  {notice.case.reference}  src {notice.source_label}  "
                f"{len(notice.case.people)} people{extra} = {count} sets  "
                f"{notice.case.borrower}"
            )
        log_fn(f"\n{len(notices)} notices, {total_sets} sets")
        progress_fn(0.75)

        stem = notice_path.stem
        print_path = out_dir / f"Print_Ready_{stem}.pdf"
        checklist_path = out_dir / f"Print_Checklist_{stem}.xlsx"

        log_fn(f"\nWriting {print_path.name}…")
        pages = build_print_pdf(reader, notices, extra_copy, print_path)
        progress_fn(0.90)

        log_fn(f"Writing {checklist_path.name}…")
        write_checklist(checklist_path, notices, extra_copy, notice_path, excel_path)
        progress_fn(1.0)

    return {
        "notices": len(notices),
        "sets": total_sets,
        "pages": pages,
        "print_pdf": str(print_path),
        "checklist": str(checklist_path),
    }


# ─── UI ───────────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Build Print Pack")
        self.configure(fg_color=C["bg"])
        fit_to_screen(self, 760, 700)
        self._excel = None
        self._notice = None
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)
        ctk.CTkLabel(
            inn, text="📦  Build Print Pack",
            font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            inn,
            text="Repeat each notice once per person (+ optional office set) → one print PDF",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(anchor="w")

        _, fi, self._prog, self._stat = add_run_footer(self, C, TINT)
        self._run_btn = add_primary_run_button(
            fi, "▶  Build Print Pack", self._start, C, TINT,
        )

        body = ctk.CTkScrollableFrame(
            self, fg_color="transparent", scrollbar_button_color=C["border"],
        )
        body.pack(fill="both", expand=True, padx=24, pady=(12, 8))

        banner = ctk.CTkFrame(
            body, fg_color=TINT["bg"], corner_radius=10,
            border_width=1, border_color=C["accent"],
        )
        banner.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\Build_Print_Pack\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"],
        ).pack(anchor="w", padx=14, pady=8)

        self._sec(body, "Excel allocation (Reference No + Name + Co-app / Guarantor)")
        self._excel_lbl = self._file_row(body, "Browse Excel…", self._pick_excel)

        self._sec(body, "Notice file (PDF or Word)")
        self._notice_lbl = self._file_row(body, "Browse PDF / Word…", self._pick_notice)

        self._sec(body, "Options")
        opts = ctk.CTkFrame(
            body, fg_color=C["card"], corner_radius=12,
            border_width=1, border_color=C["border"],
        )
        opts.pack(fill="x", pady=(0, 12))
        self._extra_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts,
            text="Extra office copy (one extra set of each notice for your file)",
            variable=self._extra_var,
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["text"], fg_color=C["accent"],
            hover_color=TINT["bdr"], border_color=C["border"],
        ).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkLabel(
            opts,
            text="Excel needs Reference No. and Name. Optional: Agreement No., Sr No., "
                 "Co-applicant 1…, Guarantor 1…. References must appear on the first page "
                 "of each notice. Print the whole PDF one-sided at actual size.",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
            wraplength=680, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        self._sec(body, "Log")
        self._log = ctk.CTkTextbox(
            body, height=220, font=ctk.CTkFont("Courier New", 11),
            fg_color=C["card"], border_color=C["border"],
            border_width=1, text_color=C["muted"], state="disabled",
        )
        self._log.pack(fill="x", pady=(0, 12))

    def _sec(self, p, t):
        ctk.CTkLabel(
            p, text=t, font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color=C["text"], anchor="w",
        ).pack(fill="x", pady=(10, 2))

    def _file_row(self, parent, btn_text, command):
        fr = ctk.CTkFrame(parent, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 8))
        lbl = ctk.CTkLabel(
            fr, text="No file selected", font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w",
        )
        lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr, text=btn_text, width=140, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=command,
        ).pack(side="right")
        return lbl

    def _write(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _pick_excel(self):
        path = filedialog.askopenfilename(
            title="Select Excel allocation",
            filetypes=[
                ("Excel files", "*.xlsx *.xlsm *.xlsb *.xls"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._excel = path
            self._excel_lbl.configure(
                text=os.path.basename(path), text_color=C["accent"],
            )

    def _pick_notice(self):
        path = filedialog.askopenfilename(
            title="Select notice PDF or Word",
            filetypes=[
                ("Notice files", "*.pdf *.docx"),
                ("PDF", "*.pdf"),
                ("Word", "*.docx"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self._notice = path
            self._notice_lbl.configure(
                text=os.path.basename(path), text_color=C["accent"],
            )

    def _start(self):
        if not self._excel:
            messagebox.showwarning("Missing", "Select the Excel allocation file.")
            return
        if not self._notice:
            messagebox.showwarning("Missing", "Select the notice PDF or Word file.")
            return
        excel = Path(self._excel)
        notice = Path(self._notice)
        if excel.suffix.lower() not in EXCEL_EXTS:
            messagebox.showwarning("Invalid", "Excel must be .xlsx / .xlsm / .xlsb / .xls")
            return
        if notice.suffix.lower() not in {PDF_EXT, WORD_EXT}:
            messagebox.showwarning("Invalid", "Notice must be a .pdf or .docx file.")
            return

        extra = bool(self._extra_var.get())
        self._run_btn.configure(state="disabled", text="Building…")
        self._prog.set(0)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run, args=(excel, notice, extra), daemon=True,
        ).start()

    def _run(self, excel: Path, notice: Path, extra: bool):
        out_dir = Path(get_output_dir())

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        def prog(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            stats = run_build(excel, notice, out_dir, extra, log, prog)
            log("\n========== SUMMARY ==========")
            log(f"Notices   : {stats['notices']}")
            log(f"Sets      : {stats['sets']}")
            log(f"Pages     : {stats['pages']}")
            log(f"Print PDF : {stats['print_pdf']}")
            log(f"Checklist : {stats['checklist']}")
            log("\nPrint the whole PDF one-sided at actual size.")
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {stats['notices']} notices, {stats['sets']} sets, {stats['pages']} pages.",
                text_color=C["green"],
            ))
            self.after(0, lambda: subprocess.Popen(["explorer", str(out_dir)]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Notices: {stats['notices']}\n"
                f"Sets: {stats['sets']}\n"
                f"Pages: {stats['pages']}\n\n{out_dir}",
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda err=str(e): messagebox.showerror("Error", err))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Build Print Pack",
            ))


if __name__ == "__main__":
    App().mainloop()
