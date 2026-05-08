"""
Tool: Excel Transformer
Multi-step pipeline: transform → merge → barcode insert → pivot → split by address count.
Embeddable Panel + standalone window.
"""

import os
import re
import glob
import threading
import subprocess
from datetime import datetime

import pandas as pd
import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Excel_Transformer")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#ff9f0a", "green":  "#30d158",
    "red":    "#ff375f", "orange": "#ff9f0a", "blue":   "#0a84ff",
}
TINT = {"bg": "#1a1200", "mid": "#2e2000", "bdr": "#5c3d00"}

# Repeating-group column pattern: name_1, final_add_2, sr_3, b_4, p_5, …
_GROUP_PREFIX_RE = re.compile(r'^(name|final_add|sr|b|p)_(\d+)$')


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def detect_groups(raw_cols):
    """Return the max repeating-group index found in column names."""
    max_n = 0
    for c in raw_cols:
        m = _GROUP_PREFIX_RE.match(c.lower().strip())
        if m:
            max_n = max(max_n, int(m.group(2)))
    return max_n


# ─── Pipeline functions ────────────────────────────────────────────────────────

def check_barcodes(data_file, barcode_file, log_fn):
    """
    Pre-flight barcode check.
    Counts how many sticker rows the data produces and compares against
    available barcodes. Raises ValueError if not enough.
    Returns (needed, available).
    """
    df = pd.read_excel(data_file)
    df.columns = df.columns.str.lower()

    needed = 0
    for _, row in df.iterrows():
        i = 1
        while True:
            if f'name_{i}' not in df.columns or pd.isna(row.get(f'name_{i}')):
                break
            needed += 1
            i += 1

    barcode_df = pd.read_excel(barcode_file, usecols=[0])
    available  = len(barcode_df)

    log_fn(f"  🔍 Rows needing a barcode : {needed:,}")
    log_fn(f"  🔍 Barcodes available     : {available:,}")

    if available < needed:
        raise ValueError(
            f"Not enough barcodes — need {needed:,} but only {available:,} available.")

    log_fn(f"  ✅ Barcode check passed  ({available - needed:,} spare)")
    return needed, available


def transform_initial_data(input_file, out_dir, selected_cols, log_fn):
    df = pd.read_excel(input_file)
    df.columns = df.columns.str.lower()

    missing = [c for c in selected_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in data file: {', '.join(missing)}")

    group_cols = ['name', 'final_add', 'sr', 'b', 'p']
    transformed_data, grouped_data = [], {}
    unique_id = 1

    for _, row in df.iterrows():
        row_data = []
        i = 1
        while True:
            cols = [f'{col}_{i}' for col in group_cols]
            if cols[0] not in df.columns or pd.isna(row[cols[0]]):
                break
            row_data.append([unique_id] + list(row[selected_cols]) + list(row[cols]))
            transformed_data.append([unique_id] + list(row[selected_cols]) + list(row[cols]))
            unique_id += 1
            i += 1

        group_count = len(row_data)
        if group_count > 0:
            grouped_data.setdefault(group_count, []).extend(row_data)

    cols_out = ['Unique_ID'] + selected_cols + group_cols

    consolidated_df = pd.DataFrame(transformed_data, columns=cols_out)
    consolidated_df.to_excel(os.path.join(out_dir, 'main.xlsx'), index=False)
    log_fn(f"  ✅ main.xlsx → {len(consolidated_df):,} rows")

    for group_count, data in grouped_data.items():
        fname = f'transformed_data_{group_count}_names.xlsx'
        pd.DataFrame(data, columns=cols_out).to_excel(os.path.join(out_dir, fname), index=False)
        log_fn(f"  ✅ {fname}")


def merge_split_files(out_dir, log_fn):
    split_files = glob.glob(os.path.join(out_dir, "transformed_data_*_names.xlsx"))
    if not split_files:
        raise FileNotFoundError("No transformed_data_*_names.xlsx files found to merge.")
    merged_df    = pd.concat([pd.read_excel(f) for f in split_files], ignore_index=True)
    sticker_path = os.path.join(out_dir, "sticker.xlsx")
    merged_df.to_excel(sticker_path, index=False)
    log_fn(f"  ✅ sticker.xlsx → {len(merged_df):,} rows from {len(split_files)} file(s)")
    return sticker_path


def insert_barcodes(sticker_path, barcode_file, log_fn):
    sticker_df  = pd.read_excel(sticker_path)
    barcode_df  = pd.read_excel(barcode_file, usecols=[0])
    barcode_df  = barcode_df.rename(columns={barcode_df.columns[0]: "barcode"})

    if len(barcode_df) < len(sticker_df):
        raise ValueError(
            f"Not enough barcodes — have {len(barcode_df):,}, need {len(sticker_df):,}.")

    sticker_df['b'] = barcode_df['barcode'].values[:len(sticker_df)]
    sticker_df.to_excel(sticker_path, index=False)
    log_fn(f"  ✅ Barcodes inserted ({len(sticker_df):,} rows)")


def pivot_and_sort(sticker_path, out_dir, selected_cols, first_col, max_groups, log_fn):
    df = pd.read_excel(sticker_path)
    df.columns = df.columns.str.strip().str.lower()

    # Fixed header = unique_id + all selected cols (unique_id always included)
    fixed_header = ['unique_id'] + [c for c in selected_cols if c != 'unique_id']

    pivoted_data = []
    for _, group in df.groupby('ref_no'):
        row_dict = {col: group[col].iloc[0] for col in fixed_header if col in group.columns}
        for i, row in enumerate(group.itertuples(index=False), start=1):
            row_dict.update({
                f'name_{i}':      row.name,
                f'final_add_{i}': row.final_add,
                f'sr_{i}':        row.sr,
                f'b_{i}':         row.b,
                f'p_{i}':         row.p,
            })
        for i in range(len(group) + 1, max_groups + 1):
            row_dict.update({
                f'name_{i}':      None,
                f'final_add_{i}': None,
                f'sr_{i}':        None,
                f'b_{i}':         None,
                f'p_{i}':         None,
            })
        pivoted_data.append(row_dict)

    df_pivoted = pd.DataFrame(pivoted_data)

    # Sort by srno — same as original script
    if 'srno' in df_pivoted.columns:
        df_pivoted = df_pivoted.sort_values(by=['srno'])

    # Put first_col as the leftmost column without affecting row order
    if first_col and first_col in df_pivoted.columns:
        other_cols = [c for c in df_pivoted.columns if c != first_col]
        df_pivoted = df_pivoted[[first_col] + other_cols]

    pivot_path = os.path.join(out_dir, "pivoted_data_with_unique_id.xlsx")
    df_pivoted.to_excel(pivot_path, index=False)
    log_fn(f"  ✅ pivoted_data_with_unique_id.xlsx → {len(df_pivoted):,} rows  (sorted by srno, padded to {max_groups} groups)")
    return pivot_path


def split_by_address_count(pivot_path, out_dir, log_fn):
    df = pd.read_excel(pivot_path)
    fa_cols = [col for col in df.columns if col.startswith('final_add_')]
    df['address_count'] = df[fa_cols].notna().sum(axis=1)
    for count in sorted(df['address_count'].unique()):
        group = df[df['address_count'] == count].drop(columns=["address_count"], errors='ignore')
        fname = f"address_count_{count}.xlsx"
        group.to_excel(os.path.join(out_dir, fname), index=False)
        log_fn(f"  ✅ {fname} → {len(group):,} rows")


# ─── UI ────────────────────────────────────────────────────────────────────────

class ExcelTransformerPanelContent(ctk.CTkScrollableFrame):

    COLS_PER_ROW = 3

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=C["border"], **kw)
        self._data_file    = None
        self._barcode_file = None
        self._base_cols    = []
        self._detected_max = 0          # groups found in file
        self._col_vars     = {}         # col -> BooleanVar  (Step 3)
        self._first_col_var = ctk.StringVar(value="prospect_no")
        self._max_grp_var  = ctk.StringVar(value="15")
        self._build()

    # ── Layout ─────────────────────────────────────────────────────────────────
    def _build(self):
        # Output banner
        banner = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(4, 14))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\Excel_Transformer\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"]
        ).pack(anchor="w", padx=14, pady=8)

        # ── Step 1: Data file ──────────────────────────────────────────────────
        self._sec("Step 1 — Select data file")
        fr1 = ctk.CTkFrame(self, fg_color="transparent")
        fr1.pack(fill="x", pady=(0, 4))
        self._data_lbl = ctk.CTkLabel(
            fr1, text="No file selected",
            font=ctk.CTkFont("Segoe UI", 12), text_color=C["muted"], anchor="w")
        self._data_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr1, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_data
        ).pack(side="right")

        # Groups-detected info line (shown after file pick)
        self._file_info = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["blue"],
            anchor="w", wraplength=700, justify="left")
        self._file_info.pack(anchor="w", pady=(2, 10))

        # ── Step 2: Barcode file ───────────────────────────────────────────────
        self._sec("Step 2 — Select barcode file  (barcode.xlsx)")
        fr2 = ctk.CTkFrame(self, fg_color="transparent")
        fr2.pack(fill="x", pady=(0, 4))
        self._barcode_lbl = ctk.CTkLabel(
            fr2, text="No file selected",
            font=ctk.CTkFont("Segoe UI", 12), text_color=C["muted"], anchor="w")
        self._barcode_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr2, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_barcode
        ).pack(side="right")

        # Live barcode check result
        self._barcode_info = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"], anchor="w")
        self._barcode_info.pack(anchor="w", pady=(2, 10))

        # ── Step 3: Column selector ────────────────────────────────────────────
        self._sec("Step 3 — Select columns")
        self._col_hint = ctk.CTkLabel(
            self,
            text="Select a data file to load its columns.  "
                 "All are selected by default — untick any you want to exclude.",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
            anchor="w", wraplength=700, justify="left")
        self._col_hint.pack(anchor="w", pady=(0, 4))

        # Select-all / Clear-all buttons
        sa_row = ctk.CTkFrame(self, fg_color="transparent")
        sa_row.pack(anchor="w", pady=(0, 4))
        for label, val in [("Select all", True), ("Clear all", False)]:
            ctk.CTkButton(
                sa_row, text=label, width=90, height=26,
                fg_color=C["card"], hover_color=C["hover"],
                border_color=C["border"], border_width=1,
                text_color=C["muted"], font=ctk.CTkFont("Segoe UI", 11),
                command=lambda v=val: self._set_all(v)
            ).pack(side="left", padx=(0, 8))

        self._col_grid = ctk.CTkFrame(
            self, fg_color=C["card"], corner_radius=8,
            border_width=1, border_color=C["border"])
        self._col_grid.pack(fill="x", pady=(4, 10))
        ctk.CTkLabel(
            self._col_grid, text="  — no columns loaded yet —",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"]
        ).pack(anchor="w", padx=12, pady=8)

        # ── Step 4: Pivot options ──────────────────────────────────────────────
        self._sec("Step 4 — Pivot options")
        opt_row = ctk.CTkFrame(self, fg_color="transparent")
        opt_row.pack(fill="x", pady=(0, 12))

        # First column
        ctk.CTkLabel(opt_row, text="First column in output:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 8))
        ctk.CTkEntry(
            opt_row, textvariable=self._first_col_var,
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], height=30, width=140
        ).pack(side="left", padx=(0, 30))

        # Max groups
        ctk.CTkLabel(opt_row, text="Max groups per ref_no:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 8))
        ctk.CTkEntry(
            opt_row, textvariable=self._max_grp_var,
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], height=30, width=60
        ).pack(side="left", padx=(0, 8))
        self._grp_det_lbl = ctk.CTkLabel(
            opt_row, text="(default 15)",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"])
        self._grp_det_lbl.pack(side="left")

        # ── Step 5: Pipeline toggles ───────────────────────────────────────────
        self._sec("Step 5 — Pipeline steps to run")
        tog_row = ctk.CTkFrame(self, fg_color="transparent")
        tog_row.pack(fill="x", pady=(0, 12))

        self._do_barcode = ctk.BooleanVar(value=True)
        self._do_pivot   = ctk.BooleanVar(value=True)
        self._do_split   = ctk.BooleanVar(value=True)

        for label, var in [
            ("Insert barcodes",        self._do_barcode),
            ("Pivot & sort",           self._do_pivot),
            ("Split by address count", self._do_split),
        ]:
            ctk.CTkCheckBox(
                tog_row, text=label, variable=var,
                font=ctk.CTkFont("Segoe UI", 12), text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"],
                border_color=C["border"], checkmark_color="#000"
            ).pack(side="left", padx=(0, 24))

        # ── Run ────────────────────────────────────────────────────────────────
        self._sec("Run")
        self._run_btn = ctk.CTkButton(
            self, text="▶  Run Pipeline",
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
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], anchor="w")
        self._stat.pack(fill="x", pady=(0, 10))

        # ── Log ────────────────────────────────────────────────────────────────
        self._sec("Log")
        self._log_box = ctk.CTkTextbox(
            self, height=220, fg_color=C["card"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], font=ctk.CTkFont("Consolas", 11))
        self._log_box.pack(fill="both", expand=True, pady=(0, 16))

    # ── Small helpers ──────────────────────────────────────────────────────────
    def _sec(self, t):
        ctk.CTkLabel(self, text=t.upper(),
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["muted"]).pack(anchor="w", pady=(8, 3))

    def _log(self, msg):
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")

    def _set_stat(self, msg, color=None):
        self._stat.configure(text=msg, text_color=color or C["muted"])

    def _set_all(self, value: bool):
        for var in self._col_vars.values():
            var.set(value)

    # ── Column grid ────────────────────────────────────────────────────────────
    def _rebuild_col_grid(self, cols):
        for w in self._col_grid.winfo_children():
            w.destroy()
        self._col_vars.clear()

        for c in range(self.COLS_PER_ROW):
            self._col_grid.columnconfigure(c, weight=1)

        for idx, col in enumerate(cols):
            var = ctk.BooleanVar(value=True)
            self._col_vars[col] = var
            ctk.CTkCheckBox(
                self._col_grid, text=col, variable=var,
                font=ctk.CTkFont("Segoe UI", 11), text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"],
                border_color=C["border"], checkmark_color="#000"
            ).grid(row=idx // self.COLS_PER_ROW, column=idx % self.COLS_PER_ROW,
                   sticky="w", padx=14, pady=5)

    # ── File pickers ───────────────────────────────────────────────────────────
    def _pick_data(self):
        p = filedialog.askopenfilename(
            title="Select data Excel file",
            filetypes=[("Excel files", "*.xlsx *.xls")])
        if not p:
            return
        self._data_file = p
        self._data_lbl.configure(text=os.path.basename(p), text_color=C["text"])
        self._file_info.configure(text="Reading…", text_color=C["faint"])

        try:
            df       = pd.read_excel(p, nrows=0)
            raw_cols = list(df.columns.str.lower().str.strip())

            # Detect repeating groups
            self._detected_max = detect_groups(raw_cols)

            # Base columns: filter out repeating-group suffixed variants
            base_cols = [c for c in raw_cols if not _GROUP_PREFIX_RE.match(c)]
            self._base_cols = base_cols

            # Show group count info
            if self._detected_max:
                group_names = ', '.join(
                    f"name_1…{self._detected_max}" if k == 'name' else
                    f"final_add_1…{self._detected_max}" if k == 'final_add' else
                    f"{k}_1…{self._detected_max}"
                    for k in ['name', 'final_add', 'sr', 'b', 'p']
                )
                self._file_info.configure(
                    text=f"📊  {self._detected_max} repeating groups detected  "
                         f"— columns: name_1…{self._detected_max},  "
                         f"final_add_1…{self._detected_max},  "
                         f"sr / b / p  (1…{self._detected_max})",
                    text_color=C["blue"])
                # Auto-set max groups to what's in the file
                self._max_grp_var.set(str(self._detected_max))
                self._grp_det_lbl.configure(
                    text=f"(detected {self._detected_max} in file)",
                    text_color=C["faint"])
            else:
                self._file_info.configure(
                    text="⚠️  No repeating-group columns (name_1, final_add_1, …) found.",
                    text_color=C["orange"])

            # Rebuild column checkboxes — all ticked by default
            self._rebuild_col_grid(base_cols)

            # Auto-set first column: prefer prospect_no, then srno, then first col
            for pref in ('prospect_no', 'srno', 'ref_no'):
                if pref in base_cols:
                    self._first_col_var.set(pref)
                    break
            else:
                if base_cols:
                    self._first_col_var.set(base_cols[0])

            # Re-run barcode check if barcode already loaded
            if self._barcode_file:
                self._async_barcode_check()

        except Exception as e:
            self._file_info.configure(
                text=f"Could not read file: {e}", text_color=C["red"])

    def _pick_barcode(self):
        p = filedialog.askopenfilename(
            title="Select barcode Excel file",
            filetypes=[("Excel files", "*.xlsx *.xls")])
        if not p:
            return
        self._barcode_file = p
        self._barcode_lbl.configure(text=os.path.basename(p), text_color=C["text"])

        if self._data_file:
            self._barcode_info.configure(text="Checking barcodes…", text_color=C["faint"])
            self._async_barcode_check()
        else:
            self._barcode_info.configure(
                text="Select a data file first to verify barcode count.",
                text_color=C["faint"])

    def _async_barcode_check(self):
        """Non-blocking barcode pre-flight — updates the info label when done."""
        def _check():
            msgs = []
            try:
                needed, available = check_barcodes(
                    self._data_file, self._barcode_file, msgs.append)
                spare   = available - needed
                summary = (f"✅  {available:,} barcodes available,  "
                           f"{needed:,} needed  ({spare:,} spare)")
                color   = C["green"]
            except ValueError as e:
                summary = f"❌  {e}"
                color   = C["red"]
            except Exception as e:
                summary = f"⚠️  Could not verify barcodes: {e}"
                color   = C["orange"]
            self.after(0, lambda: self._barcode_info.configure(
                text=summary, text_color=color))
        threading.Thread(target=_check, daemon=True).start()

    # ── Run ────────────────────────────────────────────────────────────────────
    def _get_selected_cols(self):
        return [col for col, var in self._col_vars.items() if var.get()]

    def _run(self):
        if not self._data_file:
            messagebox.showwarning("No File", "Please select a data file first.")
            return
        if self._do_barcode.get() and not self._barcode_file:
            messagebox.showwarning("No Barcode File",
                "Please select a barcode file, or uncheck 'Insert barcodes'.")
            return

        selected_cols = self._get_selected_cols()
        if not selected_cols:
            messagebox.showwarning("No Columns",
                "Please tick at least one column in Step 3.")
            return

        try:
            max_groups = int(self._max_grp_var.get())
            if max_groups < 1:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Invalid Value",
                "Max groups must be a positive integer.")
            return

        first_col  = self._first_col_var.get().strip()

        self._run_btn.configure(state="disabled", text="Processing…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(
            target=self._process,
            args=(selected_cols, first_col, max_groups),
            daemon=True
        ).start()

    def _process(self, selected_cols, first_col, max_groups):
        out_dir    = get_output_dir()
        do_barcode = self._do_barcode.get()
        do_pivot   = self._do_pivot.get()
        do_split   = self._do_split.get()

        STEPS = 2 + sum([do_barcode, do_pivot, do_split])
        step  = [0]

        def advance(msg):
            step[0] += 1
            self.after(0, lambda p=step[0] / STEPS: self._prog.set(p))
            self._log(msg)

        try:
            self._log(f"📂 Data file:    {os.path.basename(self._data_file)}")
            if self._barcode_file:
                self._log(f"📂 Barcode file: {os.path.basename(self._barcode_file)}")
            self._log(f"📁 Output:       {out_dir}")
            self._log(f"🔑 Columns:      {', '.join(selected_cols)}")
            self._log(f"🔠 First col:    {first_col or '(none)'}")
            self._log(f"📦 Max groups:   {max_groups}\n")

            # ── Barcode pre-flight ─────────────────────────────────────────────
            if do_barcode:
                self._log("🔍 Pre-flight — checking barcode count…")
                check_barcodes(self._data_file, self._barcode_file, self._log)
                self._log("")

            # ── Step 1 ─────────────────────────────────────────────────────────
            self._log("🔄 Step 1 — Transform initial data…")
            transform_initial_data(self._data_file, out_dir, selected_cols, self._log)
            advance("✔ Transform complete")

            # ── Step 2 ─────────────────────────────────────────────────────────
            self._log("\n🔗 Step 2 — Merge split files…")
            sticker_path = merge_split_files(out_dir, self._log)
            advance("✔ Merge complete")

            # ── Step 3 ─────────────────────────────────────────────────────────
            if do_barcode:
                self._log("\n🏷️  Step 3 — Insert barcodes…")
                insert_barcodes(sticker_path, self._barcode_file, self._log)
                advance("✔ Barcodes inserted")

            # ── Step 4 ─────────────────────────────────────────────────────────
            pivot_path = None
            if do_pivot:
                self._log("\n🔀 Step 4 — Pivot & sort…")
                pivot_path = pivot_and_sort(
                    sticker_path, out_dir, selected_cols, first_col, max_groups, self._log)
                advance("✔ Pivot complete")

            # ── Step 5 ─────────────────────────────────────────────────────────
            if do_split:
                if not pivot_path:
                    pivot_path = os.path.join(out_dir, "pivoted_data_with_unique_id.xlsx")
                    if not os.path.exists(pivot_path):
                        raise FileNotFoundError(
                            "pivoted_data_with_unique_id.xlsx not found. "
                            "Enable 'Pivot & sort' or ensure the file exists.")
                self._log("\n✂️  Step 5 — Split by address count…")
                split_by_address_count(pivot_path, out_dir, self._log)
                advance("✔ Split complete")

            self._log(f"\n🏁 All done!  Output → {out_dir}")
            self.after(0, lambda: self._set_stat(
                "Pipeline complete — all steps done.", C["green"]))
            subprocess.Popen(["explorer", out_dir])

        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Run Pipeline"))


# ─── Embeddable Panel wrapper ──────────────────────────────────────────────────
class ExcelTransformerPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        ExcelTransformerPanelContent(self).pack(
            fill="both", expand=True, padx=16, pady=8)


# ─── Standalone window ─────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Excel Transformer")
        self.geometry("820x800")
        self.configure(fg_color=C["bg"])

        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)

        icon_f = ctk.CTkFrame(inn, width=44, height=44,
                              fg_color=TINT["mid"], corner_radius=10)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🔀",
                     font=ctk.CTkFont("Segoe UI Emoji", 20)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(tx, text="Excel Transformer",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx, text="Transform · Merge · Barcode · Pivot · Split — all in one pipeline",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        ExcelTransformerPanelContent(self).pack(
            fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
