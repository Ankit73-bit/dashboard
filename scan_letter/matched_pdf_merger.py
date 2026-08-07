"""
Tool: Matched PDF Merger (Scan Step 3)
Merge Exact/Fuzzy-matched barcode PDFs from multiple source folders.
"""

import os
import csv
import threading
import subprocess
from datetime import datetime

import pandas as pd
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PyPDF2 import PdfMerger

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Scan_PDF_Merger")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#bf5af2", "green": "#30d158",
    "red": "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"}

SOURCES = [
    ("renamed", "Renamed PDFs"),
    ("ucp", "UCP"),
    ("tracking", "Tracking"),
]


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def find_pdf_in_subfolders(root_folder, barcode):
    if not root_folder or not os.path.exists(root_folder):
        return None
    target = f"{barcode}.pdf".lower()
    for root, _, files in os.walk(root_folder):
        for f in files:
            if f.lower() == target:
                return os.path.join(root, f)
    return None


def _find_col(columns, *candidates):
    lower = {str(c).strip().lower(): c for c in columns}
    for name in candidates:
        key = name.lower()
        if key in lower:
            return lower[key]
    for name in candidates:
        key = name.lower()
        for lc, orig in lower.items():
            if key in lc:
                return orig
    return None


def merge_pdfs(excel_folder, selected_sources, col_map, out_dir, log_fn, progress_fn):
    """
    selected_sources: list of (display_name, folder_path)
    col_map: {barcode, prospect_no, remark}
    """
    merged_folder = os.path.join(out_dir, "merged_pdfs")
    os.makedirs(merged_folder, exist_ok=True)
    log_file = os.path.join(out_dir, "merge_log.csv")

    with open(log_file, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            "Prospect_No", "Barcode", "Remark", "Merged_Folders",
            "Merged_File", "Status", "Error"
        ])

    excel_files = [
        f for f in os.listdir(excel_folder)
        if f.lower().endswith((".xls", ".xlsx")) and not f.startswith("~$")
    ]
    if not excel_files:
        raise ValueError("No Excel files found in the selected folder.")

    total_matched = merged_count = skipped = errors = 0
    folder_names = ", ".join(n for n, _ in selected_sources)

    for ei, ef in enumerate(excel_files, 1):
        log_fn(f"\nExcel: {ef}")
        path = os.path.join(excel_folder, ef)
        try:
            df = pd.read_excel(path, dtype=str)
            df.columns = (
                df.columns.astype(str).str.strip()
                .str.replace("\n", "", regex=False)
                .str.replace("\r", "", regex=False)
            )
        except Exception as e:
            log_fn(f"  Read error: {e}")
            errors += 1
            continue

        barcode_col = col_map["barcode"]
        prospect_col = col_map["prospect_no"]
        remark_col = col_map["remark"]

        for col, label in [
            (barcode_col, "Barcode"),
            (prospect_col, "Prospect No"),
            (remark_col, "Remark"),
        ]:
            if col not in df.columns:
                raise ValueError(f"Column '{col}' ({label}) not in {ef}")

        df[remark_col] = df[remark_col].fillna("").astype(str)
        matched_df = df[
            df[remark_col].str.contains("Exact Match", case=False, na=False)
            | df[remark_col].str.contains("Fuzzy Match", case=False, na=False)
        ].copy()
        log_fn(f"  Matched rows: {len(matched_df)}")
        total_matched += len(matched_df)

        with open(log_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for _, row in matched_df.iterrows():
                barcode = str(row[barcode_col]).strip()
                prospect_no = str(row[prospect_col]).strip()
                remark = str(row[remark_col]).strip()

                if not barcode or not prospect_no or barcode.lower() == "nan":
                    skipped += 1
                    continue

                found_pdfs = []
                missing = []
                for name, folder in selected_sources:
                    pdf_path = find_pdf_in_subfolders(folder, barcode)
                    if pdf_path:
                        found_pdfs.append(pdf_path)
                    else:
                        missing.append(name)

                merged_filename = f"{prospect_no}-{barcode}.pdf"
                if missing:
                    skipped += 1
                    writer.writerow([
                        prospect_no, barcode, remark, folder_names, "",
                        "Skipped", f"Missing: {', '.join(missing)}"
                    ])
                    log_fn(f"  Skip {merged_filename} (missing {', '.join(missing)})")
                    continue

                try:
                    out_path = os.path.join(merged_folder, merged_filename)
                    merger = PdfMerger()
                    for pdf in found_pdfs:
                        merger.append(pdf)
                    merger.write(out_path)
                    merger.close()
                    merged_count += 1
                    writer.writerow([
                        prospect_no, barcode, remark, folder_names,
                        out_path, "Merged", "OK"
                    ])
                    log_fn(f"  Merged → {merged_filename}")
                except Exception as e:
                    errors += 1
                    writer.writerow([
                        prospect_no, barcode, remark, folder_names,
                        "", "Row Error", str(e)
                    ])
                    log_fn(f"  Error {merged_filename}: {e}")

        progress_fn(ei / len(excel_files))

    return {
        "matched": total_matched,
        "merged": merged_count,
        "skipped": skipped,
        "errors": errors,
        "log": log_file,
        "merged_folder": merged_folder,
    }


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Matched PDF Merger")
        self.geometry("780x780")
        self.minsize(700, 640)
        self.configure(fg_color=C["bg"])
        self._excel_folder = None
        self._source_paths = {k: None for k, _ in SOURCES}
        self._source_vars = {}
        self._columns = []
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)
        ctk.CTkLabel(inn, text="📎  Matched PDF Merger",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(inn, text="Scan Step 3 — merge Exact/Fuzzy matches from multiple PDF sources",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"]).pack(anchor="w")

        # Sticky footer with run button
        footer = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0,
                              border_width=1, border_color=C["border"])
        footer.pack(side="bottom", fill="x")
        fi = ctk.CTkFrame(footer, fg_color="transparent")
        fi.pack(fill="x", padx=20, pady=12)
        self._prog = ctk.CTkProgressBar(fi, height=6, fg_color=C["hover"],
                                        progress_color=C["accent"])
        self._prog.pack(fill="x", pady=(0, 6))
        self._prog.set(0)
        self._stat = ctk.CTkLabel(fi, text="Ready.", font=ctk.CTkFont("Segoe UI", 11),
                                  text_color=C["muted"], anchor="w")
        self._stat.pack(fill="x", pady=(0, 8))
        self._run_btn = ctk.CTkButton(
            fi, text="▶  Merge Matched PDFs",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            corner_radius=24, height=44, command=self._start)
        self._run_btn.pack(fill="x")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                      scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        banner = ctk.CTkFrame(body, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            banner, text="📁  Output → Desktop\\OUTPUT\\Scan_PDF_Merger\\<timestamp>\\merged_pdfs\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"]
        ).pack(anchor="w", padx=14, pady=8)

        self._sec(body, "Excel folder (with Exact/Fuzzy remarks)")
        fr = ctk.CTkFrame(body, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 10))
        self._excel_lbl = ctk.CTkLabel(fr, text="No folder selected",
                                       font=ctk.CTkFont("Segoe UI", 12),
                                       text_color=C["muted"], anchor="w")
        self._excel_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(fr, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"], command=self._pick_excel).pack(side="right")

        self._sec(body, "PDF sources (select at least 2)")
        src_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                border_width=1, border_color=C["border"])
        src_card.pack(fill="x", pady=(0, 12))

        for i, (key, label) in enumerate(SOURCES):
            row = ctk.CTkFrame(src_card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(10 if i == 0 else 4, 10 if i == 2 else 4))
            var = ctk.BooleanVar(value=(key == "renamed"))
            self._source_vars[key] = var
            ctk.CTkCheckBox(row, text=label, variable=var, width=130,
                            font=ctk.CTkFont("Segoe UI", 12), text_color=C["text"],
                            fg_color=C["accent"], hover_color=TINT["bdr"]).pack(side="left")
            lbl = ctk.CTkLabel(row, text="No folder", font=ctk.CTkFont("Segoe UI", 11),
                               text_color=C["faint"], anchor="w")
            lbl.pack(side="left", fill="x", expand=True, padx=8)
            setattr(self, f"_src_lbl_{key}", lbl)
            ctk.CTkButton(row, text="Browse…", width=80, height=30,
                          fg_color=C["hover"], hover_color=C["border"],
                          text_color=C["text"],
                          command=lambda k=key: self._pick_source(k)).pack(side="right")

        self._sec(body, "Column mapping")
        map_card = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=12,
                                border_width=1, border_color=C["border"])
        map_card.pack(fill="x", pady=(0, 12))
        map_card.columnconfigure(1, weight=1)
        self._combos = {}
        for i, (role, label) in enumerate([
            ("barcode", "Barcode"),
            ("prospect_no", "Prospect No"),
            ("remark", "Remark"),
        ]):
            ctk.CTkLabel(map_card, text=label, font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["muted"], width=110
                         ).grid(row=i, column=0, padx=16, pady=8, sticky="w")
            cb = ctk.CTkComboBox(
                map_card, values=["(load Excel first)"], state="readonly",
                font=ctk.CTkFont("Segoe UI", 12),
                fg_color=C["hover"], border_color=C["border"],
                button_color=TINT["mid"], button_hover_color=TINT["bdr"],
                dropdown_fg_color=C["card"], dropdown_hover_color=C["hover"],
                dropdown_text_color=C["text"], text_color=C["text"], height=32)
            cb.set("(load Excel first)")
            cb.grid(row=i, column=1, padx=16, pady=8, sticky="ew")
            self._combos[role] = cb

        self._sec(body, "Log")
        self._log = ctk.CTkTextbox(body, height=160, font=ctk.CTkFont("Courier New", 11),
                                   fg_color=C["card"], border_color=C["border"],
                                   border_width=1, text_color=C["muted"], state="disabled")
        self._log.pack(fill="x", pady=(0, 8))

    def _sec(self, p, t):
        ctk.CTkLabel(p, text=t, font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w").pack(fill="x", pady=(10, 2))

    def _write(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _pick_excel(self):
        folder = filedialog.askdirectory(title="Select Excel folder")
        if not folder:
            return
        self._excel_folder = folder
        files = [f for f in os.listdir(folder)
                 if f.lower().endswith((".xls", ".xlsx")) and not f.startswith("~$")]
        self._excel_lbl.configure(
            text=f"{folder}  ({len(files)} Excel)", text_color=C["accent"])
        if not files:
            return
        try:
            df = pd.read_excel(os.path.join(folder, files[0]), nrows=0)
            df.columns = df.columns.astype(str).str.strip()
            self._columns = list(df.columns)
            for role, cb in self._combos.items():
                cb.configure(values=self._columns)
            defaults = {
                "barcode": _find_col(self._columns, "barcode", "awb", "tracking", "article"),
                "prospect_no": _find_col(
                    self._columns, "prospect_no", "prospect no", "prospect", "cuid", "ref_no"
                ),
                "remark": _find_col(self._columns, "remark", "remarks", "status"),
            }
            for role, cb in self._combos.items():
                cb.set(defaults[role] or self._columns[0])
        except Exception as e:
            messagebox.showerror("Error", f"Could not read columns:\n{e}")

    def _pick_source(self, key):
        folder = filedialog.askdirectory(title=f"Select {dict(SOURCES)[key]} folder")
        if not folder:
            return
        self._source_paths[key] = folder
        getattr(self, f"_src_lbl_{key}").configure(
            text=folder, text_color=C["accent"])
        self._source_vars[key].set(True)

    def _start(self):
        if not self._excel_folder:
            messagebox.showwarning("Missing", "Select the Excel folder.")
            return
        selected = []
        for key, label in SOURCES:
            if self._source_vars[key].get():
                path = self._source_paths[key]
                if not path:
                    messagebox.showwarning("Missing", f"Browse a folder for {label}.")
                    return
                selected.append((label, path))
        if len(selected) < 2:
            messagebox.showwarning("Sources", "Select at least 2 PDF source folders.")
            return

        col_map = {k: cb.get().strip() for k, cb in self._combos.items()}
        if any(v.startswith("(") or not v for v in col_map.values()):
            messagebox.showwarning("Columns", "Set Barcode, Prospect No, and Remark columns.")
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run, args=(selected, col_map), daemon=True
        ).start()

    def _run(self, selected, col_map):
        out_dir = get_output_dir()

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        def prog(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"Excel   → {self._excel_folder}")
            for name, path in selected:
                log(f"Source  → {name}: {path}")
            log(f"Output  → {out_dir}\n")
            stats = merge_pdfs(
                self._excel_folder, selected, col_map, out_dir, log, prog
            )
            log("\n========== SUMMARY ==========")
            log(f"Matched rows : {stats['matched']}")
            log(f"Merged       : {stats['merged']}")
            log(f"Skipped      : {stats['skipped']}")
            log(f"Errors       : {stats['errors']}")
            log(f"Log          : {stats['log']}")
            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {stats['merged']} merged, {stats['skipped']} skipped.",
                text_color=C["green"]))
            self.after(0, lambda: subprocess.Popen(["explorer", stats["merged_folder"]]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Merged: {stats['merged']}\nSkipped: {stats['skipped']}\n"
                f"Errors: {stats['errors']}\n\n{stats['merged_folder']}"
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Merge Matched PDFs"))


if __name__ == "__main__":
    App().mainloop()
