#!/usr/bin/env python3
"""
check_envelope_pattern_batch.py  (Scan Letter)

Batch envelope pattern checker. Scans a FOLDER of PDFs and for every PDF:
  - Processes pages two at a time (front/back pairs)
  - OCRs in bounded batches with parallel workers
  - Keeps valid IIFL Finance front/back pairs; drops or flags bad pairs
  - Writes cleaned PDFs (optional), per-file logs, and a master summary CSV

CLI:
    python check_envelope_pattern_batch.py /path/to/input_folder \\
        --output-dir /path/to/output_folder \\
        --log-dir /path/to/logs

Also importable by envelope_pattern_checker.py (GUI).
"""

import argparse
import csv
import os
import shutil
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pdf2image import convert_from_path
from pypdf import PdfReader, PdfWriter
import pytesseract
from rapidfuzz import fuzz

_HERE = Path(__file__).resolve().parent
POPPLER_PATH = _HERE / "poppler-25.07.0" / "Library" / "bin"
TESSERACT_CANDIDATES = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)

# Windows PATH often has the .exe itself instead of the install folder;
# point pytesseract at a known install if `tesseract` is not resolvable.
if not shutil.which("tesseract"):
    for candidate in TESSERACT_CANDIDATES:
        if candidate.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            break

# --------------------------------------------------------------------------
# Pattern definition
# --------------------------------------------------------------------------
FRONT_KEYWORDS = [
    "IIFL FINANCE",
    "INLAND SPEED POST",
    "FO No",
    "Customer ID",
    "Do not tear here",
]

BACK_KEYWORDS = [
    "IF UNDELIVERED PLEASE RETURN TO",
    "IIFL Finance Limited",
    "WITHOUT PREJUDICE",
    "Do not tear here",
]

MIN_FRONT_HITS = 1
MIN_BACK_HITS = 1


def configure_tesseract():
    """Ensure pytesseract can find tesseract.exe. Returns path or None."""
    if shutil.which("tesseract"):
        return shutil.which("tesseract")
    for candidate in TESSERACT_CANDIDATES:
        if candidate.is_file():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return str(candidate)
    return None


def get_poppler_path():
    if POPPLER_PATH.is_dir():
        return str(POPPLER_PATH)
    return None


def score_keywords(text: str, keywords: list, threshold: int) -> tuple:
    matched = []
    text_lower = text.lower()
    for kw in keywords:
        score = fuzz.partial_ratio(kw.lower(), text_lower)
        if score >= threshold:
            matched.append(kw)
    return len(matched), matched


def classify_page(text: str, threshold: int, min_front_hits: int, min_back_hits: int) -> dict:
    front_hits, front_matched = score_keywords(text, FRONT_KEYWORDS, threshold)
    back_hits, back_matched = score_keywords(text, BACK_KEYWORDS, threshold)
    return {
        "front_hits": front_hits,
        "front_matched": front_matched,
        "is_front": front_hits >= min_front_hits,
        "back_hits": back_hits,
        "back_matched": back_matched,
        "is_back": back_hits >= min_back_hits,
    }


def str2bool(value: str) -> bool:
    if isinstance(value, bool):
        return value
    v = value.strip().lower()
    if v in ("true", "t", "yes", "y", "1"):
        return True
    if v in ("false", "f", "no", "n", "0"):
        return False
    raise argparse.ArgumentTypeError(f"Expected true/false, got: {value!r}")


def ocr_image(image) -> str:
    return pytesseract.image_to_string(image)


def get_batch_texts(pdf_path: str, first_page: int, last_page: int, dpi: int,
                    workers: int, poppler_path: str = None) -> list:
    """
    Rasterize pages [first_page, last_page] (1-indexed, inclusive) and OCR
    them in parallel. Returns texts in page order.
    """
    kwargs = dict(
        dpi=dpi,
        first_page=first_page,
        last_page=last_page,
        thread_count=max(1, workers),
    )
    if poppler_path and os.path.isdir(poppler_path):
        kwargs["poppler_path"] = poppler_path

    images = convert_from_path(pdf_path, **kwargs)
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        texts = list(pool.map(ocr_image, images))
    return texts


def process_single_pdf(
    pdf_path: Path,
    output_dir: Path,
    log_dir: Path,
    dpi: int,
    threshold: int,
    batch_size: int,
    workers: int,
    remove: bool,
    min_front_hits: int,
    min_back_hits: int,
    poppler_path: str = None,
    log_fn=None,
) -> dict:
    """
    Process one PDF. If remove=True, drop bad pairs and write cleaned PDF.
    If remove=False, audit-only (log failures, no cleaned PDF).
    """
    _log = log_fn or print
    start_time = time.time()
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)

    writer = PdfWriter() if remove else None
    log_rows = []
    removed_page_numbers = []
    kept_page_numbers = []

    if batch_size % 2 != 0:
        batch_size += 1

    _log(f"\n=== {pdf_path.name} — {total_pages} page(s) ===")

    for batch_start in range(0, total_pages, batch_size):
        batch_end = min(batch_start + batch_size, total_pages)
        first_page = batch_start + 1
        last_page = batch_end

        texts = get_batch_texts(
            str(pdf_path), first_page, last_page, dpi, workers, poppler_path
        )

        i = 0
        while i < len(texts):
            abs_index = batch_start + i
            front_page_no = abs_index + 1
            has_back = (abs_index + 1) < total_pages

            front_result = classify_page(
                texts[i], threshold, min_front_hits, min_back_hits
            )

            if not has_back:
                status = (
                    "REMOVED - no matching back page"
                    if remove
                    else "FLAGGED - no matching back page (not removed)"
                )
                log_rows.append((
                    front_page_no, "front (unpaired)", status,
                    front_result["front_hits"], ", ".join(front_result["front_matched"]),
                ))
                removed_page_numbers.append(front_page_no)
                i += 1
                continue

            back_page_no = front_page_no + 1
            back_result = classify_page(
                texts[i + 1], threshold, min_front_hits, min_back_hits
            )

            pair_valid = front_result["is_front"] and back_result["is_back"]

            if pair_valid:
                if remove:
                    writer.add_page(reader.pages[abs_index])
                    writer.add_page(reader.pages[abs_index + 1])
                log_rows.append((
                    front_page_no, "front", "KEPT",
                    front_result["front_hits"], ", ".join(front_result["front_matched"]),
                ))
                log_rows.append((
                    back_page_no, "back", "KEPT",
                    back_result["back_hits"], ", ".join(back_result["back_matched"]),
                ))
                kept_page_numbers.extend([front_page_no, back_page_no])
            else:
                reasons = []
                if not front_result["is_front"]:
                    reasons.append(
                        f"page {front_page_no} failed front pattern "
                        f"({front_result['front_hits']}/{len(FRONT_KEYWORDS)} hits, "
                        f"need {min_front_hits})"
                    )
                if not back_result["is_back"]:
                    reasons.append(
                        f"page {back_page_no} failed back pattern "
                        f"({back_result['back_hits']}/{len(BACK_KEYWORDS)} hits, "
                        f"need {min_back_hits})"
                    )
                reason_str = "; ".join(reasons)
                verb = "REMOVED" if remove else "FLAGGED (not removed)"
                log_rows.append((
                    front_page_no, "front", f"{verb} - {reason_str}",
                    front_result["front_hits"], ", ".join(front_result["front_matched"]),
                ))
                log_rows.append((
                    back_page_no, "back", f"{verb} - {reason_str}",
                    back_result["back_hits"], ", ".join(back_result["back_matched"]),
                ))
                removed_page_numbers.extend([front_page_no, back_page_no])

            i += 2

        _log(
            f"  processed pages {first_page}-{last_page} of {total_pages} "
            f"(removed so far: {len(removed_page_numbers)})"
        )

    out_path = None
    if remove:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{pdf_path.stem}_cleaned.pdf"
        with open(out_path, "wb") as f:
            writer.write(f)

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{pdf_path.stem}_log.txt"
    elapsed = time.time() - start_time
    label = "removed" if remove else "flagged (not removed)"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Envelope pattern check log for: {pdf_path.name}\n")
        f.write(
            f"Mode: {'REMOVE' if remove else 'AUDIT ONLY (no pages removed, no cleaned PDF written)'}\n"
        )
        f.write(f"Total input pages: {total_pages}\n")
        f.write(f"Fuzzy match threshold: {threshold}\n")
        f.write(
            f"Min front keyword hits required: {min_front_hits}/{len(FRONT_KEYWORDS)}\n"
        )
        f.write(
            f"Min back keyword hits required: {min_back_hits}/{len(BACK_KEYWORDS)}\n"
        )
        f.write(f"Pages kept / valid: {len(kept_page_numbers)}\n")
        f.write(f"Pages {label}: {len(removed_page_numbers)} -> {removed_page_numbers}\n")
        f.write(f"Processing time: {elapsed:.1f}s\n")
        f.write("-" * 70 + "\n")
        for page_no, role, status, hits, matched in log_rows:
            f.write(f"Page {page_no:>5} [{role:<16}] {status}\n")
            f.write(f"           matched keywords: {matched or '(none)'}\n")

    csv_log_path = log_dir / f"{pdf_path.stem}_log.csv"
    with open(csv_log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["page_no", "role", "status", "hits", "matched_keywords"])
        for row in log_rows:
            w.writerow(row)

    out_name = out_path.name if out_path else "(none - audit mode)"
    _log(
        f"  done in {elapsed:.1f}s -> kept {len(kept_page_numbers)}, "
        f"{label} {len(removed_page_numbers)} -> {out_name}"
    )

    return {
        "file": pdf_path.name,
        "total_pages": total_pages,
        "kept_pages": len(kept_page_numbers),
        "removed_pages": len(removed_page_numbers),
        "removed_page_numbers": removed_page_numbers,
        "output_pdf": str(out_path) if out_path else "",
        "log_file": str(log_path),
        "elapsed_sec": round(elapsed, 1),
        "error": "",
    }


def run_batch(
    input_dir,
    output_dir,
    log_dir,
    summary_csv,
    dpi=300,
    threshold=65,
    batch_size=20,
    workers=4,
    recursive=False,
    remove=True,
    min_front_hits=MIN_FRONT_HITS,
    min_back_hits=MIN_BACK_HITS,
    poppler_path=None,
    log_fn=None,
    progress_fn=None,
):
    """
    Process all PDFs in input_dir. Returns (summary_rows, stats_dict).
    Used by CLI and the Scan GUI.
    """
    _log = log_fn or print
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    log_dir = Path(log_dir)
    summary_path = Path(summary_csv)

    if poppler_path is None:
        poppler_path = get_poppler_path()

    if not input_dir.is_dir():
        raise ValueError(f"Input folder not found: {input_dir}")

    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdf_files = sorted(input_dir.glob(pattern))
    if recursive:
        pdf_files += sorted(input_dir.glob("**/*.PDF"))
    else:
        pdf_files += sorted(input_dir.glob("*.PDF"))
    pdf_files = sorted(set(pdf_files))

    if not pdf_files:
        raise ValueError(f"No PDF files found in {input_dir}")

    _log(f"Found {len(pdf_files)} PDF(s) in {input_dir}")
    if poppler_path:
        _log(f"Poppler → {poppler_path}")

    summary_rows = []
    overall_start = time.time()

    for i, pdf_path in enumerate(pdf_files, 1):
        try:
            result = process_single_pdf(
                pdf_path, output_dir, log_dir,
                dpi, threshold, batch_size, workers, remove,
                min_front_hits, min_back_hits,
                poppler_path=poppler_path,
                log_fn=_log,
            )
            summary_rows.append(result)
        except Exception as e:
            err_text = f"{type(e).__name__}: {e}"
            _log(f"  ERROR processing {pdf_path.name}: {err_text}")
            traceback.print_exc()
            summary_rows.append({
                "file": pdf_path.name,
                "total_pages": "",
                "kept_pages": "",
                "removed_pages": "",
                "removed_page_numbers": "",
                "output_pdf": "",
                "log_file": "",
                "elapsed_sec": "",
                "error": err_text,
            })
        if progress_fn:
            progress_fn(i / len(pdf_files))

    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "file", "total_pages", "kept_pages", "removed_pages",
            "removed_page_numbers", "output_pdf", "log_file", "elapsed_sec", "error",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in summary_rows:
            w.writerow(row)

    total_elapsed = time.time() - overall_start
    ok_count = sum(1 for r in summary_rows if not r["error"])
    err_count = len(summary_rows) - ok_count
    kept_total = sum(int(r["kept_pages"] or 0) for r in summary_rows if not r["error"])
    removed_total = sum(int(r["removed_pages"] or 0) for r in summary_rows if not r["error"])

    _log(f"\n=== ALL DONE in {total_elapsed:.1f}s ===")
    _log(f"Mode: {'REMOVE' if remove else 'AUDIT ONLY (no PDFs modified)'}")
    _log(f"Processed: {ok_count} file(s) OK, {err_count} file(s) errored")
    _log(f"Master summary: {summary_path}")
    if remove:
        _log(f"Cleaned PDFs in: {output_dir}")
    _log(f"Logs in: {log_dir}")

    return summary_rows, {
        "ok": ok_count,
        "errors": err_count,
        "kept_pages": kept_total,
        "removed_pages": removed_total,
        "summary_csv": str(summary_path),
        "output_dir": str(output_dir),
        "log_dir": str(log_dir),
        "elapsed": round(total_elapsed, 1),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Batch-check the 2-page envelope pattern across a folder of PDFs."
    )
    parser.add_argument("input_dir", help="Folder containing the PDFs to check")
    parser.add_argument("--output-dir", default="cleaned_pdfs",
                        help="Folder to write cleaned PDFs into")
    parser.add_argument("--log-dir", default="logs",
                        help="Folder to write per-file logs into")
    parser.add_argument("--summary-csv", default="summary.csv",
                        help="Path for the master summary CSV")
    parser.add_argument("--dpi", type=int, default=300,
                        help="DPI used to rasterize pages for OCR")
    parser.add_argument("--threshold", type=int, default=65,
                        help="Fuzzy match threshold (0-100)")
    parser.add_argument("--batch-size", type=int, default=20,
                        help="How many pages to rasterize/OCR at once")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel OCR/rasterization workers per batch")
    parser.add_argument("--recursive", action="store_true",
                        help="Also search subfolders for PDFs")
    parser.add_argument("--remove", type=str2bool, default=True,
                        help="true: drop bad pairs and write cleaned PDF. "
                             "false: audit-only.")
    parser.add_argument("--min-front-hits", type=int, default=MIN_FRONT_HITS,
                        help=f"Min front keyword hits (default {MIN_FRONT_HITS})")
    parser.add_argument("--min-back-hits", type=int, default=MIN_BACK_HITS,
                        help=f"Min back keyword hits (default {MIN_BACK_HITS})")
    args = parser.parse_args()

    if not configure_tesseract():
        sys.exit("Tesseract OCR not found. Install Tesseract-OCR and retry.")

    try:
        run_batch(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            log_dir=args.log_dir,
            summary_csv=args.summary_csv,
            dpi=args.dpi,
            threshold=args.threshold,
            batch_size=args.batch_size,
            workers=args.workers,
            recursive=args.recursive,
            remove=args.remove,
            min_front_hits=args.min_front_hits,
            min_back_hits=args.min_back_hits,
        )
    except Exception as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
