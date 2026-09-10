"""
Tool: UCP Format PDF
Group Excel rows by Prospect No (or any column), format each group as a
styled Excel sheet with a custom header, export to PDF, then merge.
"""

import os
import re
import json
import threading
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import customtkinter as ctk
from tkinter import filedialog, messagebox
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side, Font
from openpyxl.utils import get_column_letter
from PyPDF2 import PdfMerger
try:
    from PyPDF2 import PdfReader, PdfWriter
except ImportError:  # older PyPDF2
    from PyPDF2 import PdfFileReader as PdfReader, PdfFileWriter as PdfWriter

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "UCP_Format_PDF")

DEFAULT_GROUP_COL = "Prospect_No"
DEFAULT_NAME_COL = "Prospect_No"
DEFAULT_WIDE_COL = "Address"
DEFAULT_HEADER = "IIFL | Prospect No - {prospect_no}"
DEFAULT_BATCH = 500
DEFAULT_SHEETS_PER_BOOK = 50  # groups packed into one Excel open/export (big speedup)
WIDE_WIDTH = 70
LOG_EVERY = 1  # log every N batches (each batch = sheets_per_book groups)
CHUNK_META_NAME = "chunk_split_meta.json"


class CancelledError(Exception):
    """Raised when the user cancels a running UCP job."""
    pass


C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#ff9f0a", "green":  "#30d158",
    "red":    "#ff375f",
}
TINT = {"bg": "#2e1e00", "mid": "#4a3000", "bdr": "#6b4500"}


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def find_column(columns, preferred_names):
    """Case-insensitive / partial match for a column name."""
    lower_map = {str(c).strip().lower(): c for c in columns}
    for name in preferred_names:
        key = name.lower()
        if key in lower_map:
            return lower_map[key]
    for name in preferred_names:
        key = name.lower()
        for col_l, col in lower_map.items():
            if key in col_l:
                return col
    return None


PROSPECT_COL_NAMES = (
    DEFAULT_GROUP_COL, "prospect_no", "Prospect No", "ProspectNo", "Prospect Number",
)


def pick_prospect_no(group_df, group_value):
    """
    Value for {prospect_no}: always from a Prospect_No column when present,
    not from the group-by key (which may be barcode / another ID).
    """
    prospect_col = find_column(group_df.columns, list(PROSPECT_COL_NAMES))
    if prospect_col is None:
        return group_value
    series = group_df[prospect_col].dropna()
    if series.empty:
        return group_value
    vals = series.astype(str).str.strip()
    vals = vals[vals != ""]
    unique = vals.unique()
    if len(unique) == 0:
        return group_value
    return unique[0]


def pick_filename(group_df, name_col, fallback):
    """First non-blank value from the chosen filename column (fallback: group key)."""
    if name_col and name_col in group_df.columns:
        series = group_df[name_col].dropna().astype(str).str.strip()
        series = series[(series != "") & (~series.str.lower().isin(["nan", "none", "nat"]))]
        if len(series) > 0:
            return series.iloc[0]
    return fallback


def safe_filename(raw) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", str(raw).strip())
    return name or "unnamed"


def unique_pdf_path(folder, base_name, used: set) -> str:
    """Build a unique .pdf path inside folder; tracks used basenames (case-insensitive)."""
    base = safe_filename(base_name)[:120]
    name = base
    n = 1
    while name.lower() in used:
        suffix = f"_{n}"
        name = base[: max(1, 120 - len(suffix))] + suffix
        n += 1
    used.add(name.lower())
    return os.path.join(folder, f"{name}.pdf")


def save_chunk_meta(out_dir, chunk_meta, name_col=None, group_col=None):
    """
    Persist split metadata next to the run so 'Split chunks only' can reuse it.
    chunk_meta: list of (pdf_path, filenames, page_counts)
    """
    payload = {
        "version": 1,
        "name_col": name_col,
        "group_col": group_col,
        "chunks": [
            {
                "file": os.path.basename(pdf_path),
                "filenames": [str(x) for x in filenames],
                "page_counts": [int(x) for x in (page_counts or [])],
            }
            for pdf_path, filenames, page_counts in chunk_meta
        ],
    }
    meta_path = os.path.join(out_dir, CHUNK_META_NAME)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return meta_path


def load_chunk_meta(run_dir):
    """
    Load chunk_split_meta.json from a previous run folder.
    Accepts the run root, or its output_pdfs subfolder.
    Returns (meta_path, chunks_dir, list[(pdf_path, filenames, page_counts)]).
    """
    run_dir = os.path.abspath(run_dir)
    candidates = [
        os.path.join(run_dir, CHUNK_META_NAME),
        os.path.join(os.path.dirname(run_dir), CHUNK_META_NAME),
    ]
    # Also allow selecting the output_pdfs folder
    if os.path.basename(run_dir).lower() == "output_pdfs":
        candidates.insert(0, os.path.join(os.path.dirname(run_dir), CHUNK_META_NAME))

    meta_path = next((p for p in candidates if os.path.isfile(p)), None)
    if not meta_path:
        raise FileNotFoundError(
            f"Could not find {CHUNK_META_NAME} near:\n{run_dir}\n\n"
            "Pick the previous run folder (the timestamp folder), or re-run "
            "From Excel once so metadata is saved."
        )

    root = os.path.dirname(meta_path)
    with open(meta_path, encoding="utf-8") as f:
        payload = json.load(f)

    chunks_dir = os.path.join(root, "output_pdfs")
    if not os.path.isdir(chunks_dir):
        # meta next to loose PDFs
        chunks_dir = root if any(
            fn.lower().endswith(".pdf") for fn in os.listdir(root)
        ) else chunks_dir

    if not os.path.isdir(chunks_dir):
        raise FileNotFoundError(f"Chunk PDF folder not found:\n{chunks_dir}")

    chunk_meta = []
    missing = []
    for item in payload.get("chunks", []):
        fname = item.get("file")
        pdf_path = os.path.join(chunks_dir, fname) if fname else ""
        if not pdf_path or not os.path.isfile(pdf_path):
            missing.append(fname or "?")
            continue
        chunk_meta.append((
            pdf_path,
            list(item.get("filenames") or []),
            list(item.get("page_counts") or []),
        ))

    if missing:
        raise FileNotFoundError(
            "Some chunk PDFs listed in metadata are missing:\n"
            + "\n".join(f"  - {m}" for m in missing[:20])
            + (f"\n  … and {len(missing) - 20} more" if len(missing) > 20 else "")
        )
    if not chunk_meta:
        raise ValueError(f"No chunk entries found in {meta_path}")

    return meta_path, chunks_dir, chunk_meta, root


def merge_pdfs(pdf_list, out_dir, batch_size, log_fn, progress_fn, cancel_check, progress_start=0.90, progress_end=0.98):
    """Merge PDFs into UCP_format.pdf using intermediate batches."""
    def _raise_if_cancelled(stage=""):
        if cancel_check and cancel_check():
            msg = "Cancelled by user"
            if stage:
                msg = f"{msg} ({stage})"
            raise CancelledError(msg)

    if not pdf_list:
        raise ValueError("No PDFs to merge.")

    batch_dir = os.path.join(out_dir, "output_batches")
    os.makedirs(batch_dir, exist_ok=True)

    batch_files = []
    merge_batch = max(1, min(int(batch_size or DEFAULT_BATCH), 500))
    batch_total = max(1, (len(pdf_list) + merge_batch - 1) // merge_batch)
    for i in range(0, len(pdf_list), merge_batch):
        _raise_if_cancelled("during merge")
        batch = pdf_list[i:i + merge_batch]
        batch_output = os.path.join(batch_dir, f"batch_{i // merge_batch + 1}.pdf")
        merger = PdfMerger()
        for pdf in batch:
            merger.append(pdf)
        merger.write(batch_output)
        merger.close()
        batch_files.append(batch_output)
        log_fn(f"  Batch → {os.path.basename(batch_output)} ({len(batch)} files)")
        frac = (i // merge_batch + 1) / batch_total
        progress_fn(progress_start + (progress_end - progress_start) * frac)

    _raise_if_cancelled("before final PDF")
    final_output = os.path.join(out_dir, "UCP_format.pdf")
    if len(batch_files) == 1:
        import shutil
        shutil.copy2(batch_files[0], final_output)
    else:
        merger = PdfMerger()
        for bf in batch_files:
            merger.append(bf)
        merger.write(final_output)
        merger.close()
    return final_output


def split_all_chunks(chunk_meta, single_dir, log_fn, progress_fn, cancel_check, progress_start=0.70, progress_end=0.90):
    """Split every chunk PDF in chunk_meta into singles. Returns (paths, errors)."""
    def _raise_if_cancelled(stage=""):
        if cancel_check and cancel_check():
            msg = "Cancelled by user"
            if stage:
                msg = f"{msg} ({stage})"
            raise CancelledError(msg)

    os.makedirs(single_dir, exist_ok=True)
    individual_pdfs = []
    errors = []
    used_names = set()
    total = max(1, len(chunk_meta))
    for i, (pdf_path, file_names, page_counts) in enumerate(chunk_meta, 1):
        _raise_if_cancelled(f"during split after {len(individual_pdfs)} singles")
        try:
            singles = split_chunk_pdf(
                pdf_path, file_names, page_counts, single_dir, used_names,
            )
            individual_pdfs.extend(singles)
            if i % LOG_EVERY == 0 or i == len(chunk_meta):
                log_fn(
                    f"  Split [{i}/{len(chunk_meta)}] "
                    f"{os.path.basename(pdf_path)} → {len(singles)} singles "
                    f"(total {len(individual_pdfs)})"
                )
        except Exception as e:
            errors.append((os.path.basename(pdf_path), f"split: {e}"))
            log_fn(f"❌ Split {os.path.basename(pdf_path)} — {e}")
        progress_fn(progress_start + (progress_end - progress_start) * (i / total))
    return individual_pdfs, errors


def list_chunk_pdfs(chunks_dir):
    """Return sorted chunk_XXXX.pdf paths from a folder (or its output_pdfs)."""
    chunks_dir = os.path.abspath(chunks_dir)
    if os.path.isdir(os.path.join(chunks_dir, "output_pdfs")):
        chunks_dir = os.path.join(chunks_dir, "output_pdfs")
    if not os.path.isdir(chunks_dir):
        raise FileNotFoundError(f"Chunk folder not found:\n{chunks_dir}")

    files = []
    for name in os.listdir(chunks_dir):
        if not name.lower().endswith(".pdf"):
            continue
        # Prefer chunk_0001.pdf style; still accept any pdf sorted by name
        files.append(name)
    # Prefer natural chunk_#### order
    chunkish = [f for f in files if re.match(r"(?i)^chunk_\d+", f)]
    use = sorted(chunkish) if chunkish else sorted(files)
    if not use:
        raise FileNotFoundError(f"No PDF files found in:\n{chunks_dir}")
    return [os.path.join(chunks_dir, f) for f in use], chunks_dir


def build_chunk_meta_from_excel(
    excel_path,
    chunks_dir,
    group_col,
    name_col,
    sheets_per_book,
    log_fn,
):
    """
    Rebuild split metadata from Excel + existing chunk PDFs.
    sheets_per_book must match the value used when the chunks were created.
    """
    sheets_per_book = max(1, int(sheets_per_book or DEFAULT_SHEETS_PER_BOOK))
    log_fn(f"Reading Excel → {excel_path}")
    data = pd.read_excel(excel_path, engine="openpyxl")
    data.columns = [str(c).strip() for c in data.columns]

    if group_col not in data.columns:
        found = find_column(data.columns, [group_col])
        if not found:
            raise ValueError(
                f"Group column '{group_col}' not found. "
                f"Available: {', '.join(map(str, data.columns))}"
            )
        group_col = found
        log_fn(f"Using group column → {group_col}")

    if name_col and name_col not in data.columns:
        found_name = find_column(data.columns, [name_col])
        name_col = found_name or name_col
    if not name_col or name_col not in data.columns:
        name_col = find_column(data.columns, list(PROSPECT_COL_NAMES)) or group_col
    log_fn(f"Filename → column '{name_col}'")

    grouped = data.groupby(group_col, sort=False)
    group_keys = [k for k in grouped.groups.keys() if not (pd.isna(k) or str(k).strip() == "")]
    total = len(group_keys)
    if total == 0:
        raise ValueError("No groups found in the Excel file.")

    chunk_paths, resolved_dir = list_chunk_pdfs(chunks_dir)
    n_books = (total + sheets_per_book - 1) // sheets_per_book
    log_fn(f"Groups   → {total}")
    log_fn(f"Expected chunks (groups/{sheets_per_book}) → {n_books}")
    log_fn(f"Found chunk PDFs → {len(chunk_paths)} in {resolved_dir}")

    if len(chunk_paths) != n_books:
        raise ValueError(
            f"Chunk count mismatch.\n\n"
            f"Excel groups: {total}\n"
            f"Groups / Excel file: {sheets_per_book}\n"
            f"Expected chunk PDFs: {n_books}\n"
            f"Found chunk PDFs: {len(chunk_paths)}\n\n"
            "Set 'Groups / Excel file' to the same value used when creating the chunks."
        )

    chunk_meta = []
    for book_i, pdf_path in enumerate(chunk_paths):
        start = book_i * sheets_per_book
        end = min(start + sheets_per_book, total)
        keys = group_keys[start:end]
        file_names = []
        for group_value in keys:
            g = grouped.get_group(group_value)
            file_names.append(pick_filename(g, name_col, group_value))
        # page_counts left empty → split_chunk_pdf infers from PDF page count
        chunk_meta.append((pdf_path, file_names, []))

    return chunk_meta, resolved_dir, total, group_col, name_col


def run_split_only(
    excel_path,
    chunks_dir,
    group_col,
    name_col,
    sheets_per_book,
    log_fn,
    progress_fn,
    cancel_check=None,
    merge_final=False,
    batch_size=DEFAULT_BATCH,
    out_dir=None,
):
    """
    Split existing chunk PDFs using filenames rebuilt from an Excel file.
    """
    def _raise_if_cancelled(stage=""):
        if cancel_check and cancel_check():
            msg = "Cancelled by user"
            if stage:
                msg = f"{msg} ({stage})"
            raise CancelledError(msg)

    progress_fn(0.02)
    chunk_meta, resolved_chunks, total_groups, group_col, name_col = build_chunk_meta_from_excel(
        excel_path, chunks_dir, group_col, name_col, sheets_per_book, log_fn,
    )

    # Write singles next to the chunk folder's parent run folder when possible
    parent = os.path.dirname(resolved_chunks)
    if os.path.basename(resolved_chunks).lower() == "output_pdfs":
        out_dir = out_dir or parent
    else:
        out_dir = out_dir or resolved_chunks

    single_dir = os.path.join(out_dir, "output_singles")
    os.makedirs(single_dir, exist_ok=True)

    log_fn(f"Output   → {out_dir}")
    progress_fn(0.05)

    _raise_if_cancelled("before split")
    log_fn(f"\n✂ Splitting {len(chunk_meta)} chunk PDFs into singles…")
    individual_pdfs, errors = split_all_chunks(
        chunk_meta, single_dir, log_fn, progress_fn, cancel_check,
        progress_start=0.05, progress_end=0.85,
    )
    log_fn(f"📄 Single PDFs → {single_dir} ({len(individual_pdfs)} files)")

    final_output = None
    if merge_final:
        if not individual_pdfs:
            raise ValueError("No single PDFs were created — nothing to merge.")
        log_fn(f"\nMerging {len(individual_pdfs)} single PDFs → UCP_format.pdf…")
        final_output = merge_pdfs(
            individual_pdfs, out_dir, batch_size, log_fn, progress_fn, cancel_check,
            progress_start=0.85, progress_end=0.98,
        )
        log_fn(f"🏁 Final single PDF → {final_output}")
    else:
        log_fn("\nFinal merge skipped (unchecked).")

    progress_fn(1.0)
    return {
        "created": total_groups,
        "errors": len(errors),
        "final_pdf": final_output,
        "groups": total_groups,
        "pdf_dir": resolved_chunks,
        "single_dir": single_dir,
        "chunks": len(chunk_meta),
        "singles": len(individual_pdfs),
        "split": True,
        "merged": merge_final and final_output is not None,
        "out_dir": out_dir,
    }


def split_chunk_pdf(chunk_pdf, filenames, page_counts, single_dir, used_names):
    """
    Split a multi-page chunk PDF into one PDF per group.
    filenames: display/name values in sheet order
    page_counts: pages belonging to each sheet (from Excel); may be adjusted
    Returns list of written single-PDF paths.
    """
    os.makedirs(single_dir, exist_ok=True)
    reader = PdfReader(chunk_pdf)
    total_pages = len(reader.pages)
    n = len(filenames)
    if n == 0:
        return []

    counts = list(page_counts) if page_counts else []
    if len(counts) != n:
        counts = [1] * n

    if sum(counts) != total_pages:
        if total_pages == n:
            counts = [1] * n
        elif total_pages > 0 and n > 0:
            # Distribute pages as evenly as possible, preserving order
            base, rem = divmod(total_pages, n)
            counts = [base + (1 if i < rem else 0) for i in range(n)]
            # Ensure no zero-page groups if possible
            if base == 0:
                counts = [1] * min(n, total_pages) + [0] * max(0, n - total_pages)

    paths = []
    page_idx = 0
    for name, n_pages in zip(filenames, counts):
        if n_pages <= 0 or page_idx >= total_pages:
            continue
        writer = PdfWriter()
        for _ in range(n_pages):
            if page_idx >= total_pages:
                break
            writer.add_page(reader.pages[page_idx])
            page_idx += 1
        out_path = unique_pdf_path(single_dir, name, used_names)
        with open(out_path, "wb") as f:
            writer.write(f)
        paths.append(out_path)
    return paths


def resolve_header(template: str, group_value, prospect_no=None) -> str:
    """
    Replace placeholders:
      {prospect_no} / {Prospect_No} → Prospect_No column value
      {group} / {GROUP}             → group-by column value
    If no placeholder is present, append the prospect no (fallback: group).
    """
    text = template or DEFAULT_HEADER
    p = prospect_no if prospect_no is not None else group_value
    g = group_value
    replacements = {
        "{prospect_no}": str(p),
        "{Prospect_No}": str(p),
        "{group}": str(g),
        "{GROUP}": str(g),
    }
    out = text
    for k, v in replacements.items():
        out = out.replace(k, v)
    if not any(k in text for k in replacements):
        out = f"{text} - {p}"
    return out


def _parse_one_date(val):
    """Parse a single date value; prefer DD-MM-YYYY for ambiguous strings."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return pd.NaT
    if isinstance(val, pd.Timestamp):
        return val
    if isinstance(val, datetime):
        return pd.Timestamp(val)
    # Excel serial number
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        try:
            return pd.to_datetime(val, unit="D", origin="1899-12-30", errors="coerce")
        except Exception:
            pass

    s = str(val).strip()
    if not s or s.lower() in ("nan", "nat", "none"):
        return pd.NaT

    # ISO / yyyy-mm-dd
    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}", s):
        return pd.to_datetime(s[:10], format="%Y-%m-%d", errors="coerce")

    # Explicit DD-MM-YYYY / DD/MM/YYYY (and 2-digit year)
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y", "%d.%m.%Y"):
        try:
            return pd.Timestamp(datetime.strptime(s[:10], fmt))
        except ValueError:
            continue

    # Last resort: day-first
    return pd.to_datetime(s, dayfirst=True, errors="coerce")


def _parse_date_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce")
    return series.map(_parse_one_date)


def format_date_columns(df: pd.DataFrame) -> tuple:
    """
    Format date-like columns as DD-MM-YYYY text.
    Ambiguous strings (08-03-2026) are treated as day-month-year.
    Stored as strings so Excel does not re-display them as MM-DD-YYYY.
    """
    df = df.copy()
    date_cols = []
    for col in df.columns:
        cl = str(col).strip().lower().replace("_", " ")
        if "date" in cl:
            date_cols.append(col)

    for col in date_cols:
        series = df[col]
        parsed = _parse_date_series(series)
        out = []
        for raw, ts in zip(series, parsed):
            if pd.isna(ts):
                out.append("" if pd.isna(raw) else str(raw).strip())
            else:
                out.append(pd.Timestamp(ts).strftime("%d-%m-%Y"))
        df[col] = out

    return df, date_cols


def drop_empty_columns(df: pd.DataFrame, keep=()) -> tuple:
    """
    Drop columns that are entirely empty (NaN / blank / whitespace).
    Always retains columns listed in `keep` when they exist.
    Returns (cleaned_df, list_of_dropped_column_names).
    """
    keep_set = {str(c) for c in keep}
    dropped = []
    keep_cols = []
    for col in df.columns:
        if col in keep_set:
            keep_cols.append(col)
            continue
        series = df[col]
        # Treat NaN and blank strings as empty
        nonempty = series.dropna().astype(str).str.strip()
        nonempty = nonempty[nonempty != ""]
        nonempty = nonempty[~nonempty.str.lower().isin(["nan", "none", "nat"])]
        if len(nonempty) == 0:
            dropped.append(col)
        else:
            keep_cols.append(col)
    return df[keep_cols].copy(), dropped



def _safe_sheet_name(raw: str, used: set) -> str:
    """Excel sheet names: max 31 chars, no special chars, unique in workbook."""
    name = re.sub(r'[:\\/?*\[\]]', "_", str(raw).strip()) or "Sheet"
    name = name[:31]
    base = name
    n = 1
    while name.lower() in used:
        suffix = f"_{n}"
        name = (base[: 31 - len(suffix)] + suffix)
        n += 1
    used.add(name.lower())
    return name


_THIN = Border(
    left=Side(style="thin"), right=Side(style="thin"),
    top=Side(style="thin"), bottom=Side(style="thin"),
)
_CENTER = Alignment(wrap_text=True, horizontal="center", vertical="center")
_HEADER_FONT = Font(bold=True, size=20)
_COL_FONT = Font(bold=True)


def add_styled_sheet(wb, sheet_name, group_df, header_text, wide_col_name, date_cols=None):
    """Append one styled sheet to an openpyxl Workbook (fast path)."""
    date_cols = set(date_cols or [])
    ws = wb.create_sheet(title=sheet_name)
    cols = list(group_df.columns)
    ncols = max(len(cols), 1)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    h = ws.cell(row=1, column=1, value=header_text)
    h.font = _HEADER_FONT
    h.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 35

    wide_idx = None
    date_idxs = set()
    for c_idx, col in enumerate(cols, 1):
        cell = ws.cell(row=2, column=c_idx, value=col)
        cell.font = _COL_FONT
        cell.alignment = _CENTER
        cell.border = _THIN
        name_l = str(col).strip().lower()
        if wide_col_name and name_l == str(wide_col_name).strip().lower():
            wide_idx = c_idx
        if col in date_cols or any(str(dc).strip().lower() == name_l for dc in date_cols):
            date_idxs.add(c_idx)

    # Write data via itertuples (much faster than cell-by-cell from pandas ExcelWriter)
    for r_idx, row in enumerate(group_df.itertuples(index=False, name=None), 3):
        for c_idx, val in enumerate(row, 1):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                val = ""
            elif c_idx in date_idxs:
                val = "" if (isinstance(val, float) and pd.isna(val)) else str(val)
            elif isinstance(val, float) and pd.isna(val):
                val = ""
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.alignment = _CENTER
            cell.border = _THIN
            if c_idx in date_idxs and val != "":
                cell.number_format = "@"
        ws.row_dimensions[r_idx].height = 45

    # Column widths from dataframe (avoid scanning worksheet cells)
    for c_idx, col in enumerate(cols, 1):
        letter = get_column_letter(c_idx)
        if wide_idx is not None and c_idx == wide_idx:
            ws.column_dimensions[letter].width = WIDE_WIDTH
            continue
        series = group_df.iloc[:, c_idx - 1]
        try:
            max_len = int(series.astype(str).str.len().max() or 0)
        except Exception:
            max_len = 10
        max_len = max(max_len, len(str(col)))
        ws.column_dimensions[letter].width = min(max_len + 2, 40)

    ws.row_dimensions[2].height = 45
    return ws


def write_batch_workbook(excel_path, sheet_specs):
    """
    Write many groups into one .xlsx (one sheet per group).
    sheet_specs: list of (sheet_name, group_df, header_text, wide_col_name, date_cols)
    """
    wb = Workbook()
    # remove default sheet
    wb.remove(wb.active)
    used = set()
    for raw_name, gdf, header_text, wide_col_name, date_cols in sheet_specs:
        name = _safe_sheet_name(raw_name, used)
        add_styled_sheet(wb, name, gdf, header_text, wide_col_name, date_cols)
    if not wb.sheetnames:
        # edge case: empty batch
        wb.create_sheet("Empty")
    wb.save(excel_path)
    wb.close()


def excel_book_to_pdf(excel_app, excel_path, pdf_path):
    """
    Open one multi-sheet workbook once, export all sheets to a single PDF,
    and return estimated page counts per sheet (for fast PDF splitting).
    """
    wb = excel_app.Workbooks.Open(os.path.abspath(excel_path), ReadOnly=True)
    try:
        try:
            excel_app.PrintCommunication = False
        except Exception:
            pass
        for ws in wb.Worksheets:
            ws.PageSetup.Orientation = 2  # xlLandscape
            ws.PageSetup.Zoom = False
            ws.PageSetup.FitToPagesWide = 1
            ws.PageSetup.FitToPagesTall = False
            ws.PageSetup.LeftMargin = 0.25 * 72
            ws.PageSetup.RightMargin = 0.25 * 72
            ws.PageSetup.TopMargin = 0.5 * 72
            ws.PageSetup.BottomMargin = 0.5 * 72
        try:
            excel_app.PrintCommunication = True
        except Exception:
            pass
        wb.ExportAsFixedFormat(0, os.path.abspath(pdf_path))

        # Page breaks are usually available after export
        page_counts = []
        for i in range(1, wb.Worksheets.Count + 1):
            ws = wb.Worksheets(i)
            try:
                h = int(ws.HPageBreaks.Count) + 1
                v = int(ws.VPageBreaks.Count) + 1
                page_counts.append(max(1, h * v))
            except Exception:
                page_counts.append(1)
        return page_counts
    finally:
        wb.Close(False)


def run_pipeline(
    input_file,
    out_dir,
    group_col,
    header_template,
    wide_col,
    batch_size,
    log_fn,
    progress_fn,
    cancel_check=None,
    sheets_per_book=DEFAULT_SHEETS_PER_BOOK,
    merge_final=False,
    name_col=None,
    split_singles=True,
):
    def _raise_if_cancelled(stage=""):
        if cancel_check and cancel_check():
            msg = "Cancelled by user"
            if stage:
                msg = f"{msg} ({stage})"
            raise CancelledError(msg)

    sheets_per_book = max(1, int(sheets_per_book or DEFAULT_SHEETS_PER_BOOK))
    batch_size = max(1, int(batch_size or DEFAULT_BATCH))
    merge_final = bool(merge_final)
    split_singles = bool(split_singles)

    excel_dir = os.path.join(out_dir, "output_excels")
    pdf_dir = os.path.join(out_dir, "output_pdfs")      # chunk PDFs
    single_dir = os.path.join(out_dir, "output_singles")  # split one-PDF-per-group
    batch_dir = os.path.join(out_dir, "output_batches")
    for d in (excel_dir, pdf_dir, batch_dir):
        os.makedirs(d, exist_ok=True)
    if split_singles:
        os.makedirs(single_dir, exist_ok=True)

    _raise_if_cancelled("before read")
    log_fn(f"Reading → {input_file}")
    data = pd.read_excel(input_file, engine="openpyxl")
    data.columns = [str(c).strip() for c in data.columns]

    if group_col not in data.columns:
        found = find_column(data.columns, [group_col])
        if not found:
            raise ValueError(
                f"Group column '{group_col}' not found. "
                f"Available: {', '.join(map(str, data.columns))}"
            )
        group_col = found
        log_fn(f"Using group column → {group_col}")

    prospect_col = find_column(data.columns, list(PROSPECT_COL_NAMES))
    keep_cols = [group_col]
    if prospect_col and prospect_col not in keep_cols:
        keep_cols.append(prospect_col)

    before_cols = list(data.columns)
    data, dropped_global = drop_empty_columns(data, keep=tuple(keep_cols))
    if dropped_global:
        log_fn(f"Dropped empty columns ({len(dropped_global)}): {', '.join(map(str, dropped_global))}")
    else:
        log_fn(f"Columns → {len(before_cols)} (none empty)")

    prospect_col = find_column(data.columns, list(PROSPECT_COL_NAMES))
    if prospect_col:
        log_fn(f"Header {{prospect_no}} → column '{prospect_col}'")
    else:
        log_fn(
            "⚠ No Prospect_No column found — "
            "{prospect_no} will use the group-by value"
        )

    # Filename column for split single PDFs (default Prospect_No)
    if name_col and name_col not in data.columns:
        found_name = find_column(data.columns, [name_col])
        name_col = found_name or name_col
    if not name_col or name_col not in data.columns:
        name_col = find_column(data.columns, list(PROSPECT_COL_NAMES)) or group_col
    log_fn(f"Filename → column '{name_col}' (used when splitting chunk PDFs)")

    wide_resolved = None
    if wide_col:
        wide_resolved = find_column(
            data.columns,
            [wide_col, "Address", "address", "Ref No", "ref no", "ref_no"],
        )
        if wide_resolved:
            log_fn(f"Wide column (width {WIDE_WIDTH}) → {wide_resolved}")
        else:
            log_fn(f"⚠ Wide column '{wide_col}' not found — using auto widths only")

    data, date_cols = format_date_columns(data)
    if date_cols:
        log_fn(f"Date columns (DD-MM-YYYY) → {', '.join(map(str, date_cols))}")

    _raise_if_cancelled("before grouping")
    grouped = data.groupby(group_col, sort=False)
    group_keys = [k for k in grouped.groups.keys() if not (pd.isna(k) or str(k).strip() == "")]
    total = len(group_keys)
    if total == 0:
        raise ValueError("No groups found in the Excel file.")

    n_books = (total + sheets_per_book - 1) // sheets_per_book
    log_fn(f"Groups   → {total} unique '{group_col}' values")
    log_fn(f"Speed    → {sheets_per_book} groups per Excel open ({n_books} opens)")
    out_bits = ["chunk PDFs"]
    if split_singles:
        out_bits.append("then split singles")
    if merge_final:
        out_bits.append("final merge")
    log_fn(f"Output   → {' → '.join(out_bits)}")
    log_fn(f"Header   → {header_template}\n")

    try:
        import win32com.client as win32
    except ImportError as e:
        raise RuntimeError(
            "pywin32 is required for Excel→PDF export. pip install pywin32"
        ) from e

    excel = win32.gencache.EnsureDispatch("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    try:
        excel.ScreenUpdating = False
    except Exception:
        pass
    try:
        excel.EnableEvents = False
    except Exception:
        pass
    try:
        excel.AskToUpdateLinks = False
    except Exception:
        pass

    created_groups = 0
    chunk_pdfs = []
    # Keep split metadata until ALL chunks are done
    chunk_meta = []  # list of (pdf_path, file_names, page_counts)
    individual_pdfs = []
    errors = []

    try:
        for book_i in range(n_books):
            _raise_if_cancelled(f"after {created_groups} group(s)")

            start = book_i * sheets_per_book
            end = min(start + sheets_per_book, total)
            keys = group_keys[start:end]

            sheet_specs = []
            file_names = []
            for group_value in keys:
                g = grouped.get_group(group_value).copy()
                wide_for_group = wide_resolved if wide_resolved in g.columns else None
                date_cols_group = [c for c in date_cols if c in g.columns]
                g.insert(0, "SrNo", range(1, len(g) + 1))
                prospect_no = pick_prospect_no(g, group_value)
                header_text = resolve_header(header_template, group_value, prospect_no)
                safe_sheet = re.sub(r'[<>:"/\\|?*]', "_", str(group_value).strip()) or "group"
                file_names.append(pick_filename(g, name_col, group_value))
                sheet_specs.append(
                    (safe_sheet, g, header_text, wide_for_group, date_cols_group)
                )

            excel_path = os.path.join(excel_dir, f"chunk_{book_i + 1:04d}.xlsx")
            pdf_path = os.path.join(pdf_dir, f"chunk_{book_i + 1:04d}.pdf")

            try:
                write_batch_workbook(excel_path, sheet_specs)
                page_counts = excel_book_to_pdf(excel, excel_path, pdf_path)
                created_groups += len(sheet_specs)
                chunk_pdfs.append(pdf_path)
                chunk_meta.append((pdf_path, file_names, page_counts))

                try:
                    os.remove(excel_path)
                except OSError:
                    pass
                if (book_i + 1) % LOG_EVERY == 0 or end == total:
                    log_fn(
                        f"✅ Chunk [{book_i + 1}/{n_books}] "
                        f"groups {start + 1}-{end}/{total} "
                        f"→ {os.path.basename(pdf_path)}"
                    )
            except Exception as e:
                errors.append((f"chunk_{book_i + 1:04d}", str(e)))
                log_fn(f"❌ Chunk [{book_i + 1}/{n_books}] — {e}")

            progress_fn(end / total * 0.70)
    finally:
        try:
            excel.Quit()
        except Exception:
            pass

    _raise_if_cancelled(f"after chunks — {created_groups} group(s) kept")

    if not chunk_pdfs:
        raise ValueError("No PDFs were created.")

    log_fn(f"\n📁 All chunks done → {pdf_dir} ({len(chunk_pdfs)} files)")

    # Always save metadata so "Split chunks only" can run later
    try:
        meta_path = save_chunk_meta(
            out_dir, chunk_meta, name_col=name_col, group_col=group_col,
        )
        log_fn(f"🧾 Split meta → {meta_path}")
    except Exception as e:
        log_fn(f"⚠ Could not save split meta: {e}")

    # Phase 2: split ALL chunk PDFs into singles (optional, default on)
    if split_singles:
        log_fn(f"\n✂ Splitting {len(chunk_meta)} chunk PDFs into singles…")
        individual_pdfs, split_errors = split_all_chunks(
            chunk_meta, single_dir, log_fn, progress_fn, cancel_check,
            progress_start=0.70, progress_end=0.90,
        )
        errors.extend(split_errors)
        log_fn(f"📄 Single PDFs → {single_dir} ({len(individual_pdfs)} files)")
    else:
        log_fn("\nSplit to singles skipped (unchecked).")
        progress_fn(0.90)

    final_output = None
    if merge_final:
        merge_list = individual_pdfs if individual_pdfs else chunk_pdfs
        label = "single" if individual_pdfs else "chunk"
        log_fn(f"\nMerging {len(merge_list)} {label} PDFs → UCP_format.pdf…")
        final_output = merge_pdfs(
            merge_list, out_dir, batch_size, log_fn, progress_fn, cancel_check,
            progress_start=0.90, progress_end=0.98,
        )
        log_fn(f"🏁 Final single PDF → {final_output}")
    else:
        log_fn("\nFinal merge skipped (unchecked).")

    progress_fn(1.0)
    return {
        "created": created_groups,
        "errors": len(errors),
        "final_pdf": final_output,
        "groups": total,
        "pdf_dir": pdf_dir,
        "single_dir": single_dir if split_singles else None,
        "chunks": len(chunk_pdfs),
        "singles": len(individual_pdfs),
        "split": split_singles,
        "merged": merge_final and final_output is not None,
        "out_dir": out_dir,
    }





class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("UCP Format PDF")
        self.geometry("780x820")
        self.configure(fg_color=C["bg"])
        self._path = None
        self._chunk_run_dir = None
        self._columns = []
        self._cancel_event = threading.Event()
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)
        ctk.CTkLabel(
            inn, text="📄  UCP Format PDF",
            font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            inn,
            text="Group Excel by Prospect No · styled sheets · PDF merge",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(anchor="w")

        body = ctk.CTkScrollableFrame(
            self, fg_color="transparent", scrollbar_button_color=C["border"],
        )
        body.pack(fill="both", expand=True, padx=24, pady=16)

        banner = ctk.CTkFrame(
            body, fg_color=TINT["bg"], corner_radius=10,
            border_width=1, border_color=C["accent"],
        )
        banner.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\UCP_Format_PDF\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"],
        ).pack(anchor="w", padx=14, pady=8)

        self._sec(body, "Mode")
        mode_fr = ctk.CTkFrame(body, fg_color="transparent")
        mode_fr.pack(fill="x", pady=(0, 10))
        self._mode_var = ctk.StringVar(value="From Excel")
        self._mode_seg = ctk.CTkSegmentedButton(
            mode_fr,
            values=["From Excel", "Split chunks only"],
            variable=self._mode_var,
            command=self._on_mode_change,
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["card"],
            selected_color=TINT["mid"],
            selected_hover_color=TINT["bdr"],
            unselected_color=C["hover"],
            unselected_hover_color=C["border"],
            text_color=C["text"],
        )
        self._mode_seg.set("From Excel")
        self._mode_seg.pack(fill="x")
        ctk.CTkLabel(
            mode_fr,
            text="Split chunks only: pick the Excel file + chunk PDF folder (same Groups / Excel file value as when created).",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=C["faint"],
            anchor="w",
        ).pack(fill="x", pady=(4, 0))

        self._excel_sec = ctk.CTkFrame(body, fg_color="transparent")
        self._excel_sec.pack(fill="x")
        self._sec(self._excel_sec, "Excel file")
        fr = ctk.CTkFrame(self._excel_sec, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 10))
        self._file_lbl = ctk.CTkLabel(
            fr, text="No file selected", font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w",
        )
        self._file_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick,
        ).pack(side="right")

        self._chunk_sec = ctk.CTkFrame(body, fg_color="transparent")
        # packed/unpacked by mode
        self._sec(self._chunk_sec, "Chunk PDF folder")
        cfr = ctk.CTkFrame(self._chunk_sec, fg_color="transparent")
        cfr.pack(fill="x", pady=(0, 10))
        self._chunk_lbl = ctk.CTkLabel(
            cfr, text="No folder selected", font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w",
        )
        self._chunk_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            cfr, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_chunk_run,
        ).pack(side="right")
        ctk.CTkLabel(
            self._chunk_sec,
            text="Select the folder with chunk_0001.pdf… (or the run folder containing output_pdfs).",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=C["faint"],
            anchor="w",
        ).pack(fill="x", pady=(0, 8))

        self._sec(body, "Settings")
        self._settings = ctk.CTkFrame(
            body, fg_color=C["card"], corner_radius=12,
            border_width=1, border_color=C["border"],
        )
        self._settings.pack(fill="x", pady=(0, 10))
        self._settings.columnconfigure(1, weight=1)
        settings = self._settings

        self._excel_only_widgets = []

        self._group_cb = self._dropdown(
            settings, 0, "Group by column",
            [DEFAULT_GROUP_COL],
            DEFAULT_GROUP_COL,
            "Select the ID column after loading an Excel file (default Prospect_No).",
        )
        self._name_cb = self._dropdown(
            settings, 1, "Filename column",
            [DEFAULT_NAME_COL],
            DEFAULT_NAME_COL,
            "Used to name each split single PDF (default Prospect_No).",
        )
        self._header_e = self._field(
            settings, 2, "Header text", DEFAULT_HEADER,
            "Use {prospect_no} for Prospect No, {group} for the group-by value.",
        )
        self._wide_cb = self._dropdown(
            settings, 3, "Wide column",
            [DEFAULT_WIDE_COL],
            DEFAULT_WIDE_COL,
            "Column that gets width 70 (default Address). Others auto-size.",
        )
        self._speed_e = self._field(
            settings, 4, "Groups / Excel file", str(DEFAULT_SHEETS_PER_BOOK),
            "Higher = much faster (50–80 recommended). Each Excel open exports this many groups.",
        )
        self._batch_e = self._field(
            settings, 5, "PDF merge batch", str(DEFAULT_BATCH),
            "Used only when final merge is enabled. How many PDFs to merge per intermediate batch.",
        )
        self._excel_only_widgets = [
            self._header_e, self._wide_cb,
        ]
        self._split_var = ctk.BooleanVar(value=True)
        self._split_cb = ctk.CTkCheckBox(
            settings,
            text="Split chunk PDFs into single PDFs",
            variable=self._split_var,
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["text"],
            fg_color=TINT["mid"],
            hover_color=TINT["bdr"],
            border_color=C["border"],
            checkmark_color=C["accent"],
        )
        self._split_cb.grid(row=12, column=0, columnspan=2, padx=16, pady=(10, 2), sticky="w")
        ctk.CTkLabel(
            settings,
            text="Default on — runs only after ALL chunk PDFs are finished. Names use Filename column.",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=C["faint"],
        ).grid(row=13, column=0, columnspan=2, padx=16, pady=(0, 6), sticky="w")

        self._merge_var = ctk.BooleanVar(value=False)
        self._merge_cb = ctk.CTkCheckBox(
            settings,
            text="Create final merged PDF (UCP_format.pdf)",
            variable=self._merge_var,
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["text"],
            fg_color=TINT["mid"],
            hover_color=TINT["bdr"],
            border_color=C["border"],
            checkmark_color=C["accent"],
        )
        self._merge_cb.grid(row=14, column=0, columnspan=2, padx=16, pady=(4, 2), sticky="w")
        ctk.CTkLabel(
            settings,
            text="Default off — tick to also build one combined file after chunks/singles.",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=C["faint"],
        ).grid(row=15, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="w")

        self._prog = ctk.CTkProgressBar(
            body, height=8, fg_color=C["card"], progress_color=C["accent"],
        )
        self._prog.pack(fill="x", pady=(4, 6))
        self._prog.set(0)
        self._stat = ctk.CTkLabel(
            body, text="Ready.", font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], anchor="w",
        )
        self._stat.pack(fill="x", pady=(0, 6))
        self._log = ctk.CTkTextbox(
            body, height=200, font=ctk.CTkFont("Courier New", 11),
            fg_color=C["card"], border_color=C["border"],
            border_width=1, text_color=C["muted"], state="disabled",
        )
        self._log.pack(fill="x", pady=(0, 12))

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 16))

        self._run_btn = ctk.CTkButton(
            btn_row, text="▶  Generate UCP PDFs",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            corner_radius=24, height=46, command=self._start,
        )
        self._run_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self._cancel_btn = ctk.CTkButton(
            btn_row, text="Cancel", width=120,
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            fg_color=C["card"], hover_color="#3a1520",
            text_color=C["red"], border_color=C["red"], border_width=1,
            corner_radius=24, height=46, state="disabled",
            command=self._cancel,
        )
        self._cancel_btn.pack(side="right")

        self._on_mode_change("From Excel")

    def _is_split_only(self) -> bool:
        return self._mode_seg.get() == "Split chunks only"

    def _on_mode_change(self, value=None):
        split_only = self._is_split_only()
        self._excel_sec.pack_forget()
        self._chunk_sec.pack_forget()
        if split_only:
            # Need Excel (for names) + chunk folder
            self._excel_sec.pack(fill="x", before=self._settings)
            self._chunk_sec.pack(fill="x", before=self._settings)
            self._split_var.set(True)
            self._split_cb.configure(state="disabled")
            for w in self._excel_only_widgets:
                try:
                    w.configure(state="disabled")
                except Exception:
                    pass
            # Keep group / filename / speed enabled for rebuild-from-Excel
            for w in (self._group_cb, self._name_cb):
                try:
                    w.configure(state="readonly")
                except Exception:
                    try:
                        w.configure(state="normal")
                    except Exception:
                        pass
            try:
                self._speed_e.configure(state="normal")
            except Exception:
                pass
            self._run_btn.configure(text="▶  Split Chunk PDFs")
            self._stat.configure(
                text="Split-only — pick Excel + chunk folder (same Groups / Excel file as creation).",
                text_color=C["muted"],
            )
        else:
            self._excel_sec.pack(fill="x", before=self._settings)
            self._split_cb.configure(state="normal")
            for w in self._excel_only_widgets:
                try:
                    w.configure(state="normal")
                except Exception:
                    pass
            for w in (self._group_cb, self._name_cb):
                try:
                    w.configure(state="readonly")
                except Exception:
                    pass
            try:
                self._speed_e.configure(state="normal")
            except Exception:
                pass
            self._run_btn.configure(text="▶  Generate UCP PDFs")
            self._stat.configure(text="Ready.", text_color=C["muted"])

    def _pick_chunk_run(self):
        initial = BASE_OUT if os.path.isdir(BASE_OUT) else os.path.expanduser("~")
        path = filedialog.askdirectory(
            title="Select chunk PDF folder (or run folder with output_pdfs)",
            initialdir=initial,
        )
        if not path:
            return
        try:
            paths, resolved = list_chunk_pdfs(path)
            self._chunk_run_dir = resolved
            self._chunk_lbl.configure(
                text=f"{os.path.basename(resolved)}  ({len(paths)} PDFs)",
                text_color=C["accent"],
            )
            self._stat.configure(
                text=f"Chunk folder ready — {len(paths)} PDFs",
                text_color=C["accent"],
            )
        except Exception as e:
            self._chunk_run_dir = None
            self._chunk_lbl.configure(text="No folder selected", text_color=C["muted"])
            messagebox.showerror("Invalid folder", str(e))

    def _dropdown(self, parent, row, label, values, default, hint):
        ctk.CTkLabel(
            parent, text=label, font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], width=130,
        ).grid(row=row * 2, column=0, padx=16, pady=(12 if row == 0 else 4, 0), sticky="w")
        cb = ctk.CTkComboBox(
            parent, values=values, height=34,
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["hover"], border_color=C["border"],
            button_color=TINT["mid"], button_hover_color=TINT["bdr"],
            dropdown_fg_color=C["card"], dropdown_hover_color=C["hover"],
            dropdown_text_color=C["text"], text_color=C["text"],
            state="readonly",
        )
        cb.set(default)
        cb.grid(row=row * 2, column=1, padx=16, pady=(12 if row == 0 else 4, 0), sticky="ew")
        ctk.CTkLabel(
            parent, text=hint, font=ctk.CTkFont("Segoe UI", 10),
            text_color=C["faint"],
        ).grid(
            row=row * 2 + 1, column=0, columnspan=2,
            padx=16, pady=(0, 2), sticky="w",
        )
        return cb

    def _field(self, parent, row, label, default, hint, last=False):
        ctk.CTkLabel(
            parent, text=label, font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], width=130,
        ).grid(row=row * 2, column=0, padx=16, pady=(12 if row == 0 else 4, 0), sticky="w")
        entry = ctk.CTkEntry(
            parent, height=34, fg_color=C["hover"],
            border_color=C["border"], text_color=C["text"],
        )
        entry.grid(row=row * 2, column=1, padx=16, pady=(12 if row == 0 else 4, 0), sticky="ew")
        entry.insert(0, default)
        ctk.CTkLabel(
            parent, text=hint, font=ctk.CTkFont("Segoe UI", 10),
            text_color=C["faint"],
        ).grid(
            row=row * 2 + 1, column=0, columnspan=2,
            padx=16, pady=(0, 10 if last else 2), sticky="w",
        )
        return entry

    def _sec(self, p, t):
        ctk.CTkLabel(
            p, text=t, font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color=C["text"], anchor="w",
        ).pack(fill="x", pady=(10, 2))

    def _write(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _pick(self):
        path = filedialog.askopenfilename(
            title="Select Excel file",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
        )
        if not path:
            return
        self._path = path
        try:
            cols = list(pd.read_excel(path, nrows=0).columns)
            self._columns = [str(c).strip() for c in cols]
            if not self._columns:
                raise ValueError("No columns found in the Excel file.")

            self._group_cb.configure(values=self._columns)
            self._name_cb.configure(values=self._columns)
            self._wide_cb.configure(values=self._columns)

            g = find_column(
                self._columns,
                [DEFAULT_GROUP_COL, "prospect_no", "Prospect No", "ProspectNo"],
            )
            self._group_cb.set(g or self._columns[0])

            n = find_column(
                self._columns,
                [DEFAULT_NAME_COL, "prospect_no", "Prospect No", "ProspectNo", "Prospect Number"],
            )
            self._name_cb.set(n or g or self._columns[0])

            w = find_column(
                self._columns,
                [DEFAULT_WIDE_COL, "address", "Ref No", "ref_no", "ref no", "Reference"],
            )
            self._wide_cb.set(w or self._columns[0])

            self._file_lbl.configure(
                text=f"{os.path.basename(path)}  ({len(self._columns)} cols)",
                text_color=C["accent"],
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not read Excel:\n{e}")

    def _start(self):
        merge_final = bool(self._merge_var.get())
        split_singles = bool(self._split_var.get())

        if self._is_split_only():
            if not self._path:
                messagebox.showwarning("Missing", "Select the Excel file used to create the chunks.")
                return
            if not self._columns:
                messagebox.showwarning("Missing", "Load the Excel file so columns appear in the dropdowns.")
                return
            if not self._chunk_run_dir:
                messagebox.showwarning("Missing", "Select the chunk PDF folder.")
                return
            group_col = self._group_cb.get().strip()
            name_col = self._name_cb.get().strip()
            if not group_col:
                messagebox.showwarning("Missing", "Select a group-by column.")
                return
            if not name_col:
                messagebox.showwarning("Missing", "Select a filename column.")
                return
            try:
                batch = int(self._batch_e.get().strip())
                if batch < 1:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Invalid", "PDF merge batch must be a positive number.")
                return
            try:
                sheets_per_book = int(self._speed_e.get().strip())
                if sheets_per_book < 1:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Invalid", "Groups / Excel file must be a positive number.")
                return

            self._cancel_event.clear()
            self._run_btn.configure(state="disabled", text="Splitting…")
            self._cancel_btn.configure(state="normal", text="Cancel")
            self._stat.configure(text="Splitting chunk PDFs…", text_color=C["accent"])
            self._prog.set(0)
            self._log.configure(state="normal")
            self._log.delete("1.0", "end")
            self._log.configure(state="disabled")
            threading.Thread(
                target=self._run_split_only,
                args=(
                    self._path, self._chunk_run_dir, group_col, name_col,
                    sheets_per_book, merge_final, batch,
                ),
                daemon=True,
            ).start()
            return

        if not self._path:
            messagebox.showwarning("Missing", "Select an Excel file first.")
            return
        if not self._columns:
            messagebox.showwarning("Missing", "Load an Excel file so columns appear in the dropdowns.")
            return

        group_col = self._group_cb.get().strip()
        name_col = self._name_cb.get().strip()
        wide_col = self._wide_cb.get().strip()
        header = self._header_e.get().strip() or DEFAULT_HEADER
        if not group_col:
            messagebox.showwarning("Missing", "Select a group-by column.")
            return
        if not name_col:
            messagebox.showwarning("Missing", "Select a filename column.")
            return
        if not wide_col:
            messagebox.showwarning("Missing", "Select a wide column.")
            return
        try:
            batch = int(self._batch_e.get().strip())
            if batch < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid", "PDF merge batch must be a positive number.")
            return
        try:
            sheets_per_book = int(self._speed_e.get().strip())
            if sheets_per_book < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid", "Groups / Excel file must be a positive number.")
            return

        self._cancel_event.clear()
        self._run_btn.configure(state="disabled", text="Processing…")
        self._cancel_btn.configure(state="normal", text="Cancel")
        self._stat.configure(
            text="Running… (Cancel stops after the current Excel chunk)",
            text_color=C["accent"],
        )
        self._prog.set(0)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run,
            args=(group_col, header, wide_col, batch, sheets_per_book, merge_final, name_col, split_singles),
            daemon=True,
        ).start()

    def _cancel(self):
        if self._cancel_event.is_set():
            return
        self._cancel_event.set()
        self._cancel_btn.configure(state="disabled", text="Cancelling…")
        self._stat.configure(
            text="Cancelling… finishing current step, then stopping safely.",
            text_color=C["accent"],
        )
        self._write("\n⏹ Cancel requested — will stop after the current step…")

    def _set_idle_buttons(self):
        label = "▶  Split Chunk PDFs" if self._is_split_only() else "▶  Generate UCP PDFs"
        self._run_btn.configure(state="normal", text=label)
        self._cancel_btn.configure(state="disabled", text="Cancel")

    def _finish_ok(self, stats, out_dir):
        done_msg = f"Done — {stats.get('chunks', 0)} chunks"
        if stats.get("split"):
            done_msg += f", {stats.get('singles', 0)} singles"
        if stats.get("merged") and stats.get("final_pdf"):
            done_msg += " + final merge"
        done_msg += f", {stats['errors']} errors."
        self._stat.configure(text=done_msg, text_color=C["green"])
        subprocess.Popen(["explorer", out_dir])

        result_lines = []
        if not self._is_split_only() and stats.get("created") is not None:
            result_lines.append(f"Groups processed: {stats['created']}")
        result_lines.append(f"Chunk PDFs: {stats.get('chunks', 0)}")
        if stats.get("split"):
            result_lines.append(f"Single PDFs: {stats.get('singles', 0)}")
        result_lines.append(f"Errors: {stats['errors']}")
        result_lines.append(f"Chunk folder: {stats.get('pdf_dir', out_dir)}")
        if stats.get("split"):
            result_lines.append(f"Singles folder: {stats.get('single_dir', out_dir)}")
        else:
            result_lines.append("Split to singles: skipped")
        if stats.get("merged") and stats.get("final_pdf"):
            result_lines.append(f"Final merge: {stats['final_pdf']}")
        else:
            result_lines.append("Final merge: skipped")
        messagebox.showinfo("Complete", "\n".join(result_lines))

    def _run_split_only(self, excel_path, chunks_dir, group_col, name_col, sheets_per_book, merge_final, batch):
        def log(m):
            self.after(0, lambda x=m: self._write(x))

        def prog(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            stats = run_split_only(
                excel_path, chunks_dir, group_col, name_col, sheets_per_book,
                log, prog,
                cancel_check=self._cancel_event.is_set,
                merge_final=merge_final,
                batch_size=batch,
            )
            out_dir = stats.get("out_dir") or chunks_dir
            self.after(0, lambda: self._finish_ok(stats, out_dir))
        except CancelledError as e:
            log(f"\n⏹ {e}")
            self.after(0, lambda: self._stat.configure(
                text="Cancelled — partial files kept.",
                text_color=C["accent"],
            ))
            self.after(0, lambda: subprocess.Popen(["explorer", chunks_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Cancelled",
                "Process stopped safely.\n\nAny PDFs already created were kept.",
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, self._set_idle_buttons)

    def _run(self, group_col, header, wide_col, batch, sheets_per_book, merge_final, name_col, split_singles):
        out_dir = get_output_dir()

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        def prog(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            stats = run_pipeline(
                self._path, out_dir, group_col, header, wide_col, batch, log, prog,
                cancel_check=self._cancel_event.is_set,
                sheets_per_book=sheets_per_book,
                merge_final=merge_final,
                name_col=name_col,
                split_singles=split_singles,
            )
            self.after(0, lambda: self._finish_ok(stats, out_dir))
        except CancelledError as e:
            log(f"\n⏹ {e}")
            log(f"Partial output kept in → {out_dir}")
            self.after(0, lambda: self._stat.configure(
                text="Cancelled — partial files kept in output folder.",
                text_color=C["accent"],
            ))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Cancelled",
                "Process stopped safely.\n\n"
                "Any PDFs already created were kept in the output folder.",
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, self._set_idle_buttons)


if __name__ == "__main__":
    App().mainloop()
