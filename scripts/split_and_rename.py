"""
Tool: PDF Split & Rename
Split multi-page PDFs into page groups and rename each file by:
  A) Regex match on the first page text (e.g. SL1186435), or
  B) Excel column values in split order (row 1 → first split, row 2 → second, …)
"""

import os
import re
import csv
import threading
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import customtkinter as ctk
from tkinter import filedialog, messagebox
from pypdf import PdfReader, PdfWriter

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Split_And_Rename")
DEFAULT_PATTERN = r"\bSL\d+\b"

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#bf5af2", "green": "#30d158",
    "red": "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"}

MODE_PATTERN = "From page text (regex)"
MODE_EXCEL = "From Excel (order)"


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def unique_path(folder, filename):
    dest = os.path.join(folder, filename)
    if not os.path.exists(dest):
        return dest, filename
    base, ext = os.path.splitext(filename)
    n = 1
    while True:
        name = f"{base}_{n}{ext}"
        dest = os.path.join(folder, name)
        if not os.path.exists(dest):
            return dest, name
        n += 1


def safe_id(value):
    """Normalize Excel cell → safe filename stem."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none"):
        return ""
    if re.fullmatch(r"-?\d+\.0+", s):
        s = s.split(".", 1)[0]
    if s.lower().endswith(".pdf"):
        s = s[:-4]
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s).strip(" .")
    return s


def load_excel_ids(excel_path, column, sheet_name=0):
    """Return ordered list of non-empty ID strings from one Excel column."""
    df = pd.read_excel(excel_path, sheet_name=sheet_name, dtype=str)
    df.columns = [str(c).strip() for c in df.columns]
    if column not in df.columns:
        raise ValueError(
            f"Column '{column}' not found.\nAvailable: {', '.join(map(str, df.columns))}"
        )
    ids = []
    for v in df[column].tolist():
        sid = safe_id(v)
        if sid:
            ids.append(sid)
    if not ids:
        raise ValueError(f"No usable values in column '{column}'.")
    return ids


def count_splits(pdf_paths, pages_per_file):
    total = 0
    for pdf_path in pdf_paths:
        n = len(PdfReader(str(pdf_path)).pages)
        total += (n + pages_per_file - 1) // pages_per_file
    return total


def split_and_rename_pdf(
    pdf_path,
    output_folder,
    pages_per_file,
    log_fn,
    pattern=None,
    id_iter=None,
):
    """
    Split one PDF into page groups.
    Rename by regex (pattern) OR by consuming IDs from id_iter (Excel order).
    Returns (created, named, unknown, log_rows).
    """
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    log_fn(f"\n{os.path.basename(pdf_path)} — {total_pages} page(s)")

    rx = None
    if pattern is not None:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}") from e

    created = named = unknown = 0
    file_count = 1
    log_rows = []

    for start in range(0, total_pages, pages_per_file):
        writer = PdfWriter()
        for i in range(start, min(start + pages_per_file, total_pages)):
            writer.add_page(reader.pages[i])

        matched_id = ""
        if id_iter is not None:
            # Excel order mode
            try:
                loan_number = next(id_iter)
            except StopIteration:
                loan_number = None
            if loan_number:
                filename = f"{loan_number}.pdf"
                matched_id = loan_number
                named += 1
                status = "Named (Excel order)"
            else:
                filename = f"Unknown_{file_count}.pdf"
                unknown += 1
                status = "Unknown (no Excel row left)"
        else:
            # Regex mode
            first_page_text = reader.pages[start].extract_text() or ""
            match = rx.search(first_page_text) if rx else None
            if match:
                loan_number = match.group(0)
                filename = f"{loan_number}.pdf"
                matched_id = loan_number
                named += 1
                status = "Named"
            else:
                filename = f"Unknown_{file_count}.pdf"
                unknown += 1
                status = "Unknown"

        output_path, final_name = unique_path(output_folder, filename)
        with open(output_path, "wb") as f:
            writer.write(f)

        page_range = f"{start + 1}-{min(start + pages_per_file, total_pages)}"
        log_fn(f"  [{page_range}] → {final_name} ({status})")
        log_rows.append([
            os.path.basename(pdf_path), page_range, final_name, status, matched_id,
        ])
        created += 1
        file_count += 1

    return created, named, unknown, log_rows


def process_inputs(
    pdf_paths,
    out_dir,
    pages_per_file,
    log_fn,
    progress_fn,
    pattern=None,
    excel_ids=None,
):
    split_folder = os.path.join(out_dir, "split_pdfs")
    os.makedirs(split_folder, exist_ok=True)
    log_file = os.path.join(out_dir, "split_rename_log.csv")

    id_iter = iter(excel_ids) if excel_ids is not None else None
    all_rows = []
    total_created = total_named = total_unknown = 0

    for i, pdf_path in enumerate(pdf_paths, 1):
        created, named, unknown, rows = split_and_rename_pdf(
            pdf_path, split_folder, pages_per_file, log_fn,
            pattern=pattern, id_iter=id_iter,
        )
        total_created += created
        total_named += named
        total_unknown += unknown
        all_rows.extend(rows)
        progress_fn(i / len(pdf_paths))

    leftover = 0
    if excel_ids is not None and id_iter is not None:
        leftover = sum(1 for _ in id_iter)
        if leftover:
            log_fn(f"\n⚠ {leftover} Excel ID(s) unused (more rows than splits).")

    with open(log_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Source PDF", "Page Range", "Output File", "Status", "Matched ID"])
        w.writerows(all_rows)

    return {
        "created": total_created,
        "named": total_named,
        "unknown": total_unknown,
        "leftover_excel": leftover,
        "log_file": log_file,
        "split_folder": split_folder,
    }


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF Split & Rename")
        self.geometry("760x820")
        self.minsize(680, 700)
        self.configure(fg_color=C["bg"])
        self._pdfs = []
        self._excel_path = None
        self._excel_columns = []
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(padx=28, pady=16)

        icon_f = ctk.CTkFrame(inner, width=48, height=48, fg_color=TINT["mid"], corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="✂️", font=ctk.CTkFont("Segoe UI Emoji", 22)).place(
            relx=0.5, rely=0.5, anchor="center")

        txt = ctk.CTkFrame(inner, fg_color="transparent")
        txt.pack(side="left")
        ctk.CTkLabel(
            txt, text="PDF Split & Rename",
            font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            txt, text="Split PDFs into page groups · rename by regex or Excel order",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(anchor="w")

        body = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C["border"],
        )
        body.pack(fill="both", expand=True, padx=24, pady=16)

        banner = ctk.CTkFrame(
            body, fg_color=TINT["bg"], corner_radius=10,
            border_width=1, border_color=C["accent"],
        )
        banner.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\Split_And_Rename\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"],
        ).pack(anchor="w", padx=14, pady=8)

        self._section(body, "Step 1 — Select PDF file(s)")
        fr = ctk.CTkFrame(body, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 8))
        self._src_lbl = ctk.CTkLabel(
            fr, text="No PDF selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w",
        )
        self._src_lbl.pack(side="left", fill="x", expand=True)
        btns = ctk.CTkFrame(fr, fg_color="transparent")
        btns.pack(side="right")
        ctk.CTkButton(
            btns, text="File…", width=80, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_file,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btns, text="Folder…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_folder,
        ).pack(side="left")

        self._section(body, "Step 2 — Rename mode")
        self._mode_var = ctk.StringVar(value=MODE_PATTERN)
        self._mode_seg = ctk.CTkSegmentedButton(
            body,
            values=[MODE_PATTERN, MODE_EXCEL],
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
        self._mode_seg.set(MODE_PATTERN)
        self._mode_seg.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            body,
            text="Excel (order): splits are renamed in sequence from the selected column "
                 "(1st split ← row 1, 2nd ← row 2, …). Page text is not read.",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
            anchor="w", wraplength=680, justify="left",
        ).pack(fill="x", pady=(0, 8))

        self._section(body, "Step 3 — Settings")
        settings = ctk.CTkFrame(
            body, fg_color=C["card"], corner_radius=12,
            border_width=1, border_color=C["border"],
        )
        settings.pack(fill="x", pady=(0, 10))
        settings.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            settings, text="Pages per file",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], width=120,
        ).grid(row=0, column=0, padx=16, pady=(14, 8), sticky="w")
        self._pages_e = ctk.CTkEntry(
            settings, width=100, height=34,
            fg_color=C["hover"], border_color=C["border"], text_color=C["text"],
        )
        self._pages_e.grid(row=0, column=1, padx=16, pady=(14, 8), sticky="w")
        self._pages_e.insert(0, "2")

        # Pattern mode widgets
        self._pat_lbl = ctk.CTkLabel(
            settings, text="ID pattern",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], width=120,
        )
        self._pat_lbl.grid(row=1, column=0, padx=16, pady=(0, 4), sticky="w")
        self._pat_e = ctk.CTkEntry(
            settings, height=34,
            fg_color=C["hover"], border_color=C["border"], text_color=C["text"],
        )
        self._pat_e.grid(row=1, column=1, padx=16, pady=(0, 4), sticky="ew")
        self._pat_e.insert(0, DEFAULT_PATTERN)
        self._pat_hint = ctk.CTkLabel(
            settings,
            text="Regex matched on the first page of each split (default: SL numbers).",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
        )
        self._pat_hint.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="w")

        # Excel mode widgets (hidden until mode switch)
        self._excel_lbl = ctk.CTkLabel(
            settings, text="Excel file",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], width=120,
        )
        self._excel_row = ctk.CTkFrame(settings, fg_color="transparent")
        self._excel_file_lbl = ctk.CTkLabel(
            self._excel_row, text="No file selected",
            font=ctk.CTkFont("Segoe UI", 12), text_color=C["muted"], anchor="w",
        )
        self._excel_file_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            self._excel_row, text="Browse…", width=80, height=30,
            fg_color=C["hover"], hover_color=C["border"],
            text_color=C["text"], command=self._pick_excel,
        ).pack(side="right")

        self._col_lbl = ctk.CTkLabel(
            settings, text="Rename column",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], width=120,
        )
        self._col_cb = ctk.CTkComboBox(
            settings, values=["(load Excel first)"], state="readonly",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["hover"], border_color=C["border"],
            button_color=TINT["mid"], button_hover_color=TINT["bdr"],
            dropdown_fg_color=C["card"], dropdown_hover_color=C["hover"],
            dropdown_text_color=C["text"], text_color=C["text"], height=34,
        )
        self._col_cb.set("(load Excel first)")
        self._excel_hint = ctk.CTkLabel(
            settings,
            text="IDs are used in Excel row order. Extra splits → Unknown_N; unused rows are logged.",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
        )

        self._section(body, "Progress")
        self._prog = ctk.CTkProgressBar(
            body, height=8, fg_color=C["card"], progress_color=C["accent"],
        )
        self._prog.pack(fill="x", pady=(4, 8))
        self._prog.set(0)
        self._stat = ctk.CTkLabel(
            body, text="Ready.",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], anchor="w",
        )
        self._stat.pack(fill="x", pady=(0, 8))
        self._log = ctk.CTkTextbox(
            body, height=200, font=ctk.CTkFont("Courier New", 11),
            fg_color=C["card"], border_color=C["border"], border_width=1,
            text_color=C["muted"], state="disabled",
        )
        self._log.pack(fill="x", pady=(0, 16))

        self._run_btn = ctk.CTkButton(
            body, text="▶  Split & Rename",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"],
            border_color=C["accent"], border_width=1,
            corner_radius=24, height=48,
            command=self._start,
        )
        self._run_btn.pack(fill="x", pady=(0, 20))

        self._on_mode_change(MODE_PATTERN)

    def _section(self, parent, text):
        ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color=C["text"], anchor="w",
        ).pack(fill="x", pady=(14, 2))

    def _is_excel_mode(self):
        return self._mode_seg.get() == MODE_EXCEL

    def _on_mode_change(self, value=None):
        excel = self._is_excel_mode()
        # Hide pattern widgets
        if excel:
            self._pat_lbl.grid_remove()
            self._pat_e.grid_remove()
            self._pat_hint.grid_remove()
            self._excel_lbl.grid(row=1, column=0, padx=16, pady=(0, 4), sticky="w")
            self._excel_row.grid(row=1, column=1, padx=16, pady=(0, 4), sticky="ew")
            self._col_lbl.grid(row=2, column=0, padx=16, pady=(0, 4), sticky="w")
            self._col_cb.grid(row=2, column=1, padx=16, pady=(0, 4), sticky="ew")
            self._excel_hint.grid(row=3, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="w")
        else:
            self._excel_lbl.grid_remove()
            self._excel_row.grid_remove()
            self._col_lbl.grid_remove()
            self._col_cb.grid_remove()
            self._excel_hint.grid_remove()
            self._pat_lbl.grid(row=1, column=0, padx=16, pady=(0, 4), sticky="w")
            self._pat_e.grid(row=1, column=1, padx=16, pady=(0, 4), sticky="ew")
            self._pat_hint.grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="w")

    def _write_log(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_pdfs(self, paths):
        self._pdfs = [str(p) for p in paths]
        n = len(self._pdfs)
        if n == 0:
            self._src_lbl.configure(text="No PDF selected", text_color=C["muted"])
        elif n == 1:
            self._src_lbl.configure(text=self._pdfs[0], text_color=C["accent"])
        else:
            self._src_lbl.configure(
                text=f"{n} PDF files selected", text_color=C["accent"],
            )

    def _pick_file(self):
        paths = filedialog.askopenfilenames(
            title="Select PDF file(s)",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if paths:
            self._set_pdfs(paths)

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Select folder containing PDFs")
        if not folder:
            return
        pdfs = sorted(Path(folder).glob("*.pdf")) + sorted(Path(folder).glob("*.PDF"))
        pdfs = sorted(set(pdfs))
        if not pdfs:
            messagebox.showwarning("No PDFs", "No PDF files found in that folder.")
            return
        self._set_pdfs(pdfs)

    def _pick_excel(self):
        path = filedialog.askopenfilename(
            title="Select Excel with rename IDs (row order = split order)",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            df = pd.read_excel(path, nrows=0)
            cols = [str(c).strip() for c in df.columns]
            if not cols:
                raise ValueError("No columns found.")
            self._excel_path = path
            self._excel_columns = cols
            self._excel_file_lbl.configure(
                text=f"{os.path.basename(path)}  ({len(cols)} cols)",
                text_color=C["accent"],
            )
            self._col_cb.configure(values=cols)
            # Prefer common ID columns
            lower = {c.lower(): c for c in cols}
            pick = None
            for key in (
                "loan account no", "loan_no", "loan no", "prospect_no", "prospect no",
                "barcode", "sr no", "sl", "id", "ref_no",
            ):
                if key in lower:
                    pick = lower[key]
                    break
            self._col_cb.set(pick or cols[0])
        except Exception as e:
            messagebox.showerror("Error", f"Could not read Excel:\n{e}")

    def _start(self):
        if not self._pdfs:
            messagebox.showwarning("Missing", "Select a PDF file or folder first.")
            return
        try:
            pages = int(self._pages_e.get().strip())
            if pages < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid", "Pages per file must be a positive number.")
            return

        excel_mode = self._is_excel_mode()
        pattern = None
        excel_ids = None

        if excel_mode:
            if not self._excel_path:
                messagebox.showwarning("Missing", "Select an Excel file for order rename.")
                return
            col = self._col_cb.get().strip()
            if not col or col.startswith("("):
                messagebox.showwarning("Missing", "Select the rename column.")
                return
            try:
                excel_ids = load_excel_ids(self._excel_path, col)
            except Exception as e:
                messagebox.showerror("Excel error", str(e))
                return
            # Pre-flight count hint
            try:
                n_splits = count_splits(self._pdfs, pages)
                if n_splits > len(excel_ids):
                    if not messagebox.askyesno(
                        "Not enough Excel rows",
                        f"Expected splits: {n_splits}\n"
                        f"Excel IDs: {len(excel_ids)}\n\n"
                        f"{n_splits - len(excel_ids)} split(s) will be Unknown_N.\n"
                        "Continue?",
                    ):
                        return
                elif len(excel_ids) > n_splits:
                    if not messagebox.askyesno(
                        "Extra Excel rows",
                        f"Expected splits: {n_splits}\n"
                        f"Excel IDs: {len(excel_ids)}\n\n"
                        f"{len(excel_ids) - n_splits} Excel ID(s) will be unused.\n"
                        "Continue?",
                    ):
                        return
            except Exception as e:
                messagebox.showerror("Error", f"Could not count PDF pages:\n{e}")
                return
        else:
            pattern = self._pat_e.get().strip() or DEFAULT_PATTERN
            try:
                re.compile(pattern)
            except re.error as e:
                messagebox.showwarning("Invalid pattern", f"Regex error: {e}")
                return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run,
            args=(pages, pattern, excel_ids, excel_mode),
            daemon=True,
        ).start()

    def _run(self, pages, pattern, excel_ids, excel_mode):
        out_dir = get_output_dir()

        def log(msg):
            self.after(0, lambda m=msg: self._write_log(m))

        def progress(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"PDFs    → {len(self._pdfs)} file(s)")
            log(f"Pages   → {pages} per split")
            if excel_mode:
                log(f"Mode    → Excel order")
                log(f"Excel   → {os.path.basename(self._excel_path)}")
                log(f"Column  → {self._col_cb.get()}")
                log(f"IDs     → {len(excel_ids)}")
            else:
                log(f"Mode    → Regex")
                log(f"Pattern → {pattern}")
            log(f"Output  → {out_dir}")

            stats = process_inputs(
                self._pdfs, out_dir, pages, log, progress,
                pattern=pattern, excel_ids=excel_ids,
            )

            log("\n========== SUMMARY ==========")
            log(f"Created : {stats['created']}")
            log(f"Named   : {stats['named']}")
            log(f"Unknown : {stats['unknown']}")
            if excel_mode and stats.get("leftover_excel"):
                log(f"Unused Excel IDs : {stats['leftover_excel']}")
            log(f"Log     : {stats['log_file']}")

            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {stats['named']} named, {stats['unknown']} unknown.",
                text_color=C["green"],
            ))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Created: {stats['created']}\n"
                f"Named: {stats['named']}\n"
                f"Unknown: {stats['unknown']}\n\n{out_dir}",
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Split & Rename",
            ))


if __name__ == "__main__":
    App().mainloop()
