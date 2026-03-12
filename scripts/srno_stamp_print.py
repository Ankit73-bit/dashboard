import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from io import BytesIO
import pandas as pd
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "border": "#2a2a3d",
    "hover": "#1e1e2e", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#30d158", "red": "#ff375f",
    "orange": "#ff9f0a", "blue": "#0a84ff",
}
TINT = {"bg": "#082a12", "mid": "#0f4020", "bdr": "#185c2e"}

# ─── Output dir ───────────────────────────────────────────────────────────────
def get_output_dir(sub):
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(desktop, "OUTPUT", sub, ts)
    os.makedirs(path, exist_ok=True)
    return path

# ─── Default printer ──────────────────────────────────────────────────────────
def get_default_printer():
    try:
        import win32print
        return win32print.GetDefaultPrinter()
    except Exception:
        return "Default Printer"

# ─── SR No stamp logic ────────────────────────────────────────────────────────
def create_overlay(text, w, h, font_size, margin_left, margin_top):
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=(w, h))
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(margin_left, h - margin_top, text)
    c.save()
    packet.seek(0)
    return PdfReader(packet)

def stamp_pdf(src_pdf, out_pdf, srno, font_size, margin_left, margin_top):
    reader = PdfReader(str(src_pdf))
    writer = PdfWriter()
    first = reader.pages[0]
    w = float(first.mediabox.width)
    h = float(first.mediabox.height)
    overlay = create_overlay(str(srno), w, h, font_size, margin_left, margin_top)
    first.merge_page(overlay.pages[0])
    writer.add_page(first)
    for p in reader.pages[1:]:
        writer.add_page(p)
    with open(out_pdf, "wb") as f:
        writer.write(f)

# ─── Print logic ──────────────────────────────────────────────────────────────
def detect_edge(pdf_path):
    reader = PdfReader(str(pdf_path))
    page = reader.pages[0]
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    return "long" if h >= w else "short"

def print_pdf_file(file_path, duplex, duplex_edge):
    if sys.platform.startswith("win"):
        import win32api, win32print
        printer = win32print.GetDefaultPrinter()
        phandle = win32print.OpenPrinter(printer)
        try:
            attrs = win32print.GetPrinter(phandle, 2)
            devmode = attrs["pDevMode"]
            devmode.Duplex = 3 if duplex and duplex_edge == "long" else 2 if duplex else 1
            try:
                win32print.SetPrinter(phandle, 2, attrs, 0)
            except Exception:
                pass
            win32api.ShellExecute(0, "print", str(file_path), None, ".", 0)
        finally:
            win32print.ClosePrinter(phandle)
    else:
        import subprocess
        cmd = ["lp", "-o", "media=A4"]
        cmd += ["-o", f"sides=two-sided-{duplex_edge}-edge" if duplex else "sides=one-sided"]
        cmd.append(str(file_path))
        subprocess.run(cmd, check=True)

# ─── App ──────────────────────────────────────────────────────────────────────
class SrnoStampPrintApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SR No Stamp & Print")
        self.geometry("760x900")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])

        self.excel_path = None
        self.pdf_dir    = None
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._stop_flag = False

        self._build()

    # ── UI ────────────────────────────────────────────────────────────────────
    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=16)
        icon_f = ctk.CTkFrame(inn, width=48, height=48, fg_color=TINT["mid"], corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🖨️", font=ctk.CTkFont("Segoe UI Emoji", 22)).place(relx=0.5, rely=0.5, anchor="center")
        tc = ctk.CTkFrame(inn, fg_color="transparent")
        tc.pack(side="left")
        ctk.CTkLabel(tc, text="SR No Stamp & Print", font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tc, text="Stamp serial numbers on PDFs then send to default printer", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).pack(anchor="w")

        # Printer badge
        self.printer_name = get_default_printer()
        ctk.CTkLabel(inn, text=f"🖨  {self.printer_name}", font=ctk.CTkFont("Segoe UI", 10, "bold"), text_color=C["accent"]).pack(side="right", padx=(20, 0))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # ── Step 1: Excel file ──
        self._section(body, "Step 1 — Excel file (filename + srno columns)")
        self.excel_label, _ = self._file_row(body, "No file selected", self._browse_excel)

        # Column name inputs
        col_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12, border_width=1, border_color=C["border"])
        col_card.pack(fill="x", pady=(0, 10))
        col_inner = ctk.CTkFrame(col_card, fg_color="transparent")
        col_inner.pack(fill="x", padx=16, pady=12)
        col_inner.columnconfigure(1, weight=1)
        col_inner.columnconfigure(3, weight=1)

        ctk.CTkLabel(col_inner, text="Filename column:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.filename_col = ctk.CTkEntry(col_inner, placeholder_text="filename", font=ctk.CTkFont("Segoe UI", 12), fg_color=C["hover"], border_color=C["border"], text_color=C["text"], height=32)
        self.filename_col.grid(row=0, column=1, sticky="ew", padx=(0, 20))
        self.filename_col.insert(0, "filename")

        ctk.CTkLabel(col_inner, text="SR No column:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.srno_col = ctk.CTkEntry(col_inner, placeholder_text="srno", font=ctk.CTkFont("Segoe UI", 12), fg_color=C["hover"], border_color=C["border"], text_color=C["text"], height=32)
        self.srno_col.grid(row=0, column=3, sticky="ew")
        self.srno_col.insert(0, "srno")

        # ── Step 2: PDF folder ──
        self._section(body, "Step 2 — Folder containing source PDFs")
        self.pdf_dir_label, _ = self._file_row(body, "No folder selected", self._browse_pdf_dir, folder=True)

        # ── Step 3: Stamp settings ──
        self._section(body, "Step 3 — Stamp settings")
        stamp_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12, border_width=1, border_color=C["border"])
        stamp_card.pack(fill="x", pady=(4, 10))
        sg = ctk.CTkFrame(stamp_card, fg_color="transparent")
        sg.pack(fill="x", padx=16, pady=12)
        sg.columnconfigure(1, weight=1)
        sg.columnconfigure(3, weight=1)

        ctk.CTkLabel(sg, text="Font size:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.font_size = ctk.CTkEntry(sg, font=ctk.CTkFont("Segoe UI", 12), fg_color=C["hover"], border_color=C["border"], text_color=C["text"], height=32, width=60)
        self.font_size.grid(row=0, column=1, sticky="w", padx=(0, 20))
        self.font_size.insert(0, "10")

        ctk.CTkLabel(sg, text="Margin left:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.margin_left = ctk.CTkEntry(sg, font=ctk.CTkFont("Segoe UI", 12), fg_color=C["hover"], border_color=C["border"], text_color=C["text"], height=32, width=60)
        self.margin_left.grid(row=0, column=3, sticky="w")
        self.margin_left.insert(0, "40")

        ctk.CTkLabel(sg, text="Margin top:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.margin_top = ctk.CTkEntry(sg, font=ctk.CTkFont("Segoe UI", 12), fg_color=C["hover"], border_color=C["border"], text_color=C["text"], height=32, width=60)
        self.margin_top.grid(row=1, column=1, sticky="w")
        self.margin_top.insert(0, "30")

        # ── Step 4: Print settings ──
        self._section(body, "Step 4 — Print settings")
        print_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12, border_width=1, border_color=C["border"])
        print_card.pack(fill="x", pady=(4, 10))
        pg = ctk.CTkFrame(print_card, fg_color="transparent")
        pg.pack(fill="x", padx=16, pady=12)
        pg.columnconfigure(1, weight=1)
        pg.columnconfigure(3, weight=1)

        # Batch size
        ctk.CTkLabel(pg, text="Batch size:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.batch_size = ctk.CTkEntry(pg, font=ctk.CTkFont("Segoe UI", 12), fg_color=C["hover"], border_color=C["border"], text_color=C["text"], height=32, width=60)
        self.batch_size.grid(row=0, column=1, sticky="w", padx=(0, 20))
        self.batch_size.insert(0, "20")

        # Delay between prints
        ctk.CTkLabel(pg, text="Delay between prints (sec):", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.delay_prints = ctk.CTkEntry(pg, font=ctk.CTkFont("Segoe UI", 12), fg_color=C["hover"], border_color=C["border"], text_color=C["text"], height=32, width=60)
        self.delay_prints.grid(row=0, column=3, sticky="w")
        self.delay_prints.insert(0, "5")

        # Delay between batches
        ctk.CTkLabel(pg, text="Delay between batches (sec):", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.delay_batches = ctk.CTkEntry(pg, font=ctk.CTkFont("Segoe UI", 12), fg_color=C["hover"], border_color=C["border"], text_color=C["text"], height=32, width=60)
        self.delay_batches.grid(row=1, column=1, sticky="w", padx=(0, 20))
        self.delay_batches.insert(0, "10")

        # Duplex
        ctk.CTkLabel(pg, text="Duplex printing:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=1, column=2, sticky="w", padx=(0, 8))
        self.duplex_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(pg, text="Enable duplex", variable=self.duplex_var, font=ctk.CTkFont("Segoe UI", 11),
                        text_color=C["text"], fg_color=C["accent"], hover_color=TINT["bdr"],
                        border_color=C["border"], checkmark_color=C["bg"],
                        command=self._toggle_duplex).grid(row=1, column=3, sticky="w")

        self.duplex_edge_var = ctk.StringVar(value="long")
        self.duplex_row = ctk.CTkFrame(print_card, fg_color="transparent")
        self.duplex_row.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(self.duplex_row, text="Flip edge:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).pack(side="left", padx=(0, 10))
        for label, val in [("Long", "long"), ("Short", "short"), ("Auto-detect", "auto")]:
            ctk.CTkRadioButton(self.duplex_row, text=label, variable=self.duplex_edge_var, value=val,
                               font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
                               fg_color=C["accent"], hover_color=TINT["bdr"]
                               ).pack(side="left", padx=(0, 16))
        self.duplex_row.pack_forget()

        # ── Progress ──
        self._section(body, "Progress")
        self.progress = ctk.CTkProgressBar(body, height=8, fg_color=C["card"], progress_color=C["accent"])
        self.progress.pack(fill="x", pady=(4, 8))
        self.progress.set(0)

        stats = ctk.CTkFrame(body, fg_color="transparent")
        stats.pack(fill="x", pady=(0, 8))
        self.stat_total   = self._stat(stats, "Total",    "0", C["blue"])
        self.stat_stamped = self._stat(stats, "Stamped",  "0", C["accent"])
        self.stat_printed = self._stat(stats, "Printed",  "0", C["accent"])
        self.stat_failed  = self._stat(stats, "Failed",   "0", C["red"])
        self.stat_missing = self._stat(stats, "Missing",  "0", C["orange"])

        self.log = ctk.CTkTextbox(body, height=160, font=ctk.CTkFont("Courier New", 11),
                                  fg_color=C["card"], border_color=C["border"], border_width=1,
                                  text_color=C["muted"], state="disabled")
        self.log.pack(fill="x", pady=(0, 12))

        # ── Action buttons ──
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 20))

        self.run_btn = ctk.CTkButton(btn_row, text="🖨️  Stamp & Print",
                                     font=ctk.CTkFont("Segoe UI", 14, "bold"),
                                     fg_color=TINT["mid"], hover_color=TINT["bdr"],
                                     text_color=C["accent"], border_color=C["accent"], border_width=1,
                                     corner_radius=24, height=48, command=self._start)
        self.run_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.pause_btn = ctk.CTkButton(btn_row, text="⏸  Pause",
                                       font=ctk.CTkFont("Segoe UI", 13, "bold"),
                                       fg_color=C["card"], hover_color=C["hover"],
                                       text_color=C["orange"], border_color=C["orange"], border_width=1,
                                       corner_radius=24, height=48, width=130,
                                       state="disabled", command=self._toggle_pause)
        self.pause_btn.pack(side="right")

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _section(self, p, t):
        ctk.CTkLabel(p, text=t, font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w").pack(fill="x", pady=(14, 2))

    def _file_row(self, parent, placeholder, cmd, folder=False):
        card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12, border_width=1, border_color=C["border"])
        card.pack(fill="x", pady=(4, 10))
        lbl = ctk.CTkLabel(card, text=placeholder, font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], anchor="w")
        lbl.pack(side="left", padx=16, pady=12, fill="x", expand=True)
        ctk.CTkButton(card, text="Browse", font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=TINT["mid"], hover_color=TINT["bdr"],
                      text_color=C["accent"], border_color=C["accent"], border_width=1,
                      corner_radius=20, height=32, width=100, command=cmd
                      ).pack(side="right", padx=12, pady=8)
        return lbl, card

    def _stat(self, parent, label, val, color):
        f = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=10, border_width=1, border_color=C["border"])
        f.pack(side="left", padx=(0, 8))
        v = ctk.CTkLabel(f, text=val, font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=color)
        v.pack(padx=14, pady=(6, 0))
        ctk.CTkLabel(f, text=label, font=ctk.CTkFont("Segoe UI", 10), text_color=C["muted"]).pack(padx=14, pady=(0, 6))
        return v

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _toggle_duplex(self):
        if self.duplex_var.get():
            self.duplex_row.pack(fill="x", padx=16, pady=(0, 12))
        else:
            self.duplex_row.pack_forget()

    def _browse_excel(self):
        p = filedialog.askopenfilename(title="Select Excel file", filetypes=[("Excel", "*.xlsx *.xls")])
        if p:
            self.excel_path = p
            self.excel_label.configure(text=os.path.basename(p), text_color=C["accent"])

    def _browse_pdf_dir(self):
        p = filedialog.askdirectory(title="Select folder containing PDFs")
        if p:
            self.pdf_dir = p
            count = len(list(Path(p).glob("*.pdf")))
            self.pdf_dir_label.configure(text=f"{os.path.basename(p)}  ({count} PDFs found)", text_color=C["accent"])

    def _toggle_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self.pause_btn.configure(text="▶  Resume", text_color=C["accent"])
            self._log("⏸  Paused — click Resume to continue")
        else:
            self._pause_event.set()
            self.pause_btn.configure(text="⏸  Pause", text_color=C["orange"])
            self._log("▶  Resumed")

    # ── Run ───────────────────────────────────────────────────────────────────
    def _start(self):
        if not self.excel_path:
            messagebox.showwarning("Missing", "Please select an Excel file.")
            return
        if not self.pdf_dir:
            messagebox.showwarning("Missing", "Please select the PDF source folder.")
            return

        self._stop_flag = False
        self._pause_event.set()
        self.run_btn.configure(state="disabled", text="Processing…")
        self.pause_btn.configure(state="normal")
        self.progress.set(0)
        for s in [self.stat_total, self.stat_stamped, self.stat_printed, self.stat_failed, self.stat_missing]:
            s.configure(text="0")

        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            out_dir      = get_output_dir("SrNo_Stamp_Print")
            log_path     = os.path.join(out_dir, "job.log")
            missing_path = os.path.join(out_dir, "missing.csv")

            logging.basicConfig(filename=log_path, level=logging.INFO,
                                format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")

            font_size    = int(self.font_size.get() or 10)
            margin_left  = int(self.margin_left.get() or 40)
            margin_top   = int(self.margin_top.get() or 30)
            batch_size   = int(self.batch_size.get() or 20)
            delay_prints = float(self.delay_prints.get() or 5)
            delay_batch  = float(self.delay_batches.get() or 10)
            duplex       = self.duplex_var.get()
            duplex_edge  = self.duplex_edge_var.get()

            fname_col = self.filename_col.get().strip()
            srno_col  = self.srno_col.get().strip()

            df   = pd.read_excel(self.excel_path)
            pdfs = list(Path(self.pdf_dir).glob("*.pdf"))

            self._log(f"Loaded {len(df)} rows · {len(pdfs)} PDFs in folder")
            self.stat_total.configure(text=str(len(df)))
            logging.info(f"Job started — {len(df)} rows, {len(pdfs)} source PDFs")

            # ── Phase 1: Stamp ──────────────────────────────────────────────
            self._log("\n── Phase 1: Stamping SR numbers ──")
            generated = []
            missing   = []
            stamped   = 0

            for idx, row in df.iterrows():
                self._pause_event.wait()
                prospect = str(row[fname_col]).strip()
                srno     = str(row[srno_col]).strip()
                if not prospect or not srno:
                    continue

                matches = [p for p in pdfs if prospect in p.stem]
                if not matches:
                    missing.append(prospect)
                    self._log(f"  ⚠️  Missing: {prospect}")
                    logging.warning(f"Missing PDF for: {prospect}")
                    continue

                src = sorted(matches, key=lambda x: len(x.stem))[0]
                out_name = f"{idx+1:04d}__{src.stem}__SRNO_{srno}.pdf"
                out_path = os.path.join(out_dir, out_name)

                stamp_pdf(src, out_path, srno, font_size, margin_left, margin_top)
                generated.append(Path(out_path))
                stamped += 1
                self.stat_stamped.configure(text=str(stamped))
                self.stat_missing.configure(text=str(len(missing)))
                self._log(f"  ✅  [{idx+1}] {src.name} → SRNO {srno}")
                logging.info(f"Stamped: {out_name}")
                self.progress.set((idx + 1) / len(df) * 0.5)

            # Save missing CSV
            if missing:
                pd.DataFrame({"missing": missing}).to_csv(missing_path, index=False)
                self._log(f"\n⚠️  {len(missing)} missing PDFs saved → missing.csv")

            if not generated:
                self._log("❌  No PDFs stamped. Aborting print phase.")
                return

            # ── Phase 2: Print ──────────────────────────────────────────────
            self._log(f"\n── Phase 2: Printing {len(generated)} PDFs ──")
            printed = 0
            failed  = 0

            for batch_start in range(0, len(generated), batch_size):
                self._pause_event.wait()
                batch = generated[batch_start:batch_start + batch_size]
                self._log(f"\n  Batch {batch_start+1} → {batch_start+len(batch)}")

                for pdf in batch:
                    self._pause_event.wait()
                    pages = len(PdfReader(str(pdf)).pages)
                    edge  = detect_edge(str(pdf)) if duplex and duplex_edge == "auto" else duplex_edge
                    use_duplex = duplex and pages > 1
                    mode  = f"DUPLEX {edge}" if use_duplex else "SIMPLEX"

                    try:
                        print_pdf_file(str(pdf), use_duplex, edge)
                        printed += 1
                        self.stat_printed.configure(text=str(printed))
                        self._log(f"  🖨️   {pdf.name} [{pages}p · {mode}]")
                        logging.info(f"Printed: {pdf.name}")
                    except Exception as e:
                        failed += 1
                        self.stat_failed.configure(text=str(failed))
                        self._log(f"  ❌  {pdf.name} → {e}")
                        logging.error(f"Print failed: {pdf.name} — {e}")

                    self.progress.set(0.5 + (batch_start + printed + failed) / len(generated) * 0.5)
                    time.sleep(delay_prints)

                if batch_start + batch_size < len(generated):
                    self._log(f"  ⏳  Waiting {delay_batch}s before next batch…")
                    time.sleep(delay_batch)

            self._log(f"\n{'─'*44}")
            self._log(f"Done.  Stamped: {stamped}  |  Printed: {printed}  |  Failed: {failed}  |  Missing: {len(missing)}")
            self._log(f"Log → {log_path}")
            logging.info("Job complete")

            import subprocess
            subprocess.Popen(["explorer", out_dir])
            messagebox.showinfo("Complete", f"Stamped: {stamped}\nPrinted: {printed}\nFailed: {failed}\nMissing: {len(missing)}\n\nOutput: {out_dir}")

        except Exception as e:
            self._log(f"\n❌  Error: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            self.run_btn.configure(state="normal", text="🖨️  Stamp & Print")
            self.pause_btn.configure(state="disabled", text="⏸  Pause")
            self.progress.set(1)

if __name__ == "__main__":
    SrnoStampPrintApp().mainloop()
