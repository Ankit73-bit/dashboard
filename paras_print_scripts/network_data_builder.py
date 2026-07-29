"""
Tool: Network Data Builder
Enrich a PFL / roster Excel with branch Address, Pincode, Champion Name,
and Contact via VLOOKUP against the Network list (match on LEFT 4 of
Location Code). Outputs data.xlsx ready for Grouped Excel.
"""

import os
import re
import threading
import subprocess
from datetime import datetime

import pandas as pd
import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Network_Data_Builder")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "cyan":   "#00f5ff", "green":  "#30d158",
    "red":    "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#062d30", "mid": "#0a4a4e", "bdr": "#0d6b70"}

OUTPUT_COLUMNS = [
    "Sr No",
    "Consignee Name(Champion Name)",
    "product name",
    "Legal Entity",
    "address",
    "pincode",
    "Contact. No.",
    "challan no",
    "Employee Code",
    "ID Count",
    "location code",
]

# Auto-detect candidates for each mapping role
PFL_DEFAULTS = {
    "location": ("Location Code", "location code", "LocationCode"),
    "employee": ("Employee Code", "employee code", "EmployeeCode"),
    "legal":    ("Legal Entity", "legal entity"),
}
NET_DEFAULTS = {
    "location": ("Location Code", "location code", "LocationCode"),
    "address":  ("Address", "address"),
    "name":     ("Branch Champion", "Champion Name", "name"),
    "pincode":  ("Pin code", "Pincode", "Pin Code", "pin code"),
    "contact":  ("Branch Champion Contact", "Champion Contact", "contact"),
}


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def _norm_cols(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _find_col(columns, *candidates):
    """Case-insensitive / partial column finder against a list of column names."""
    lower_map = {str(c).strip().lower(): c for c in columns}
    for name in candidates:
        key = name.strip().lower()
        if key in lower_map:
            return lower_map[key]
    for name in candidates:
        key = name.strip().lower()
        for lc, orig in lower_map.items():
            if key in lc or lc in key:
                return orig
    return None


def _loc_key(value):
    """Excel LEFT(col, 4) equivalent — take first 4 characters of location code."""
    if pd.isna(value):
        return ""
    s = str(value).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return s[:4]


def build_data_xlsx(pfl_path, network_path, log_fn, progress_fn,
                    product_name="ID CARD", challan_no="",
                    pfl_cols=None, net_cols=None):
    """
    pfl_cols: {location, employee, legal}
    net_cols: {location, address, name, pincode, contact}
    """
    pfl_cols = pfl_cols or {}
    net_cols = net_cols or {}

    log_fn(f"📂 PFL / roster : {os.path.basename(pfl_path)}")
    log_fn(f"📂 Network list : {os.path.basename(network_path)}")
    log_fn(f"🏷️  Product name : {product_name or '(blank)'}")
    log_fn(f"🧾 Challan no   : {challan_no or '(blank)'}")
    progress_fn(0.1)

    pfl = _norm_cols(pd.read_excel(pfl_path, dtype=str))
    net = _norm_cols(pd.read_excel(network_path, dtype=str))
    log_fn(f"📊 PFL rows: {len(pfl):,}  |  Network rows: {len(net):,}")
    progress_fn(0.25)

    pfl_loc   = (pfl_cols.get("location") or "").strip()
    pfl_emp   = (pfl_cols.get("employee") or "").strip()
    pfl_legal = (pfl_cols.get("legal") or "").strip()

    net_loc     = (net_cols.get("location") or "").strip()
    net_addr    = (net_cols.get("address") or "").strip()
    net_name    = (net_cols.get("name") or "").strip()
    net_pin     = (net_cols.get("pincode") or "").strip()
    net_contact = (net_cols.get("contact") or "").strip()

    missing = []
    for label, col, df in [
        ("PFL: Location Code", pfl_loc, pfl),
        ("PFL: Employee Code", pfl_emp, pfl),
        ("Network: Location Code (lookup key)", net_loc, net),
        ("Network: Address → address", net_addr, net),
        ("Network: Name → Consignee Name", net_name, net),
        ("Network: Contact → Contact. No.", net_contact, net),
    ]:
        if not col:
            missing.append(f"{label} (not selected)")
        elif col not in df.columns:
            missing.append(f"{label} — '{col}' not in file")

    if pfl_legal and pfl_legal not in pfl.columns:
        missing.append(f"PFL: Legal Entity — '{pfl_legal}' not in file")
    if net_pin and net_pin not in net.columns:
        missing.append(f"Network: Pincode — '{net_pin}' not in file")

    if missing:
        raise ValueError("Column mapping error:\n- " + "\n- ".join(missing))

    log_fn(f"🔑 Match: LEFT({pfl_loc}, 4)  ↔  {net_loc}")
    log_fn(f"📎 Map:  address←{net_addr}  name←{net_name}  "
           f"pincode←{net_pin or '(none)'}  contact←{net_contact}")
    log_fn(f"📎 PFL:  employee←{pfl_emp}  legal←{pfl_legal or '(none)'}")
    progress_fn(0.4)

    pfl = pfl.copy()
    pfl["_loc_key"] = pfl[pfl_loc].map(_loc_key)

    lookup_exact = net.copy()
    lookup_exact["_match"] = lookup_exact[net_loc].astype(str).str.strip()
    lookup_exact["_match"] = lookup_exact["_match"].map(
        lambda v: v.split(".")[0] if re.fullmatch(r"\d+\.0+", str(v).strip()) else str(v).strip()
    )

    cols_keep = {
        "_match": "_match",
        net_addr: "_address",
        net_name: "_name",
        net_contact: "_contact",
    }
    if net_pin:
        cols_keep[net_pin] = "_pincode"

    exact_df = lookup_exact[list(cols_keep.keys())].rename(columns=cols_keep)
    exact_df = exact_df.drop_duplicates(subset=["_match"], keep="first")

    merged = pfl.merge(exact_df, left_on="_loc_key", right_on="_match", how="left")

    matched = merged["_address"].notna().sum()
    unmatched = len(merged) - matched
    log_fn(f"✅ Matched: {matched:,}   ❌ Unmatched: {unmatched:,}")
    progress_fn(0.7)

    out = pd.DataFrame({
        "Sr No": "",
        "Consignee Name(Champion Name)": merged["_name"].fillna(""),
        "product name": product_name,
        "Legal Entity": merged[pfl_legal].fillna("") if pfl_legal else "",
        "address": merged["_address"].fillna(""),
        "pincode": merged["_pincode"].fillna("") if "_pincode" in merged.columns else "",
        "Contact. No.": merged["_contact"].fillna(""),
        "challan no": challan_no,
        "Employee Code": merged[pfl_emp].fillna(""),
        "ID Count": "",
        "location code": merged["_loc_key"],
    })
    out = out[OUTPUT_COLUMNS]

    unmatched_df = merged.loc[
        merged["_address"].isna(),
        [c for c in [pfl_emp, pfl_loc, "_loc_key"] if c]
    ].copy()
    unmatched_df.columns = [
        "Employee Code" if c == pfl_emp else
        "Location Code (original)" if c == pfl_loc else
        "Lookup key (LEFT 4)"
        for c in unmatched_df.columns
    ]

    progress_fn(0.9)
    return out, unmatched_df, matched, unmatched


class NetworkDataBuilderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Network Data Builder")
        self.geometry("780x820")
        self.minsize(720, 700)
        self.configure(fg_color=C["bg"])
        self._pfl_path = None
        self._net_path = None
        self._pfl_columns = []
        self._net_columns = []
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(padx=28, pady=16)

        icon_f = ctk.CTkFrame(inner, width=48, height=48, fg_color=TINT["mid"], corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🗺️", font=ctk.CTkFont("Segoe UI Emoji", 22)).place(
            relx=0.5, rely=0.5, anchor="center")

        txt = ctk.CTkFrame(inner, fg_color="transparent")
        txt.pack(side="left")
        ctk.CTkLabel(txt, text="Network Data Builder",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(txt, text="VLOOKUP branch address · name · pincode · contact → data.xlsx",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                      scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        banner = ctk.CTkFrame(body, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["cyan"])
        banner.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\Network_Data_Builder\\<timestamp>\\data.xlsx",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["cyan"]
        ).pack(anchor="w", padx=14, pady=8)

        # ── Step 1: PFL ──
        self._section(body, "Step 1 — PFL / Roster Excel")
        fr1 = ctk.CTkFrame(body, fg_color="transparent")
        fr1.pack(fill="x", pady=(0, 6))
        self._pfl_lbl = ctk.CTkLabel(
            fr1, text="No file selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._pfl_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr1, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_pfl
        ).pack(side="right")

        self._pfl_map = self._mapping_card(
            body,
            title="PFL column mapping",
            rows=[
                ("location", "Location Code", "→ location code (LEFT 4)"),
                ("employee", "Employee Code", "→ Employee Code"),
                ("legal",    "Legal Entity",  "→ Legal Entity  (optional)"),
            ],
        )

        # ── Step 2: Network ──
        self._section(body, "Step 2 — Network List Excel (lookup)")
        fr2 = ctk.CTkFrame(body, fg_color="transparent")
        fr2.pack(fill="x", pady=(0, 6))
        self._net_lbl = ctk.CTkLabel(
            fr2, text="No file selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._net_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr2, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick_net
        ).pack(side="right")

        self._net_map = self._mapping_card(
            body,
            title="Network lookup & mapping",
            rows=[
                ("location", "Lookup key",  "Location Code  (match key)"),
                ("address",  "Address",     "→ address"),
                ("name",     "Name",        "→ Consignee Name (Champion)"),
                ("pincode",  "Pincode",     "→ pincode  (optional)"),
                ("contact",  "Contact",     "→ Contact. No."),
            ],
        )

        # ── Step 3: Fill fields ──
        self._section(body, "Step 3 — Fill fields")
        fields = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                              border_width=1, border_color=C["border"])
        fields.pack(fill="x", pady=(0, 12))
        fields.columnconfigure(1, weight=1)

        ctk.CTkLabel(fields, text="Product name",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"], anchor="w", width=110
                     ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")
        self._product_e = ctk.CTkEntry(
            fields, font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["hover"], border_color=C["border"],
            text_color=C["text"], height=36)
        self._product_e.grid(row=0, column=1, padx=16, pady=(14, 6), sticky="ew")
        self._product_e.insert(0, "ID CARD")

        ctk.CTkLabel(fields, text="Challan no",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"], anchor="w", width=110
                     ).grid(row=1, column=0, padx=16, pady=(6, 14), sticky="w")
        self._challan_e = ctk.CTkEntry(
            fields, placeholder_text="e.g. CH-001",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["hover"], border_color=C["border"],
            text_color=C["text"], height=36)
        self._challan_e.grid(row=1, column=1, padx=16, pady=(6, 14), sticky="ew")

        tip = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=10,
                           border_width=1, border_color=C["border"])
        tip.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            tip,
            text=("Columns auto-detect when you browse a file — change any dropdown if needed.\n"
                  "Then review data.xlsx → leave Sr No & ID Count empty → run Grouped Excel."),
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], justify="left", anchor="w"
        ).pack(anchor="w", padx=14, pady=10)

        self._section(body, "Progress")
        self._prog = ctk.CTkProgressBar(body, height=8, fg_color=C["card"],
                                        progress_color=C["cyan"])
        self._prog.pack(fill="x", pady=(4, 8))
        self._prog.set(0)

        self._stat = ctk.CTkLabel(body, text="Ready.",
                                  font=ctk.CTkFont("Segoe UI", 11),
                                  text_color=C["muted"], anchor="w")
        self._stat.pack(fill="x", pady=(0, 8))

        self._log = ctk.CTkTextbox(body, height=140,
                                   font=ctk.CTkFont("Courier New", 11),
                                   fg_color=C["card"],
                                   border_color=C["border"], border_width=1,
                                   text_color=C["muted"], state="disabled")
        self._log.pack(fill="x", pady=(0, 16))

        self._run_btn = ctk.CTkButton(
            body, text="▶  Build data.xlsx",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["cyan"],
            border_color=C["cyan"], border_width=1,
            corner_radius=24, height=48,
            command=self._start)
        self._run_btn.pack(fill="x", pady=(0, 20))

    def _mapping_card(self, parent, title, rows):
        """Build a card of label + combobox rows. Returns dict of role → CTkComboBox."""
        card = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12,
                            border_width=1, border_color=C["border"])
        card.pack(fill="x", pady=(0, 12))
        card.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            card, text=title,
            font=ctk.CTkFont("Segoe UI", 11, "bold"),
            text_color=C["cyan"], anchor="w"
        ).grid(row=0, column=0, columnspan=3, padx=16, pady=(12, 6), sticky="w")

        combos = {}
        for i, (role, label, hint) in enumerate(rows, start=1):
            ctk.CTkLabel(
                card, text=label,
                font=ctk.CTkFont("Segoe UI", 11),
                text_color=C["muted"], anchor="w", width=120
            ).grid(row=i, column=0, padx=16, pady=4, sticky="w")

            combo = ctk.CTkComboBox(
                card, values=["(select file first)"],
                state="readonly",
                font=ctk.CTkFont("Segoe UI", 12),
                fg_color=C["hover"], border_color=C["border"],
                button_color=TINT["mid"], button_hover_color=TINT["bdr"],
                dropdown_fg_color=C["card"], dropdown_hover_color=C["hover"],
                dropdown_text_color=C["text"],
                text_color=C["text"], height=32, width=220)
            combo.set("(select file first)")
            combo.grid(row=i, column=1, padx=(0, 8), pady=4, sticky="ew")

            ctk.CTkLabel(
                card, text=hint,
                font=ctk.CTkFont("Segoe UI", 10),
                text_color=C["faint"], anchor="w"
            ).grid(row=i, column=2, padx=(0, 16), pady=4, sticky="w")

            combos[role] = combo

        # bottom padding
        ctk.CTkFrame(card, height=8, fg_color="transparent").grid(
            row=len(rows) + 1, column=0)

        return combos

    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w").pack(fill="x", pady=(14, 2))

    def _write_log(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_combos(self, combos, columns, defaults):
        values = list(columns) if columns else ["(no columns)"]
        # Allow blank for optional fields
        values_with_blank = ["(none)"] + values
        for role, combo in combos.items():
            optional = role in ("legal", "pincode")
            opts = values_with_blank if optional else values
            combo.configure(values=opts)
            detected = _find_col(columns, *defaults.get(role, ())) if columns else None
            if detected:
                combo.set(detected)
            elif optional:
                combo.set("(none)")
            elif columns:
                combo.set(columns[0])
            else:
                combo.set("(select file first)")

    def _pick_pfl(self):
        path = filedialog.askopenfilename(
            title="Select PFL / roster Excel",
            filetypes=[("Excel files", "*.xlsx *.xls")])
        if not path:
            return
        try:
            df = _norm_cols(pd.read_excel(path, nrows=0))
            self._pfl_columns = list(df.columns)
            self._pfl_path = path
            self._pfl_lbl.configure(
                text=f"{os.path.basename(path)}  ({len(self._pfl_columns)} cols)",
                text_color=C["cyan"])
            self._set_combos(self._pfl_map, self._pfl_columns, PFL_DEFAULTS)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read columns:\n{e}")

    def _pick_net(self):
        path = filedialog.askopenfilename(
            title="Select Network List Excel",
            filetypes=[("Excel files", "*.xlsx *.xls")])
        if not path:
            return
        try:
            df = _norm_cols(pd.read_excel(path, nrows=0))
            self._net_columns = list(df.columns)
            self._net_path = path
            self._net_lbl.configure(
                text=f"{os.path.basename(path)}  ({len(self._net_columns)} cols)",
                text_color=C["cyan"])
            self._set_combos(self._net_map, self._net_columns, NET_DEFAULTS)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read columns:\n{e}")

    def _combo_val(self, combo):
        v = combo.get().strip()
        if v in ("(select file first)", "(no columns)", "(none)", ""):
            return ""
        return v

    def _start(self):
        if not self._pfl_path:
            messagebox.showwarning("Missing file", "Please select the PFL / roster Excel.")
            return
        if not self._net_path:
            messagebox.showwarning("Missing file", "Please select the Network List Excel.")
            return

        pfl_cols = {k: self._combo_val(c) for k, c in self._pfl_map.items()}
        net_cols = {k: self._combo_val(c) for k, c in self._net_map.items()}

        required = [
            ("PFL Location Code", pfl_cols.get("location")),
            ("PFL Employee Code", pfl_cols.get("employee")),
            ("Network Lookup key", net_cols.get("location")),
            ("Network Address", net_cols.get("address")),
            ("Network Name", net_cols.get("name")),
            ("Network Contact", net_cols.get("contact")),
        ]
        missing = [label for label, val in required if not val]
        if missing:
            messagebox.showwarning(
                "Mapping incomplete",
                "Please set these columns:\n- " + "\n- ".join(missing))
            return

        product_name = self._product_e.get().strip() or "ID CARD"
        challan_no = self._challan_e.get().strip()

        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._stat.configure(text="Starting…", text_color=C["muted"])
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run,
            args=(product_name, challan_no, pfl_cols, net_cols),
            daemon=True
        ).start()

    def _run(self, product_name, challan_no, pfl_cols, net_cols):
        out_dir = get_output_dir()

        def log(msg):
            self.after(0, lambda m=msg: self._write_log(m))

        def progress(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"Output → {out_dir}\n")
            out_df, unmatched_df, matched, unmatched = build_data_xlsx(
                self._pfl_path, self._net_path, log, progress,
                product_name=product_name, challan_no=challan_no,
                pfl_cols=pfl_cols, net_cols=net_cols,
            )

            data_path = os.path.join(out_dir, "data.xlsx")
            out_df.to_excel(data_path, index=False)
            log(f"\n💾 Saved: data.xlsx  ({len(out_df):,} rows)")

            if len(unmatched_df):
                miss_path = os.path.join(out_dir, "unmatched_locations.xlsx")
                unmatched_df.to_excel(miss_path, index=False)
                log(f"⚠️  Unmatched locations → unmatched_locations.xlsx ({len(unmatched_df):,} rows)")

            log("\nNext steps:")
            log("  1. Open data.xlsx to review")
            log("  2. Leave Sr No and ID Count empty")
            log("  3. Run Grouped Excel on data.xlsx for the final output")

            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {matched:,} matched, {unmatched:,} unmatched → data.xlsx",
                text_color=C["green"]))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Built data.xlsx with {len(out_df):,} rows.\n"
                f"✅ Matched: {matched:,}\n"
                f"❌ Unmatched: {unmatched:,}\n\n"
                f"Saved to:\n{out_dir}\n\n"
                "Review data.xlsx, then run Grouped Excel."
            ))
        except Exception as e:
            log(f"\n💥 Error: {e}")
            self.after(0, lambda: self._stat.configure(text=f"Error: {e}", text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Build data.xlsx"))


if __name__ == "__main__":
    NetworkDataBuilderApp().mainloop()
