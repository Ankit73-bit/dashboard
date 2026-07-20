"""
Tool: Tracking PDF Matcher
Match barcodes from Excel sheets to tracking PDFs, copy them into each
batch folder, and merge into a single MERGED.pdf.
"""

import os
import shutil
import threading
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PyPDF2 import PdfMerger

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Tracking_PDF_Matcher")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#bf5af2", "green":  "#30d158",
    "red":    "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"}

BARCODE_KEYWORDS = ("barcode", "tracking", "article")


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def find_barcode_excel(folder):
    """Return (excel_path, barcode_column) for the first matching sheet in folder."""
    try:
        files = os.listdir(folder)
    except OSError:
        return None, None

    for file in files:
        if not (file.endswith(".xlsx") or file.endswith(".xls")):
            continue
        if file.startswith("~$"):
            continue

        path = os.path.join(folder, file)
        try:
            df = pd.read_excel(path, nrows=5)
            for col in df.columns:
                name = str(col).lower()
                if any(k in name for k in BARCODE_KEYWORDS):
                    return path, col
        except Exception:
            continue

    return None, None


def match_folder(root, tracking_pdf_folder, log_fn):
    """
    Process one folder that contains a barcode Excel.
    Copies matching PDFs into <root>/Tracking/ and writes MERGED.pdf.
    Returns (copied, missing, excel_name) or None if no Excel found.
    """
    excel_path, barcode_column = find_barcode_excel(root)
    if not excel_path:
        return None

    log_fn(f"\n📂 Processing: {root}")
    log_fn(f"   Excel: {os.path.basename(excel_path)}  |  Column: {barcode_column}")

    df = pd.read_excel(excel_path)
    tracking_folder = os.path.join(root, "Tracking")
    os.makedirs(tracking_folder, exist_ok=True)

    merger = PdfMerger()
    copied = 0
    missing = []

    try:
        for barcode in df[barcode_column].dropna():
            barcode = str(barcode).strip()
            if not barcode or barcode.lower() == "nan":
                continue

            pdf_name = barcode + ".pdf"
            pdf_path = os.path.join(tracking_pdf_folder, pdf_name)

            if os.path.exists(pdf_path):
                dest = os.path.join(tracking_folder, pdf_name)
                shutil.copy2(pdf_path, dest)
                merger.append(dest)
                copied += 1
                log_fn(f"   ✅ Copied: {pdf_name}")
            else:
                missing.append(pdf_name)
                log_fn(f"   ❌ Missing: {pdf_name}")

        merged_file = os.path.join(tracking_folder, "MERGED.pdf")
        if copied:
            merger.write(merged_file)
            log_fn(f"   📎 Merged → {merged_file}")
        else:
            log_fn("   ⚠️  No PDFs found — MERGED.pdf not created.")
    finally:
        merger.close()

    return {
        "root": root,
        "excel": os.path.basename(excel_path),
        "column": str(barcode_column),
        "copied": copied,
        "missing": missing,
        "tracking_folder": tracking_folder,
    }


def run_matcher(main_folder, tracking_pdf_folder, log_fn, progress_fn):
    """Walk main_folder, match barcodes to tracking PDFs in each subfolder."""
    folders = []
    for root, dirs, _files in os.walk(main_folder):
        # Skip Tracking output folders so we don't re-process them
        dirs[:] = [d for d in dirs if d.lower() != "tracking"]
        folders.append(root)

    results = []
    total = len(folders)

    for i, root in enumerate(folders, 1):
        result = match_folder(root, tracking_pdf_folder, log_fn)
        if result:
            results.append(result)
        progress_fn(i / total if total else 1)

    return results


class TrackingPdfMatcherApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Tracking PDF Matcher")
        self.geometry("740x720")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self._main_folder = None
        self._pdf_folder = None
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(padx=28, pady=16)

        icon_f = ctk.CTkFrame(inner, width=48, height=48, fg_color=TINT["mid"], corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🔗", font=ctk.CTkFont("Segoe UI Emoji", 22)).place(
            relx=0.5, rely=0.5, anchor="center")

        txt = ctk.CTkFrame(inner, fg_color="transparent")
        txt.pack(side="left")
        ctk.CTkLabel(txt, text="Tracking PDF Matcher",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(txt, text="Match Excel barcodes to tracking PDFs, copy & merge per batch",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                      scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        banner = ctk.CTkFrame(body, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            banner,
            text="📁  Matched PDFs → <batch folder>\\Tracking\\  ·  Log → Desktop\\OUTPUT\\Tracking_PDF_Matcher\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"]
        ).pack(anchor="w", padx=14, pady=8)

        self._section(body, "Step 1 — Select Main Batch Folder")
        ctk.CTkLabel(body,
                     text="Walks all subfolders looking for Excel files with a barcode / tracking / article column.",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=C["faint"], anchor="w").pack(fill="x", pady=(0, 4))
        fr1 = ctk.CTkFrame(body, fg_color="transparent")
        fr1.pack(fill="x", pady=(0, 14))
        self._main_lbl = ctk.CTkLabel(
            fr1, text="No folder selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._main_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr1, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_main
        ).pack(side="right")

        self._section(body, "Step 2 — Select Tracking PDFs Folder")
        ctk.CTkLabel(body,
                     text="Folder of individual tracking PDFs named <barcode>.pdf",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=C["faint"], anchor="w").pack(fill="x", pady=(0, 4))
        fr2 = ctk.CTkFrame(body, fg_color="transparent")
        fr2.pack(fill="x", pady=(0, 14))
        self._pdf_lbl = ctk.CTkLabel(
            fr2, text="No folder selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._pdf_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr2, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_pdfs
        ).pack(side="right")

        self._section(body, "Progress")
        self._prog = ctk.CTkProgressBar(body, height=8, fg_color=C["card"],
                                        progress_color=C["accent"])
        self._prog.pack(fill="x", pady=(4, 8))
        self._prog.set(0)

        self._stat = ctk.CTkLabel(body, text="Ready.",
                                  font=ctk.CTkFont("Segoe UI", 11),
                                  text_color=C["muted"], anchor="w")
        self._stat.pack(fill="x", pady=(0, 8))

        self._log = ctk.CTkTextbox(body, height=220,
                                   font=ctk.CTkFont("Courier New", 11),
                                   fg_color=C["card"],
                                   border_color=C["border"], border_width=1,
                                   text_color=C["muted"], state="disabled")
        self._log.pack(fill="x", pady=(0, 16))

        self._run_btn = ctk.CTkButton(
            body, text="▶  Match & Merge Tracking PDFs",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"],
            border_color=C["accent"], border_width=1,
            corner_radius=24, height=48,
            command=self._start)
        self._run_btn.pack(fill="x", pady=(0, 20))

    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w").pack(fill="x", pady=(14, 2))

    def _write_log(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _pick_main(self):
        folder = filedialog.askdirectory(title="Select main batch folder")
        if not folder:
            return
        self._main_folder = folder
        self._main_lbl.configure(text=folder, text_color=C["accent"])

    def _pick_pdfs(self):
        folder = filedialog.askdirectory(title="Select tracking PDFs folder")
        if not folder:
            return
        self._pdf_folder = folder
        count = len([f for f in os.listdir(folder) if f.lower().endswith(".pdf")])
        self._pdf_lbl.configure(
            text=f"{folder}  ({count} PDF{'s' if count != 1 else ''})",
            text_color=C["accent"] if count else C["red"])

    def _start(self):
        if not self._main_folder:
            messagebox.showwarning("No Folder", "Please select the main batch folder.")
            return
        if not self._pdf_folder:
            messagebox.showwarning("No Folder", "Please select the tracking PDFs folder.")
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._stat.configure(text="Starting…", text_color=C["muted"])
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        out_dir = get_output_dir()

        def log(msg):
            self.after(0, lambda m=msg: self._write_log(m))

        def progress(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"Main folder  → {self._main_folder}")
            log(f"Tracking PDFs → {self._pdf_folder}")
            log(f"Run log      → {out_dir}\n")

            results = run_matcher(self._main_folder, self._pdf_folder, log, progress)

            if not results:
                log("\nNo Excel files with a barcode/tracking/article column were found.")
                self.after(0, lambda: self._stat.configure(
                    text="No matching Excel files found.", text_color=C["orange"]))
                self.after(0, lambda: messagebox.showwarning(
                    "Nothing Found",
                    "No Excel files with a barcode, tracking, or article column were found "
                    "in the selected folder tree."))
                return

            total_copied = sum(r["copied"] for r in results)
            total_missing = sum(len(r["missing"]) for r in results)

            # Write summary + missing list to OUTPUT
            summary_path = os.path.join(out_dir, "summary.txt")
            missing_path = os.path.join(out_dir, "missing.txt")
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(f"Main folder: {self._main_folder}\n")
                f.write(f"Tracking PDFs: {self._pdf_folder}\n")
                f.write(f"Folders processed: {len(results)}\n")
                f.write(f"PDFs copied: {total_copied}\n")
                f.write(f"PDFs missing: {total_missing}\n\n")
                for r in results:
                    f.write(f"{r['root']}\n")
                    f.write(f"  Excel: {r['excel']}  Column: {r['column']}\n")
                    f.write(f"  Copied: {r['copied']}  Missing: {len(r['missing'])}\n")
                    f.write(f"  Tracking: {r['tracking_folder']}\n\n")

            with open(missing_path, "w", encoding="utf-8") as f:
                for r in results:
                    for name in r["missing"]:
                        f.write(f"{r['root']}\t{name}\n")

            log(f"\n{'─' * 40}")
            log(f"Done!  {len(results)} folder(s)  |  ✅ {total_copied} copied  |  ❌ {total_missing} missing")
            log(f"Summary → {summary_path}")

            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {total_copied} copied, {total_missing} missing across {len(results)} folder(s).",
                text_color=C["green"]))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Processed {len(results)} folder(s).\n"
                f"✅ {total_copied} PDFs copied\n"
                f"❌ {total_missing} missing\n\n"
                f"Tracking folders are inside each batch folder.\n"
                f"Run log saved to:\n{out_dir}"
            ))
        except Exception as e:
            log(f"\n💥 Error: {e}")
            self.after(0, lambda: self._stat.configure(text=f"Error: {e}", text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Match & Merge Tracking PDFs"))


if __name__ == "__main__":
    TrackingPdfMatcherApp().mainloop()
