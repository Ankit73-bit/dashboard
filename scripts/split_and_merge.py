"""
Tool: PDF Split & Zip
Split a folder of PDFs into fixed-size batches and create a ZIP for each batch.
"""

import os
import shutil
import threading
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Split_And_Merge")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#64d2ff", "green":  "#30d158",
    "red":    "#ff375f",
}
TINT = {"bg": "#062030", "mid": "#0a3550", "bdr": "#0f5070"}


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def split_and_zip(source_folder, output_folder, pdfs_per_batch, delete_folders_after_zip, log_fn, progress_fn):
    source = Path(source_folder)
    output = Path(output_folder)
    output.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(source.glob("*.pdf"))
    if not pdf_files:
        log_fn("No PDF files found in the selected folder.")
        return False, 0, 0

    total = len(pdf_files)
    batch_count = (total + pdfs_per_batch - 1) // pdfs_per_batch
    log_fn(f"Found {total} PDF file(s). Creating {batch_count} batch(es) of up to {pdfs_per_batch}.\n")

    for batch_no, start in enumerate(range(0, total, pdfs_per_batch), start=1):
        batch = pdf_files[start:start + pdfs_per_batch]
        folder_name = f"Batch_{batch_no:03d}"
        batch_folder = output / folder_name
        batch_folder.mkdir(exist_ok=True)

        log_fn(f"Creating {folder_name} ({len(batch)} PDFs)...")

        for pdf in batch:
            shutil.copy2(pdf, batch_folder / pdf.name)

        zip_path = output / f"{folder_name}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
            for file in batch_folder.iterdir():
                zipf.write(file, arcname=file.name)

        log_fn(f"  Created {zip_path.name}")

        if delete_folders_after_zip:
            shutil.rmtree(batch_folder)

        progress_fn(batch_no / batch_count)

    return True, total, batch_count


class SplitAndMergeApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF Split & Zip")
        self.geometry("720x680")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self._source = None
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(padx=28, pady=16)

        icon_f = ctk.CTkFrame(inner, width=48, height=48, fg_color=TINT["mid"], corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="📦", font=ctk.CTkFont("Segoe UI Emoji", 22)).place(
            relx=0.5, rely=0.5, anchor="center")

        txt = ctk.CTkFrame(inner, fg_color="transparent")
        txt.pack(side="left")
        ctk.CTkLabel(txt, text="PDF Split & Zip",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(txt, text="Split PDFs into batches and create a ZIP for each batch",
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
            text="📁  Output → Desktop\\OUTPUT\\Split_And_Merge\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"]
        ).pack(anchor="w", padx=14, pady=8)

        self._section(body, "Step 1 — Select PDF Source Folder")
        fr = ctk.CTkFrame(body, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 14))
        self._folder_lbl = ctk.CTkLabel(
            fr, text="No folder selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._folder_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_folder
        ).pack(side="right")

        self._section(body, "Step 2 — Batch Settings")
        settings = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                border_width=1, border_color=C["border"])
        settings.pack(fill="x", pady=(0, 14))
        settings.columnconfigure(1, weight=1)

        ctk.CTkLabel(settings, text="PDFs per batch",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"], anchor="w", width=130
                     ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")
        self._batch_e = ctk.CTkEntry(
            settings, font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["hover"], border_color=C["border"],
            text_color=C["text"], height=36, width=120)
        self._batch_e.grid(row=0, column=1, padx=16, pady=(14, 6), sticky="w")
        self._batch_e.insert(0, "500")

        self._delete_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            settings, text="Delete temporary batch folders after creating ZIPs",
            variable=self._delete_var,
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"],
            fg_color=C["accent"], hover_color=TINT["bdr"]
        ).grid(row=1, column=0, columnspan=2, padx=16, pady=(6, 14), sticky="w")

        self._section(body, "Progress")
        self._prog = ctk.CTkProgressBar(body, height=8, fg_color=C["card"],
                                        progress_color=C["accent"])
        self._prog.pack(fill="x", pady=(4, 8))
        self._prog.set(0)

        self._stat = ctk.CTkLabel(body, text="Ready.",
                                  font=ctk.CTkFont("Segoe UI", 11),
                                  text_color=C["muted"], anchor="w")
        self._stat.pack(fill="x", pady=(0, 8))

        self._log = ctk.CTkTextbox(body, height=180,
                                   font=ctk.CTkFont("Courier New", 11),
                                   fg_color=C["card"],
                                   border_color=C["border"], border_width=1,
                                   text_color=C["muted"], state="disabled")
        self._log.pack(fill="x", pady=(0, 16))

        self._run_btn = ctk.CTkButton(
            body, text="▶  Split & Create ZIPs",
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

    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Select folder containing PDFs")
        if not folder:
            return
        self._source = folder
        count = len(list(Path(folder).glob("*.pdf")))
        self._folder_lbl.configure(
            text=f"{folder}  ({count} PDF{'s' if count != 1 else ''})",
            text_color=C["accent"] if count else C["red"])

    def _start(self):
        if not self._source:
            messagebox.showwarning("No Folder", "Please select a source folder first.")
            return
        try:
            pdfs_per_batch = int(self._batch_e.get().strip())
            if pdfs_per_batch < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Invalid Batch Size", "PDFs per batch must be a positive number.")
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._stat.configure(text="Starting…", text_color=C["muted"])
        threading.Thread(
            target=self._run,
            args=(pdfs_per_batch, self._delete_var.get()),
            daemon=True
        ).start()

    def _run(self, pdfs_per_batch, delete_folders):
        out_dir = get_output_dir()

        def log(msg):
            self.after(0, lambda m=msg: self._write_log(m))

        def progress(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"Source → {self._source}")
            log(f"Output → {out_dir}\n")

            ok, total, batches = split_and_zip(
                self._source, out_dir, pdfs_per_batch, delete_folders, log, progress
            )

            if not ok:
                self.after(0, lambda: self._stat.configure(
                    text="No PDF files found.", text_color=C["red"]))
                self.after(0, lambda: messagebox.showwarning(
                    "No PDFs", "No PDF files were found in the selected folder."))
                return

            log(f"\nDone! {total} PDF(s) split into {batches} ZIP batch(es).")
            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {batches} ZIP batch(es) created from {total} PDF(s).",
                text_color=C["green"]))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Created {batches} ZIP batch(es) from {total} PDF(s).\n\nSaved to:\n{out_dir}"
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=f"Error: {e}", text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Split & Create ZIPs"))


if __name__ == "__main__":
    SplitAndMergeApp().mainloop()
