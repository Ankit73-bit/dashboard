"""
ui.py  – Typst PDF Generation Pipeline
Launched from the Dashboard as a subprocess.
"""

import os
import sys
import json
import shutil
import threading
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from multiprocessing import cpu_count
from dotenv import load_dotenv

load_dotenv()

# ui.py lives inside scripts/capri_pipeline/
# We need the PARENT (scripts/) on sys.path so `import capri_pipeline` works.
_THIS_DIR   = os.path.dirname(os.path.abspath(__file__))   # …/scripts/capri_pipeline
_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)                  # …/scripts

for _p in (_SCRIPTS_DIR, _THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

BASE_DIR = _THIS_DIR  # working dir for relative paths inside the pipeline UI


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
        self._images_var = tk.StringVar()

        _field_row(c1, "Data file (.xlsx / .csv)", self._data_var, 0,
                   lambda: self._browse_file(self._data_var, [("Excel/CSV","*.xlsx *.xls *.csv")]),
                   self.CARD, self.FG, self.ENT)
        _field_row(c1, "Notice Config (.json) [Optional]", self._config_var, 1,
                   lambda: self._browse_file(self._config_var, [("JSON","*.json")]),
                   self.CARD, self.FG, self.ENT)
        _field_row(c1, "Output folder", self._output_var, 2, None, self.CARD, self.FG, self.ENT)
        _field_row(c1, "Merge folder",  self._merge_var,  3, None, self.CARD, self.FG, self.ENT)
        _field_row(c1, "Images folder [Optional]", self._images_var, 4,
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

        for txt, cmd in [
            ("📂  Load Config",  self._load_config),
            ("💾  Save Config",  self._save_config),
            ("▶   Run Pipeline", self._run_pipeline),
        ]:
            is_run = "Run" in txt
            tk.Button(bar, text=txt, command=cmd,
                      bg=self.ACC if is_run else "#3d3d55",
                      fg="#ffffff", relief="flat",
                      font=("Segoe UI", 10, "bold" if is_run else "normal"),
                      padx=14, pady=6,
                      activebackground="#5a48d0" if is_run else "#555570",
                      activeforeground="#ffffff",
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

    def _build_config_dict(self) -> dict:
        templates = self._load_templates_from_folder()
        if not templates:
            raise ValueError(
                "No template mapping loaded.\n"
                "Select a template folder that contains `template.json` (and the referenced .typ files)."
            )
        out_name   = self._output_var.get().strip() or "OUTPUT"
        merge_name = self._merge_var.get().strip()  or "MERGE_PDF"

        return {
            "paths": {
                "data":      self._data_var.get().strip(),
                "config":    self._config_var.get().strip(),
                "templates": templates,
                "output":    os.path.join(BASE_DIR, out_name),
                "merge":     os.path.join(BASE_DIR, merge_name),
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

    def _run_pipeline(self):
        try:
            cfg_dict = self._build_config_dict()
        except ValueError as e:
            messagebox.showerror("Validation error", str(e))
            return

        self._status_var.set("⏳  Running…")

        def _worker():
            try:
                from capri_pipeline.config import AppConfig
                from capri_pipeline.logging_config import setup_logging
                from capri_pipeline.main import main as run_main
                setup_logging()

                config = AppConfig.from_dict(cfg_dict)
                if config.paths.images and os.path.exists(config.paths.images):
                    os.makedirs(config.paths.output, exist_ok=True)
                    for img in os.listdir(config.paths.images):
                        src = os.path.join(config.paths.images, img)
                        dst = os.path.join(config.paths.output, img)
                        if os.path.isfile(src):
                            shutil.copy(src, dst)

                run_main(config)
                self.after(0, lambda: self._status_var.set("✅  Done"))
            except Exception as e:
                logging.error(f"Pipeline error: {e}", exc_info=True)
                self.after(0, lambda err=e: self._status_var.set(f"❌  Failed: {err}"))

        threading.Thread(target=_worker, daemon=True).start()


# ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = TypstApp()
    app.mainloop()
