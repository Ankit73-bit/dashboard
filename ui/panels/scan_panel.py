"""
Scan tab — barcode scan / match / merge tools from scan_letter/.
"""

import os
import customtkinter as ctk

from ui.theme import C, t
from ui.cards import ServiceCard

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCAN_SCRIPTS = os.path.join(HERE, "scan_letter")

SCAN_SERVICES = [
    {
        "title":       "1 · Envelope Pattern Check",
        "description": "OCR-check front/back envelope pairs; remove or flag bad pages before barcode split.",
        "icon":        "📋",
        "accent":      C["orange"],
        "tag":         "Step 1 · Pre-check",
        "script":      os.path.join(SCAN_SCRIPTS, "envelope_pattern_checker.py"),
        "sample":      None,
        "docs": {
            "what": "Scans a folder of multi-page PDFs in front/back pairs. Uses OCR to verify the IIFL address page comes first and the “IF UNDELIVERED PLEASE RETURN TO” page second. Valid pairs are kept; bad pairs are removed (cleaned PDF) or only logged (audit mode). Writes per-file logs and a master summary.csv.",
            "when": "Use before Barcode Split & Rename when scans may have reversed or unpaired pages.",
            "steps": [
                ("Select scanned PDFs folder", "Folder of large multi-page scan PDFs."),
                ("Choose mode", "Remove bad pairs (writes cleaned PDFs) or audit-only (log failures)."),
                ("Click Run", "Each PDF is OCR-checked in batches; logs and summary go to the OUTPUT folder."),
            ],
            "tips": [
                "Requires pdf2image, pytesseract, pypdf, rapidfuzz. Poppler is bundled under scan_letter\\poppler-25.07.0; install Tesseract-OCR.",
                "Cleaned PDFs are named <original>_cleaned.pdf — feed those into Step 2.",
                "Per-file *_log.csv lists every page kept or removed and why.",
            ],
            "output": "Desktop\\OUTPUT\\Scan_Envelope_Pattern\\<timestamp>\\",
        },
    },
    {
        "title":       "2 · Barcode Split & Rename",
        "description": "Split scanned PDFs into page groups, read barcodes, and rename files by barcode.",
        "icon":        "✂️",
        "accent":      C["cyan"],
        "tag":         "Step 2 · Scan",
        "script":      os.path.join(SCAN_SCRIPTS, "barcode_split_rename.py"),
        "sample":      None,
        "docs": {
            "what": "Takes a folder of scanned multi-page PDFs, splits them into fixed page groups (default 2 pages), reads the barcode from each split with pdf2image + pyzbar, and saves uniquely named <barcode>.pdf files. Duplicates and no-barcode splits are sorted into separate folders with a CSV log.",
            "when": "Use after Envelope Pattern Check (or on already-clean scans). Output renamed_pdfs feed into Barcode Excel Matcher.",
            "steps": [
                ("Select scanned PDFs folder", "Browse to cleaned_pdfs from Step 1, or your multi-page scanned PDFs."),
                ("Set pages per split", "Default is 2 (one letter = 2 pages). Change if your scan layout differs."),
                ("Click Run", "Splits are created, barcodes read, and files sorted into renamed / not_renamed / duplicate folders."),
            ],
            "tips": [
                "Requires pdf2image, pyzbar, and PyPDF2. Poppler is bundled under scan_letter\\poppler-25.07.0.",
                "Duplicate barcodes go to duplicate_pdfs with unique suffixes.",
                "A rename_log.csv is written inside the renamed folder.",
            ],
            "output": "Desktop\\OUTPUT\\Scan_Split_Rename\\<timestamp>\\",
        },
    },
    {
        "title":       "3 · Barcode Excel Matcher",
        "description": "Exact-match renamed barcode PDFs against Excel tracking lists; update remarks.",
        "icon":        "🔗",
        "accent":      C["green"],
        "tag":         "Step 3 · Match",
        "script":      os.path.join(SCAN_SCRIPTS, "barcode_excel_matcher.py"),
        "sample":      None,
        "docs": {
            "what": "Loads barcodes from Excel files (barcode / AWB / tracking columns), then matches each renamed PDF filename. Exact matches stay; unmatched PDFs move to not_found. Excel rows get a remark column (Exact Match).",
            "when": "Use after Barcode Split & Rename, when you have renamed_pdfs and Excel lists of expected barcodes.",
            "steps": [
                ("Select renamed PDFs folder", "Usually the renamed_pdfs output from Step 2."),
                ("Select Excel folder", "Folder of .xlsx/.xls files containing barcode / tracking columns."),
                ("Click Run", "PDFs are exact-matched and Excel remarks updated."),
            ],
            "tips": [
                "Only exact barcode matches are kept; near-misses are treated as not found.",
                "India Post format (e.g. EK123456789IN) is validated when loading Excel.",
            ],
            "output": "Desktop\\OUTPUT\\Scan_Barcode_Matcher\\<timestamp>\\",
        },
    },
    {
        "title":       "4 · Matched PDF Merger",
        "description": "Merge Exact/Fuzzy-matched barcode PDFs from Renamed + UCP + Tracking into one file per prospect.",
        "icon":        "📎",
        "accent":      C["purple"],
        "tag":         "Step 4 · Merge",
        "script":      os.path.join(SCAN_SCRIPTS, "matched_pdf_merger.py"),
        "sample":      None,
        "docs": {
            "what": "Reads Excel files with Exact Match / Fuzzy Match remarks, finds <barcode>.pdf in each selected source folder (Renamed PDFs, UCP, Tracking), and merges those PDFs into <prospect_no>-<barcode>.pdf. Rows missing any selected source are skipped and logged.",
            "when": "Use as the final Scan step after matching, when you need one combined PDF per matched prospect from multiple PDF sources.",
            "steps": [
                ("Select Excel folder", "Excel files with remark column from Step 3 (Exact Match / Fuzzy Match)."),
                ("Pick PDF sources", "Tick at least 2 of: Renamed PDFs, UCP, Tracking — and browse each folder."),
                ("Map columns", "Confirm Barcode, Prospect No, and Remark columns (auto-detected when possible)."),
                ("Click Run", "Matched rows are merged; merge_log.csv records success and skips."),
            ],
            "tips": [
                "At least two PDF source folders must be selected.",
                "Only rows whose remark contains Exact Match or Fuzzy Match are processed.",
                "Output files are named <prospect_no>-<barcode>.pdf.",
            ],
            "output": "Desktop\\OUTPUT\\Scan_PDF_Merger\\<timestamp>\\",
        },
    },
]


class ScanPanel(ctk.CTkFrame):
    """Scan tab — barcode split, match, and merge tools."""

    def __init__(self, master, open_docs_cb=None, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.open_docs_cb = open_docs_cb
        self._build()

    def _build(self):
        top = ctk.CTkFrame(self, height=62, fg_color=C["sidebar"], corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="📡  Scan",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(side="left", padx=26)

        count_pill = ctk.CTkFrame(top, fg_color=t(C["cyan"], "mid"), corner_radius=10)
        count_pill.pack(side="right", padx=20)
        ctk.CTkLabel(count_pill,
                     text=f"  {len(SCAN_SERVICES)} tools  ",
                     font=ctk.CTkFont("Segoe UI", 11, "bold"),
                     text_color=C["cyan"]).pack(pady=4)

        ctk.CTkLabel(self,
                     text="SCAN LETTER WORKFLOW  ·  Run steps 1 → 2 → 3 → 4 in order",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["faint"]).pack(anchor="w", padx=28, pady=(14, 2))

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["cyan"])
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        scroll.columnconfigure(0, weight=1)
        scroll.columnconfigure(1, weight=1)
        scroll.columnconfigure(2, weight=1)

        for i, svc in enumerate(SCAN_SERVICES):
            ServiceCard(scroll, svc, open_docs_cb=self.open_docs_cb).grid(
                row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")
