"""
Tool: PDF to JPG
Convert a single PDF or a folder of PDFs into JPG images — one image per page.
Embeddable Panel + standalone window.
"""

import os
import threading
import subprocess
from pathlib import Path
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "PDF_to_JPG")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#ff9f0a", "green":  "#30d158",
    "red":    "#ff375f",
}
TINT = {"bg": "#2e1e00", "mid": "#4a3000", "bdr": "#6b4500"}


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def _check_pdf2image():
    try:
        from pdf2image import convert_from_path  # noqa: F401
        return True
    except ImportError:
        return False


# ─── Embeddable Panel Content ─────────────────────────────────────────────────

class PdfToJpgPanelContent(ctk.CTkScrollableFrame):

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=C["border"], **kw)
        self._source_path = None   # file or folder
        self._mode = "single"
        self._build()

    def _build(self):
        # Dependency warning if pdf2image missing
        if not _check_pdf2image():
            warn = ctk.CTkFrame(self, fg_color="#300a14", corner_radius=10,
                                border_width=1, border_color=C["red"])
            warn.pack(fill="x", pady=(4, 10))
            ctk.CTkLabel(warn,
                         text="⚠️  pdf2image not installed.  Run:  pip install pdf2image",
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["red"]).pack(anchor="w", padx=14, pady=8)

        # Output banner
        banner = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(4, 14))
        ctk.CTkLabel(banner,
                     text="📁  Output → Desktop\\OUTPUT\\PDF_to_JPG\\<timestamp>\\",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["accent"]).pack(anchor="w", padx=14, pady=8)

        # Step 1 — Mode
        self._sec("Step 1 — Mode")
        mode_row = ctk.CTkFrame(self, fg_color="transparent")
        mode_row.pack(fill="x", pady=(0, 10))
        self._mode_var = ctk.StringVar(value="single")
        for lbl, val in [("Single PDF file", "single"), ("Folder of PDFs", "folder")]:
            ctk.CTkRadioButton(
                mode_row, text=lbl, variable=self._mode_var, value=val,
                font=ctk.CTkFont("Segoe UI", 12), text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"],
                border_color=C["border"],
                command=self._on_mode_change
            ).pack(side="left", padx=(0, 28))

        # Step 2 — Source
        self._sec("Step 2 — Select source")
        src_row = ctk.CTkFrame(self, fg_color="transparent")
        src_row.pack(fill="x", pady=(0, 10))
        self._src_lbl = ctk.CTkLabel(
            src_row, text="Nothing selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._src_lbl.pack(side="left", fill="x", expand=True)
        self._browse_btn = ctk.CTkButton(
            src_row, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick)
        self._browse_btn.pack(side="right")

        # Step 3 — DPI
        self._sec("Step 3 — Output resolution (DPI)")
        dpi_row = ctk.CTkFrame(self, fg_color="transparent")
        dpi_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(dpi_row, text="DPI:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 12))
        self._dpi_var = ctk.StringVar(value="150")
        ctk.CTkEntry(dpi_row, textvariable=self._dpi_var,
                     fg_color=C["card"], border_color=C["border"],
                     text_color=C["text"], height=34, width=80
                     ).pack(side="left")
        ctk.CTkLabel(dpi_row,
                     text="   72 = screen  ·  150 = balanced  ·  300 = print quality",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=C["faint"]).pack(side="left")

        # Step 4 — Run
        self._sec("Step 4 — Run")
        self._run_btn = ctk.CTkButton(
            self, text="▶  Convert to JPG",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["bg"], hover_color=TINT["mid"],
            border_color=C["accent"], border_width=1,
            text_color=C["accent"], height=44,
            command=self._run)
        self._run_btn.pack(fill="x", pady=(0, 10))

        self._prog = ctk.CTkProgressBar(
            self, fg_color=C["card"], progress_color=C["accent"], height=8)
        self._prog.set(0)
        self._prog.pack(fill="x", pady=(0, 4))

        self._stat = ctk.CTkLabel(
            self, text="Ready.",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], anchor="w")
        self._stat.pack(fill="x", pady=(0, 10))

        # Log
        self._sec("Log")
        self._log_box = ctk.CTkTextbox(
            self, height=200, fg_color=C["card"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], font=ctk.CTkFont("Consolas", 11))
        self._log_box.pack(fill="both", expand=True, pady=(0, 16))

    def _sec(self, t):
        ctk.CTkLabel(self, text=t.upper(),
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["muted"]).pack(anchor="w", pady=(8, 3))

    def _log(self, msg):
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")

    def _set_stat(self, msg, color=None):
        self._stat.configure(text=msg, text_color=color or C["muted"])

    def _on_mode_change(self):
        self._source_path = None
        self._src_lbl.configure(text="Nothing selected", text_color=C["muted"])

    def _pick(self):
        if self._mode_var.get() == "single":
            p = filedialog.askopenfilename(
                title="Select PDF file",
                filetypes=[("PDF files", "*.pdf")])
        else:
            p = filedialog.askdirectory(title="Select folder containing PDFs")
        if not p:
            return
        self._source_path = p
        self._src_lbl.configure(
            text=os.path.basename(p) or p, text_color=C["text"])

    def _run(self):
        if not _check_pdf2image():
            messagebox.showerror("Missing Dependency",
                                 "pdf2image is not installed.\n\nRun:  pip install pdf2image\n\n"
                                 "Also ensure Poppler is installed and in your system PATH.")
            return
        if not self._source_path:
            messagebox.showwarning("No Source", "Please select a PDF file or folder first.")
            return
        try:
            dpi = int(self._dpi_var.get())
        except ValueError:
            messagebox.showwarning("Bad DPI", "DPI must be a whole number (e.g. 150).")
            return

        self._run_btn.configure(state="disabled", text="Converting…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(target=self._process, args=(dpi,), daemon=True).start()

    def _process(self, dpi):
        from pdf2image import convert_from_path
        out_dir = get_output_dir()
        mode    = self._mode_var.get()

        try:
            if mode == "single":
                pdfs = [self._source_path]
            else:
                pdfs = [
                    os.path.join(self._source_path, f)
                    for f in os.listdir(self._source_path)
                    if f.lower().endswith(".pdf")
                ]

            total = len(pdfs)
            self._log(f"📄 PDFs found: {total}")
            self._log(f"🖼️  DPI: {dpi}")

            total_pages = 0
            for idx, pdf_path in enumerate(pdfs, 1):
                name = Path(pdf_path).stem
                self._log(f"\n[{idx}/{total}] Converting: {os.path.basename(pdf_path)}")
                self.after(0, lambda v=idx / total * 0.9: self._prog.set(v))

                pages = convert_from_path(pdf_path, dpi=dpi)
                for i, page in enumerate(pages, 1):
                    out_name = f"{name}_page_{i:03d}.jpg"
                    page.save(os.path.join(out_dir, out_name), "JPEG")
                    total_pages += 1
                self._log(f"   ✅ {len(pages)} page(s) saved")

            self.after(0, lambda: self._prog.set(1))
            self._log(f"\n🏁 Done!  {total} PDF(s) → {total_pages} JPG(s) → {out_dir}")
            self.after(0, lambda: self._set_stat(
                f"Done! {total} PDF(s) → {total_pages} image(s) saved.", C["green"]))
            subprocess.Popen(["explorer", out_dir])

        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Convert to JPG"))


# ─── Embeddable Panel wrapper ─────────────────────────────────────────────────
class PdfToJpgPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        PdfToJpgPanelContent(self).pack(fill="both", expand=True, padx=16, pady=8)


# ─── Standalone App ───────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF to JPG")
        self.geometry("800x740")
        self.configure(fg_color=C["bg"])

        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)

        icon_f = ctk.CTkFrame(inn, width=44, height=44,
                              fg_color=TINT["mid"], corner_radius=10)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🖼️",
                     font=ctk.CTkFont("Segoe UI Emoji", 20)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(tx, text="PDF to JPG",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx, text="Convert single PDFs or entire folders to JPG images",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        PdfToJpgPanelContent(self).pack(fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
