import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime
from PyPDF2 import PdfReader

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "border": "#2a2a3d",
    "hover": "#1e1e2e", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#00f5ff", "red": "#ff375f",
    "orange": "#ff9f0a", "green": "#30d158",
}
TINT = {"bg": "#062d30", "mid": "#0a4a4e", "bdr": "#0d6b70"}

def get_output_dir():
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(desktop, "OUTPUT", "Quick_Print", ts)
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

def print_file(file_path, duplex, duplex_edge):
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
        ext = os.path.splitext(str(file_path))[1].lower()
        if ext == ".pdf":
            cmd = ["lp", "-o", "media=A4"]
            cmd += ["-o", f"sides=two-sided-{duplex_edge}-edge" if duplex else "sides=one-sided"]
            cmd.append(str(file_path))
            subprocess.run(cmd, check=True)
        else:
            subprocess.run(["lp", str(file_path)], check=True)


class QuickPrintApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Quick Print")
        self.geometry("760x820")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.source_items = []
        self.all_files    = []
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
        ctk.CTkLabel(icon_f, text="🖨️", font=ctk.CTkFont("Segoe UI Emoji", 22)).place(relx=0.5, rely=0.5, anchor="center")
        tc = ctk.CTkFrame(inn, fg_color="transparent")
        tc.pack(side="left")
        ctk.CTkLabel(tc, text="Quick Print", font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tc, text="Add any documents or folders and send to the default printer", font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).pack(anchor="w")
        ctk.CTkLabel(inn, text=f"🖨  {get_default_printer()}", font=ctk.CTkFont("Segoe UI", 10, "bold"), text_color=C["accent"]).pack(side="right", padx=(20, 0))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent", scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        # ── Step 1: Add files / folders ──
        self._section(body, "Step 1 — Add files or folders")

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 6))
        ctk.CTkButton(btn_row, text="＋ Add Files",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=TINT["mid"], hover_color=TINT["bdr"],
                      text_color=C["accent"], border_color=C["accent"], border_width=1,
                      corner_radius=20, height=36, width=140, command=self._add_files
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="＋ Add Folders",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=TINT["mid"], hover_color=TINT["bdr"],
                      text_color=C["accent"], border_color=C["accent"], border_width=1,
                      corner_radius=20, height=36, width=140, command=self._add_folders
                      ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Clear All",
                      font=ctk.CTkFont("Segoe UI", 12),
                      fg_color="transparent", hover_color=C["hover"],
                      text_color=C["muted"], corner_radius=20, height=36, width=90,
                      command=self._clear_all
                      ).pack(side="right")

        self.file_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12, border_width=1, border_color=C["border"])
        self.file_card.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(self.file_card, text="No files added yet",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"]).pack(padx=16, pady=14)

        self.summary_label = ctk.CTkLabel(body, text="", font=ctk.CTkFont("Segoe UI", 11, "bold"),
                                          text_color=C["muted"], anchor="w")
        self.summary_label.pack(fill="x", pady=(0, 4))

        # ── Step 2: Print settings ──
        self._section(body, "Step 2 — Print settings")
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
        self.delay_prints.insert(0, "3")

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
        self.stat_total   = self._stat(stats, "Total",   "0", C["accent"])
        self.stat_printed = self._stat(stats, "Printed", "0", C["green"])
        self.stat_failed  = self._stat(stats, "Failed",  "0", C["red"])

        self.log = ctk.CTkTextbox(body, height=140, font=ctk.CTkFont("Courier New", 11),
                                  fg_color=C["card"], border_color=C["border"], border_width=1,
                                  text_color=C["muted"], state="disabled")
        self.log.pack(fill="x", pady=(0, 12))

        btn_row2 = ctk.CTkFrame(body, fg_color="transparent")
        btn_row2.pack(fill="x", pady=(0, 20))
        self.run_btn = ctk.CTkButton(btn_row2, text="🖨️  Print All",
                                     font=ctk.CTkFont("Segoe UI", 14, "bold"),
                                     fg_color=TINT["mid"], hover_color=TINT["bdr"],
                                     text_color=C["accent"], border_color=C["accent"], border_width=1,
                                     corner_radius=24, height=48, command=self._start)
        self.run_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.pause_btn = ctk.CTkButton(btn_row2, text="⏸  Pause",
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

    def _add_files(self):
        paths = filedialog.askopenfilenames(title="Select files to print")
        if paths:
            for p in paths:
                if p not in self.source_items:
                    self.source_items.append(p)
            self._refresh()

    def _add_folders(self):
        folder = filedialog.askdirectory(title="Select folder")
        if folder and folder not in self.source_items:
            self.source_items.append(folder)
            self._refresh()

    def _clear_all(self):
        self.source_items.clear()
        self.all_files.clear()
        self._refresh()

    def _resolve_files(self):
        files = []
        for item in self.source_items:
            if os.path.isfile(item):
                files.append(item)
            elif os.path.isdir(item):
                for root, _, fnames in os.walk(item):
                    for f in fnames:
                        files.append(os.path.join(root, f))
        seen, result = set(), []
        for f in files:
            if f not in seen:
                seen.add(f)
                result.append(f)
        return result

    def _refresh(self):
        self.all_files = self._resolve_files()
        for w in self.file_card.winfo_children():
            w.destroy()

        if not self.source_items:
            ctk.CTkLabel(self.file_card, text="No files added yet",
                         font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"]).pack(padx=16, pady=14)
            self.summary_label.configure(text="")
            self.stat_total.configure(text="0")
            return

        for item in self.source_items:
            row = ctk.CTkFrame(self.file_card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=3)
            is_dir = os.path.isdir(item)
            ctk.CTkLabel(row, text=f"  {'📁' if is_dir else '📄'}  {os.path.basename(item)}",
                         font=ctk.CTkFont("Segoe UI", 11), text_color=C["text"], anchor="w"
                         ).pack(side="left", fill="x", expand=True)
            if is_dir:
                count = sum(1 for _ in Path(item).rglob("*") if Path(_).is_file())
                ctk.CTkLabel(row, text=f"{count} files", font=ctk.CTkFont("Segoe UI", 10), text_color=C["muted"]).pack(side="left", padx=(0, 8))
            ctk.CTkButton(row, text="✕", font=ctk.CTkFont("Segoe UI", 11),
                          fg_color="transparent", hover_color=C["hover"],
                          text_color=C["muted"], width=28, height=28, corner_radius=14,
                          command=lambda i=item: self._remove(i)).pack(side="right")

        ctk.CTkFrame(self.file_card, height=6, fg_color="transparent").pack()
        total = len(self.all_files)
        self.summary_label.configure(text=f"{total} file{'s' if total != 1 else ''} queued for printing", text_color=C["accent"])
        self.stat_total.configure(text=str(total))

    def _remove(self, item):
        if item in self.source_items:
            self.source_items.remove(item)
        self._refresh()

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
        if not self.all_files:
            messagebox.showwarning("No Files", "Please add at least one file or folder.")
            return
        self._pause_event.set()
        self.run_btn.configure(state="disabled", text="Printing…")
        self.pause_btn.configure(state="normal")
        self.progress.set(0)
        self.stat_printed.configure(text="0")
        self.stat_failed.configure(text="0")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            out_dir  = get_output_dir()
            log_path = os.path.join(out_dir, "job.log")
            logging.basicConfig(filename=log_path, level=logging.INFO,
                                format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")

            batch_size   = int(self.batch_size.get() or 20)
            delay_prints = float(self.delay_prints.get() or 3)
            delay_batch  = float(self.delay_batches.get() or 10)
            duplex       = self.duplex_var.get()
            duplex_edge  = self.duplex_edge_var.get()
            files        = self.all_files
            total        = len(files)

            self._log(f"Starting print job — {total} file(s)")
            logging.info(f"Job started — {total} files")

            printed = 0
            failed  = 0

            for batch_start in range(0, total, batch_size):
                self._pause_event.wait()
                batch = files[batch_start:batch_start + batch_size]
                self._log(f"\n  Batch {batch_start+1} → {batch_start+len(batch)}")

                for fpath in batch:
                    self._pause_event.wait()
                    fname = os.path.basename(fpath)
                    ext   = os.path.splitext(fpath)[1].lower()

                    # Duplex edge — only meaningful for PDFs
                    edge = "long"
                    use_duplex = duplex
                    if ext == ".pdf":
                        pages = len(PdfReader(fpath).pages)
                        edge  = detect_edge(fpath) if duplex and duplex_edge == "auto" else duplex_edge
                        use_duplex = duplex and pages > 1
                        mode = f"DUPLEX {edge}" if use_duplex else "SIMPLEX"
                    else:
                        mode = "default settings"

                    try:
                        print_file(fpath, use_duplex, edge)
                        printed += 1
                        self.stat_printed.configure(text=str(printed))
                        self._log(f"  🖨️   {fname} [{mode}]")
                        logging.info(f"Printed: {fname}")
                    except Exception as e:
                        failed += 1
                        self.stat_failed.configure(text=str(failed))
                        self._log(f"  ❌  {fname} → {e}")
                        logging.error(f"Failed: {fname} — {e}")

                    self.progress.set((printed + failed) / total)
                    time.sleep(delay_prints)

                if batch_start + batch_size < total:
                    self._log(f"  ⏳  Waiting {delay_batch}s…")
                    time.sleep(delay_batch)

            self._log(f"\n{'─'*44}")
            self._log(f"Done.  Printed: {printed}  |  Failed: {failed}")
            self._log(f"Log → {log_path}")
            logging.info("Job complete")

            import subprocess
            subprocess.Popen(["explorer", out_dir])
            messagebox.showinfo("Complete", f"Printed: {printed}\nFailed: {failed}\n\nLog: {out_dir}")

        except Exception as e:
            self._log(f"\n❌  Error: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            self.run_btn.configure(state="normal", text="🖨️  Print All")
            self.pause_btn.configure(state="disabled", text="⏸  Pause")
            self.progress.set(1)


if __name__ == "__main__":
    QuickPrintApp().mainloop()
