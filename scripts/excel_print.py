import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
import pandas as pd
from PyPDF2 import PdfReader

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "border": "#2a2a3d",
    "hover": "#1e1e2e", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#bf5af2", "red": "#ff375f",
    "orange": "#ff9f0a", "green": "#30d158", "blue": "#0a84ff",
}
TINT = {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"}

def get_output_dir():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(desktop, "OUTPUT", "Excel_Print", ts)
    os.makedirs(path, exist_ok=True)
    return path

def get_default_printer():
    try:
        import win32print
        return win32print.GetDefaultPrinter()
    except Exception:
        return "Default Printer"

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


class ExcelPrintApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Excel-Based PDF Printer")
        self.geometry("760x860")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.excel_path = None
        self.pdf_dir    = None
        self.col_vars   = {}
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._build()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=16)
        icon_f = ctk.CTkFrame(inn, width=48, height=48, fg_color=TINT["mid"], corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="📋", font=ctk.CTkFont("Segoe UI Emoji", 22)).place(relx=0.5, rely=0.5, anchor="center")
        tc = ctk.CTkFrame(inn, fg_color="transparent")
        tc.pack(side="left")
        ctk.CTkLabel(tc, text="Excel-Based PDF Printer", font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tc, text="Print PDFs in the exact order defined by an Excel list", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).pack(anchor="w")
        ctk.CTkLabel(inn, text=f"🖨  {get_default_printer()}", font=ctk.CTkFont("Segoe UI", 10, "bold"), text_color=C["accent"]).pack(side="right", padx=(20, 0))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # ── Step 1: Excel ──
        self._section(body, "Step 1 — Excel file with print order")
        file_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12, border_width=1, border_color=C["border"])
        file_card.pack(fill="x", pady=(4, 6))
        self.excel_label = ctk.CTkLabel(file_card, text="No file selected", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], anchor="w")
        self.excel_label.pack(side="left", padx=16, pady=12, fill="x", expand=True)
        ctk.CTkButton(file_card, text="Browse", font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=TINT["mid"], hover_color=TINT["bdr"],
                      text_color=C["accent"], border_color=C["accent"], border_width=1,
                      corner_radius=20, height=32, width=100, command=self._browse_excel
                      ).pack(side="right", padx=12, pady=8)

        # Column picker (dynamic)
        self.col_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12, border_width=1, border_color=C["border"])
        self.col_card.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(self.col_card, text="Load an Excel file to pick the filename column",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"]).pack(padx=16, pady=12)

        # ── Step 2: PDF folder ──
        self._section(body, "Step 2 — Folder containing PDFs")
        dir_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12, border_width=1, border_color=C["border"])
        dir_card.pack(fill="x", pady=(4, 10))
        self.dir_label = ctk.CTkLabel(dir_card, text="No folder selected", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], anchor="w")
        self.dir_label.pack(side="left", padx=16, pady=12, fill="x", expand=True)
        ctk.CTkButton(dir_card, text="Browse", font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=TINT["mid"], hover_color=TINT["bdr"],
                      text_color=C["accent"], border_color=C["accent"], border_width=1,
                      corner_radius=20, height=32, width=100, command=self._browse_dir
                      ).pack(side="right", padx=12, pady=8)

        # ── Step 3: Print settings ──
        self._section(body, "Step 3 — Print settings")
        pc = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12, border_width=1, border_color=C["border"])
        pc.pack(fill="x", pady=(4, 10))
        pg = ctk.CTkFrame(pc, fg_color="transparent")
        pg.pack(fill="x", padx=16, pady=12)
        pg.columnconfigure(1, weight=1)
        pg.columnconfigure(3, weight=1)

        ctk.CTkLabel(pg, text="Batch size:", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.batch_size = ctk.CTkEntry(pg, font=ctk.CTkFont("Segoe UI", 12), fg_color=C["hover"], border_color=C["border"], text_color=C["text"], height=32, width=60)
        self.batch_size.grid(row=0, column=1, sticky="w", padx=(0, 20))
        self.batch_size.insert(0, "20")

        ctk.CTkLabel(pg, text="Delay between prints (sec):", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.delay_prints = ctk.CTkEntry(pg, font=ctk.CTkFont("Segoe UI", 12), fg_color=C["hover"], border_color=C["border"], text_color=C["text"], height=32, width=60)
        self.delay_prints.grid(row=0, column=3, sticky="w")
        self.delay_prints.insert(0, "5")

        ctk.CTkLabel(pg, text="Delay between batches (sec):", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.delay_batches = ctk.CTkEntry(pg, font=ctk.CTkFont("Segoe UI", 12), fg_color=C["hover"], border_color=C["border"], text_color=C["text"], height=32, width=60)
        self.delay_batches.grid(row=1, column=1, sticky="w", padx=(0, 20))
        self.delay_batches.insert(0, "10")

        self.duplex_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(pg, text="Enable duplex", variable=self.duplex_var,
                        font=ctk.CTkFont("Segoe UI", 11), text_color=C["text"],
                        fg_color=C["accent"], hover_color=TINT["bdr"],
                        border_color=C["border"], checkmark_color=C["bg"],
                        command=self._toggle_duplex).grid(row=1, column=2, columnspan=2, sticky="w")

        self.duplex_edge_var = ctk.StringVar(value="long")
        self.duplex_row = ctk.CTkFrame(pc, fg_color="transparent")
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
        self.stat_total   = self._stat(stats, "Total",   "0", C["blue"])
        self.stat_printed = self._stat(stats, "Printed", "0", C["green"])
        self.stat_failed  = self._stat(stats, "Failed",  "0", C["red"])
        self.stat_missing = self._stat(stats, "Missing", "0", C["orange"])

        self.log = ctk.CTkTextbox(body, height=150, font=ctk.CTkFont("Courier New", 11),
                                  fg_color=C["card"], border_color=C["border"], border_width=1,
                                  text_color=C["muted"], state="disabled")
        self.log.pack(fill="x", pady=(0, 12))

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 20))
        self.run_btn = ctk.CTkButton(btn_row, text="📋  Print in Excel Order",
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

    def _section(self, p, t):
        ctk.CTkLabel(p, text=t, font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w").pack(fill="x", pady=(14, 2))

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
        if not p:
            return
        self.excel_path = p
        self.excel_label.configure(text=os.path.basename(p), text_color=C["accent"])
        self._load_columns(p)

    def _browse_dir(self):
        p = filedialog.askdirectory(title="Select PDF folder")
        if p:
            self.pdf_dir = p
            count = len(list(Path(p).glob("*.pdf")))
            self.dir_label.configure(text=f"{os.path.basename(p)}  ({count} PDFs found)", text_color=C["accent"])

    def _load_columns(self, path):
        try:
            df = pd.read_excel(path, nrows=0)
            cols = list(df.columns)
        except Exception as e:
            messagebox.showerror("Error", f"Could not read Excel:\n{e}")
            return

        for w in self.col_card.winfo_children():
            w.destroy()

        inner = ctk.CTkFrame(self.col_card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(inner, text="Select the column containing PDF filenames:",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).pack(anchor="w", pady=(0, 8))

        self.selected_col = ctk.StringVar(value=cols[0])
        for col in cols:
            ctk.CTkRadioButton(inner, text=col, variable=self.selected_col, value=col,
                               font=ctk.CTkFont("Segoe UI", 11), text_color=C["text"],
                               fg_color=C["accent"], hover_color=TINT["bdr"]
                               ).pack(anchor="w", pady=2)

    def _toggle_pause(self):
        if self._pause_event.is_set():
            self._pause_event.clear()
            self.pause_btn.configure(text="▶  Resume", text_color=C["green"])
            self._log("⏸  Paused — click Resume to continue")
        else:
            self._pause_event.set()
            self.pause_btn.configure(text="⏸  Pause", text_color=C["orange"])
            self._log("▶  Resumed")

    def _start(self):
        if not self.excel_path:
            messagebox.showwarning("Missing", "Please select an Excel file.")
            return
        if not self.pdf_dir:
            messagebox.showwarning("Missing", "Please select the PDF folder.")
            return
        if not hasattr(self, "selected_col"):
            messagebox.showwarning("Missing", "Please select the filename column.")
            return

        self._pause_event.set()
        self.run_btn.configure(state="disabled", text="Processing…")
        self.pause_btn.configure(state="normal")
        self.progress.set(0)
        for s in [self.stat_total, self.stat_printed, self.stat_failed, self.stat_missing]:
            s.configure(text="0")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            out_dir  = get_output_dir()
            log_path = os.path.join(out_dir, "job.log")
            logging.basicConfig(filename=log_path, level=logging.INFO,
                                format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")

            batch_size   = int(self.batch_size.get() or 20)
            delay_prints = float(self.delay_prints.get() or 5)
            delay_batch  = float(self.delay_batches.get() or 10)
            duplex       = self.duplex_var.get()
            duplex_edge  = self.duplex_edge_var.get()
            col          = self.selected_col.get()

            df   = pd.read_excel(self.excel_path)
            pdfs = list(Path(self.pdf_dir).glob("*.pdf"))
            prospects = df[col].astype(str).str.strip().tolist()
            self.stat_total.configure(text=str(len(prospects)))
            self._log(f"Loaded {len(prospects)} rows · {len(pdfs)} PDFs in folder")

            # ── Match PDFs ──────────────────────────────────────────────────
            matched = {}
            missing = []
            for prospect in prospects:
                if not prospect:
                    continue
                candidates = [p for p in pdfs if prospect in p.stem]
                if candidates:
                    matched[prospect] = sorted(candidates, key=lambda x: len(x.stem))[0]
                else:
                    missing.append(prospect)

            self.stat_missing.configure(text=str(len(missing)))

            if missing:
                missing_path = os.path.join(out_dir, "missing.csv")
                pd.DataFrame({"missing": missing}).to_csv(missing_path, index=False)
                self._log(f"⚠️  {len(missing)} PDFs not found — saved to missing.csv")

                # Ask user — continue or abort
                answer = messagebox.askyesno(
                    "Missing PDFs Found",
                    f"{len(missing)} PDFs could not be matched.\n\n"
                    f"Missing list saved to:\n{missing_path}\n\n"
                    f"Continue printing {len(matched)} matched PDFs?\n"
                    f"Click No to abort."
                )
                if not answer:
                    self._log("❌  Aborted by user.")
                    return

            to_print = [matched[p] for p in prospects if p in matched]
            if not to_print:
                self._log("❌  No PDFs to print.")
                return

            # ── Print ───────────────────────────────────────────────────────
            printed = 0
            failed  = 0

            for batch_start in range(0, len(to_print), batch_size):
                self._pause_event.wait()
                batch = to_print[batch_start:batch_start + batch_size]
                self._log(f"\n  Batch {batch_start+1} → {batch_start+len(batch)}")

                for pdf in batch:
                    self._pause_event.wait()
                    pages = len(PdfReader(str(pdf)).pages)
                    edge  = detect_edge(str(pdf)) if duplex and duplex_edge == "auto" else duplex_edge
                    use_duplex = duplex and pages > 1
                    mode  = f"DUPLEX {edge}" if use_duplex else "SIMPLEX"

                    try_count = 0
                    while try_count < 3:
                        try:
                            print_pdf_file(str(pdf), use_duplex, edge)
                            printed += 1
                            self.stat_printed.configure(text=str(printed))
                            self._log(f"  🖨️   {pdf.name} [{pages}p · {mode}]")
                            logging.info(f"Printed: {pdf.name}")
                            break
                        except Exception as e:
                            try_count += 1
                            self._log(f"  ⚠️  Attempt {try_count}/3 failed: {e}")
                            if try_count >= 3:
                                failed += 1
                                self.stat_failed.configure(text=str(failed))
                                logging.error(f"Failed after 3 attempts: {pdf.name}")
                                break

                    self.progress.set((printed + failed) / len(to_print))
                    time.sleep(delay_prints)

                if batch_start + batch_size < len(to_print):
                    self._log(f"  ⏳  Waiting {delay_batch}s…")
                    time.sleep(delay_batch)

            self._log(f"\n{'─'*44}")
            self._log(f"Done.  Printed: {printed}  |  Failed: {failed}  |  Missing: {len(missing)}")
            self._log(f"Log → {log_path}")
            logging.info("Job complete")

            import subprocess
            subprocess.Popen(["explorer", out_dir])
            messagebox.showinfo("Complete", f"Printed: {printed}\nFailed: {failed}\nMissing: {len(missing)}\n\nLog: {out_dir}")

        except Exception as e:
            self._log(f"\n❌  Error: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            self.run_btn.configure(state="normal", text="📋  Print in Excel Order")
            self.pause_btn.configure(state="disabled", text="⏸  Pause")
            self.progress.set(1)

if __name__ == "__main__":
    ExcelPrintApp().mainloop()
