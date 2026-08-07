"""
Tool: Barcode Excel Matcher (Scan Step 2)
Exact + fuzzy match renamed barcode PDFs to Excel lists.
"""

import os
import sys
import shutil
import threading
import subprocess
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

# Allow importing sibling match.py (must resolve relative to this file)
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import match as matcher  # noqa: E402
except ModuleNotFoundError:
    # Show a clear error if launched without a console (Launch →)
    import tkinter as _tk
    from tkinter import messagebox as _mb
    _root = _tk.Tk()
    _root.withdraw()
    _mb.showerror(
        "Barcode Excel Matcher",
        "Could not load match.py from the scan_letter folder.\n\n"
        f"Expected:\n{os.path.join(_HERE, 'match.py')}"
    )
    _root.destroy()
    raise SystemExit(1)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Scan_Barcode_Matcher")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#30d158", "green": "#30d158",
    "red": "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#082a12", "mid": "#0f4020", "bdr": "#185c2e"}


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def run_match(pdf_folder, excel_folder, out_dir, log_fn, progress_fn):
    """Run matcher against user folders; mirror key outputs into out_dir."""
    not_found = os.path.join(out_dir, "not_found_barcodes")
    dup_conflict = os.path.join(out_dir, "duplicate_match_conflicts")
    os.makedirs(not_found, exist_ok=True)
    os.makedirs(dup_conflict, exist_ok=True)

    # Point matcher module at user / output folders
    matcher.PDF_FOLDER = pdf_folder
    matcher.EXCEL_FOLDER = excel_folder
    matcher.NOT_FOUND_FOLDER = not_found
    matcher.DUPLICATE_MATCH_FOLDER = dup_conflict
    matcher.RENAME_LOG_FILE = os.path.join(out_dir, "rename_match_log.csv")

    # Tee prints into UI log
    class _Tee:
        def write(self, s):
            if s and s.strip():
                log_fn(s.rstrip())
        def flush(self):
            pass

    old_stdout = sys.stdout
    sys.stdout = _Tee()
    try:
        progress_fn(0.1)
        excel_barcode_to_files, excel_files = matcher.load_excel_barcodes()
        if not excel_barcode_to_files:
            raise ValueError("No barcodes loaded from Excel folder.")

        progress_fn(0.3)
        matcher.prepare_log()

        progress_fn(0.4)
        (
            exact_count,
            fuzzy_count,
            moved_count,
            duplicate_conflict_count,
            found_barcodes,
            errors,
        ) = matcher.process_pdfs(excel_barcode_to_files)

        progress_fn(0.85)
        matcher.update_excel_remarks(excel_files)
        progress_fn(1.0)

        # Copy updated excels summary note
        excel_copy = os.path.join(out_dir, "excel_used")
        os.makedirs(excel_copy, exist_ok=True)
        for ef in excel_files:
            src = os.path.join(excel_folder, ef)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(excel_copy, ef))

        return {
            "exact": exact_count,
            "fuzzy": fuzzy_count,
            "moved": moved_count,
            "conflicts": duplicate_conflict_count,
            "errors": len(errors),
            "log": matcher.RENAME_LOG_FILE,
        }
    finally:
        sys.stdout = old_stdout


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Barcode Excel Matcher")
        self.geometry("760x640")
        self.configure(fg_color=C["bg"])
        self._pdf_folder = None
        self._excel_folder = None
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)
        ctk.CTkLabel(inn, text="🔗  Barcode Excel Matcher",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(inn, text="Scan Step 2 — exact + fuzzy match PDFs to Excel barcodes",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).pack(anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                      scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        banner = ctk.CTkFrame(body, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            banner, text="📁  Logs → Desktop\\OUTPUT\\Scan_Barcode_Matcher\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"]
        ).pack(anchor="w", padx=14, pady=8)

        self._folder_row(body, "Renamed PDFs folder (from Step 1)", "_pdf_lbl", self._pick_pdf)
        self._folder_row(body, "Excel folder (barcode / AWB lists)", "_excel_lbl", self._pick_excel)

        tip = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=10,
                           border_width=1, border_color=C["border"])
        tip.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            tip,
            text=("PDFs are matched in-place in the renamed folder.\n"
                  "Not-found & conflicts + log are saved to the OUTPUT timestamp folder.\n"
                  "Excel files are updated with a remark column."),
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
            justify="left", anchor="w"
        ).pack(anchor="w", padx=14, pady=10)

        self._prog = ctk.CTkProgressBar(body, height=8, fg_color=C["card"],
                                        progress_color=C["accent"])
        self._prog.pack(fill="x", pady=(4, 6))
        self._prog.set(0)
        self._stat = ctk.CTkLabel(body, text="Ready.", font=ctk.CTkFont("Segoe UI", 11),
                                  text_color=C["muted"], anchor="w")
        self._stat.pack(fill="x", pady=(0, 6))
        self._log = ctk.CTkTextbox(body, height=220, font=ctk.CTkFont("Courier New", 11),
                                   fg_color=C["card"], border_color=C["border"],
                                   border_width=1, text_color=C["muted"], state="disabled")
        self._log.pack(fill="x", pady=(0, 12))

        self._run_btn = ctk.CTkButton(
            body, text="▶  Match Barcodes",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            corner_radius=24, height=46, command=self._start)
        self._run_btn.pack(fill="x", pady=(0, 16))

    def _folder_row(self, parent, title, lbl_attr, cmd):
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w").pack(fill="x", pady=(10, 2))
        fr = ctk.CTkFrame(parent, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 8))
        lbl = ctk.CTkLabel(fr, text="No folder selected",
                           font=ctk.CTkFont("Segoe UI", 12),
                           text_color=C["muted"], anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        setattr(self, lbl_attr, lbl)
        ctk.CTkButton(fr, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"], command=cmd).pack(side="right")

    def _write(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _pick_pdf(self):
        folder = filedialog.askdirectory(title="Select renamed PDFs folder")
        if folder:
            self._pdf_folder = folder
            n = len([f for f in os.listdir(folder) if f.lower().endswith(".pdf")])
            self._pdf_lbl.configure(text=f"{folder}  ({n} PDFs)", text_color=C["accent"])

    def _pick_excel(self):
        folder = filedialog.askdirectory(title="Select Excel folder")
        if folder:
            self._excel_folder = folder
            n = len([f for f in os.listdir(folder)
                     if f.lower().endswith((".xls", ".xlsx"))])
            self._excel_lbl.configure(text=f"{folder}  ({n} Excel)", text_color=C["accent"])

    def _start(self):
        if not self._pdf_folder:
            messagebox.showwarning("Missing", "Select the renamed PDFs folder.")
            return
        if not self._excel_folder:
            messagebox.showwarning("Missing", "Select the Excel folder.")
            return
        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        out_dir = get_output_dir()

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        def prog(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"PDFs   → {self._pdf_folder}")
            log(f"Excel  → {self._excel_folder}")
            log(f"Output → {out_dir}\n")
            stats = run_match(self._pdf_folder, self._excel_folder, out_dir, log, prog)
            log("\n========== SUMMARY ==========")
            log(f"Exact matches : {stats['exact']}")
            log(f"Fuzzy matches : {stats['fuzzy']}")
            log(f"Not found     : {stats['moved']}")
            log(f"Conflicts     : {stats['conflicts']}")
            log(f"Errors        : {stats['errors']}")
            log(f"Log           : {stats['log']}")
            self.after(0, lambda: self._stat.configure(
                text=f"Done — exact {stats['exact']}, fuzzy {stats['fuzzy']}, missing {stats['moved']}.",
                text_color=C["green"]))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Exact: {stats['exact']}\nFuzzy: {stats['fuzzy']}\n"
                f"Not found: {stats['moved']}\nConflicts: {stats['conflicts']}\n\n"
                f"Next: Matched PDF Merger.\n\n{out_dir}"
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Match Barcodes"))


if __name__ == "__main__":
    App().mainloop()
