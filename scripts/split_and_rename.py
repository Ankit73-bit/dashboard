"""
Tool: PDF Split & Rename by SL
Split multi-page PDFs into page groups and rename each file from an SL number
found on the first page of the group (e.g. SL1186435).
"""

import os
import re
import csv
import threading
import subprocess
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from tkinter import filedialog, messagebox
from pypdf import PdfReader, PdfWriter

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Split_And_Rename")
DEFAULT_PATTERN = r"\bSL\d+\b"

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#bf5af2", "green":  "#30d158",
    "red":    "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"}


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


def split_and_rename_pdf(pdf_path, output_folder, pages_per_file, pattern, log_fn):
    """
    Split one PDF into page groups and rename by regex match on the first page.
    Returns (created, named, unknown).
    """
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    log_fn(f"\n{os.path.basename(pdf_path)} — {total_pages} page(s)")

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

        first_page_text = reader.pages[start].extract_text() or ""
        match = rx.search(first_page_text)

        if match:
            loan_number = match.group(0)
            filename = f"{loan_number}.pdf"
            named += 1
        else:
            filename = f"Unknown_{file_count}.pdf"
            unknown += 1

        output_path, final_name = unique_path(output_folder, filename)
        with open(output_path, "wb") as f:
            writer.write(f)

        page_range = f"{start + 1}-{min(start + pages_per_file, total_pages)}"
        status = "Named" if match else "Unknown"
        log_fn(f"  [{page_range}] → {final_name} ({status})")
        log_rows.append([
            os.path.basename(pdf_path), page_range, final_name, status,
            match.group(0) if match else "",
        ])
        created += 1
        file_count += 1

    return created, named, unknown, log_rows


def process_inputs(pdf_paths, out_dir, pages_per_file, pattern, log_fn, progress_fn):
    split_folder = os.path.join(out_dir, "split_pdfs")
    os.makedirs(split_folder, exist_ok=True)
    log_file = os.path.join(out_dir, "split_rename_log.csv")

    all_rows = []
    total_created = total_named = total_unknown = 0

    for i, pdf_path in enumerate(pdf_paths, 1):
        created, named, unknown, rows = split_and_rename_pdf(
            pdf_path, split_folder, pages_per_file, pattern, log_fn
        )
        total_created += created
        total_named += named
        total_unknown += unknown
        all_rows.extend(rows)
        progress_fn(i / len(pdf_paths))

    with open(log_file, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Source PDF", "Page Range", "Output File", "Status", "Matched ID"])
        w.writerows(all_rows)

    return {
        "created": total_created,
        "named": total_named,
        "unknown": total_unknown,
        "log_file": log_file,
        "split_folder": split_folder,
    }


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF Split & Rename by SL")
        self.geometry("740x700")
        self.configure(fg_color=C["bg"])
        self._pdfs = []
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
        ctk.CTkLabel(txt, text="PDF Split & Rename by SL",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(txt, text="Split PDFs into page groups · rename from SL number on page 1",
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
            text="📁  Output → Desktop\\OUTPUT\\Split_And_Rename\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"]
        ).pack(anchor="w", padx=14, pady=8)

        self._section(body, "Step 1 — Select PDF file(s)")
        fr = ctk.CTkFrame(body, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 8))
        self._src_lbl = ctk.CTkLabel(
            fr, text="No PDF selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._src_lbl.pack(side="left", fill="x", expand=True)
        btns = ctk.CTkFrame(fr, fg_color="transparent")
        btns.pack(side="right")
        ctk.CTkButton(
            btns, text="File…", width=80, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_file
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btns, text="Folder…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_folder
        ).pack(side="left")

        self._section(body, "Step 2 — Settings")
        settings = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                border_width=1, border_color=C["border"])
        settings.pack(fill="x", pady=(0, 14))
        settings.columnconfigure(1, weight=1)

        ctk.CTkLabel(settings, text="Pages per file",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"], width=120
                     ).grid(row=0, column=0, padx=16, pady=(14, 8), sticky="w")
        self._pages_e = ctk.CTkEntry(
            settings, width=100, height=34,
            fg_color=C["hover"], border_color=C["border"], text_color=C["text"])
        self._pages_e.grid(row=0, column=1, padx=16, pady=(14, 8), sticky="w")
        self._pages_e.insert(0, "2")

        ctk.CTkLabel(settings, text="ID pattern",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"], width=120
                     ).grid(row=1, column=0, padx=16, pady=(0, 14), sticky="w")
        self._pat_e = ctk.CTkEntry(
            settings, height=34,
            fg_color=C["hover"], border_color=C["border"], text_color=C["text"])
        self._pat_e.grid(row=1, column=1, padx=16, pady=(0, 14), sticky="ew")
        self._pat_e.insert(0, DEFAULT_PATTERN)
        ctk.CTkLabel(
            settings,
            text="Regex matched on the first page of each split (default: SL numbers).",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).grid(row=2, column=0, columnspan=2, padx=16, pady=(0, 12), sticky="w")

        self._section(body, "Progress")
        self._prog = ctk.CTkProgressBar(body, height=8, fg_color=C["card"],
                                        progress_color=C["accent"])
        self._prog.pack(fill="x", pady=(4, 8))
        self._prog.set(0)
        self._stat = ctk.CTkLabel(body, text="Ready.",
                                  font=ctk.CTkFont("Segoe UI", 11),
                                  text_color=C["muted"], anchor="w")
        self._stat.pack(fill="x", pady=(0, 8))
        self._log = ctk.CTkTextbox(body, height=200,
                                   font=ctk.CTkFont("Courier New", 11),
                                   fg_color=C["card"],
                                   border_color=C["border"], border_width=1,
                                   text_color=C["muted"], state="disabled")
        self._log.pack(fill="x", pady=(0, 16))

        self._run_btn = ctk.CTkButton(
            body, text="▶  Split & Rename",
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

    def _set_pdfs(self, paths):
        self._pdfs = [str(p) for p in paths]
        n = len(self._pdfs)
        if n == 0:
            self._src_lbl.configure(text="No PDF selected", text_color=C["muted"])
        elif n == 1:
            self._src_lbl.configure(text=self._pdfs[0], text_color=C["accent"])
        else:
            self._src_lbl.configure(
                text=f"{n} PDF files selected", text_color=C["accent"])

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
        threading.Thread(target=self._run, args=(pages, pattern), daemon=True).start()

    def _run(self, pages, pattern):
        out_dir = get_output_dir()

        def log(msg):
            self.after(0, lambda m=msg: self._write_log(m))

        def progress(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"PDFs    → {len(self._pdfs)} file(s)")
            log(f"Pages   → {pages} per split")
            log(f"Pattern → {pattern}")
            log(f"Output  → {out_dir}")

            stats = process_inputs(
                self._pdfs, out_dir, pages, pattern, log, progress
            )

            log("\n========== SUMMARY ==========")
            log(f"Created : {stats['created']}")
            log(f"Named   : {stats['named']}")
            log(f"Unknown : {stats['unknown']}")
            log(f"Log     : {stats['log_file']}")

            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {stats['named']} named, {stats['unknown']} unknown.",
                text_color=C["green"]))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Created: {stats['created']}\n"
                f"Named (SL): {stats['named']}\n"
                f"Unknown: {stats['unknown']}\n\n{out_dir}"
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
