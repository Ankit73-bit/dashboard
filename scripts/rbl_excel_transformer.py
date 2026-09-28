"""
Tool: RBL Excel Transformer
Pipeline for RBL-style notice lists (CSV/Excel) prepared with numbered address slots:
  name_1, address_1, name_2, address_2, …

Flow:
  [optional] link-loan expand (groupby CUST_ID, suffix only selected cols)
  → unpivot person slots → sticker rows → barcodes → pivot → split by address count.

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
    "mobile", "mobile_no", "sr", "b", "p", "count", "details", "barcode",
)
_SLOT_COL_RE = re.compile(
    r"^(" + "|".join(_SLOT_PREFIXES) + r")_(\d+)$",
    re.I,
)

# Long-form sticker columns (order matches sample pivoted layout intent)
GROUP_COLS = [
    "details", "name", "final_add", "state", "city", "mobile",
    "sr", "barcode", "b", "p", "count",
]

BARCODE_TYPST = (
    '#text(font: "IDAHC39M Code 39 Barcode", size: 8.5pt, [({code})])'
)

# Columns typically unique per linked loan (pre-ticked when Link-loan option is on)
_LINK_EXPAND_DEFAULTS = {
    "loan_account_no", "loan account no", "dln", "notice_amt", "sanction_amt",
    "product_code", "product_type", "veh reg no", "veh_reg_no", "amt_date",
    "amt_type", "notice_type", "notice_date", "srno", "sr no", "sanction_date",
    "count_1", "count_2",
}

# Amount-like columns pre-ticked for per-customer sum_* when link loans are on
_LINK_SUM_DEFAULTS = {
    "notice_amt", "sanction_amt",
}


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def _norm(c):
    return str(c).strip().lower().replace("\n", " ").replace("\r", "")


def _clean(v):
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    # Excel/pandas often load mobiles (and similar IDs) as float → strip trailing .0
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if isinstance(v, float) and not v.is_integer():
            return str(v).strip()
        try:
            return str(int(v))
        except (ValueError, OverflowError):
            return str(v).strip()
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return ""
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        return s[:-2]
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
            "count": lower.get(f"count_{n}"),
            "details": lower.get(f"details_{n}"),
            "barcode": lower.get(f"barcode_{n}"),
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


def build_details(name, final_add, state, city, mobile, pin=""):
    """
    Match sample_output-style details:
      NAME \\ ADDRESS \\ CITY - STATE - PIN \\ Mobile - MOBILE
    (single backslash separators)
    """
    location = " - ".join(p for p in (city or "", state or "", pin or "") if p)
    parts = [
        f"Name: {name}" if name else "",
        f"Address: {final_add}" if final_add else "",
        location,
        f"Mobile - {mobile}" if mobile else "Mobile - ",
    ]
    return " \\ ".join(parts)


def build_barcode_typst(code):
    """Typst barcode expression used in sample_output barcode_N column."""
    code = _clean(code)
    if not code:
        return ""
    return BARCODE_TYPST.format(code=code)


def detect_link_loan_hint(df):
    """Return (row_count_with_link_in_dln, dln_col_name_or_None)."""
    dln = find_col(df.columns, "dln")
    if not dln:
        return 0, None
    n = int(df[dln].astype(str).str.contains("link", case=False, na=False).sum())
    return n, dln


def _default_expand_col(col):
    c = _norm(col)
    if c in _LINK_EXPAND_DEFAULTS:
        return True
    # amt_date.1 etc. from duplicate headers
    base = c.split(".")[0]
    return base in _LINK_EXPAND_DEFAULTS


def _default_sum_col(col):
    c = _norm(col)
    base = c.split(".")[0]
    return base in _LINK_SUM_DEFAULTS or c in _LINK_SUM_DEFAULTS


def expand_link_loans(df, groupby_col, expand_cols, log_fn, sum_cols=None):
    """
    Collapse multiple rows per groupby_col into one wide row (like separate_main),
    but only suffix expand_cols with _1, _2, … — other columns keep the first
    non-empty value. Optional sum_cols get a sum_{col} total per group.
    Returns (expanded_df, max_links).
    """
    if groupby_col not in df.columns:
        raise ValueError(f"Group-by column '{groupby_col}' not found.")
    expand_cols = [c for c in expand_cols if c in df.columns and c != groupby_col]
    if not expand_cols:
        raise ValueError("Select at least one column to expand with _1, _2, …")
    sum_cols = [c for c in (sum_cols or []) if c in df.columns and c != groupby_col]

    other_cols = [c for c in df.columns if c != groupby_col and c not in expand_cols]
    sizes = df.groupby(groupby_col, sort=False).size()
    max_n = int(sizes.max())
    multi = int((sizes > 1).sum())

    sums_map = {}
    if sum_cols:
        work = df[[groupby_col] + sum_cols].copy()
        for c in sum_cols:
            work[c] = pd.to_numeric(work[c], errors="coerce")
        agg = work.groupby(groupby_col, sort=False)[sum_cols].sum(min_count=1)
        sums_map = {k: v for k, v in agg.to_dict(orient="index").items()}

    rows_out = []
    for key, group in df.groupby(groupby_col, sort=False):
        group = group.reset_index(drop=True)
        out = {groupby_col: key}
        for c in other_cols:
            raw = None
            for v in group[c].tolist():
                if _clean(v):
                    raw = v
                    break
            if raw is None and len(group):
                raw = group[c].iloc[0]
            out[c] = raw
        for i in range(len(group)):
            suffix = i + 1
            for c in expand_cols:
                out[f"{c}_{suffix}"] = group.at[i, c]
        for i in range(len(group) + 1, max_n + 1):
            for c in expand_cols:
                out[f"{c}_{i}"] = None
        if sum_cols:
            totals = sums_map.get(key, {})
            for c in sum_cols:
                val = totals.get(c)
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    out[f"sum_{c}"] = None
                else:
                    # keep int when whole number
                    try:
                        fv = float(val)
                        out[f"sum_{c}"] = int(fv) if fv.is_integer() else fv
                    except (TypeError, ValueError):
                        out[f"sum_{c}"] = val
        rows_out.append(out)

    result = pd.DataFrame(rows_out)
    ordered = [groupby_col] + other_cols
    for c in expand_cols:
        for i in range(1, max_n + 1):
            ordered.append(f"{c}_{i}")
    for c in sum_cols:
        ordered.append(f"sum_{c}")
    result = result.reindex(columns=[c for c in ordered if c in result.columns])

    # Avoid Excel float display like 119423.0 for whole-number sums
    for c in sum_cols:
        sc = f"sum_{c}"
        if sc not in result.columns:
            continue
        cleaned = []
        for v in result[sc].tolist():
            if v is None or (isinstance(v, float) and pd.isna(v)):
                cleaned.append(None)
            else:
                try:
                    fv = float(v)
                    cleaned.append(int(fv) if fv.is_integer() else fv)
                except (TypeError, ValueError):
                    cleaned.append(v)
        result[sc] = cleaned

    log_fn(f"  Link-loan expand: {len(df):,} rows -> {len(result):,} rows")
    log_fn(
        f"  Group-by: {groupby_col}  |  customers with >1 loan: {multi:,}  "
        f"|  max links: {max_n}"
    )
    log_fn(f"  Expanded cols (_1.._{max_n}): {', '.join(expand_cols)}")
    if sum_cols:
        log_fn(f"  Sum cols (sum_*): {', '.join(sum_cols)}")
    return result, max_n


def remap_selected_after_expand(selected_cols, expand_cols, max_n, sum_cols=None):
    """Map kept columns: expanded ones become col_1 … col_N; append sum_* cols."""
    expand_set = set(expand_cols)
    out = []
    for c in selected_cols:
        if c in expand_set:
            for i in range(1, max_n + 1):
                out.append(f"{c}_{i}")
        else:
            out.append(c)
    for c in (sum_cols or []):
        sc = f"sum_{c}"
        if sc not in out:
            out.append(sc)
    return out


def count_needed_barcodes(df, slots, only_indices=None):
    """
    Count address rows that need a barcode.
    only_indices: optional set/list of slot indexes to include (e.g. {1} for
    link-loan mode where only name_1 / address_1 get barcodes).
    """
    needed = 0
    for _, row in df.iterrows():
        for slot in slots:
            if not slot.get("name"):
                continue
            if only_indices is not None and slot.get("index") not in only_indices:
                continue
            if _clean(row[slot["name"]]):
                needed += 1
    return needed


def check_barcodes(
    data_file, barcode_file, log_fn, data_sheet=0, barcode_sheet=0,
    barcode_only_first_slot=False, link_groupby=None,
):
    df = read_data_file(data_file, sheet_name=data_sheet)
    # When link-loan expand already applied OR we pass groupby on raw data,
    # count one customer row for barcode planning.
    if link_groupby and link_groupby in df.columns:
        df = df.groupby(link_groupby, sort=False).first().reset_index()
        log_fn(f"  🔍 Link-loan barcode count uses group-by '{link_groupby}' (1 row / customer)")

    slots = detect_person_slots(df.columns)
    only = {1} if barcode_only_first_slot else None
    if barcode_only_first_slot:
        log_fn("  🔍 Link-loan mode: barcodes only for slot _1 (name_1 / address_1)")
    needed = count_needed_barcodes(df, slots, only_indices=only)

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


def transform_rbl_data(
    input_file, out_dir, selected_cols, log_fn, sheet_name=0,
    barcode_only_first_slot=False,
):
    df = read_data_file(input_file, sheet_name=sheet_name)
    slots = detect_person_slots(df.columns)
    log_fn(f"  Person slots detected → {len(slots)}  (name_1 / address_1 …)")
    log_fn(f"  Sheet → {sheet_name}")
    if barcode_only_first_slot:
        log_fn("  Barcode flag → only slot _1 will receive a barcode (link-loan mode)")

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
    sr_col = find_col(df.columns, "sr no", "srno", "sr_no", "s.no", "s no", "SrNo")

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
            state_val = _clean(row[slot["state"]]) if slot.get("state") else ""
            city_val = _clean(row[slot["city"]]) if slot.get("city") else ""
            mobile_val = _clean(row[slot["mobile"]]) if slot.get("mobile") else ""
            count_val = _clean(row[slot["count"]]) if slot.get("count") else ""
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

            slot_index = slot.get("index", 1)
            needs_barcode = (not barcode_only_first_slot) or (slot_index == 1)

            # details_ / barcode_ — generated (or pass through if already in input)
            if slot.get("details") and _clean(row[slot["details"]]):
                details_val = _clean(row[slot["details"]])
            else:
                details_val = build_details(
                    name, final_add, state_val, city_val, mobile_val, pin_val,
                )
            if needs_barcode and slot.get("barcode") and _clean(row[slot["barcode"]]):
                barcode_val = _clean(row[slot["barcode"]])
            elif needs_barcode:
                barcode_val = build_barcode_typst(b_val)
            else:
                # Link-loan: slots _2, _3… keep address data but no barcode
                barcode_val = ""
                b_val = ""

            base_vals = [_clean(row[c]) for c in selected_cols]
            rec = (
                [unique_id]
                + base_vals
                + [
                    details_val, name, final_add, state_val, city_val, mobile_val,
                    sr_val, barcode_val, b_val, pin_val, count_val,
                    1 if needs_barcode else 0,
                ]
            )
            row_people.append(rec)
            transformed.append(rec)
            unique_id += 1

        n = len(row_people)
        if n:
            grouped.setdefault(n, []).extend(row_people)

    cols_out = ["Unique_ID"] + selected_cols + GROUP_COLS + ["needs_barcode"]
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
    barcode_df = barcode_df.rename(columns={barcode_df.columns[0]: "barcode_raw"})

    # Link-loan mode: only rows flagged needs_barcode==1 consume a code
    needs_col = None
    for c in sticker_df.columns:
        if _norm(c) == "needs_barcode":
            needs_col = c
            break
    if needs_col is not None:
        mask = sticker_df[needs_col].apply(
            lambda v: str(v).strip().lower() in ("1", "1.0", "true", "yes")
        )
    else:
        mask = pd.Series([True] * len(sticker_df), index=sticker_df.index)

    n_needed = int(mask.sum())
    if len(barcode_df) < n_needed:
        raise ValueError(
            f"Not enough barcodes — have {len(barcode_df):,}, need {n_needed:,}."
        )

    codes = [_clean(v) for v in barcode_df["barcode_raw"].tolist()]
    code_iter = iter(codes)
    b_vals = []
    barcode_vals = []
    for flag in mask.tolist():
        if flag:
            c = next(code_iter)
            b_vals.append(c)
            barcode_vals.append(build_barcode_typst(c))
        else:
            b_vals.append("")
            barcode_vals.append("")

    sticker_df["b"] = b_vals
    sticker_df["barcode"] = barcode_vals
    # Refresh details in case address fields changed (usually already set)
    if "details" in sticker_df.columns:
        sticker_df["details"] = [
            build_details(
                _clean(r.get("name", "")),
                _clean(r.get("final_add", "")),
                _clean(r.get("state", "")),
                _clean(r.get("city", "")),
                _clean(r.get("mobile", "")),
                _clean(r.get("p", "")),
            )
            for _, r in sticker_df.iterrows()
        ]
    if needs_col is not None:
        sticker_df = sticker_df.drop(columns=[needs_col])
    sticker_df.to_excel(sticker_path, index=False)
    skipped = len(sticker_df) - n_needed
    if skipped:
        log_fn(
            f"  ✅ Barcodes inserted on {n_needed:,} of {len(sticker_df):,} rows "
            f"(skipped {skipped:,} non-_1 slots) — b + barcode Typst"
        )
    else:
        log_fn(f"  ✅ Barcodes inserted ({len(sticker_df):,} rows) — b + barcode Typst")


def pivot_and_sort(sticker_path, out_dir, selected_cols, first_col, max_groups, log_fn):
    df = pd.read_excel(sticker_path)
    df.columns = [_norm(c) for c in df.columns]
    # Internal flag from transform — never pivot into output
    df = df.drop(columns=["needs_barcode"], errors="ignore")

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
                f"details_{i}": _clean(getattr(row, "details", None)) or None,
                f"name_{i}": _clean(getattr(row, "name", None)) or None,
                f"final_add_{i}": _clean(getattr(row, "final_add", None)) or None,
                f"state_{i}": _clean(getattr(row, "state", None)) or None,
                f"city_{i}": _clean(getattr(row, "city", None)) or None,
                f"mobile_{i}": _clean(getattr(row, "mobile", None)) or None,
                f"sr_{i}": _clean(getattr(row, "sr", None)) or None,
                f"barcode_{i}": _clean(getattr(row, "barcode", None)) or None,
                f"b_{i}": _clean(getattr(row, "b", None)) or None,
                f"p_{i}": _clean(getattr(row, "p", None)) or None,
                f"count_{i}": _clean(getattr(row, "count", None)) or None,
            })
        for i in range(len(group) + 1, max_groups + 1):
            row_dict.update({
                f"details_{i}": None,
                f"name_{i}": None,
                f"final_add_{i}": None,
                f"state_{i}": None,
                f"city_{i}": None,
                f"mobile_{i}": None,
                f"sr_{i}": None,
                f"barcode_{i}": None,
                f"b_{i}": None,
                f"p_{i}": None,
                f"count_{i}": None,
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
        self._all_cols = []
        self._detected_slots = 0
        self._col_vars = {}
        self._link_expand_vars = {}
        self._link_sum_vars = {}
        self._do_link_loan = ctk.BooleanVar(value=False)
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

        self._sec("Optional — Link loans (DLN)")
        ctk.CTkLabel(
            self,
            text="If DLN has link loans (same CUST_ID, multiple loan rows), enable this to "
                 "collapse them like Excel CUID Separator — but only the columns you tick "
                 "get _1, _2, … suffixes. Leave unchecked when there are no link loans. "
                 "When enabled, barcodes are assigned only to slot _1 (not _2, _3, …).",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
            anchor="w", wraplength=700, justify="left",
        ).pack(anchor="w", pady=(0, 4))

        link_tog = ctk.CTkFrame(self, fg_color="transparent")
        link_tog.pack(fill="x", pady=(0, 4))
        ctk.CTkCheckBox(
            link_tog, text="Data has link loans",
            variable=self._do_link_loan,
            font=ctk.CTkFont("Segoe UI", 12), text_color=C["text"],
            fg_color=C["accent"], hover_color=TINT["bdr"],
            border_color=C["border"], checkmark_color="#000",
            command=self._toggle_link_loan_ui,
        ).pack(side="left")
        self._link_info_lbl = ctk.CTkLabel(
            link_tog, text="",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"],
        )
        self._link_info_lbl.pack(side="left", padx=(16, 0))

        self._link_opts = ctk.CTkFrame(
            self, fg_color=C["card"], corner_radius=8,
            border_width=1, border_color=C["border"],
        )
        self._link_opts.pack(fill="x", pady=(4, 10))

        gb_row = ctk.CTkFrame(self._link_opts, fg_color="transparent")
        gb_row.pack(fill="x", padx=12, pady=(10, 6))
        ctk.CTkLabel(
            gb_row, text="Group by:",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], width=80,
        ).pack(side="left")
        self._link_groupby_cb = ctk.CTkComboBox(
            gb_row, values=["(load file first)"], state="readonly",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["hover"], border_color=C["border"],
            button_color=TINT["mid"], button_hover_color=TINT["bdr"],
            dropdown_fg_color=C["card"], dropdown_hover_color=C["hover"],
            dropdown_text_color=C["text"], text_color=C["text"], height=30,
            width=220,
            command=self._on_link_groupby_change,
        )
        self._link_groupby_cb.set("(load file first)")
        self._link_groupby_cb.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            self._link_opts,
            text="Columns to expand (_1, _2, …) — others keep first value only:",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(0, 4))

        link_sa = ctk.CTkFrame(self._link_opts, fg_color="transparent")
        link_sa.pack(anchor="w", padx=12, pady=(0, 4))
        for label, val in [("Select all", True), ("Clear all", False)]:
            ctk.CTkButton(
                link_sa, text=label, width=90, height=26,
                fg_color=C["hover"], hover_color=C["border"],
                border_color=C["border"], border_width=1,
                text_color=C["muted"], font=ctk.CTkFont("Segoe UI", 11),
                command=lambda v=val: self._set_all_link_expand(v),
            ).pack(side="left", padx=(0, 8))

        self._link_expand_grid = ctk.CTkFrame(self._link_opts, fg_color="transparent")
        self._link_expand_grid.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkLabel(
            self._link_expand_grid, text="  — load a data file first —",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"],
        ).pack(anchor="w", padx=4, pady=4)

        ctk.CTkLabel(
            self._link_opts,
            text="Columns to sum (adds sum_col per customer — optional):",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
            anchor="w",
        ).pack(anchor="w", padx=12, pady=(4, 4))

        link_sum_sa = ctk.CTkFrame(self._link_opts, fg_color="transparent")
        link_sum_sa.pack(anchor="w", padx=12, pady=(0, 4))
        for label, val in [("Select all", True), ("Clear all", False)]:
            ctk.CTkButton(
                link_sum_sa, text=label, width=90, height=26,
                fg_color=C["hover"], hover_color=C["border"],
                border_color=C["border"], border_width=1,
                text_color=C["muted"], font=ctk.CTkFont("Segoe UI", 11),
                command=lambda v=val: self._set_all_link_sum(v),
            ).pack(side="left", padx=(0, 8))

        self._link_sum_grid = ctk.CTkFrame(self._link_opts, fg_color="transparent")
        self._link_sum_grid.pack(fill="x", padx=8, pady=(0, 10))
        ctk.CTkLabel(
            self._link_sum_grid, text="  — load a data file first —",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"],
        ).pack(anchor="w", padx=4, pady=4)

        self._toggle_link_loan_ui()

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

    def _set_all_link_expand(self, value: bool):
        for var in self._link_expand_vars.values():
            var.set(value)

    def _set_all_link_sum(self, value: bool):
        for var in self._link_sum_vars.values():
            var.set(value)

    def _toggle_link_loan_ui(self):
        enabled = bool(self._do_link_loan.get())
        state = "normal" if enabled else "disabled"
        try:
            self._link_groupby_cb.configure(state="readonly" if enabled else "disabled")
        except Exception:
            pass
        for grid in (self._link_expand_grid, self._link_sum_grid):
            for child in grid.winfo_children():
                try:
                    child.configure(state=state)
                except Exception:
                    pass
        self._link_opts.configure(
            border_color=C["accent"] if enabled else C["border"],
        )
        if self._data_file and self._barcode_file:
            self._async_barcode_check()

    def _on_link_groupby_change(self, value=None):
        if self._all_cols:
            self._rebuild_link_expand_grid(self._all_cols)
            self._rebuild_link_sum_grid(self._all_cols)
        if self._data_file and self._barcode_file:
            self._async_barcode_check()

    def _rebuild_link_expand_grid(self, cols):
        for w in self._link_expand_grid.winfo_children():
            w.destroy()
        self._link_expand_vars.clear()
        groupby = self._link_groupby_cb.get()
        expand_candidates = [c for c in cols if c != groupby]
        for c in range(self.COLS_PER_ROW):
            self._link_expand_grid.columnconfigure(c, weight=1)
        if not expand_candidates:
            ctk.CTkLabel(
                self._link_expand_grid, text="  — no columns —",
                font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"],
            ).pack(anchor="w", padx=4, pady=4)
            self._toggle_link_loan_ui()
            return
        for idx, col in enumerate(expand_candidates):
            var = ctk.BooleanVar(value=_default_expand_col(col))
            self._link_expand_vars[col] = var
            cb = ctk.CTkCheckBox(
                self._link_expand_grid, text=col, variable=var,
                font=ctk.CTkFont("Segoe UI", 11), text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"],
                border_color=C["border"], checkmark_color="#000",
            )
            cb.grid(
                row=idx // self.COLS_PER_ROW, column=idx % self.COLS_PER_ROW,
                sticky="w", padx=10, pady=4,
            )
        self._toggle_link_loan_ui()

    def _rebuild_link_sum_grid(self, cols):
        for w in self._link_sum_grid.winfo_children():
            w.destroy()
        self._link_sum_vars.clear()
        groupby = self._link_groupby_cb.get()
        candidates = [c for c in cols if c != groupby]
        for c in range(self.COLS_PER_ROW):
            self._link_sum_grid.columnconfigure(c, weight=1)
        if not candidates:
            ctk.CTkLabel(
                self._link_sum_grid, text="  — no columns —",
                font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"],
            ).pack(anchor="w", padx=4, pady=4)
            self._toggle_link_loan_ui()
            return
        for idx, col in enumerate(candidates):
            var = ctk.BooleanVar(value=_default_sum_col(col))
            self._link_sum_vars[col] = var
            cb = ctk.CTkCheckBox(
                self._link_sum_grid, text=col, variable=var,
                font=ctk.CTkFont("Segoe UI", 11), text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"],
                border_color=C["border"], checkmark_color="#000",
            )
            cb.grid(
                row=idx // self.COLS_PER_ROW, column=idx % self.COLS_PER_ROW,
                sticky="w", padx=10, pady=4,
            )
        self._toggle_link_loan_ui()
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
        self._all_cols = list(df.columns)

        self._rebuild_col_grid(base_cols)
        for var in self._col_vars.values():
            var.set(True)

        # Link-loan group-by + expand columns
        gb_vals = list(df.columns)
        self._link_groupby_cb.configure(values=gb_vals if gb_vals else ["(none)"])
        preferred_gb = find_col(
            df.columns, "cust_id", "cuid", "customer id", "customer_id", "cust id",
        )
        self._link_groupby_cb.set(preferred_gb or (gb_vals[0] if gb_vals else "(none)"))
        self._rebuild_link_expand_grid(self._all_cols)
        self._rebuild_link_sum_grid(self._all_cols)

        link_n, dln_col = detect_link_loan_hint(df)
        if dln_col and link_n:
            self._link_info_lbl.configure(
                text=f"Detected {link_n:,} row(s) with 'Link' in {dln_col}",
                text_color=C["orange"],
            )
        elif dln_col:
            self._link_info_lbl.configure(
                text=f"Column '{dln_col}' found — no 'Link' text detected",
                text_color=C["faint"],
            )
        else:
            self._link_info_lbl.configure(
                text="No DLN column found",
                text_color=C["faint"],
            )

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
        do_link = bool(self._do_link_loan.get())
        link_groupby = self._link_groupby_cb.get() if do_link else None
        if link_groupby in (None, "(load file first)", "(none)"):
            link_groupby = None

        def _check():
            try:
                needed, available = check_barcodes(
                    self._data_file, self._barcode_file, lambda *_: None,
                    data_sheet=data_sheet, barcode_sheet=barcode_sheet,
                    barcode_only_first_slot=do_link,
                    link_groupby=link_groupby if do_link else None,
                )
                spare = available - needed
                suffix = " (link-loan: slot _1 only)" if do_link else ""
                summary = (
                    f"✅  {available:,} barcodes available,  "
                    f"{needed:,} needed  ({spare:,} spare){suffix}"
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

    def _get_link_expand_cols(self):
        return [col for col, var in self._link_expand_vars.items() if var.get()]

    def _get_link_sum_cols(self):
        return [col for col, var in self._link_sum_vars.items() if var.get()]

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
        do_link = bool(self._do_link_loan.get())
        link_groupby = self._link_groupby_cb.get()
        link_expand = self._get_link_expand_cols()
        link_sum = self._get_link_sum_cols()
        if do_link:
            if not link_groupby or link_groupby in ("(load file first)", "(none)"):
                messagebox.showwarning(
                    "Link loans",
                    "Select a group-by column (usually CUST_ID).",
                )
                return
            if not link_expand:
                messagebox.showwarning(
                    "Link loans",
                    "Tick at least one column to expand with _1, _2, …",
                )
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
            args=(
                selected_cols, first_col, max_groups,
                do_link, link_groupby, link_expand, link_sum,
            ),
            daemon=True,
        ).start()

    def _process(
        self, selected_cols, first_col, max_groups,
        do_link, link_groupby, link_expand, link_sum,
    ):
        out_dir = get_output_dir()
        do_barcode = self._do_barcode.get()
        do_pivot = self._do_pivot.get()
        do_split = self._do_split.get()
        STEPS = 2 + sum([do_link, do_barcode, do_pivot, do_split])
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
            self._log(f"📦 Max slots:    {max_groups}")
            if do_link:
                self._log(f"🔗 Link loans:   ON  groupby={link_groupby}")
                self._log(f"   Expand:       {', '.join(link_expand)}")
                self._log(
                    f"   Sum:          {', '.join(link_sum) if link_sum else '(none)'}"
                )
            else:
                self._log("🔗 Link loans:   OFF")
            self._log("")

            data_path = self._data_file
            transform_sheet = data_sheet

            if do_link:
                self._log("🔄 Step 0 — Expand link loans (selected columns only)…")
                df = read_data_file(self._data_file, sheet_name=data_sheet)
                expanded, max_links = expand_link_loans(
                    df, link_groupby, link_expand, self._log, sum_cols=link_sum,
                )
                data_path = os.path.join(out_dir, "00_link_loan_expanded.xlsx")
                expanded.to_excel(data_path, index=False)
                self._log(f"  ✅ Saved {os.path.basename(data_path)}")
                selected_cols = remap_selected_after_expand(
                    selected_cols, link_expand, max_links, sum_cols=link_sum,
                )
                if first_col in link_expand:
                    first_col = f"{first_col}_1"
                self._log(f"  🔑 Columns after expand: {', '.join(selected_cols)}")
                transform_sheet = 0
                advance("✔ Link-loan expand complete")

            if do_barcode:
                self._log("🔍 Pre-flight — checking barcode count…")
                check_barcodes(
                    data_path, self._barcode_file, self._log,
                    data_sheet=transform_sheet, barcode_sheet=barcode_sheet,
                    barcode_only_first_slot=do_link,
                    link_groupby=None,
                )
                self._log("")

            self._log("🔄 Step 1 — Transform numbered slots (name_1 / address_1 …) → sticker rows…")
            transform_rbl_data(
                data_path, out_dir, selected_cols, self._log,
                sheet_name=transform_sheet,
                barcode_only_first_slot=do_link,
            )
            advance("✔ Transform complete")

            self._log("\n🔗 Step 2 — Merge split files…")
            sticker_path = merge_split_files(out_dir, self._log)
            advance("✔ Merge complete")

            if do_barcode:
                self._log("\n🏷️  Step 3 — Insert barcodes…")
                if do_link:
                    self._log("  (Link-loan: barcodes only on slot _1)")
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
            text="RBL Excel with name_1 / address_1 … → [Link loans] · Transform · Barcode · Pivot · Split",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(anchor="w")

        RBLExcelTransformerPanel(self).pack(fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
