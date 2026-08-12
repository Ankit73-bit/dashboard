"""
Tool: Envelope Pattern Checker (Scan Pre-check)
Batch-check IIFL envelope front/back page pairs; clean or audit PDFs.
"""

import os
import sys
import threading
import subprocess
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import check_envelope_pattern_batch as checker  # noqa: E402
except ModuleNotFoundError:
    import tkinter as _tk
    from tkinter import messagebox as _mb
    _root = _tk.Tk()
    _root.withdraw()
    _mb.showerror(
        "Envelope Pattern Checker",
        "Could not load check_envelope_pattern_batch.py from scan_letter.\n\n"
        f"Expected:\n{os.path.join(_HERE, 'check_envelope_pattern_batch.py')}"
    )
    _root.destroy()
    raise SystemExit(1)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Scan_Envelope_Pattern")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#ff9f0a", "green": "#30d158",
    "red": "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#2e1e00", "mid": "#4a3000", "bdr": "#6b4500"}


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Envelope Pattern Checker")
        self.geometry("780x720")
        self.configure(fg_color=C["bg"])
        self._folder = None
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)
        ctk.CTkLabel(
            inn, text="📋  Envelope Pattern Checker",
            font=ctk.CTkFont("Segoe UI", 18, "bold"),
            text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            inn,
            text="Pre-check — OCR front/back pairs · keep valid · log / remove bad pages",
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
        banner.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\Scan_Envelope_Pattern\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"],
        ).pack(anchor="w", padx=14, pady=8)

        self._sec(body, "Scanned PDFs folder")
        fr = ctk.CTkFrame(body, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 10))
        self._folder_lbl = ctk.CTkLabel(
            fr, text="No folder selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w",
        )
        self._folder_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick,
        ).pack(side="right")

        self._sec(body, "Settings")
        settings = ctk.CTkFrame(
            body, fg_color=C["card"], corner_radius=12,
            border_width=1, border_color=C["border"],
        )
        settings.pack(fill="x", pady=(0, 12))
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)

        self._dpi_e = self._setting(settings, 0, 0, "DPI", "300")
        self._thr_e = self._setting(settings, 0, 2, "Threshold", "65")
        self._batch_e = self._setting(settings, 1, 0, "Batch size", "20")
        self._workers_e = self._setting(settings, 1, 2, "Workers", "4")

        opts = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        opts.pack(fill="x", pady=(0, 12))
        self._remove_var = ctk.BooleanVar(value=True)
        self._recursive_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            opts, text="Remove bad pairs & write cleaned PDFs",
            variable=self._remove_var,
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["text"], fg_color=C["accent"],
            hover_color=TINT["bdr"], border_color=C["border"],
        ).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkCheckBox(
            opts, text="Include PDFs in subfolders",
            variable=self._recursive_var,
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["text"], fg_color=C["accent"],
            hover_color=TINT["bdr"], border_color=C["border"],
        ).pack(anchor="w", padx=16, pady=(4, 12))
        ctk.CTkLabel(
            opts,
            text="Unchecked = audit only (logs which pages fail; no cleaned PDF).",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(anchor="w", padx=16, pady=(0, 12))

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

        self._run_btn = ctk.CTkButton(
            body, text="▶  Check Envelope Pattern",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            corner_radius=24, height=46, command=self._start,
        )
        self._run_btn.pack(fill="x", pady=(0, 16))

    def _setting(self, parent, row, col, label, default):
        ctk.CTkLabel(
            parent, text=label, font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], width=90,
        ).grid(row=row, column=col, padx=(16, 4), pady=10, sticky="w")
        entry = ctk.CTkEntry(
            parent, width=90, height=34,
            fg_color=C["hover"], border_color=C["border"], text_color=C["text"],
        )
        entry.grid(row=row, column=col + 1, padx=(0, 16), pady=10, sticky="w")
        entry.insert(0, default)
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
        folder = filedialog.askdirectory(title="Select scanned PDFs folder")
        if folder:
            self._folder = folder
            n = len([f for f in os.listdir(folder) if f.lower().endswith(".pdf")])
            self._folder_lbl.configure(
                text=f"{folder}  ({n} PDFs)", text_color=C["accent"],
            )

    def _start(self):
        if not self._folder:
            messagebox.showwarning("Missing", "Select the scanned PDFs folder.")
            return
        try:
            dpi = int(self._dpi_e.get().strip())
            threshold = int(self._thr_e.get().strip())
            batch_size = int(self._batch_e.get().strip())
            workers = int(self._workers_e.get().strip())
            if dpi < 72 or threshold < 1 or batch_size < 2 or workers < 1:
                raise ValueError
        except ValueError:
            messagebox.showwarning(
                "Invalid",
                "Check settings: DPI ≥ 72, threshold ≥ 1, batch size ≥ 2, workers ≥ 1.",
            )
            return

        poppler = checker.get_poppler_path()
        if not poppler:
            messagebox.showerror(
                "Poppler missing",
                f"Bundled Poppler not found at:\n{checker.POPPLER_PATH}\n\n"
                "Place poppler-25.07.0 inside the scan_letter folder.",
            )
            return

        if not checker.configure_tesseract():
            messagebox.showerror(
                "Tesseract missing",
                "Tesseract OCR not found.\n"
                "Install Tesseract-OCR (e.g. C:\\Program Files\\Tesseract-OCR).",
            )
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run,
            args=(dpi, threshold, batch_size, workers),
            daemon=True,
        ).start()

    def _run(self, dpi, threshold, batch_size, workers):
        out_dir = get_output_dir()
        cleaned = os.path.join(out_dir, "cleaned_pdfs")
        logs = os.path.join(out_dir, "logs")
        summary = os.path.join(out_dir, "summary.csv")

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        def prog(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"Input   → {self._folder}")
            log(f"Output  → {out_dir}")
            log(f"Mode    → {'REMOVE' if self._remove_var.get() else 'AUDIT ONLY'}")
            log(f"Poppler → {checker.get_poppler_path()}\n")

            _rows, stats = checker.run_batch(
                input_dir=self._folder,
                output_dir=cleaned,
                log_dir=logs,
                summary_csv=summary,
                dpi=dpi,
                threshold=threshold,
                batch_size=batch_size,
                workers=workers,
                recursive=self._recursive_var.get(),
                remove=self._remove_var.get(),
                poppler_path=checker.get_poppler_path(),
                log_fn=log,
                progress_fn=prog,
            )

            log("\n========== SUMMARY ==========")
            log(f"Files OK     : {stats['ok']}")
            log(f"File errors  : {stats['errors']}")
            log(f"Pages kept   : {stats['kept_pages']}")
            log(f"Pages bad    : {stats['removed_pages']}")
            log(f"Summary CSV  : {stats['summary_csv']}")
            log(f"Elapsed      : {stats['elapsed']}s")

            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=(
                    f"Done — {stats['ok']} files, "
                    f"{stats['kept_pages']} kept, "
                    f"{stats['removed_pages']} bad pages."
                ),
                text_color=C["green"],
            ))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Files OK: {stats['ok']}\n"
                f"Errors: {stats['errors']}\n"
                f"Pages kept: {stats['kept_pages']}\n"
                f"Pages bad: {stats['removed_pages']}\n\n"
                f"Summary:\n{stats['summary_csv']}\n\n{out_dir}",
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Check Envelope Pattern",
            ))


if __name__ == "__main__":
    App().mainloop()
