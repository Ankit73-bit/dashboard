"""
Tool: RBL Excel Transformer
Pipeline for RBL-style notice lists (CSV/Excel) prepared with numbered address slots:
  name_1, address_1, name_2, address_2, …

Flow: unpivot person slots → sticker rows → barcodes → pivot → split by address count.

Optional extras per slot (same index): pin_1, mobile_1, state_1, city_1, sr_1, b_1, p_1
(final_add_N is accepted as an alias for address_N).
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

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "RBL_Excel_Transformer")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#0a84ff", "green": "#30d158",
    "red": "#ff375f", "orange": "#ff9f0a", "blue": "#0a84ff",
}
TINT = {"bg": "#001a2e", "mid": "#003050", "bdr": "#004878"}

# Numbered person-slot columns: name_1, address_2, pin_3, …
_SLOT_PREFIXES = (
    "name", "address", "final_add", "state", "city", "pin",
    "mobile", "mobile_no", "sr", "b", "p",
)
_SLOT_COL_RE = re.compile(
    r"^(" + "|".join(_SLOT_PREFIXES) + r")_(\d+)$",
    re.I,
)

GROUP_COLS = ["name", "final_add", "sr", "b", "p"]


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def _norm(c):
    return str(c).strip().lower().replace("\n", " ").replace("\r", "")


def _clean(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return ""
    return s


def list_sheets(path):
    """Return sheet names for Excel; CSV → ['(csv)']."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        return ["(csv)"]
    xl = pd.ExcelFile(path)
    names = list(xl.sheet_names)
    xl.close()
    return names


def _normalize_columns(df):
    new_cols = []
    seen = {}
    for c in df.columns:
        base = _norm(c)
        if base in seen:
            seen[base] += 1
            base = f"{base}.{seen[base]}"
        else:
            seen[base] = 0
        new_cols.append(base)
    df = df.copy()
    df.columns = new_cols
    return df


def read_data_file(path, sheet_name=0):
    """Load CSV or Excel sheet; normalize column names to lowercase stripped."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(path, dtype=str)
    else:
        df = pd.read_excel(path, sheet_name=sheet_name, dtype=str)
    return _normalize_columns(df)


def prefer_sheet(sheets, *candidates):
    """Pick a preferred sheet name (case-insensitive), else first."""
    if not sheets:
        return 0
    lower = {str(s).strip().lower(): s for s in sheets}
    for name in candidates:
        key = name.lower()
        if key in lower:
            return lower[key]
    return sheets[0]


def is_person_column(col):
    """True for name_1 / address_2 / pin_3 … (excluded from base column checkboxes)."""
    c = _norm(col)
    if _SLOT_COL_RE.match(c):
        return True
    if c in ("address count", "address_count", "count"):
        return True
    return False


def find_col(columns, *candidates):
    lower = {_norm(c): c for c in columns}
    for name in candidates:
        key = _norm(name)
        if key in lower:
            return lower[key]
    for name in candidates:
        key = _norm(name)
        for lc, orig in lower.items():
            if key in lc:
                return orig
    return None


def detect_max_slot(columns):
    """Highest N found in name_N / address_N / final_add_N."""
    max_n = 0
    for c in columns:
        m = _SLOT_COL_RE.match(_norm(c))
        if m and m.group(1).lower() in ("name", "address", "final_add"):
            max_n = max(max_n, int(m.group(2)))
    return max_n


def detect_person_slots(columns):
    """
    Build person slots from numbered columns:
      name_1 + address_1 (+ pin_1 / mobile_1 / …)
      name_2 + address_2 …
    """
    cols = list(columns)
    lower = {_norm(c): c for c in cols}
    max_n = detect_max_slot(cols)
    slots = []

    for n in range(1, max_n + 1):
        name_col = lower.get(f"name_{n}")
        addr_col = lower.get(f"address_{n}") or lower.get(f"final_add_{n}")
        slots.append({
            "index": n,
            "name": name_col,
            "address": addr_col,
            "state": lower.get(f"state_{n}"),
            "city": lower.get(f"city_{n}"),
            "pin": lower.get(f"pin_{n}") or lower.get(f"p_{n}"),
            "mobile": lower.get(f"mobile_{n}") or lower.get(f"mobile_no_{n}"),
            "sr": lower.get(f"sr_{n}"),
            "b": lower.get(f"b_{n}"),
            "p": lower.get(f"p_{n}") or lower.get(f"pin_{n}"),
        })
    return slots


def build_final_add(row, slot):
    addr = _clean(row[slot["address"]]) if slot.get("address") else ""
    if addr:
        return addr
    parts = []
    for key in ("state", "city", "pin"):
        col = slot.get(key)
        if col:
            v = _clean(row[col])
            if v:
                parts.append(v)
    return ", ".join(parts)


def count_needed_barcodes(df, slots):
    needed = 0
    for _, row in df.iterrows():
        for slot in slots:
            if not slot.get("name"):
                continue
            if _clean(row[slot["name"]]):
                needed += 1
    return needed


def check_barcodes(data_file, barcode_file, log_fn, data_sheet=0, barcode_sheet=0):
    df = read_data_file(data_file, sheet_name=data_sheet)
    slots = detect_person_slots(df.columns)
    needed = count_needed_barcodes(df, slots)

    barcode_df = pd.read_excel(barcode_file, sheet_name=barcode_sheet, usecols=[0])
    available = len(barcode_df)

    log_fn(f"  🔍 Address rows needing a barcode : {needed:,}")
    log_fn(f"  🔍 Barcodes available              : {available:,}")

    if available < needed:
        raise ValueError(
            f"Not enough barcodes — need {needed:,} but only {available:,} available."
        )
    log_fn(f"  ✅ Barcode check passed  ({available - needed:,} spare)")
    return needed, available


def transform_rbl_data(input_file, out_dir, selected_cols, log_fn, sheet_name=0):
    df = read_data_file(input_file, sheet_name=sheet_name)
    slots = detect_person_slots(df.columns)
    log_fn(f"  Person slots detected → {len(slots)}  (name_1 / address_1 …)")
    log_fn(f"  Sheet → {sheet_name}")

    if not slots:
        raise ValueError(
            "No numbered address columns found.\n\n"
            "Prepare columns like: name_1, address_1, name_2, address_2, …"
        )

    # Map selected cols (UI may show original-ish lower names) to df columns
    missing = [c for c in selected_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns in data file: {', '.join(missing)}")

    group_key = find_col(
        df.columns,
        "loan account no", "loan_account_no", "loan no", "ref_no", "cust id", "cust_id",
    )
    sr_col = find_col(df.columns, "sr no", "srno", "sr_no", "s.no", "s no")

    transformed = []
    grouped = {}
    unique_id = 1

    for _, row in df.iterrows():
        row_people = []
        for slot in slots:
            if not slot.get("name"):
                continue
            name = _clean(row[slot["name"]])
            if not name:
                continue
            final_add = build_final_add(row, slot)
            # Prefer per-slot sr/b/p; fall back to row SR NO / pin
            if slot.get("sr"):
                sr_val = _clean(row[slot["sr"]])
            else:
                sr_val = _clean(row[sr_col]) if sr_col else ""
            if slot.get("b"):
                b_val = _clean(row[slot["b"]])
            else:
                b_val = ""
            if slot.get("p"):
                pin_val = _clean(row[slot["p"]])
            elif slot.get("pin"):
                pin_val = _clean(row[slot["pin"]])
            else:
                pin_val = ""
            base_vals = [_clean(row[c]) for c in selected_cols]
            rec = [unique_id] + base_vals + [name, final_add, sr_val, b_val, pin_val]
            row_people.append(rec)
            transformed.append(rec)
            unique_id += 1

        n = len(row_people)
        if n:
            grouped.setdefault(n, []).extend(row_people)

    cols_out = ["Unique_ID"] + selected_cols + GROUP_COLS
    consolidated = pd.DataFrame(transformed, columns=cols_out)

    # Add ref_no helper for pivot (loan account / cust id)
    if group_key and group_key in consolidated.columns:
        consolidated["ref_no"] = consolidated[group_key]

    main_path = os.path.join(out_dir, "main.xlsx")
    consolidated.to_excel(main_path, index=False)
    log_fn(f"  ✅ main.xlsx → {len(consolidated):,} rows")
    if group_key:
        log_fn(f"  Group key → {group_key}")

    for group_count, data in grouped.items():
        fname = f"transformed_data_{group_count}_names.xlsx"
        part = pd.DataFrame(data, columns=cols_out)
        if group_key and group_key in part.columns:
            part["ref_no"] = part[group_key]
        part.to_excel(os.path.join(out_dir, fname), index=False)
        log_fn(f"  ✅ {fname} → {len(part):,} rows")

    if not transformed:
        raise ValueError(
            "No address rows produced — check that name_1 / name_2 … have values."
        )

    return main_path, group_key, sr_col


def merge_split_files(out_dir, log_fn):
    split_files = glob.glob(os.path.join(out_dir, "transformed_data_*_names.xlsx"))
    if not split_files:
        # Fall back to main.xlsx
        main = os.path.join(out_dir, "main.xlsx")
        if os.path.isfile(main):
            sticker_path = os.path.join(out_dir, "sticker.xlsx")
            pd.read_excel(main).to_excel(sticker_path, index=False)
            log_fn(f"  ✅ sticker.xlsx ← main.xlsx")
            return sticker_path
        raise FileNotFoundError("No transformed_data_*_names.xlsx files found to merge.")
    merged_df = pd.concat([pd.read_excel(f) for f in split_files], ignore_index=True)
    sticker_path = os.path.join(out_dir, "sticker.xlsx")
    merged_df.to_excel(sticker_path, index=False)
    log_fn(f"  ✅ sticker.xlsx → {len(merged_df):,} rows from {len(split_files)} file(s)")
    return sticker_path


def insert_barcodes(sticker_path, barcode_file, log_fn, barcode_sheet=0):
    sticker_df = pd.read_excel(sticker_path)
    barcode_df = pd.read_excel(barcode_file, sheet_name=barcode_sheet, usecols=[0])
    barcode_df = barcode_df.rename(columns={barcode_df.columns[0]: "barcode"})

    if len(barcode_df) < len(sticker_df):
        raise ValueError(
            f"Not enough barcodes — have {len(barcode_df):,}, need {len(sticker_df):,}."
        )

    # Prefer column 'b'; create if missing
    sticker_df["b"] = barcode_df["barcode"].values[: len(sticker_df)]
    sticker_df.to_excel(sticker_path, index=False)
    log_fn(f"  ✅ Barcodes inserted ({len(sticker_df):,} rows)")


def pivot_and_sort(sticker_path, out_dir, selected_cols, first_col, max_groups, log_fn):
    df = pd.read_excel(sticker_path)
    df.columns = [_norm(c) for c in df.columns]

    group_col = "ref_no"
    if group_col not in df.columns:
        group_col = find_col(
            df.columns,
            "loan account no", "loan_account_no", "loan no", "cust id", "unique_id",
        )
    if not group_col:
        raise ValueError("No group column for pivot (need loan account no / ref_no).")

    fixed_header = ["unique_id"] + [c for c in selected_cols if c != "unique_id"]
    # keep ref_no in fixed if present
    if "ref_no" in df.columns and "ref_no" not in fixed_header:
        fixed_header = ["unique_id", "ref_no"] + [
            c for c in fixed_header if c not in ("unique_id", "ref_no")
        ]

    pivoted_data = []
    for _, group in df.groupby(group_col, sort=False):
        row_dict = {col: group[col].iloc[0] for col in fixed_header if col in group.columns}
        for i, row in enumerate(group.itertuples(index=False), start=1):
            row_dict.update({
                f"name_{i}": getattr(row, "name", None),
                f"final_add_{i}": getattr(row, "final_add", None),
                f"sr_{i}": getattr(row, "sr", None),
                f"b_{i}": getattr(row, "b", None),
                f"p_{i}": getattr(row, "p", None),
            })
        for i in range(len(group) + 1, max_groups + 1):
            row_dict.update({
                f"name_{i}": None,
                f"final_add_{i}": None,
                f"sr_{i}": None,
                f"b_{i}": None,
                f"p_{i}": None,
            })
        pivoted_data.append(row_dict)

    df_pivoted = pd.DataFrame(pivoted_data)

    # Sort by sr no if present
    sort_col = find_col(df_pivoted.columns, "sr no", "srno", "sr_no")
    if sort_col:
        try:
            df_pivoted["_sort"] = pd.to_numeric(df_pivoted[sort_col], errors="coerce")
            df_pivoted = df_pivoted.sort_values(by=["_sort"]).drop(columns=["_sort"])
        except Exception:
            df_pivoted = df_pivoted.sort_values(by=[sort_col])

    first_col = _norm(first_col) if first_col else ""
    if first_col and first_col in df_pivoted.columns:
        other = [c for c in df_pivoted.columns if c != first_col]
        df_pivoted = df_pivoted[[first_col] + other]

    pivot_path = os.path.join(out_dir, "pivoted_data_with_unique_id.xlsx")
    df_pivoted.to_excel(pivot_path, index=False)
    log_fn(
        f"  ✅ pivoted_data_with_unique_id.xlsx → {len(df_pivoted):,} rows  "
        f"(grouped by {group_col}, padded to {max_groups} address slots)"
    )
    return pivot_path


def split_by_address_count(pivot_path, out_dir, log_fn):
    df = pd.read_excel(pivot_path)
    fa_cols = [col for col in df.columns if str(col).startswith("final_add_")]
    if not fa_cols:
        fa_cols = [col for col in df.columns if str(col).startswith("name_")]
    df["address_count"] = df[fa_cols].notna().sum(axis=1)
    for count in sorted(df["address_count"].unique()):
        group = df[df["address_count"] == count].drop(columns=["address_count"], errors="ignore")
        fname = f"address_count_{count}.xlsx"
        group.to_excel(os.path.join(out_dir, fname), index=False)
        log_fn(f"  ✅ {fname} → {len(group):,} rows")


# ─── UI ────────────────────────────────────────────────────────────────────────

class RBLExcelTransformerPanel(ctk.CTkScrollableFrame):
    COLS_PER_ROW = 3

    def __init__(self, parent, **kw):
        super().__init__(
            parent, fg_color="transparent",
            scrollbar_button_color=C["border"], **kw,
        )
        self._data_file = None
        self._barcode_file = None
        self._data_sheet = 0
        self._barcode_sheet = 0
        self._base_cols = []
        self._detected_slots = 0
        self._col_vars = {}
        self._first_col_var = ctk.StringVar(value="loan account no")
        self._max_grp_var = ctk.StringVar(value="2")
        self._build()

    def _build(self):
        banner = ctk.CTkFrame(
            self, fg_color=TINT["bg"], corner_radius=10,
            border_width=1, border_color=C["accent"],
        )
        banner.pack(fill="x", pady=(4, 14))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\RBL_Excel_Transformer\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"],
        ).pack(anchor="w", padx=14, pady=8)

        self._sec("Step 1 — Select data file (name_1 / address_1 …)")
        fr1 = ctk.CTkFrame(self, fg_color="transparent")
        fr1.pack(fill="x", pady=(0, 4))
        self._data_lbl = ctk.CTkLabel(
            fr1, text="No file selected",
            font=ctk.CTkFont("Segoe UI", 12), text_color=C["muted"], anchor="w",
        )
        self._data_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr1, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_data,
        ).pack(side="right")

        sheet1 = ctk.CTkFrame(self, fg_color="transparent")
        sheet1.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            sheet1, text="Data sheet",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], width=90,
        ).pack(side="left")
        self._data_sheet_cb = ctk.CTkComboBox(
            sheet1, values=["(load file first)"], state="readonly",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["hover"], border_color=C["border"],
            button_color=TINT["mid"], button_hover_color=TINT["bdr"],
            dropdown_fg_color=C["card"], dropdown_hover_color=C["hover"],
            dropdown_text_color=C["text"], text_color=C["text"], height=30,
            command=self._on_data_sheet_change,
        )
        self._data_sheet_cb.set("(load file first)")
        self._data_sheet_cb.pack(side="left", fill="x", expand=True)

        self._file_info = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["blue"],
            anchor="w", wraplength=700, justify="left",
        )
        self._file_info.pack(anchor="w", pady=(2, 10))

        self._sec("Step 2 — Select barcode file / sheet")
        fr2 = ctk.CTkFrame(self, fg_color="transparent")
        fr2.pack(fill="x", pady=(0, 4))
        self._barcode_lbl = ctk.CTkLabel(
            fr2, text="No file selected",
            font=ctk.CTkFont("Segoe UI", 12), text_color=C["muted"], anchor="w",
        )
        self._barcode_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr2, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_barcode,
        ).pack(side="right")

        sheet2 = ctk.CTkFrame(self, fg_color="transparent")
        sheet2.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            sheet2, text="Barcode sheet",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], width=90,
        ).pack(side="left")
        self._barcode_sheet_cb = ctk.CTkComboBox(
            sheet2, values=["(load file first)"], state="readonly",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["hover"], border_color=C["border"],
            button_color=TINT["mid"], button_hover_color=TINT["bdr"],
            dropdown_fg_color=C["card"], dropdown_hover_color=C["hover"],
            dropdown_text_color=C["text"], text_color=C["text"], height=30,
            command=self._on_barcode_sheet_change,
        )
        self._barcode_sheet_cb.set("(load file first)")
        self._barcode_sheet_cb.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            self,
            text="Tip: sample_rbl_excel_transformer.xlsx has sheets Data + Barcodes — you can pick the same file twice.",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
            anchor="w", wraplength=700, justify="left",
        ).pack(anchor="w", pady=(0, 6))

        self._barcode_info = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"], anchor="w",
        )
        self._barcode_info.pack(anchor="w", pady=(2, 10))

        self._sec("Step 3 — Select columns to keep")
        ctk.CTkLabel(
            self,
            text="Numbered slots (name_1, address_1, name_2…) are handled automatically. "
                 "Tick the loan / notice columns to carry through.",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
            anchor="w", wraplength=700, justify="left",
        ).pack(anchor="w", pady=(0, 4))

        sa_row = ctk.CTkFrame(self, fg_color="transparent")
        sa_row.pack(anchor="w", pady=(0, 4))
        for label, val in [("Select all", True), ("Clear all", False)]:
            ctk.CTkButton(
                sa_row, text=label, width=90, height=26,
                fg_color=C["card"], hover_color=C["hover"],
                border_color=C["border"], border_width=1,
                text_color=C["muted"], font=ctk.CTkFont("Segoe UI", 11),
                command=lambda v=val: self._set_all(v),
            ).pack(side="left", padx=(0, 8))

        self._col_grid = ctk.CTkFrame(
            self, fg_color=C["card"], corner_radius=8,
            border_width=1, border_color=C["border"],
        )
        self._col_grid.pack(fill="x", pady=(4, 10))
        ctk.CTkLabel(
            self._col_grid, text="  — no columns loaded yet —",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"],
        ).pack(anchor="w", padx=12, pady=8)

        self._sec("Step 4 — Pivot options")
        opt_row = ctk.CTkFrame(self, fg_color="transparent")
        opt_row.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            opt_row, text="First column in output:",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(side="left", padx=(0, 8))
        ctk.CTkEntry(
            opt_row, textvariable=self._first_col_var,
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], height=30, width=160,
        ).pack(side="left", padx=(0, 30))
        ctk.CTkLabel(
            opt_row, text="Max address slots:",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(side="left", padx=(0, 8))
        ctk.CTkEntry(
            opt_row, textvariable=self._max_grp_var,
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], height=30, width=60,
        ).pack(side="left", padx=(0, 8))
        self._grp_det_lbl = ctk.CTkLabel(
            opt_row, text="(name_1 / address_1 …)",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
        )
        self._grp_det_lbl.pack(side="left")

        self._sec("Step 5 — Pipeline steps to run")
        tog_row = ctk.CTkFrame(self, fg_color="transparent")
        tog_row.pack(fill="x", pady=(0, 12))
        self._do_barcode = ctk.BooleanVar(value=True)
        self._do_pivot = ctk.BooleanVar(value=True)
        self._do_split = ctk.BooleanVar(value=True)
        for label, var in [
            ("Insert barcodes", self._do_barcode),
            ("Pivot & sort", self._do_pivot),
            ("Split by address count", self._do_split),
        ]:
            ctk.CTkCheckBox(
                tog_row, text=label, variable=var,
                font=ctk.CTkFont("Segoe UI", 12), text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"],
                border_color=C["border"], checkmark_color="#000",
            ).pack(side="left", padx=(0, 24))

        self._sec("Run")
        self._run_btn = ctk.CTkButton(
            self, text="▶  Run Pipeline",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["bg"], hover_color=TINT["mid"],
            border_color=C["accent"], border_width=1,
            text_color=C["accent"], height=44,
            command=self._run,
        )
        self._run_btn.pack(fill="x", pady=(0, 10))

        self._prog = ctk.CTkProgressBar(
            self, fg_color=C["card"], progress_color=C["accent"], height=8,
        )
        self._prog.set(0)
        self._prog.pack(fill="x", pady=(0, 4))

        self._stat = ctk.CTkLabel(
            self, text="Ready.",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], anchor="w",
        )
        self._stat.pack(fill="x", pady=(0, 10))

        self._sec("Log")
        self._log_box = ctk.CTkTextbox(
            self, height=220, fg_color=C["card"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], font=ctk.CTkFont("Consolas", 11),
        )
        self._log_box.pack(fill="both", expand=True, pady=(0, 16))

    def _sec(self, t):
        ctk.CTkLabel(
            self, text=t.upper(),
            font=ctk.CTkFont("Segoe UI", 10, "bold"),
            text_color=C["muted"],
        ).pack(anchor="w", pady=(8, 3))

    def _log(self, msg):
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")

    def _set_stat(self, msg, color=None):
        self._stat.configure(text=msg, text_color=color or C["muted"])

    def _set_all(self, value: bool):
        for var in self._col_vars.values():
            var.set(value)

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
                border_color=C["border"], checkmark_color="#000",
            ).grid(
                row=idx // self.COLS_PER_ROW, column=idx % self.COLS_PER_ROW,
                sticky="w", padx=14, pady=5,
            )

    def _pick_data(self):
        p = filedialog.askopenfilename(
            title="Select RBL data file",
            filetypes=[
                ("CSV / Excel", "*.csv *.xlsx *.xls"),
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx *.xls"),
                ("All files", "*.*"),
            ],
        )
        if not p:
            return
        self._data_file = p
        self._data_lbl.configure(text=os.path.basename(p), text_color=C["text"])
        self._file_info.configure(text="Reading…", text_color=C["faint"])
        try:
            sheets = list_sheets(p)
            preferred = prefer_sheet(sheets, "Data", "Sheet1", "data")
            self._data_sheet_cb.configure(values=sheets)
            self._data_sheet_cb.set(preferred if preferred != "(csv)" else sheets[0])
            self._data_sheet = self._data_sheet_cb.get()
            self._load_data_sheet()
        except Exception as e:
            self._file_info.configure(
                text=f"Could not read file: {e}", text_color=C["red"],
            )

    def _on_data_sheet_change(self, value=None):
        if not self._data_file:
            return
        self._data_sheet = value or self._data_sheet_cb.get()
        try:
            self._load_data_sheet()
        except Exception as e:
            self._file_info.configure(
                text=f"Could not read sheet: {e}", text_color=C["red"],
            )

    def _load_data_sheet(self):
        sheet = self._data_sheet_cb.get()
        if sheet == "(csv)":
            sheet = 0
        self._data_sheet = sheet
        df = read_data_file(self._data_file, sheet_name=sheet)
        slots = detect_person_slots(df.columns)
        self._detected_slots = len(slots)
        base_cols = [c for c in df.columns if not is_person_column(c)]
        self._base_cols = base_cols

        self._rebuild_col_grid(base_cols)
        for var in self._col_vars.values():
            var.set(True)

        named = []
        for i, slot in enumerate(slots):
            n = slot.get("name") or "(missing name_N)"
            a = slot.get("address") or "(missing address_N)"
            named.append(f"#{slot.get('index', i + 1)} {n} / {a}")
        if not slots:
            self._file_info.configure(
                text="⚠️  No name_1 / address_1 columns found. "
                     "Rename person columns to name_1, address_1, name_2, address_2, …",
                text_color=C["orange"],
            )
        else:
            self._file_info.configure(
                text=f"📊  Sheet '{sheet}' · {len(df):,} rows · "
                     f"{self._detected_slots} slot(s) (name_N / address_N)\n"
                     + "   " + "  |  ".join(named),
                text_color=C["blue"],
            )
        self._max_grp_var.set(str(max(2, self._detected_slots)))
        self._grp_det_lbl.configure(
            text=f"(detected {self._detected_slots} slot(s))",
            text_color=C["faint"],
        )

        for pref in (
            "loan account no", "sr no", "cust id", "ref_no", "prospect_no",
        ):
            if pref in base_cols:
                self._first_col_var.set(pref)
                break
        else:
            if base_cols:
                self._first_col_var.set(base_cols[0])

        if self._barcode_file:
            self._async_barcode_check()

    def _pick_barcode(self):
        p = filedialog.askopenfilename(
            title="Select barcode Excel file (or same sample workbook)",
            filetypes=[("Excel files", "*.xlsx *.xls")],
        )
        if not p:
            return
        self._barcode_file = p
        self._barcode_lbl.configure(text=os.path.basename(p), text_color=C["text"])
        try:
            sheets = list_sheets(p)
            preferred = prefer_sheet(sheets, "Barcodes", "Barcode", "barcodes", "Sheet2")
            self._barcode_sheet_cb.configure(values=sheets)
            self._barcode_sheet_cb.set(preferred)
            self._barcode_sheet = preferred
        except Exception as e:
            self._barcode_info.configure(
                text=f"Could not read barcode sheets: {e}", text_color=C["red"],
            )
            return

        if self._data_file:
            self._barcode_info.configure(text="Checking barcodes…", text_color=C["faint"])
            self._async_barcode_check()
        else:
            self._barcode_info.configure(
                text="Select a data file first to verify barcode count.",
                text_color=C["faint"],
            )

    def _on_barcode_sheet_change(self, value=None):
        self._barcode_sheet = value or self._barcode_sheet_cb.get()
        if self._data_file and self._barcode_file:
            self._async_barcode_check()

    def _async_barcode_check(self):
        data_sheet = self._data_sheet_cb.get()
        barcode_sheet = self._barcode_sheet_cb.get()
        if data_sheet == "(csv)":
            data_sheet = 0

        def _check():
            try:
                needed, available = check_barcodes(
                    self._data_file, self._barcode_file, lambda *_: None,
                    data_sheet=data_sheet, barcode_sheet=barcode_sheet,
                )
                spare = available - needed
                summary = (
                    f"✅  {available:,} barcodes available,  "
                    f"{needed:,} needed  ({spare:,} spare)"
                )
                color = C["green"]
            except ValueError as e:
                summary = f"❌  {e}"
                color = C["red"]
            except Exception as e:
                summary = f"⚠️  Could not verify barcodes: {e}"
                color = C["orange"]
            self.after(0, lambda: self._barcode_info.configure(
                text=summary, text_color=color,
            ))
        threading.Thread(target=_check, daemon=True).start()

    def _get_selected_cols(self):
        return [col for col, var in self._col_vars.items() if var.get()]

    def _run(self):
        if not self._data_file:
            messagebox.showwarning("No File", "Please select a data file first.")
            return
        if self._do_barcode.get() and not self._barcode_file:
            messagebox.showwarning(
                "No Barcode File",
                "Please select a barcode file, or uncheck 'Insert barcodes'.",
            )
            return
        selected_cols = self._get_selected_cols()
        if not selected_cols:
            messagebox.showwarning("No Columns", "Please tick at least one column in Step 3.")
            return
        try:
            max_groups = int(self._max_grp_var.get())
            if max_groups < 1:
                raise ValueError()
        except ValueError:
            messagebox.showwarning("Invalid Value", "Max address slots must be a positive integer.")
            return

        first_col = self._first_col_var.get().strip()
        self._run_btn.configure(state="disabled", text="Processing…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(
            target=self._process,
            args=(selected_cols, first_col, max_groups),
            daemon=True,
        ).start()

    def _process(self, selected_cols, first_col, max_groups):
        out_dir = get_output_dir()
        do_barcode = self._do_barcode.get()
        do_pivot = self._do_pivot.get()
        do_split = self._do_split.get()
        STEPS = 2 + sum([do_barcode, do_pivot, do_split])
        step = [0]

        def advance(msg):
            step[0] += 1
            self.after(0, lambda p=step[0] / STEPS: self._prog.set(p))
            self._log(msg)

        try:
            data_sheet = self._data_sheet_cb.get()
            if data_sheet == "(csv)":
                data_sheet = 0
            barcode_sheet = self._barcode_sheet_cb.get()

            self._log(f"📂 Data file:    {os.path.basename(self._data_file)}")
            self._log(f"📄 Data sheet:   {data_sheet}")
            if self._barcode_file:
                self._log(f"📂 Barcode file: {os.path.basename(self._barcode_file)}")
                self._log(f"📄 Barcode sheet:{barcode_sheet}")
            self._log(f"📁 Output:       {out_dir}")
            self._log(f"🔑 Columns:      {', '.join(selected_cols)}")
            self._log(f"🔠 First col:    {first_col or '(none)'}")
            self._log(f"📦 Max slots:    {max_groups}\n")

            if do_barcode:
                self._log("🔍 Pre-flight — checking barcode count…")
                check_barcodes(
                    self._data_file, self._barcode_file, self._log,
                    data_sheet=data_sheet, barcode_sheet=barcode_sheet,
                )
                self._log("")

            self._log("🔄 Step 1 — Transform numbered slots (name_1 / address_1 …) → sticker rows…")
            transform_rbl_data(
                self._data_file, out_dir, selected_cols, self._log,
                sheet_name=data_sheet,
            )
            advance("✔ Transform complete")

            self._log("\n🔗 Step 2 — Merge split files…")
            sticker_path = merge_split_files(out_dir, self._log)
            advance("✔ Merge complete")

            if do_barcode:
                self._log("\n🏷️  Step 3 — Insert barcodes…")
                insert_barcodes(
                    sticker_path, self._barcode_file, self._log,
                    barcode_sheet=barcode_sheet,
                )
                advance("✔ Barcodes inserted")

            pivot_path = None
            if do_pivot:
                self._log("\n🔀 Step 4 — Pivot & sort…")
                pivot_path = pivot_and_sort(
                    sticker_path, out_dir, selected_cols, first_col, max_groups, self._log,
                )
                advance("✔ Pivot complete")

            if do_split:
                if not pivot_path:
                    pivot_path = os.path.join(out_dir, "pivoted_data_with_unique_id.xlsx")
                    if not os.path.exists(pivot_path):
                        raise FileNotFoundError(
                            "pivoted_data_with_unique_id.xlsx not found. "
                            "Enable 'Pivot & sort' or ensure the file exists."
                        )
                self._log("\n✂️  Step 5 — Split by address count…")
                split_by_address_count(pivot_path, out_dir, self._log)
                advance("✔ Split complete")

            self._log(f"\n🏁 All done!  Output → {out_dir}")
            self.after(0, lambda: self._set_stat(
                "Pipeline complete — all steps done.", C["green"],
            ))
            subprocess.Popen(["explorer", out_dir])
        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Run Pipeline",
            ))


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("RBL Excel Transformer")
        self.geometry("820x820")
        self.configure(fg_color=C["bg"])

        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)

        icon_f = ctk.CTkFrame(inn, width=44, height=44, fg_color=TINT["mid"], corner_radius=10)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(
            icon_f, text="🏦", font=ctk.CTkFont("Segoe UI Emoji", 20),
        ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(
            tx, text="RBL Excel Transformer",
            font=ctk.CTkFont("Segoe UI", 17, "bold"), text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            tx,
            text="RBL Excel with name_1 / address_1 … → Transform · Barcode · Pivot · Split",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(anchor="w")

        RBLExcelTransformerPanel(self).pack(fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
