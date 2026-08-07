"""
Tool: Barcode Split & Rename (Scan Step 1)
Split scanned PDFs, read barcodes, rename by barcode.
"""

import os
import csv
import shutil
import threading
import subprocess
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PyPDF2 import PdfReader, PdfWriter

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Scan_Split_Rename")
_HERE = os.path.dirname(os.path.abspath(__file__))
POPPLER_PATH = os.path.join(_HERE, "poppler-25.07.0", "Library", "bin")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#00f5ff", "green": "#30d158",
    "red": "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#062d30", "mid": "#0a4a4e", "bdr": "#0d6b70"}


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def split_pdf(input_pdf, pages_per_split, output_folder, log_fn):
    reader = PdfReader(input_pdf)
    total_pages = len(reader.pages)
    split_files = []
    base = os.path.splitext(os.path.basename(input_pdf))[0]

    for i in range(0, total_pages, pages_per_split):
        writer = PdfWriter()
        for j in range(i, min(i + pages_per_split, total_pages)):
            writer.add_page(reader.pages[j])

        output_path = os.path.join(
            output_folder, f"{base}_split_{i // pages_per_split + 1}.pdf"
        )
        if not os.path.exists(output_path):
            with open(output_path, "wb") as f:
                writer.write(f)
            log_fn(f"  Created split: {os.path.basename(output_path)}")
        else:
            log_fn(f"  Split exists: {os.path.basename(output_path)}")
        split_files.append(output_path)

    return split_files


def extract_barcode_from_pdf(pdf_path, poppler_path, log_fn):
    try:
        from pdf2image import convert_from_path
        from pyzbar.pyzbar import decode
    except ImportError as e:
        log_fn(f"Missing dependency: {e}")
        return None

    kwargs = dict(dpi=300, first_page=1, last_page=2)
    if poppler_path and os.path.isdir(poppler_path):
        kwargs["poppler_path"] = poppler_path

    try:
        pages = convert_from_path(pdf_path, **kwargs)
        for page_num, img in enumerate(pages, start=1):
            barcodes = decode(img)
            if barcodes:
                data = barcodes[0].data.decode("utf-8").strip()
                log_fn(f"  Barcode on page {page_num}: {data}")
                return data
    except Exception as e:
        log_fn(f"  Barcode error: {e}")
    return None


def get_unique_filename(folder, barcode):
    counter = 0
    while True:
        filename = f"{barcode}.pdf" if counter == 0 else f"{barcode}_{counter}.pdf"
        full_path = os.path.join(folder, filename)
        if not os.path.exists(full_path):
            return filename, full_path
        counter += 1


def process_pdfs(input_folder, out_dir, pages_per_split, poppler_path, log_fn, progress_fn):
    split_folder = os.path.join(out_dir, "split_pdfs")
    renamed_folder = os.path.join(out_dir, "renamed_pdfs")
    not_renamed_folder = os.path.join(out_dir, "not_renamed_pdfs")
    duplicate_folder = os.path.join(out_dir, "duplicate_pdfs")

    for d in (split_folder, renamed_folder, not_renamed_folder, duplicate_folder):
        os.makedirs(d, exist_ok=True)

    log_file = os.path.join(renamed_folder, "rename_log.csv")
    with open(log_file, "w", newline="", encoding="utf-8") as log:
        csv.writer(log).writerow(["Original Filename", "New Filename", "Barcode", "Status"])

    pdfs = [f for f in os.listdir(input_folder) if f.lower().endswith(".pdf")]
    if not pdfs:
        raise ValueError("No PDF files found in the selected folder.")

    total_splits = renamed = duplicates = no_barcode = errors = 0
    # Rough progress: each source PDF is one unit
    for pi, filename in enumerate(pdfs, 1):
        pdf_path = os.path.join(input_folder, filename)
        log_fn(f"\nProcessing: {filename}")
        split_files = split_pdf(pdf_path, pages_per_split, split_folder, log_fn)

        with open(log_file, "a", newline="", encoding="utf-8") as log:
            writer = csv.writer(log)
            for split_pdf_path in split_files:
                total_splits += 1
                if not os.path.exists(split_pdf_path):
                    errors += 1
                    writer.writerow([split_pdf_path, "", "", "Missing Split File"])
                    continue

                barcode = extract_barcode_from_pdf(split_pdf_path, poppler_path, log_fn)
                if barcode:
                    try:
                        original_file = os.path.join(renamed_folder, f"{barcode}.pdf")
                        if os.path.exists(original_file):
                            duplicates += 1
                            dup_name, dup_path = get_unique_filename(duplicate_folder, barcode)
                            shutil.copy2(split_pdf_path, dup_path)
                            log_fn(f"  Duplicate → {dup_name}")
                            writer.writerow([split_pdf_path, dup_name, barcode, "Duplicate"])
                        else:
                            new_name = f"{barcode}.pdf"
                            shutil.copy2(split_pdf_path, os.path.join(renamed_folder, new_name))
                            renamed += 1
                            log_fn(f"  Saved → {new_name}")
                            writer.writerow([split_pdf_path, new_name, barcode, "Renamed"])
                    except Exception as e:
                        errors += 1
                        writer.writerow([split_pdf_path, "", barcode, f"Copy Error: {e}"])
                else:
                    try:
                        dest = os.path.join(not_renamed_folder, os.path.basename(split_pdf_path))
                        shutil.copy2(split_pdf_path, dest)
                        no_barcode += 1
                        log_fn("  No barcode → not_renamed")
                        writer.writerow([
                            split_pdf_path, os.path.basename(split_pdf_path), "", "No Barcode Found"
                        ])
                    except Exception as e:
                        errors += 1
                        writer.writerow([split_pdf_path, "", "", f"No Barcode Copy Error: {e}"])

        progress_fn(pi / len(pdfs))

    return {
        "total_splits": total_splits,
        "renamed": renamed,
        "duplicates": duplicates,
        "no_barcode": no_barcode,
        "errors": errors,
        "log_file": log_file,
        "renamed_folder": renamed_folder,
    }


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Barcode Split & Rename")
        self.geometry("760x700")
        self.configure(fg_color=C["bg"])
        self._folder = None
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)
        ctk.CTkLabel(inn, text="✂️  Barcode Split & Rename",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(inn, text="Scan Step 1 — split PDFs · read barcodes · rename",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).pack(anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                      scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        banner = ctk.CTkFrame(body, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            banner, text="📁  Output → Desktop\\OUTPUT\\Scan_Split_Rename\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"]
        ).pack(anchor="w", padx=14, pady=8)

        self._sec(body, "Scanned PDFs folder")
        fr = ctk.CTkFrame(body, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 10))
        self._folder_lbl = ctk.CTkLabel(fr, text="No folder selected",
                                        font=ctk.CTkFont("Segoe UI", 12),
                                        text_color=C["muted"], anchor="w")
        self._folder_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(fr, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"],
                      command=self._pick).pack(side="right")

        self._sec(body, "Settings")
        settings = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                border_width=1, border_color=C["border"])
        settings.pack(fill="x", pady=(0, 12))
        settings.columnconfigure(1, weight=1)

        ctk.CTkLabel(settings, text="Pages per split",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], width=120
                     ).grid(row=0, column=0, padx=16, pady=14, sticky="w")
        self._pages_e = ctk.CTkEntry(settings, width=100, height=34,
                                     fg_color=C["hover"], border_color=C["border"],
                                     text_color=C["text"])
        self._pages_e.grid(row=0, column=1, padx=16, pady=14, sticky="w")
        self._pages_e.insert(0, "2")

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
            body, text="▶  Split & Rename",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            corner_radius=24, height=46, command=self._start)
        self._run_btn.pack(fill="x", pady=(0, 16))

    def _sec(self, p, t):
        ctk.CTkLabel(p, text=t, font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w").pack(fill="x", pady=(10, 2))

    def _write(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _pick(self):
        folder = filedialog.askdirectory(title="Select scanned PDFs folder")
        if folder:
            self._folder = folder
            n = len([f for f in os.listdir(folder) if f.lower().endswith(".pdf")])
            self._folder_lbl.configure(text=f"{folder}  ({n} PDFs)", text_color=C["accent"])

    def _start(self):
        if not self._folder:
            messagebox.showwarning("Missing", "Select the scanned PDFs folder.")
            return
        try:
            pages = int(self._pages_e.get().strip())
            if pages < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid", "Pages per split must be a positive number.")
            return

        if not os.path.isdir(POPPLER_PATH):
            messagebox.showerror(
                "Poppler missing",
                f"Bundled Poppler not found at:\n{POPPLER_PATH}\n\n"
                "Place poppler-25.07.0 inside the scan_letter folder."
            )
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(target=self._run, args=(pages,), daemon=True).start()

    def _run(self, pages):
        out_dir = get_output_dir()

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        def prog(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"Input   → {self._folder}")
            log(f"Output  → {out_dir}")
            log(f"Poppler → {POPPLER_PATH}\n")
            stats = process_pdfs(self._folder, out_dir, pages, POPPLER_PATH, log, prog)
            log("\n========== SUMMARY ==========")
            log(f"Total splits : {stats['total_splits']}")
            log(f"Renamed      : {stats['renamed']}")
            log(f"Duplicates   : {stats['duplicates']}")
            log(f"No barcode   : {stats['no_barcode']}")
            log(f"Errors       : {stats['errors']}")
            log(f"Log          : {stats['log_file']}")
            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {stats['renamed']} renamed, {stats['no_barcode']} no barcode.",
                text_color=C["green"]))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Renamed: {stats['renamed']}\n"
                f"Duplicates: {stats['duplicates']}\n"
                f"No barcode: {stats['no_barcode']}\n\n"
                f"Next: use renamed_pdfs with Barcode Excel Matcher.\n\n{out_dir}"
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Split & Rename"))


if __name__ == "__main__":
    App().mainloop()
