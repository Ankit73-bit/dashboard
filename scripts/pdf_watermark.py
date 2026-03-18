import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import io
from datetime import datetime
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg":     "#0a0a0f",
    "card":   "#16161f",
    "border": "#2a2a3d",
    "hover":  "#1e1e2e",
    "text":   "#e8e8f0",
    "muted":  "#8888aa",
    "faint":  "#44445a",
    "accent": "#bf5af2",   # purple
}

TINT = {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"}


# ─── Helper: get Desktop OUTPUT path ──────────────────────────────────────────
def get_output_dir():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    ts      = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path    = os.path.join(desktop, "OUTPUT", "PDF_Watermark", ts)
    os.makedirs(path, exist_ok=True)
    return path


# ─── Watermark logic ──────────────────────────────────────────────────────────
def create_watermark_pdf(text, opacity, font_size, rotation, color_rgb, width, height):
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=(width, height))

    c.setFont("Helvetica-Bold", font_size)
    r, g, b = color_rgb
    c.setFillColorRGB(r, g, b, alpha=opacity)

    c.saveState()
    c.translate(width / 2, height / 2)  # dynamic center
    c.rotate(rotation)
    c.drawCentredString(0, 0, text)
    c.restoreState()

    c.save()
    packet.seek(0)

    return PdfReader(packet)

def watermark_pdf(input_path, output_path, text, opacity, font_size, rotation, color_rgb):

    reader = PdfReader(input_path)
    writer = PdfWriter()

    for page in reader.pages:

        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        watermark_reader = create_watermark_pdf(
            text, opacity, font_size, rotation, color_rgb, width, height
        )

        watermark_page = watermark_reader.pages[0]

        page.merge_page(watermark_page)
        writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)


# ─── App ──────────────────────────────────────────────────────────────────────
class WatermarkApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF Watermark Tool")
        self.geometry("720x760")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.selected_files = []
        self._build()

    def _build(self):
        # ── Header ──────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(padx=28, pady=16)

        icon_f = ctk.CTkFrame(inner, width=48, height=48,
                              fg_color=TINT["mid"], corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🔏",
                     font=ctk.CTkFont("Segoe UI Emoji", 22)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        txt = ctk.CTkFrame(inner, fg_color="transparent")
        txt.pack(side="left")
        ctk.CTkLabel(txt, text="PDF Watermark Tool",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(txt, text="Add diagonal watermark text to one or more PDF files",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        # ── Body ────────────────────────────────────────────────────────────
        body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                      scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # ── Section: Select PDFs ──
        self._section(body, "📂  Select PDF Files")

        file_row = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                border_width=1, border_color=C["border"])
        file_row.pack(fill="x", pady=(4, 10))

        self.file_label = ctk.CTkLabel(
            file_row, text="No files selected",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], anchor="w")
        self.file_label.pack(side="left", padx=16, pady=12, fill="x", expand=True)

        btn_row = ctk.CTkFrame(file_row, fg_color="transparent")
        btn_row.pack(side="right", padx=12)

        ctk.CTkButton(btn_row, text="Browse Files",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=TINT["mid"], hover_color=TINT["bdr"],
                      text_color=C["accent"], border_color=C["accent"], border_width=1,
                      corner_radius=20, height=32, width=120,
                      command=self._browse_files).pack(side="left", padx=(0, 6))

        ctk.CTkButton(btn_row, text="Browse Folder",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=TINT["mid"], hover_color=TINT["bdr"],
                      text_color=C["accent"], border_color=C["accent"], border_width=1,
                      corner_radius=20, height=32, width=120,
                      command=self._browse_folder).pack(side="left")

        # File list preview
        self.file_list_frame = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                            border_width=1, border_color=C["border"])
        self.file_list_frame.pack(fill="x", pady=(0, 10))
        self.file_list_label = ctk.CTkLabel(
            self.file_list_frame,
            text="Selected files will appear here",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=C["faint"])
        self.file_list_label.pack(padx=16, pady=10)

        # ── Section: Watermark Settings ──
        self._section(body, "⚙️  Watermark Settings")

        settings = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                border_width=1, border_color=C["border"])
        settings.pack(fill="x", pady=(4, 10))
        settings.columnconfigure(1, weight=1)

        # Watermark text
        self._field_label(settings, "Watermark Text", 0)
        self.wm_text = ctk.CTkEntry(
            settings, placeholder_text="e.g. CONFIDENTIAL or MSME",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["hover"], border_color=C["border"],
            text_color=C["text"], height=36)
        self.wm_text.grid(row=0, column=1, padx=16, pady=(12, 6), sticky="ew")
        self.wm_text.insert(0, "MSME")

        # Font size
        self._field_label(settings, "Font Size", 1)
        size_row = ctk.CTkFrame(settings, fg_color="transparent")
        size_row.grid(row=1, column=1, padx=16, pady=6, sticky="ew")
        self.font_size_var = ctk.IntVar(value=120)
        self.font_size_slider = ctk.CTkSlider(
            size_row, from_=40, to=220, variable=self.font_size_var,
            fg_color=TINT["bg"], progress_color=C["accent"],
            button_color=C["accent"], button_hover_color=TINT["bdr"],
            command=lambda v: self.font_size_display.configure(text=str(int(v))))
        self.font_size_slider.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.font_size_display = ctk.CTkLabel(
            size_row, text="120", width=36,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color=C["accent"])
        self.font_size_display.pack(side="left")

        # Rotation
        self._field_label(settings, "Rotation (°)", 2)
        rot_row = ctk.CTkFrame(settings, fg_color="transparent")
        rot_row.grid(row=2, column=1, padx=16, pady=6, sticky="ew")
        self.rotation_var = ctk.IntVar(value=45)
        self.rotation_slider = ctk.CTkSlider(
            rot_row, from_=0, to=90, variable=self.rotation_var,
            fg_color=TINT["bg"], progress_color=C["accent"],
            button_color=C["accent"], button_hover_color=TINT["bdr"],
            command=lambda v: self.rotation_display.configure(text=str(int(v))))
        self.rotation_slider.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.rotation_display = ctk.CTkLabel(
            rot_row, text="45", width=36,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color=C["accent"])
        self.rotation_display.pack(side="left")

        # Opacity
        self._field_label(settings, "Opacity", 3)
        op_row = ctk.CTkFrame(settings, fg_color="transparent")
        op_row.grid(row=3, column=1, padx=16, pady=6, sticky="ew")
        self.opacity_var = ctk.DoubleVar(value=0.15)
        self.opacity_slider = ctk.CTkSlider(
            op_row, from_=0.02, to=1.0, variable=self.opacity_var,
            fg_color=TINT["bg"], progress_color=C["accent"],
            button_color=C["accent"], button_hover_color=TINT["bdr"],
            command=lambda v: self.opacity_display.configure(text=f"{v:.0%}"))
        self.opacity_slider.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.opacity_display = ctk.CTkLabel(
            op_row, text="15%", width=36,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color=C["accent"])
        self.opacity_display.pack(side="left")

        # Color
        self._field_label(settings, "Colour", 4)
        color_row = ctk.CTkFrame(settings, fg_color="transparent")
        color_row.grid(row=4, column=1, padx=16, pady=(6, 14), sticky="w")
        self.color_var = ctk.StringVar(value="Gray")
        for label, val in [("Gray", "Gray"), ("Black", "Black"), ("Red", "Red"), ("Blue", "Blue")]:
            ctk.CTkRadioButton(
                color_row, text=label, variable=self.color_var, value=val,
                font=ctk.CTkFont("Segoe UI", 11),
                text_color=C["muted"],
                fg_color=C["accent"], hover_color=TINT["bdr"]
            ).pack(side="left", padx=(0, 18))

        # ── Section: Progress & Log ──
        self._section(body, "📋  Progress")

        self.progress = ctk.CTkProgressBar(body, height=8,
                                           fg_color=C["card"],
                                           progress_color=C["accent"])
        self.progress.pack(fill="x", pady=(4, 8))
        self.progress.set(0)

        self.log = ctk.CTkTextbox(body, height=130,
                                  font=ctk.CTkFont("Courier New", 11),
                                  fg_color=C["card"],
                                  border_color=C["border"], border_width=1,
                                  text_color=C["muted"],
                                  state="disabled")
        self.log.pack(fill="x", pady=(0, 16))

        # ── Run button ──
        self.run_btn = ctk.CTkButton(
            body, text="🔏  Apply Watermark",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"],
            border_color=C["accent"], border_width=1,
            corner_radius=24, height=48,
            command=self._start)
        self.run_btn.pack(fill="x", pady=(0, 20))

    # ── UI helpers ────────────────────────────────────────────────────────────
    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w"
                     ).pack(fill="x", pady=(14, 2))

    def _field_label(self, parent, text, row):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"], anchor="w", width=130
                     ).grid(row=row, column=0, padx=16, pady=6, sticky="w")

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ── File selection ────────────────────────────────────────────────────────
    def _browse_files(self):
        files = filedialog.askopenfilenames(
            title="Select PDF files",
            filetypes=[("PDF files", "*.pdf")])
        if files:
            self.selected_files = list(files)
            self._refresh_file_list()

    def _browse_folder(self):
        folder = filedialog.askdirectory(title="Select folder containing PDFs")
        if folder:
            self.selected_files = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.lower().endswith(".pdf")
            ]
            self._refresh_file_list()

    def _refresh_file_list(self):
        count = len(self.selected_files)
        self.file_label.configure(
            text=f"{count} PDF file{'s' if count != 1 else ''} selected",
            text_color=C["accent"] if count else C["muted"])

        # Clear old list
        for w in self.file_list_frame.winfo_children():
            w.destroy()

        if not self.selected_files:
            ctk.CTkLabel(self.file_list_frame,
                         text="Selected files will appear here",
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color=C["faint"]).pack(padx=16, pady=10)
            return

        for fp in self.selected_files[:10]:   # show max 10 in preview
            ctk.CTkLabel(self.file_list_frame,
                         text=f"  📄  {os.path.basename(fp)}",
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color=C["muted"], anchor="w"
                         ).pack(fill="x", padx=12, pady=2)
        if count > 10:
            ctk.CTkLabel(self.file_list_frame,
                         text=f"  … and {count - 10} more",
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color=C["faint"], anchor="w"
                         ).pack(fill="x", padx=12, pady=(0, 6))
        else:
            ctk.CTkFrame(self.file_list_frame, height=6,
                         fg_color="transparent").pack()

    # ── Run ───────────────────────────────────────────────────────────────────
    def _start(self):
        if not self.selected_files:
            messagebox.showwarning("No Files", "Please select at least one PDF file.")
            return
        text = self.wm_text.get().strip()
        if not text:
            messagebox.showwarning("No Text", "Please enter watermark text.")
            return
        self.run_btn.configure(state="disabled", text="Processing…")
        self.progress.set(0)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        text      = self.wm_text.get().strip()
        font_size = int(self.font_size_var.get())
        rotation  = int(self.rotation_var.get())
        opacity   = round(self.opacity_var.get(), 2)
        color_map = {
            "Gray":  (0.6, 0.6, 0.6),
            "Black": (0.0, 0.0, 0.0),
            "Red":   (0.8, 0.1, 0.1),
            "Blue":  (0.1, 0.2, 0.8),
        }
        color_rgb = color_map.get(self.color_var.get(), (0.6, 0.6, 0.6))

        out_dir   = get_output_dir()
        total     = len(self.selected_files)
        success   = 0
        errors    = 0

        self._log(f"Starting — {total} file(s)  |  Text: \"{text}\"")
        self._log(f"Output → {out_dir}\n")

        for i, fp in enumerate(self.selected_files, 1):
            fname = os.path.basename(fp)
            out_path = os.path.join(out_dir, fname)
            try:
                watermark_pdf(fp, out_path, text, opacity, font_size, rotation, color_rgb)
                self._log(f"✅  [{i}/{total}]  {fname}")
                success += 1
            except Exception as e:
                self._log(f"❌  [{i}/{total}]  {fname}  →  {e}")
                errors += 1
            self.progress.set(i / total)

        self._log(f"\n{'─'*40}")
        self._log(f"Done.  {success} succeeded  |  {errors} failed")

        self.run_btn.configure(state="normal", text="🔏  Apply Watermark")

        if success:
            import subprocess
            subprocess.Popen(["explorer", out_dir])
            messagebox.showinfo(
                "Complete",
                f"Watermark applied to {success} file(s).\n\nSaved to:\n{out_dir}"
            )
        else:
            messagebox.showerror("Failed", "All files failed. Check the log for details.")


if __name__ == "__main__":
    WatermarkApp().mainloop()
