import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import pandas as pd
import numpy as np
from datetime import datetime
from PyPDF2 import PdfMerger

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
    "accent": "#ff9f0a",   # orange
}
TINT = {"bg": "#2e1e00", "mid": "#4a3000", "bdr": "#6b4500"}


# ─── Output path ──────────────────────────────────────────────────────────────
def get_output_dir():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    ts      = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path    = os.path.join(desktop, "OUTPUT", "Sticker_Tool", ts)
    os.makedirs(path, exist_ok=True)
    return path


# ─── Core logic ───────────────────────────────────────────────────────────────
def format_sticker_excel(df, selected_cols, stickers_per_sheet):
    """Reformat dataframe: group rows in sets of N across columns."""
    df = df[selected_cols].copy()
    df["_Group"] = (np.arange(len(df)) % stickers_per_sheet) + 1

    grouped = []
    for i in range(1, stickers_per_sheet + 1):
        group = df[df["_Group"] == i].copy()
        group = group.drop(columns=["_Group"])
        group.columns = [f"{col}{i}" for col in group.columns]
        group = group.reset_index(drop=True)
        grouped.append(group)

    return pd.concat(grouped, axis=1)


def replace_placeholders(template_content, data):
    for placeholder, value in data.items():
        template_content = template_content.replace(f"{{{{{placeholder}}}}}", str(value))
    return template_content


def generate_pdfs(excel_path, template_path, output_dir, log_fn, progress_fn):
    """Generate one PDF per row and merge into a single PDF."""
    try:
        from typst import compile as typst_compile
    except ImportError:
        log_fn("❌  'typst' library not found. Please run setup.bat again.")
        return False

    df = pd.read_excel(excel_path)
    df = df.fillna("")

    with open(template_path, "r", encoding="utf-8") as f:
        template_content = f.read()

    total = len(df)
    generated = []
    temp_dir = os.path.join(output_dir, "_temp")
    os.makedirs(temp_dir, exist_ok=True)

    for index, row in df.iterrows():
        data_dict = row.to_dict()
        filled = replace_placeholders(template_content, data_dict)

        temp_typ = os.path.join(temp_dir, f"temp_{index + 1}.typ")
        out_pdf  = os.path.join(temp_dir, f"output_{index + 1}.pdf")

        with open(temp_typ, "w", encoding="utf-8") as f:
            f.write(filled)

        try:
            typst_compile(temp_typ, out_pdf)
            generated.append(out_pdf)
            log_fn(f"✅  [{index + 1}/{total}]  Row {index + 1} → PDF")
        except Exception as e:
            log_fn(f"❌  [{index + 1}/{total}]  Row {index + 1} failed: {e}")

        os.remove(temp_typ)
        progress_fn((index + 1) / total * 0.5 + 0.5)  # second half of progress

    if generated:
        merged_path = os.path.join(output_dir, "stickers_merged.pdf")
        merger = PdfMerger()
        for pdf in generated:
            merger.append(pdf)
        merger.write(merged_path)
        merger.close()
        log_fn(f"\n📄  Merged PDF → stickers_merged.pdf")

    # Clean up temp folder
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)

    return len(generated) > 0


# ─── App ──────────────────────────────────────────────────────────────────────
class StickerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sticker Format Tool")
        self.geometry("760x850")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])

        self.excel_path    = None
        self.template_path = None
        self.col_vars      = {}   # column name → BooleanVar
        self.output_dir    = None

        self._build()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(padx=28, pady=16)

        icon_f = ctk.CTkFrame(inner, width=48, height=48,
                              fg_color=TINT["mid"], corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🏷️",
                     font=ctk.CTkFont("Segoe UI Emoji", 22)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        txt = ctk.CTkFrame(inner, fg_color="transparent")
        txt.pack(side="left")
        ctk.CTkLabel(txt, text="Sticker Format Tool",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(txt, text="Format Excel data into sticker sheets and generate PDFs",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        # Scrollable body
        body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                      scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # ── Step 1: Excel file ──
        self._section(body, "Step 1 — Select your Excel file")

        file_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                 border_width=1, border_color=C["border"])
        file_card.pack(fill="x", pady=(4, 10))

        self.excel_label = ctk.CTkLabel(
            file_card, text="No file selected",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], anchor="w")
        self.excel_label.pack(side="left", padx=16, pady=12, fill="x", expand=True)

        ctk.CTkButton(
            file_card, text="Browse",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            corner_radius=20, height=32, width=100,
            command=self._browse_excel
        ).pack(side="right", padx=12, pady=8)

        # ── Step 2: Column selection (dynamic) ──
        self._section(body, "Step 2 — Select columns to include")

        self.col_frame = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                      border_width=1, border_color=C["border"])
        self.col_frame.pack(fill="x", pady=(4, 10))

        self.col_placeholder = ctk.CTkLabel(
            self.col_frame,
            text="Load an Excel file above to see available columns",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["faint"])
        self.col_placeholder.pack(padx=16, pady=16)

        # ── Step 3: Stickers per sheet ──
        self._section(body, "Step 3 — Stickers per sheet")

        sps_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                border_width=1, border_color=C["border"])
        sps_card.pack(fill="x", pady=(4, 10))

        sps_inner = ctk.CTkFrame(sps_card, fg_color="transparent")
        sps_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(sps_inner, text="Stickers per sheet:",
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=C["muted"]).pack(side="left")

        self.sps_var = ctk.IntVar(value=12)
        self.sps_display = ctk.CTkLabel(
            sps_inner, text="12",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            text_color=C["accent"], width=36)
        self.sps_display.pack(side="right")

        self.sps_slider = ctk.CTkSlider(
            sps_inner, from_=1, to=30, number_of_steps=29,
            variable=self.sps_var,
            fg_color=TINT["bg"], progress_color=C["accent"],
            button_color=C["accent"], button_hover_color=TINT["bdr"],
            command=lambda v: self.sps_display.configure(text=str(int(v))))
        self.sps_slider.pack(side="right", fill="x", expand=True, padx=(16, 12))

        # ── Step 4: Typst template ──
        self._section(body, "Step 4 — Select Typst template (.typ)")

        tmpl_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                 border_width=1, border_color=C["border"])
        tmpl_card.pack(fill="x", pady=(4, 10))

        self.tmpl_label = ctk.CTkLabel(
            tmpl_card, text="No template selected",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], anchor="w")
        self.tmpl_label.pack(side="left", padx=16, pady=12, fill="x", expand=True)

        ctk.CTkButton(
            tmpl_card, text="Browse",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            corner_radius=20, height=32, width=100,
            command=self._browse_template
        ).pack(side="right", padx=12, pady=8)

        # ── Progress & log ──
        self._section(body, "Progress")

        self.progress = ctk.CTkProgressBar(body, height=8,
                                           fg_color=C["card"],
                                           progress_color=C["accent"])
        self.progress.pack(fill="x", pady=(4, 8))
        self.progress.set(0)

        self.log = ctk.CTkTextbox(body, height=140,
                                  font=ctk.CTkFont("Courier New", 11),
                                  fg_color=C["card"],
                                  border_color=C["border"], border_width=1,
                                  text_color=C["muted"],
                                  state="disabled")
        self.log.pack(fill="x", pady=(0, 16))

        # ── Run button ──
        self.run_btn = ctk.CTkButton(
            body, text="🏷️  Generate Sticker Sheet + PDF",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"],
            border_color=C["accent"], border_width=1,
            corner_radius=24, height=48,
            command=self._start)
        self.run_btn.pack(fill="x", pady=(0, 20))

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w"
                     ).pack(fill="x", pady=(14, 2))

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ── File browsing ─────────────────────────────────────────────────────────
    def _browse_excel(self):
        path = filedialog.askopenfilename(
            title="Select Excel file",
            filetypes=[("Excel files", "*.xlsx *.xls")])
        if not path:
            return
        self.excel_path = path
        self.excel_label.configure(
            text=os.path.basename(path), text_color=C["accent"])
        self._load_columns(path)

    def _browse_template(self):
        path = filedialog.askopenfilename(
            title="Select Typst template",
            filetypes=[("Typst files", "*.typ"), ("All files", "*.*")])
        if not path:
            return
        self.template_path = path
        self.tmpl_label.configure(
            text=os.path.basename(path), text_color=C["accent"])

    # ── Load columns from Excel ───────────────────────────────────────────────
    def _load_columns(self, path):
        try:
            df = pd.read_excel(path, nrows=0)   # read headers only
            columns = list(df.columns)
        except Exception as e:
            messagebox.showerror("Error", f"Could not read Excel file:\n{e}")
            return

        # Clear placeholder and old checkboxes
        for w in self.col_frame.winfo_children():
            w.destroy()
        self.col_vars = {}

        if not columns:
            ctk.CTkLabel(self.col_frame,
                         text="No columns found in this file.",
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["faint"]).pack(padx=16, pady=12)
            return

        # Header row with select all toggle
        hdr_row = ctk.CTkFrame(self.col_frame, fg_color="transparent")
        hdr_row.pack(fill="x", padx=14, pady=(10, 4))

        ctk.CTkLabel(hdr_row, text=f"{len(columns)} columns found — select the ones to include:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left")

        ctk.CTkButton(hdr_row, text="Select All",
                      font=ctk.CTkFont("Segoe UI", 10),
                      fg_color="transparent", hover_color=C["hover"],
                      text_color=C["accent"], height=24, width=80,
                      command=lambda: self._toggle_all(True)
                      ).pack(side="right")
        ctk.CTkButton(hdr_row, text="Clear All",
                      font=ctk.CTkFont("Segoe UI", 10),
                      fg_color="transparent", hover_color=C["hover"],
                      text_color=C["muted"], height=24, width=70,
                      command=lambda: self._toggle_all(False)
                      ).pack(side="right", padx=(0, 4))

        ctk.CTkFrame(self.col_frame, height=1,
                     fg_color=C["border"]).pack(fill="x", padx=14)

        # Checkbox grid — 3 per row
        grid = ctk.CTkFrame(self.col_frame, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=(8, 12))

        for i, col in enumerate(columns):
            var = ctk.BooleanVar(value=True)
            self.col_vars[col] = var
            cb = ctk.CTkCheckBox(
                grid, text=col,
                variable=var,
                font=ctk.CTkFont("Segoe UI", 11),
                text_color=C["text"],
                fg_color=C["accent"],
                hover_color=TINT["bdr"],
                border_color=C["border"],
                checkmark_color=C["bg"])
            cb.grid(row=i // 3, column=i % 3,
                    padx=10, pady=4, sticky="w")

    def _toggle_all(self, state):
        for var in self.col_vars.values():
            var.set(state)

    # ── Run ───────────────────────────────────────────────────────────────────
    def _start(self):
        if not self.excel_path:
            messagebox.showwarning("Missing", "Please select an Excel file.")
            return

        selected = [col for col, var in self.col_vars.items() if var.get()]
        if not selected:
            messagebox.showwarning("No Columns", "Please select at least one column.")
            return

        if not self.template_path:
            messagebox.showwarning("Missing", "Please select a Typst template (.typ) file.")
            return

        self.run_btn.configure(state="disabled", text="Processing…")
        self.progress.set(0)
        threading.Thread(target=self._run, args=(selected,), daemon=True).start()

    def _run(self, selected_cols):
        try:
            stickers = int(self.sps_var.get())
            out_dir  = get_output_dir()
            self.output_dir = out_dir

            # ── Step 1: Format Excel ──
            self._log(f"Reading Excel: {os.path.basename(self.excel_path)}")
            self._log(f"Columns selected: {', '.join(selected_cols)}")
            self._log(f"Stickers per sheet: {stickers}\n")

            df = pd.read_excel(self.excel_path)
            final_df = format_sticker_excel(df, selected_cols, stickers)

            excel_out = os.path.join(out_dir, "sticker_formatted.xlsx")
            final_df.to_excel(excel_out, index=False)
            self._log(f"✅  Formatted Excel saved → sticker_formatted.xlsx")
            self.progress.set(0.5)

            # ── Step 2: Generate PDFs ──
            self._log(f"\nGenerating PDFs from template...")
            self._log(f"Template: {os.path.basename(self.template_path)}\n")

            success = generate_pdfs(
                excel_out,
                self.template_path,
                out_dir,
                log_fn=self._log,
                progress_fn=lambda v: self.progress.set(v)
            )

            self._log(f"\n{'─' * 40}")

            if success:
                self._log(f"✅  All done! Output saved to:\n    {out_dir}")
                import subprocess
                subprocess.Popen(["explorer", out_dir])
                messagebox.showinfo(
                    "Complete",
                    f"Sticker sheet and PDF generated successfully.\n\nSaved to:\n{out_dir}")
            else:
                self._log("⚠️  Excel saved but PDF generation failed. Check the log.")
                messagebox.showwarning(
                    "Partial Complete",
                    f"Formatted Excel was saved but PDF generation failed.\n\nCheck the log for details.\n\nExcel saved to:\n{out_dir}")

        except Exception as e:
            self._log(f"\n❌  Error: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            self.run_btn.configure(state="normal", text="🏷️  Generate Sticker Sheet + PDF")
            self.progress.set(1)


if __name__ == "__main__":
    StickerApp().mainloop()
