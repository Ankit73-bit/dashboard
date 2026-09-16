"""
Tool: Excel Mapped PDF Merger
Merge PDFs from 3 folders using Excel column mapping for filenames.
Example: Notice (loan no) + Dispatch proof (barcode) + Tracking proof (barcode).
"""

import os
import re
import csv
import threading
import subprocess
from datetime import datetime

import pandas as pd
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PyPDF2 import PdfMerger

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Excel_Mapped_PDF_Merger")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#bf5af2", "green": "#30d158",
    "red": "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"}

# Default labels + preferred Excel columns for each source
SOURCES = [
    ("notice", "Notice PDFs", ("loan no", "loan_no", "loanno", "loan number", "prospect_no", "prospect no", "prospect")),
    ("dispatch", "Dispatch Proof", ("barcode", "awb", "tracking", "article", "dispatch barcode")),
    ("tracking", "Tracking Proof", ("barcode", "awb", "tracking", "article", "tracking barcode")),
]

OUTPUT_COL_CANDIDATES = (
    "loan no", "loan_no", "loanno", "loan number",
    "prospect_no", "prospect no", "prospect", "cuid", "ref_no",
)


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def _find_col(columns, *candidates):
    lower = {str(c).strip().lower(): c for c in columns}
    for name in candidates:
        key = name.lower()
        if key in lower:
            return lower[key]
    for name in candidates:
        key = name.lower()
        for lc, orig in lower.items():
            if key in lc:
                return orig
    return None


def clean_cell(value):
    """Normalize Excel cell → filename token (no extension)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none"):
        return ""
    # Excel often turns IDs into 12345.0
    if re.fullmatch(r"-?\d+\.0+", s):
        s = s.split(".", 1)[0]
    if s.lower().endswith(".pdf"):
        s = s[:-4]
    return s.strip()


def safe_filename(name):
    name = clean_cell(name) or "unnamed"
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.strip(" .")
    return name or "unnamed"


def find_pdf(root_folder, key):
    """Find {key}.pdf under root (including subfolders). Case-insensitive."""
    if not root_folder or not os.path.isdir(root_folder):
        return None
    key = clean_cell(key)
    if not key:
        return None
    target = f"{key}.pdf".lower()
    for root, _, files in os.walk(root_folder):
        for f in files:
            if f.lower() == target:
                return os.path.join(root, f)
    return None


def list_excel_sheets(excel_path):
    """Return sheet names for an Excel workbook."""
    xl = pd.ExcelFile(excel_path)
    names = list(xl.sheet_names)
    xl.close()
    return names


def merge_mapped_pdfs(excel_path, sources, out_name_col, out_dir, log_fn, progress_fn, sheet_name=0):
    """
    sources: list of dicts:
      {key, label, folder, column}
    Merge order follows the list order (folder 1 → 2 → 3).
    """
    merged_folder = os.path.join(out_dir, "merged_pdfs")
    os.makedirs(merged_folder, exist_ok=True)
    log_file = os.path.join(out_dir, "merge_log.csv")

    header = (
        ["Row", "Output_File", "Status", "Error"]
        + [f"{s['label']}_Key" for s in sources]
        + [f"{s['label']}_PDF" for s in sources]
    )
    with open(log_file, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(header)

    log_fn(f"Reading Excel → {excel_path}")
    log_fn(f"Sheet    → {sheet_name}")
    df = pd.read_excel(excel_path, sheet_name=sheet_name, dtype=str)
    df.columns = (
        df.columns.astype(str).str.strip()
        .str.replace("\n", "", regex=False)
        .str.replace("\r", "", regex=False)
    )

    for s in sources:
        if s["column"] not in df.columns:
            raise ValueError(
                f"Column '{s['column']}' for '{s['label']}' not found in Excel.\n"
                f"Available: {', '.join(map(str, df.columns))}"
            )
    if out_name_col not in df.columns:
        raise ValueError(
            f"Output filename column '{out_name_col}' not found in Excel.\n"
            f"Available: {', '.join(map(str, df.columns))}"
        )

    total = len(df)
    merged_count = skipped = errors = 0
    used_names = {}

    log_fn(f"Rows     → {total}")
    for s in sources:
        log_fn(f"Source   → {s['label']}: folder={s['folder']}  col={s['column']}")
    log_fn(f"Filename → column '{out_name_col}'")
    log_fn("")

    with open(log_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for idx, row in df.iterrows():
            row_num = int(idx) + 2  # Excel-ish (header = 1)
            keys = [clean_cell(row[s["column"]]) for s in sources]
            out_base = safe_filename(row[out_name_col])

            # Require at least one key; skip empty rows
            if not any(keys) and not clean_cell(row[out_name_col]):
                skipped += 1
                writer.writerow([row_num, "", "Skipped", "Empty row"] + keys + [""] * len(sources))
                continue

            found = []
            missing = []
            paths_for_log = []
            for s, key in zip(sources, keys):
                if not key:
                    missing.append(f"{s['label']} (empty key)")
                    paths_for_log.append("")
                    continue
                path = find_pdf(s["folder"], key)
                if path:
                    found.append(path)
                    paths_for_log.append(path)
                else:
                    missing.append(f"{s['label']} ({key}.pdf)")
                    paths_for_log.append("")

            # Avoid collisions: loan1.pdf, loan1_2.pdf, …
            count = used_names.get(out_base, 0) + 1
            used_names[out_base] = count
            out_name = f"{out_base}.pdf" if count == 1 else f"{out_base}_{count}.pdf"

            if missing:
                skipped += 1
                writer.writerow([
                    row_num, out_name, "Skipped", f"Missing: {', '.join(missing)}",
                    *keys, *paths_for_log,
                ])
                log_fn(f"  Skip row {row_num} → {out_name} ({', '.join(missing)})")
                progress_fn((idx + 1) / max(total, 1))
                continue

            try:
                out_path = os.path.join(merged_folder, out_name)
                merger = PdfMerger()
                for pdf in found:
                    merger.append(pdf)
                merger.write(out_path)
                merger.close()
                merged_count += 1
                writer.writerow([
                    row_num, out_path, "Merged", "OK",
                    *keys, *paths_for_log,
                ])
                log_fn(f"  Merged → {out_name}")
            except Exception as e:
                errors += 1
                writer.writerow([
                    row_num, out_name, "Error", str(e),
                    *keys, *paths_for_log,
                ])
                log_fn(f"  Error row {row_num} → {out_name}: {e}")

            progress_fn((idx + 1) / max(total, 1))

    return {
        "total": total,
        "merged": merged_count,
        "skipped": skipped,
        "errors": errors,
        "log": log_file,
        "merged_folder": merged_folder,
    }


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Excel Mapped PDF Merger")
        self.geometry("820x820")
        self.minsize(720, 680)
        self.configure(fg_color=C["bg"])
        self._excel_path = None
        self._columns = []
        self._sheets = []
        self._folder_paths = {k: None for k, _, _ in SOURCES}
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)
        ctk.CTkLabel(
            inn, text="📎  Excel Mapped PDF Merger",
            font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            inn,
            text="Merge 3 PDF folders using Excel columns for filenames (e.g. notice + dispatch + tracking).",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(anchor="w")

        footer = ctk.CTkFrame(
            self, fg_color=C["card"], corner_radius=0,
            border_width=1, border_color=C["border"],
        )
        footer.pack(side="bottom", fill="x")
        fi = ctk.CTkFrame(footer, fg_color="transparent")
        fi.pack(fill="x", padx=20, pady=12)
        self._prog = ctk.CTkProgressBar(
            fi, height=6, fg_color=C["hover"], progress_color=C["accent"],
        )
        self._prog.pack(fill="x", pady=(0, 6))
        self._prog.set(0)
        self._stat = ctk.CTkLabel(
            fi, text="Ready.", font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], anchor="w",
        )
        self._stat.pack(fill="x", pady=(0, 8))
        self._run_btn = ctk.CTkButton(
            fi, text="▶  Merge PDFs",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            corner_radius=24, height=44, command=self._start,
        )
        self._run_btn.pack(fill="x")

        body = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C["border"],
        )
        body.pack(fill="both", expand=True, padx=24, pady=16)

        banner = ctk.CTkFrame(
            body, fg_color=TINT["bg"], corner_radius=10,
            border_width=1, border_color=C["accent"],
        )
        banner.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\Excel_Mapped_PDF_Merger\\<timestamp>\\merged_pdfs\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"],
        ).pack(anchor="w", padx=14, pady=8)

        self._sec(body, "Excel mapping file")
        fr = ctk.CTkFrame(body, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 10))
        self._excel_lbl = ctk.CTkLabel(
            fr, text="No file selected", font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w",
        )
        self._excel_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_excel,
        ).pack(side="right")

        self._sec(body, "PDF sources (merged in this order)")
        self._folder_lbls = {}
        src_card = ctk.CTkFrame(
            body, fg_color=C["card"], corner_radius=12,
            border_width=1, border_color=C["border"],
        )
        src_card.pack(fill="x", pady=(0, 8))
        for i, (key, label, _) in enumerate(SOURCES):
            top = ctk.CTkFrame(src_card, fg_color="transparent")
            top.pack(fill="x", padx=14, pady=(10 if i == 0 else 4, 10 if i == 2 else 4))
            ctk.CTkLabel(
                top, text=f"{i + 1}. {label}",
                font=ctk.CTkFont("Segoe UI", 12, "bold"),
                text_color=C["text"], width=150, anchor="w",
            ).pack(side="left")
            fl = ctk.CTkLabel(
                top, text="No folder", font=ctk.CTkFont("Segoe UI", 11),
                text_color=C["faint"], anchor="w",
            )
            fl.pack(side="left", fill="x", expand=True, padx=8)
            self._folder_lbls[key] = fl
            ctk.CTkButton(
                top, text="Browse…", width=80, height=30,
                fg_color=C["hover"], hover_color=C["border"],
                text_color=C["text"],
                command=lambda k=key, lb=label: self._pick_folder(k, lb),
            ).pack(side="right")

        self._sec(body, "Column mapping (dropdowns)")
        map_card = ctk.CTkFrame(
            body, fg_color=C["card"], corner_radius=12,
            border_width=1, border_color=C["border"],
        )
        map_card.pack(fill="x", pady=(0, 8))
        map_card.columnconfigure(1, weight=1)

        self._combos = {}
        map_rows = [
            ("sheet", "Excel sheet"),
            ("notice", "1. Notice filename col"),
            ("dispatch", "2. Dispatch filename col"),
            ("tracking", "3. Tracking filename col"),
            ("output", "Output PDF name col"),
        ]
        for i, (role, label) in enumerate(map_rows):
            ctk.CTkLabel(
                map_card, text=label, font=ctk.CTkFont("Segoe UI", 11),
                text_color=C["muted"], width=180, anchor="w",
            ).grid(row=i, column=0, padx=16, pady=8, sticky="w")
            cb = ctk.CTkComboBox(
                map_card, values=["(load Excel first)"], state="readonly",
                font=ctk.CTkFont("Segoe UI", 12),
                fg_color=C["hover"], border_color=C["border"],
                button_color=TINT["mid"], button_hover_color=TINT["bdr"],
                dropdown_fg_color=C["card"], dropdown_hover_color=C["hover"],
                dropdown_text_color=C["text"], text_color=C["text"], height=32,
                command=self._on_sheet_change if role == "sheet" else None,
            )
            cb.set("(load Excel first)")
            cb.grid(row=i, column=1, padx=16, pady=8, sticky="ew")
            self._combos[role] = cb

        ctk.CTkLabel(
            body,
            text="Pick columns from the Excel headers. PDFs are looked up as <column value>.pdf. Missing any PDF skips the row.",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"], anchor="w",
        ).pack(fill="x", pady=(0, 8))

        self._sec(body, "Log")
        self._log = ctk.CTkTextbox(
            body, height=160, font=ctk.CTkFont("Courier New", 11),
            fg_color=C["card"], border_color=C["border"],
            border_width=1, text_color=C["muted"], state="disabled",
        )
        self._log.pack(fill="x", pady=(0, 8))

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

    def _pick_excel(self):
        path = filedialog.askopenfilename(
            title="Select Excel mapping file",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
        )
        if not path:
            return
        self._excel_path = path
        try:
            self._sheets = list_excel_sheets(path)
            sheet_cb = self._combos["sheet"]
            sheet_cb.configure(values=self._sheets or ["(no sheets)"])
            sheet_cb.set(self._sheets[0] if self._sheets else "(no sheets)")
            self._load_columns_for_sheet(self._sheets[0] if self._sheets else 0)
            self._excel_lbl.configure(
                text=f"{os.path.basename(path)}  ({len(self._columns)} cols, {len(self._sheets)} sheet(s))",
                text_color=C["accent"],
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not read Excel:\n{e}")

    def _on_sheet_change(self, sheet_name=None):
        if not self._excel_path:
            return
        sheet = sheet_name or self._combos["sheet"].get()
        if not sheet or sheet.startswith("("):
            return
        try:
            self._load_columns_for_sheet(sheet)
            self._excel_lbl.configure(
                text=f"{os.path.basename(self._excel_path)}  ({len(self._columns)} cols) · {sheet}",
                text_color=C["accent"],
            )
        except Exception as e:
            messagebox.showerror("Error", f"Could not read sheet '{sheet}':\n{e}")

    def _load_columns_for_sheet(self, sheet_name):
        df = pd.read_excel(self._excel_path, sheet_name=sheet_name, nrows=0)
        df.columns = df.columns.astype(str).str.strip()
        self._columns = list(df.columns)
        if not self._columns:
            raise ValueError("No columns found on this sheet.")

        for key, _, candidates in SOURCES:
            cb = self._combos[key]
            cb.configure(values=self._columns)
            found = _find_col(self._columns, *candidates)
            cb.set(found or self._columns[0])

        out_cb = self._combos["output"]
        out_cb.configure(values=self._columns)
        out = _find_col(self._columns, *OUTPUT_COL_CANDIDATES)
        out_cb.set(out or self._columns[0])

    def _pick_folder(self, key, label):
        folder = filedialog.askdirectory(title=f"Select {label} folder")
        if not folder:
            return
        self._folder_paths[key] = folder
        self._folder_lbls[key].configure(
            text=os.path.basename(folder) or folder,
            text_color=C["accent"],
        )

    def _start(self):
        if not self._excel_path:
            messagebox.showwarning("Missing", "Select the Excel mapping file.")
            return
        if not self._columns:
            messagebox.showwarning("Missing", "Load the Excel file so columns appear in the dropdowns.")
            return

        sheet = self._combos["sheet"].get().strip()
        if not sheet or sheet.startswith("("):
            messagebox.showwarning("Missing", "Select an Excel sheet.")
            return

        sources = []
        for key, label, _ in SOURCES:
            folder = self._folder_paths[key]
            if not folder:
                messagebox.showwarning("Missing", f"Select a folder for {label}.")
                return
            col = self._combos[key].get().strip()
            if not col or col.startswith("("):
                messagebox.showwarning("Missing", f"Select filename column for {label}.")
                return
            sources.append({
                "key": key,
                "label": label,
                "folder": folder,
                "column": col,
            })

        out_col = self._combos["output"].get().strip()
        if not out_col or out_col.startswith("("):
            messagebox.showwarning("Missing", "Select the output filename column.")
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._stat.configure(text="Merging…", text_color=C["accent"])
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run, args=(sources, out_col, sheet), daemon=True,
        ).start()

    def _run(self, sources, out_col, sheet):
        out_dir = get_output_dir()

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        def prog(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"Excel   → {self._excel_path}")
            log(f"Sheet   → {sheet}")
            log(f"Output  → {out_dir}\n")
            stats = merge_mapped_pdfs(
                self._excel_path, sources, out_col, out_dir, log, prog,
                sheet_name=sheet,
            )
            log("\n========== SUMMARY ==========")
            log(f"Rows     : {stats['total']}")
            log(f"Merged   : {stats['merged']}")
            log(f"Skipped  : {stats['skipped']}")
            log(f"Errors   : {stats['errors']}")
            log(f"Log      : {stats['log']}")
            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {stats['merged']} merged, {stats['skipped']} skipped.",
                text_color=C["green"],
            ))
            self.after(0, lambda: subprocess.Popen(["explorer", stats["merged_folder"]]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Merged: {stats['merged']}\nSkipped: {stats['skipped']}\n"
                f"Errors: {stats['errors']}\n\n{stats['merged_folder']}",
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Merge PDFs",
            ))


if __name__ == "__main__":
    App().mainloop()
