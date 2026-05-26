"""
ui.py  – Typst PDF Generation Pipeline
Launched from the Dashboard as a subprocess.
"""

import os
import sys
import json
import shutil
import subprocess
import threading
import logging
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from multiprocessing import cpu_count
from dotenv import load_dotenv

load_dotenv()

# ui.py lives inside scripts/pdf_generator/
# We need the PARENT (scripts/) on sys.path so `import pdf_generator` works.
_THIS_DIR   = os.path.dirname(os.path.abspath(__file__))   # …/scripts/pdf_generator
_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)                  # …/scripts

for _p in (_SCRIPTS_DIR, _THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

BASE_DIR = _THIS_DIR  # working dir for relative paths inside the pipeline UI

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "PDF_Generator")


def get_run_output_dirs(out_name: str = "OUTPUT", merge_name: str = "MERGE_PDF"):
    """Create a timestamped run folder with OUTPUT and MERGE_PDF subfolders."""
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = os.path.join(BASE_OUT, ts)
    output_dir = os.path.join(run_dir, out_name or "OUTPUT")
    merge_dir = os.path.join(run_dir, merge_name or "MERGE_PDF")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(merge_dir, exist_ok=True)
    return output_dir, merge_dir, run_dir


# ───────────────────────────────────────────────────────────────
#  Logging → ScrolledText
# ───────────────────────────────────────────────────────────────
class _TextHandler(logging.Handler):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def emit(self, record):
        msg = self.format(record) + "\n"
        lvl = record.levelname
        def _write():
            self.widget.configure(state="normal")
            self.widget.insert(tk.END, msg, lvl)
            self.widget.see(tk.END)
            self.widget.configure(state="disabled")
        self.widget.after(0, _write)


# ───────────────────────────────────────────────────────────────
#  Small reusable helpers
# ───────────────────────────────────────────────────────────────
def _field_row(parent, label, var, row, browse_fn=None, card_bg="#2a2a3e",
               fg="#cdd6f4", ent_bg="#313244", width=46):
    tk.Label(parent, text=label, bg=card_bg, fg=fg,
             font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w",
                                          padx=(0, 10), pady=5)
    e = tk.Entry(parent, textvariable=var, bg=ent_bg, fg=fg,
                 insertbackground=fg, relief="flat",
                 font=("Segoe UI", 10), width=width)
    e.grid(row=row, column=1, sticky="ew", pady=5)
    if browse_fn:
        tk.Button(parent, text="…", command=browse_fn,
                  bg="#3d3d55", fg=fg, relief="flat",
                  font=("Segoe UI", 10), padx=6,
                  activebackground="#7c6af7",
                  activeforeground="#ffffff",
                  cursor="hand2").grid(row=row, column=2, padx=(6, 0), pady=5)
    return e


def _section(parent, title, bg="#2a2a3e", fg="#7c6af7"):
    tk.Label(parent, text=title, bg=bg, fg=fg,
             font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(16, 4), padx=2)
    tk.Frame(parent, bg=fg, height=1).pack(fill="x", pady=(0, 10))


def _card(parent, bg="#2a2a3e"):
    f = tk.Frame(parent, bg=bg, padx=16, pady=12)
    f.pack(fill="x", pady=(0, 6))
    return f


# ───────────────────────────────────────────────────────────────
#  Main App
# ───────────────────────────────────────────────────────────────
class TypstApp(tk.Tk):

    BG   = "#1e1e2e"
    CARD = "#2a2a3e"
    ACC  = "#7c6af7"
    FG   = "#cdd6f4"
    ENT  = "#313244"
    GRN  = "#a6e3a1"
    YEL  = "#f9e2af"
    RED  = "#f38ba8"
    BLU  = "#89b4fa"

    def __init__(self):
        super().__init__()
        self.title("PDF Generation Pipeline")
        self.geometry("900x820")
        self.minsize(820, 700)
        self.configure(bg=self.BG)
        self._control = None
        self._pipeline_running = False
        self._paused = False
        self._current_run = None
        self._build()
        self._attach_logger()

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=self.ACC, height=52)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  PDF Generation Pipeline",
                 bg=self.ACC, fg="#ffffff",
                 font=("Segoe UI", 15, "bold")).pack(side="left", padx=18, pady=12)

        # Scrollable body
        body_frame = tk.Frame(self, bg=self.BG)
        body_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(body_frame, bg=self.BG, highlightthickness=0)
        vsb = ttk.Scrollbar(body_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._scroll_frame = tk.Frame(canvas, bg=self.BG)
        _wid = canvas.create_window((0, 0), window=self._scroll_frame, anchor="nw")

        def _on_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def _on_canvas_resize(e):
            canvas.itemconfig(_wid, width=e.width)

        self._scroll_frame.bind("<Configure>", _on_configure)
        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        root = self._scroll_frame
        pad = dict(padx=16)

        # ── 1. Paths ──
        _section(root, "📂  File & Folder Paths", bg=self.BG)
        c1 = _card(root, self.CARD)
        c1.columnconfigure(1, weight=1)

        self._data_var   = tk.StringVar()
        self._config_var = tk.StringVar()
        self._output_var = tk.StringVar(value="OUTPUT")
        self._merge_var  = tk.StringVar(value="MERGE_PDF")
        self._base_out   = BASE_OUT  # Desktop\OUTPUT\PDF_Generator
        self._images_var = tk.StringVar()

        _field_row(c1, "Data file (.xlsx / .csv)", self._data_var, 0,
                   lambda: self._browse_file(self._data_var, [("Excel/CSV","*.xlsx *.xls *.csv")]),
                   self.CARD, self.FG, self.ENT)
        _field_row(c1, "Notice Config (.json) [Optional]", self._config_var, 1,
                   lambda: self._browse_file(self._config_var, [("JSON","*.json")]),
                   self.CARD, self.FG, self.ENT)
        # Output path banner
        out_banner = tk.Frame(c1, bg="#082a12", padx=10, pady=6)
        out_banner.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 2))
        tk.Label(
            out_banner,
            text=f"📁  Output → Desktop\\OUTPUT\\PDF_Generator\\<timestamp>\\<folder name>",
            bg="#082a12", fg="#30d158", font=("Segoe UI", 9, "italic")
        ).pack(anchor="w")

        _field_row(c1, "Output folder name", self._output_var, 3, None, self.CARD, self.FG, self.ENT)
        _field_row(c1, "Merge folder name",  self._merge_var,  4, None, self.CARD, self.FG, self.ENT)
        _field_row(c1, "Images folder [Optional]", self._images_var, 5,
                   lambda: self._browse_dir(self._images_var),
                   self.CARD, self.FG, self.ENT)

        # ── 2. Templates ──
        _section(root, "📄  Templates", bg=self.BG)
        c2 = _card(root, self.CARD)
        c2.columnconfigure(1, weight=1)

        self._tpl_folder_var = tk.StringVar()

        tk.Label(c2, text="Template folder", bg=self.CARD, fg=self.FG,
                 font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", padx=(0,10), pady=5)
        tpl_entry = tk.Entry(c2, textvariable=self._tpl_folder_var,
                              bg=self.ENT, fg=self.FG, insertbackground=self.FG,
                              relief="flat", font=("Segoe UI", 10), width=46)
        tpl_entry.grid(row=0, column=1, sticky="ew", pady=5)
        tk.Button(c2, text="…", command=self._browse_template_folder,
                  bg="#3d3d55", fg=self.FG, relief="flat",
                  font=("Segoe UI", 10), padx=6,
                  activebackground=self.ACC, activeforeground="#ffffff",
                  cursor="hand2").grid(row=0, column=2, padx=(6,0), pady=5)

        tk.Label(c2, text="Template mapping (template.json: state/key → .typ)",
                 bg=self.CARD, fg=self.BLU,
                 font=("Segoe UI", 9, "italic")).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(4, 2))

        self._tpl_preview = tk.Text(c2, height=5,
                                     bg=self.ENT, fg=self.GRN,
                                     font=("Consolas", 9), relief="flat",
                                     state="disabled", wrap="word")
        self._tpl_preview.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        self._tpl_folder_var.trace_add("write", lambda *_: self._refresh_tpl_preview())

        # ── 3. Processing ──
        _section(root, "⚙  Processing", bg=self.BG)
        c3 = _card(root, self.CARD)
        c3.columnconfigure(1, weight=1)
        c3.columnconfigure(3, weight=1)

        self._gen_pdf = tk.BooleanVar(value=True)
        self._mrg_pdf = tk.BooleanVar(value=True)
        self._pdf_pwd = tk.BooleanVar(value=False)

        chk_row = tk.Frame(c3, bg=self.CARD)
        chk_row.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        for txt, var in [("Generate PDFs", self._gen_pdf), ("Merge PDFs", self._mrg_pdf), ("PDF Protection", self._pdf_pwd)]:
            tk.Checkbutton(chk_row, text=txt, variable=var,
                           bg=self.CARD, fg=self.FG, selectcolor=self.ENT,
                           activebackground=self.CARD, activeforeground=self.FG,
                           font=("Segoe UI", 10)).pack(side="left", padx=12)

        max_cpu = cpu_count()
        self._chunksize   = tk.IntVar(value=500)
        self._batchsize   = tk.IntVar(value=500)
        self._max_mem     = tk.IntVar(value=1024)
        self._retry       = tk.IntVar(value=3)
        self._max_workers = tk.IntVar(value=max(1, max_cpu - 2))
        self._pwd_field   = tk.StringVar()

        left_spinners = [
            ("Chunk size",      self._chunksize,   50,  5000, 50),
            ("Batch size",      self._batchsize,   50,  5000, 50),
            ("Max memory (MB)", self._max_mem,    128,  8192, 128),
        ]
        right_spinners = [
            ("Retry attempts",  self._retry,        1,    10,  1),
            ("Max workers",     self._max_workers,  1, max_cpu, 1),
        ]

        def _spin(parent, label, var, lo, hi, inc, row, col_offset):
            tk.Label(parent, text=label, bg=self.CARD, fg=self.FG,
                     font=("Segoe UI", 10)).grid(
                row=row, column=col_offset, sticky="w",
                padx=(0 if col_offset == 0 else 20, 8), pady=5)
            ttk.Spinbox(parent, from_=lo, to=hi, increment=inc,
                        textvariable=var, width=9).grid(
                row=row, column=col_offset+1, sticky="w", pady=5)

        for i, (l, v, lo, hi, inc) in enumerate(left_spinners, start=1):
            _spin(c3, l, v, lo, hi, inc, i, 0)
        for i, (l, v, lo, hi, inc) in enumerate(right_spinners, start=1):
            _spin(c3, l, v, lo, hi, inc, i, 2)

        tk.Label(c3, text="Password column", bg=self.CARD, fg=self.FG,
                 font=("Segoe UI", 10)).grid(
            row=len(left_spinners)+1, column=0, sticky="w", padx=(0, 8), pady=5)
        self._pwd_entry = tk.Entry(c3, textvariable=self._pwd_field,
                                    bg=self.ENT, fg=self.FG,
                                    insertbackground=self.FG, relief="flat",
                                    font=("Segoe UI", 10), width=20, state="disabled")
        self._pwd_entry.grid(row=len(left_spinners)+1, column=1, sticky="w", pady=5)
        self._pdf_pwd.trace_add("write", lambda *_: self._pwd_entry.configure(
            state="normal" if self._pdf_pwd.get() else "disabled"))

        # ── 4. S3 Upload ──
        _section(root, "☁  S3 Upload", bg=self.BG)
        c4 = _card(root, self.CARD)
        c4.columnconfigure(1, weight=1)

        self._upload_en  = tk.BooleanVar(value=False)
        self._s3_uri     = tk.StringVar()
        self._upload_all = tk.BooleanVar(value=False)

        chk_row2 = tk.Frame(c4, bg=self.CARD)
        chk_row2.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0,8))
        tk.Checkbutton(chk_row2, text="Enable S3 Upload", variable=self._upload_en,
                        bg=self.CARD, fg=self.FG, selectcolor=self.ENT,
                        activebackground=self.CARD, activeforeground=self.FG,
                        font=("Segoe UI", 10), command=self._toggle_upload_fields).pack(side="left")
        tk.Checkbutton(chk_row2, text="Upload entire folder", variable=self._upload_all,
                        bg=self.CARD, fg=self.FG, selectcolor=self.ENT,
                        activebackground=self.CARD, activeforeground=self.FG,
                        font=("Segoe UI", 10)).pack(side="left", padx=20)

        self._upload_entries = []
        tk.Label(c4, text="S3 URI / prefix", bg=self.CARD, fg=self.FG,
                 font=("Segoe UI", 10)).grid(row=1, column=0, sticky="w", padx=(0,10), pady=4)
        s3_uri_entry = tk.Entry(c4, textvariable=self._s3_uri,
                                 bg=self.ENT, fg=self.FG, insertbackground=self.FG,
                                 relief="flat", font=("Segoe UI", 10), width=46, state="disabled")
        s3_uri_entry.grid(row=1, column=1, sticky="ew", pady=4)
        self._upload_entries.append(s3_uri_entry)

        # ── 5. Log ──
        _section(root, "📋  Log", bg=self.BG)
        log_card = tk.Frame(root, bg=self.CARD, padx=16, pady=12)
        log_card.pack(fill="both", expand=True, pady=(0, 6), **pad)

        self._log_box = scrolledtext.ScrolledText(
            log_card, state="disabled", wrap="word",
            bg="#0d0d1a", fg=self.FG, font=("Consolas", 9), relief="flat",
            insertbackground=self.FG, height=10)
        self._log_box.pack(fill="both", expand=True)
        self._log_box.tag_config("INFO",    foreground=self.GRN)
        self._log_box.tag_config("WARNING", foreground=self.YEL)
        self._log_box.tag_config("ERROR",   foreground=self.RED)
        self._log_box.tag_config("DEBUG",   foreground=self.BLU)

        tk.Button(log_card, text="Clear log", command=self._clear_log,
                  bg="#3d3d55", fg=self.FG, relief="flat",
                  font=("Segoe UI", 9), padx=8,
                  activebackground=self.ACC, activeforeground="#ffffff",
                  cursor="hand2").pack(anchor="e", pady=(6, 0))

        # ── Bottom bar ──
        bar = tk.Frame(self, bg="#14141f", pady=10)
        bar.pack(fill="x", side="bottom")

        self._status_var = tk.StringVar(value="Idle")
        tk.Label(bar, textvariable=self._status_var, bg="#14141f", fg=self.ACC,
                 font=("Segoe UI", 10, "italic")).pack(side="left", padx=16)

        self._run_btn = tk.Button(
            bar, text="▶   Run Pipeline", command=self._run_pipeline,
            bg=self.ACC, fg="#ffffff", relief="flat",
            font=("Segoe UI", 10, "bold"), padx=14, pady=6,
            activebackground="#5a48d0", activeforeground="#ffffff",
            cursor="hand2",
        )
        self._run_btn.pack(side="right", padx=(0, 10))

        self._btn_restart = tk.Button(
            bar, text="🔄  Restart", command=self._restart_pipeline,
            bg="#3d3d55", fg="#ffffff", relief="flat",
            font=("Segoe UI", 10), padx=10, pady=6, state="disabled",
            activebackground="#555570", activeforeground="#ffffff",
            cursor="hand2",
        )
        self._btn_restart.pack(side="right", padx=(0, 6))

        self._btn_stop = tk.Button(
            bar, text="⏹  Stop", command=self._stop_pipeline,
            bg="#3d3d55", fg="#ffffff", relief="flat",
            font=("Segoe UI", 10), padx=10, pady=6, state="disabled",
            activebackground="#555570", activeforeground="#ffffff",
            cursor="hand2",
        )
        self._btn_stop.pack(side="right", padx=(0, 6))

        self._btn_resume = tk.Button(
            bar, text="▶  Resume", command=self._resume_pipeline,
            bg="#3d3d55", fg="#ffffff", relief="flat",
            font=("Segoe UI", 10), padx=10, pady=6, state="disabled",
            activebackground="#555570", activeforeground="#ffffff",
            cursor="hand2",
        )
        self._btn_resume.pack(side="right", padx=(0, 6))

        self._btn_pause = tk.Button(
            bar, text="⏸  Pause", command=self._pause_pipeline,
            bg="#3d3d55", fg="#ffffff", relief="flat",
            font=("Segoe UI", 10), padx=10, pady=6, state="disabled",
            activebackground="#555570", activeforeground="#ffffff",
            cursor="hand2",
        )
        self._btn_pause.pack(side="right", padx=(0, 6))

        for txt, cmd in [
            ("📂  Load Config",  self._load_config),
            ("💾  Save Config",  self._save_config),
        ]:
            tk.Button(bar, text=txt, command=cmd,
                      bg="#3d3d55", fg="#ffffff", relief="flat",
                      font=("Segoe UI", 10), padx=14, pady=6,
                      activebackground="#555570", activeforeground="#ffffff",
                      cursor="hand2").pack(side="right", padx=(0, 10))

    # ── Template folder helpers ──
    def _browse_template_folder(self):
        path = filedialog.askdirectory(title="Select Template Folder")
        if path:
            self._tpl_folder_var.set(path)

    def _refresh_tpl_preview(self):
        folder = self._tpl_folder_var.get()
        self._tpl_preview.configure(state="normal")
        self._tpl_preview.delete("1.0", tk.END)
        if folder and os.path.isdir(folder):
            try:
                templates = self._load_templates_from_folder(soft_fail=True)
                if not templates:
                    self._tpl_preview.insert(tk.END, "  No template mapping found.")
                else:
                    def _sk(k):
                        if k == "": return "ZZZZZZ"
                        if k == "-": return "YYYYYY"
                        return k
                    lines = []
                    for k in sorted(templates.keys(), key=_sk):
                        v = templates[k]
                        shown_key = k if k else "''"
                        mark = "✓" if os.path.exists(v) else "MISSING"
                        lines.append(f"  {shown_key}  →  {os.path.basename(v)}  [{mark}]")
                    if len(lines) > 30:
                        lines = lines[:30] + [f"  ... (+{len(lines) - 30} more)"]
                    if "DEFAULT" in templates:
                        lines.append("  --------------------------------------------------\n  DEFAULT key is configured for fallback.")
                    self._tpl_preview.insert(tk.END, "\n".join(lines))
            except Exception as e:
                self._tpl_preview.insert(tk.END, f"  Template mapping error:\n  {e}")
        else:
            self._tpl_preview.insert(tk.END, "  No folder selected yet.")
        self._tpl_preview.configure(state="disabled")

    def _load_templates_from_folder(self, soft_fail: bool = False) -> dict:
        folder = self._tpl_folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            return {}

        mapping_path = os.path.join(folder, "template.json")
        if not os.path.exists(mapping_path):
            mapping_path = os.path.join(BASE_DIR, "template.json")

        if not os.path.exists(mapping_path):
            if soft_fail:
                return {}
            raise ValueError(
                "Missing `template.json`.\n"
                "Put template.json in the selected template folder, or keep it in the scripts folder."
            )

        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            if soft_fail:
                return {}
            raise ValueError(f"Failed to read template mapping JSON: {mapping_path}\n{e}")

        template_dict = data.get("template_dict") or {}
        if not isinstance(template_dict, dict) or not template_dict:
            if soft_fail:
                return {}
            raise ValueError(f"Invalid template.json format (expected object `template_dict`): {mapping_path}")

        templates = {}
        existing_templates = {}
        missing_files = []
        for state_key, typ_filename in template_dict.items():
            if not isinstance(typ_filename, str):
                continue
            typ_path = os.path.join(folder, typ_filename)
            templates[state_key] = typ_path
            if os.path.exists(typ_path):
                existing_templates[state_key] = typ_path
            else:
                missing_files.append(f"{state_key!r} -> {typ_filename}")

        if "DEFAULT" not in template_dict:
            if soft_fail:
                return templates
            raise ValueError(
                "template.json is missing a `DEFAULT` mapping.\n"
                "Add `\"DEFAULT\": \"default.typ\"` (or equivalent)."
            )

        if soft_fail:
            return templates

        default_path = templates.get("DEFAULT")
        if not default_path or not os.path.exists(default_path):
            raise ValueError(
                "DEFAULT template file is missing from the selected folder.\n"
                f"Expected: {os.path.join(folder, template_dict.get('DEFAULT', 'default.typ'))}"
            )

        return existing_templates

    # ── Browse helpers ──
    def _browse_file(self, var, filetypes):
        p = filedialog.askopenfilename(filetypes=filetypes)
        if p:
            var.set(p)

    def _browse_dir(self, var):
        p = filedialog.askdirectory()
        if p:
            var.set(p)

    def _toggle_upload_fields(self):
        st = "normal" if self._upload_en.get() else "disabled"
        for e in self._upload_entries:
            e.configure(state=st)

    def _attach_logger(self):
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        h = _TextHandler(self._log_box)
        h.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        root_logger.addHandler(h)

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", tk.END)
        self._log_box.configure(state="disabled")

    def _set_pipeline_buttons(self, running: bool = False, paused: bool = False) -> None:
        self._run_btn.configure(state="disabled" if running else "normal")
        self._btn_pause.configure(state="normal" if running and not paused else "disabled")
        self._btn_resume.configure(state="normal" if running and paused else "disabled")
        self._btn_stop.configure(state="normal" if running else "disabled")
        self._btn_restart.configure(state="normal" if running else "normal")

    def _on_control_event(self, event: str) -> None:
        if event == "paused":
            self._paused = True
            self._status_var.set("⏸  Paused")
            self._set_pipeline_buttons(running=True, paused=True)
        elif event == "resumed":
            self._paused = False
            self._status_var.set("⏳  Running…")
            self._set_pipeline_buttons(running=True, paused=False)

    def _pause_pipeline(self) -> None:
        if not self._pipeline_running or self._paused or not self._control:
            return
        messagebox.showinfo(
            "Pause",
            "The process will pause after completing the current batch.",
        )
        self._control.request_pause()
        self._status_var.set("⏸  Pausing after current batch…")

    def _resume_pipeline(self) -> None:
        if not self._pipeline_running or not self._paused or not self._control:
            return
        self._control.resume()
        self._paused = False
        self._status_var.set("⏳  Running…")
        self._set_pipeline_buttons(running=True, paused=False)

    def _stop_pipeline(self) -> None:
        if not self._pipeline_running or not self._control:
            return
        messagebox.showinfo(
            "Stop",
            "The process will stop after completing the current batch.",
        )
        self._control.request_stop()
        self._status_var.set("⏹  Stopping after current batch…")

    def _restart_pipeline(self) -> None:
        if self._pipeline_running:
            if not self._control:
                return
            messagebox.showinfo(
                "Restart",
                "The process will restart after completing the current batch.\n\n"
                "All PDFs and progress in this run will be cleared, "
                "then processing will start from the beginning.",
            )
            self._control.request_restart()
            self._status_var.set("🔄  Restarting after current batch…")
        else:
            self._run_pipeline(clear_first=True, reuse_run=True)

    def _build_config_dict(self, output_dir: str = None, merge_dir: str = None) -> dict:
        templates = self._load_templates_from_folder()
        if not templates:
            raise ValueError(
                "No template mapping loaded.\n"
                "Select a template folder that contains `template.json` (and the referenced .typ files)."
            )
        out_name   = self._output_var.get().strip() or "OUTPUT"
        merge_name = self._merge_var.get().strip()  or "MERGE_PDF"

        if output_dir is None:
            output_dir = os.path.join(BASE_OUT, out_name)
        if merge_dir is None:
            merge_dir = os.path.join(BASE_OUT, merge_name)

        return {
            "paths": {
                "data":      self._data_var.get().strip(),
                "config":    self._config_var.get().strip(),
                "templates": templates,
                "output":    output_dir,
                "merge":     merge_dir,
                "images":    self._images_var.get().strip(),
            },
            "processing": {
                "generate_pdfs":  self._gen_pdf.get(),
                "merge_pdfs":     self._mrg_pdf.get(),
                "chunksize":      self._chunksize.get(),
                "batch_size":     self._batchsize.get(),
                "max_memory_mb":  self._max_mem.get(),
                "retry_attempts": self._retry.get(),
                "max_workers":    self._max_workers.get(),
                "pdf_protection": {
                    "enabled":          self._pdf_pwd.get(),
                    "password_field":   self._pwd_field.get().strip() or None,
                    "default_password": "password",
                },
                "compress": {"enabled": False},
            },
            "upload": {
                "enabled":               self._upload_en.get(),
                "bucket_name":           os.getenv("S3_BUCKET_NAME") or None,
                "s3_uri":                self._s3_uri.get().strip() or None,
                "aws_access_key_id":     os.getenv("AWS_ACCESS_KEY_ID") or None,
                "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY") or None,
                "aws_region":            os.getenv("AWS_REGION") or None,
                "upload_entire_folder":  self._upload_all.get(),
            },
        }

    def _save_config(self):
        try:
            cfg = self._build_config_dict()
        except ValueError as e:
            messagebox.showerror("Validation", str(e))
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json")],
            initialfile="pipeline_config.json")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            messagebox.showinfo("Saved", f"Config saved to:\n{path}")

    def _load_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                cfg = json.load(f)
            self._apply_config(cfg)
        except Exception as e:
            messagebox.showerror("Load error", str(e))

    def _apply_config(self, cfg: dict):
        p = cfg.get("paths", {})
        self._data_var.set(p.get("data", ""))
        self._config_var.set(p.get("config", ""))
        self._output_var.set(os.path.basename(p.get("output", "OUTPUT")))
        self._merge_var.set(os.path.basename(p.get("merge", "MERGE_PDF")))
        self._images_var.set(p.get("images", ""))
        tpls = p.get("templates", {})
        if tpls:
            first = next(iter(tpls.values()))
            self._tpl_folder_var.set(os.path.dirname(first))
        proc = cfg.get("processing", {})
        self._gen_pdf.set(proc.get("generate_pdfs", True))
        self._mrg_pdf.set(proc.get("merge_pdfs", True))
        self._chunksize.set(proc.get("chunksize", 500))
        self._batchsize.set(proc.get("batch_size", 500))
        self._max_mem.set(proc.get("max_memory_mb", 1024))
        self._retry.set(proc.get("retry_attempts", 3))
        self._max_workers.set(proc.get("max_workers", max(1, cpu_count()-2)))
        prot = proc.get("pdf_protection", {})
        self._pdf_pwd.set(prot.get("enabled", False))
        self._pwd_field.set(prot.get("password_field") or "")
        upl = cfg.get("upload", {})
        self._upload_en.set(upl.get("enabled", False))
        self._s3_uri.set(upl.get("s3_uri") or "")
        self._upload_all.set(upl.get("upload_entire_folder", False))
        self._toggle_upload_fields()
        messagebox.showinfo("Loaded", "Configuration applied.")

    def _run_pipeline(self, clear_first: bool = False, reuse_run: bool = False):
        if self._pipeline_running:
            return

        try:
            out_name = self._output_var.get().strip() or "OUTPUT"
            merge_name = self._merge_var.get().strip() or "MERGE_PDF"

            if not reuse_run and not clear_first and self._current_run:
                state_path = os.path.join(
                    self._current_run["output"], "state", "processing_state.json"
                )
                if os.path.isfile(state_path):
                    ans = messagebox.askyesnocancel(
                        "Resume previous run?",
                        f"Saved progress was found in:\n{self._current_run['run_dir']}\n\n"
                        "Yes — resume this run\n"
                        "No — start a new timestamped run\n"
                        "Cancel",
                    )
                    if ans is None:
                        return
                    if ans:
                        reuse_run = True
                    else:
                        self._current_run = None

            if reuse_run and self._current_run:
                output_dir = self._current_run["output"]
                merge_dir = self._current_run["merge"]
                run_dir = self._current_run["run_dir"]
                os.makedirs(output_dir, exist_ok=True)
                os.makedirs(merge_dir, exist_ok=True)
            else:
                output_dir, merge_dir, run_dir = get_run_output_dirs(out_name, merge_name)
            cfg_dict = self._build_config_dict(output_dir=output_dir, merge_dir=merge_dir)
        except ValueError as e:
            messagebox.showerror("Validation error", str(e))
            return

        data_path = cfg_dict["paths"]["data"]
        if not data_path or not os.path.isfile(data_path):
            messagebox.showwarning("No File", "Please select a data file (.xlsx / .csv) first.")
            return

        if clear_first:
            from pdf_generator.pipeline_control import clear_run_output
            clear_run_output(output_dir, merge_dir)

        self._current_run = {
            "output": output_dir,
            "merge": merge_dir,
            "run_dir": run_dir,
        }
        self._pipeline_running = True
        self._paused = False
        self._set_pipeline_buttons(running=True)
        self._status_var.set("⏳  Running…")
        logging.info(f"Run folder: {run_dir}")

        def _worker():
            from pdf_generator.config import AppConfig
            from pdf_generator.logging_config import setup_logging
            from pdf_generator.main import main as run_main
            from pdf_generator.pipeline_control import (
                PipelineRestart,
                PipelineStopped,
                clear_run_output,
                reset_control,
            )

            control = reset_control()
            self._control = control
            control.set_status_callback(
                lambda event: self.after(0, lambda e=event: self._on_control_event(e))
            )

            try:
                while True:
                    try:
                        log_path = setup_logging(output_folder=run_dir)
                        logging.info(f"Log file: {log_path}")

                        config = AppConfig.from_dict(cfg_dict)

                        if config.paths.images and os.path.exists(config.paths.images):
                            for img in os.listdir(config.paths.images):
                                src = os.path.join(config.paths.images, img)
                                dst = os.path.join(config.paths.output, img)
                                if os.path.isfile(src):
                                    shutil.copy(src, dst)

                        run_main(config, control=control)

                        def _on_success():
                            self._current_run = None
                            self._status_var.set("✅  Done")
                            subprocess.Popen(["explorer", run_dir])
                            messagebox.showinfo(
                                "Complete",
                                "PDF pipeline finished successfully.\n\n"
                                f"Run folder:\n{run_dir}\n\n"
                                f"PDFs:\n{output_dir}\n\n"
                                f"Merged PDFs:\n{merge_dir}",
                            )

                        self.after(0, _on_success)
                        break

                    except PipelineRestart:
                        clear_run_output(output_dir, merge_dir)
                        control = reset_control()
                        self._control = control
                        control.set_status_callback(
                            lambda event: self.after(0, lambda e=event: self._on_control_event(e))
                        )
                        self._paused = False
                        logging.info("Restarting pipeline from the beginning…")
                        self.after(0, lambda: self._status_var.set("🔄  Restarting…"))
                        self.after(0, lambda: self._set_pipeline_buttons(running=True))
                        continue

                    except PipelineStopped:
                        def _on_stopped():
                            self._status_var.set("⏹  Stopped")
                            messagebox.showinfo(
                                "Stopped",
                                "Pipeline stopped after the current batch.\n\n"
                                "Progress was saved. Click Run to resume from the "
                                "last completed batch in this run folder.",
                            )

                        self.after(0, _on_stopped)
                        break

            except Exception as e:
                logging.error(f"Pipeline error: {e}", exc_info=True)

                def _on_failure(err=e):
                    self._status_var.set(f"❌  Failed: {err}")
                    messagebox.showerror("Pipeline Failed", str(err))

                self.after(0, _on_failure)
            finally:
                self._pipeline_running = False
                self._paused = False
                self._control = None
                self.after(0, lambda: self._set_pipeline_buttons(running=False))

        threading.Thread(target=_worker, daemon=True).start()


# ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = TypstApp()
    app.mainloop()
