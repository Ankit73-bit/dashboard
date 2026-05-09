"""
Tool: Photo Renamer
Rename employee photos to their IDs from Excel/CSV, convert to PNG,
log duplicates and generate a not_found_rows.xlsx.
Embeddable Panel + standalone window.
"""

import os
import shutil
import threading
import subprocess
from pathlib import Path
from datetime import datetime

import pandas as pd
import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Photo_Renamer")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#ff9f0a", "green":  "#30d158",
    "red":    "#ff375f",
}
# Using orange accent (same as PDF to JPG but distinguishable in context)
TINT = {"bg": "#2e1e00", "mid": "#4a3000", "bdr": "#6b4500"}

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
COMMON_ID_COLS = {"employeeid", "empid", "eid", "employee id", "emp id",
                  "employee code", "emp code", "empcode"}


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def _check_pillow():
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False


# ─── Embeddable Panel Content ─────────────────────────────────────────────────

class PhotoRenamerPanelContent(ctk.CTkScrollableFrame):

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=C["border"], **kw)
        self._data_file     = None
        self._photos_folder = None
        self._df            = None
        self._columns       = []
        self._build()

    def _build(self):
        # Dependency warning
        if not _check_pillow():
            warn = ctk.CTkFrame(self, fg_color="#300a14", corner_radius=10,
                                border_width=1, border_color=C["red"])
            warn.pack(fill="x", pady=(4, 10))
            ctk.CTkLabel(warn,
                         text="⚠️  Pillow not installed.  Run:  pip install Pillow",
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["red"]).pack(anchor="w", padx=14, pady=8)

        # Output banner
        banner = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(4, 14))
        ctk.CTkLabel(banner,
                     text="📁  Output → Desktop\\OUTPUT\\Photo_Renamer\\<timestamp>\\renamed\\",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["accent"]).pack(anchor="w", padx=14, pady=8)

        # Step 1 — Data file
        self._sec("Step 1 — Select Excel / CSV data file")
        dr = ctk.CTkFrame(self, fg_color="transparent")
        dr.pack(fill="x", pady=(0, 4))
        self._data_lbl = ctk.CTkLabel(
            dr, text="No file selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._data_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(dr, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"],
                      command=self._pick_data).pack(side="right")

        self._cols_hint = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=C["faint"], anchor="w",
            justify="left", wraplength=560)
        self._cols_hint.pack(fill="x", pady=(2, 8))

        # Step 2 — ID column
        self._sec("Step 2 — Employee ID column")
        col_row = ctk.CTkFrame(self, fg_color="transparent")
        col_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(col_row, text="Column:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 12))
        self._col_var = ctk.StringVar(value="")
        ctk.CTkEntry(col_row, textvariable=self._col_var,
                     placeholder_text="e.g. Employee Code",
                     fg_color=C["card"], border_color=C["border"],
                     text_color=C["text"], height=34, width=260
                     ).pack(side="left")

        # Step 3 — Photos folder
        self._sec("Step 3 — Photos folder")
        pr = ctk.CTkFrame(self, fg_color="transparent")
        pr.pack(fill="x", pady=(0, 10))
        self._photos_lbl = ctk.CTkLabel(
            pr, text="No folder selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._photos_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(pr, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"],
                      command=self._pick_photos).pack(side="right")

        # Step 4 — Run
        self._sec("Step 4 — Run")
        self._run_btn = ctk.CTkButton(
            self, text="▶  Rename & Convert",
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
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], anchor="w")
        self._stat.pack(fill="x", pady=(0, 10))

        # Log
        self._sec("Log")
        self._log_box = ctk.CTkTextbox(
            self, height=220, fg_color=C["card"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], font=ctk.CTkFont("Consolas", 11))
        self._log_box.pack(fill="both", expand=True, pady=(0, 16))

    def _sec(self, t):
        ctk.CTkLabel(self, text=t.upper(),
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["muted"]).pack(anchor="w", pady=(8, 3))

    def _log(self, msg):
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")

    def _set_stat(self, msg, color=None):
        self._stat.configure(text=msg, text_color=color or C["muted"])

    def _pick_data(self):
        p = filedialog.askopenfilename(
            title="Select Excel or CSV file",
            filetypes=[("Data files", "*.xlsx *.xls *.csv")])
        if not p:
            return
        self._data_file = p
        self._data_lbl.configure(text=os.path.basename(p), text_color=C["text"])
        try:
            if p.lower().endswith(".csv"):
                df = pd.read_csv(p, dtype=str, nrows=0)
            else:
                df = pd.read_excel(p, nrows=0)
            self._columns = list(df.columns)
            hint = "Detected columns:  " + "   |   ".join(self._columns)
            self._cols_hint.configure(text=hint, text_color=C["faint"])
            # Auto-fill ID column
            for col in self._columns:
                if col.lower().replace(" ", "") in COMMON_ID_COLS:
                    self._col_var.set(col)
                    break
        except Exception as e:
            self._cols_hint.configure(text=f"Could not read: {e}", text_color=C["red"])

    def _pick_photos(self):
        p = filedialog.askdirectory(title="Select photos folder")
        if p:
            self._photos_folder = p
            n = sum(1 for f in os.listdir(p)
                    if Path(f).suffix.lower() in PHOTO_EXTS)
            self._photos_lbl.configure(
                text=f"{os.path.basename(p)}  ({n} photos detected)",
                text_color=C["text"])

    def _run(self):
        if not _check_pillow():
            messagebox.showerror("Missing Dependency",
                                 "Pillow is not installed.\n\nRun:  pip install Pillow")
            return
        if not self._data_file:
            messagebox.showwarning("No File", "Please select an Excel/CSV file.")
            return
        col = self._col_var.get().strip()
        if not col:
            messagebox.showwarning("No Column", "Please enter the Employee ID column name.")
            return
        if not self._photos_folder:
            messagebox.showwarning("No Photos", "Please select the photos folder.")
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(target=self._process, args=(col,), daemon=True).start()

    def _process(self, col):
        from PIL import Image

        out_dir     = get_output_dir()
        renamed_dir = os.path.join(out_dir, "renamed")
        os.makedirs(renamed_dir, exist_ok=True)

        try:
            self._log(f"📂 Data file:    {os.path.basename(self._data_file)}")
            self._log(f"📸 Photos:       {os.path.basename(self._photos_folder)}")
            self._log(f"🔑 ID column:    {col}\n")
            self.after(0, lambda: self._prog.set(0.1))

            # Load data
            if self._data_file.lower().endswith(".csv"):
                df = pd.read_csv(self._data_file, dtype=str)
            else:
                df = pd.read_excel(self._data_file, dtype=str)

            if col not in df.columns:
                raise ValueError(
                    f"Column '{col}' not found.\nAvailable: {', '.join(df.columns)}")

            employee_ids = (
                df[col].dropna().astype(str).str.strip().str.upper()
                .unique().tolist()
            )
            # Sort longest first to avoid partial-match collision
            employee_ids.sort(key=len, reverse=True)
            self._log(f"📊 IDs loaded: {len(employee_ids)}")
            self.after(0, lambda: self._prog.set(0.2))

            photo_files = [
                f for f in os.listdir(self._photos_folder)
                if os.path.isfile(os.path.join(self._photos_folder, f))
                and Path(f).suffix.lower() in PHOTO_EXTS
            ]
            self._log(f"🖼️  Photos found: {len(photo_files)}\n")

            used_ids   = {}   # id → [filenames]
            matched_ids = set()
            not_found_files = []
            renamed_count   = 0

            def _next_path(folder, base):
                p = os.path.join(folder, base + ".png")
                counter = 1
                while os.path.exists(p):
                    p = os.path.join(folder, f"{base}_{counter}.png")
                    counter += 1
                return p

            for idx, fname in enumerate(photo_files):
                src  = os.path.join(self._photos_folder, fname)
                root = Path(fname).stem.upper()
                matched_id = None
                for eid in employee_ids:
                    if root.startswith(eid) or eid in root:
                        matched_id = eid
                        break

                if matched_id:
                    matched_ids.add(matched_id)
                    used_ids.setdefault(matched_id, []).append(fname)
                    dest = _next_path(renamed_dir, matched_id)
                    try:
                        img = Image.open(src).convert("RGB")
                        img.save(dest, "PNG")
                        renamed_count += 1
                    except Exception as e:
                        self._log(f"   ⚠️  Convert error [{fname}]: {e}")
                else:
                    not_found_files.append(fname)

                self.after(0, lambda v=0.2 + 0.65 * (idx + 1) / len(photo_files):
                           self._prog.set(v))

            self._log(f"✅ Renamed:       {renamed_count}")
            self._log(f"❓ Unmatched photos: {len(not_found_files)}")

            # Write logs.txt
            log_path = os.path.join(out_dir, "logs.txt")
            with open(log_path, "w", encoding="utf-8") as lf:
                lf.write("Log — Unmatched Photos & Duplicates\n")
                lf.write("=" * 60 + "\n\n")
                if not_found_files:
                    lf.write("UNMATCHED PHOTOS (no employee ID found):\n")
                    for f in not_found_files:
                        lf.write(f"  - {f}\n")
                    lf.write("\n")
                dupes = {k: v for k, v in used_ids.items() if len(v) > 1}
                if dupes:
                    lf.write("DUPLICATES (multiple photos for same ID):\n")
                    for eid, files in dupes.items():
                        lf.write(f"  {eid}: {', '.join(files)}\n")
            self._log(f"📝 logs.txt saved")

            # not_found_rows.xlsx
            ids_upper = df[col].str.upper()
            missing_rows = df[~ids_upper.isin(matched_ids)]
            if not missing_rows.empty:
                nfr_path = os.path.join(out_dir, "not_found_rows.xlsx")
                missing_rows.to_excel(nfr_path, index=False)
                self._log(f"📋 not_found_rows.xlsx  ({len(missing_rows)} rows without a photo)")
            else:
                self._log("✅ All employee IDs had a matching photo!")

            self.after(0, lambda: self._prog.set(1))
            self._log(f"\n🏁 Done!  {renamed_count} PNG(s) → {renamed_dir}")
            self.after(0, lambda: self._set_stat(
                f"Done! {renamed_count} renamed · {len(not_found_files)} unmatched photos.",
                C["green"]))
            subprocess.Popen(["explorer", out_dir])

        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Rename & Convert"))


# ─── Embeddable Panel wrapper ─────────────────────────────────────────────────
class PhotoRenamerPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        PhotoRenamerPanelContent(self).pack(fill="both", expand=True, padx=16, pady=8)


# ─── Standalone App ───────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Photo Renamer")
        self.geometry("800x780")
        self.configure(fg_color=C["bg"])

        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)

        icon_f = ctk.CTkFrame(inn, width=44, height=44,
                              fg_color=TINT["mid"], corner_radius=10)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="✏️",
                     font=ctk.CTkFont("Segoe UI Emoji", 20)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(tx, text="Photo Renamer",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx, text="Rename & convert photos to PNG using employee IDs from Excel/CSV",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        PhotoRenamerPanelContent(self).pack(fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
