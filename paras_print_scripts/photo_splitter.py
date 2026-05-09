"""
Tool: Photo Splitter
Match employee photos to Excel rosters and copy them into per-Excel subfolders.
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
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Photo_Splitter")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#bf5af2", "green":  "#30d158",
    "red":    "#ff375f",
}
TINT = {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"}
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"}


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


# ─── Embeddable Panel Content ─────────────────────────────────────────────────

class PhotoSplitterPanelContent(ctk.CTkScrollableFrame):

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=C["border"], **kw)
        self._photos_folder = None
        self._excel_folder  = None
        self._build()

    def _build(self):
        # Output banner
        banner = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(4, 14))
        ctk.CTkLabel(banner,
                     text="📁  Output → Desktop\\OUTPUT\\Photo_Splitter\\<timestamp>\\<excel_name>\\",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["accent"]).pack(anchor="w", padx=14, pady=8)

        # Step 1 — Photos folder
        self._sec("Step 1 — Photos folder (named by employee code)")
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

        # Step 2 — Excel folder
        self._sec("Step 2 — Excel files folder")
        er = ctk.CTkFrame(self, fg_color="transparent")
        er.pack(fill="x", pady=(0, 10))
        self._excel_lbl = ctk.CTkLabel(
            er, text="No folder selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._excel_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(er, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"],
                      command=self._pick_excel).pack(side="right")

        # Step 3 — Column name
        self._sec("Step 3 — Employee Code column name")
        col_row = ctk.CTkFrame(self, fg_color="transparent")
        col_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(col_row, text="Column:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 12))
        self._col_var = ctk.StringVar(value="Employee Code")
        ctk.CTkEntry(col_row, textvariable=self._col_var,
                     placeholder_text="e.g. Employee Code",
                     fg_color=C["card"], border_color=C["border"],
                     text_color=C["text"], height=34, width=260
                     ).pack(side="left")

        # Step 4 — Run
        self._sec("Step 4 — Run")
        self._run_btn = ctk.CTkButton(
            self, text="▶  Split Photos",
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

    def _pick_photos(self):
        p = filedialog.askdirectory(title="Select photos folder")
        if p:
            self._photos_folder = p
            count = sum(1 for f in os.listdir(p)
                        if Path(f).suffix in PHOTO_EXTS)
            self._photos_lbl.configure(
                text=f"{os.path.basename(p)}  ({count} photos detected)",
                text_color=C["text"])

    def _pick_excel(self):
        p = filedialog.askdirectory(title="Select Excel files folder")
        if p:
            self._excel_folder = p
            count = sum(1 for f in os.listdir(p)
                        if f.lower().endswith((".xlsx", ".xls")))
            self._excel_lbl.configure(
                text=f"{os.path.basename(p)}  ({count} Excel file(s) found)",
                text_color=C["text"])

    def _run(self):
        if not self._photos_folder:
            messagebox.showwarning("No Photos", "Please select a photos folder first.")
            return
        if not self._excel_folder:
            messagebox.showwarning("No Excel", "Please select the Excel files folder first.")
            return
        col = self._col_var.get().strip()
        if not col:
            messagebox.showwarning("No Column", "Please enter the Employee Code column name.")
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(target=self._process, args=(col,), daemon=True).start()

    def _process(self, col):
        out_dir = get_output_dir()
        excels  = [f for f in os.listdir(self._excel_folder)
                   if f.lower().endswith((".xlsx", ".xls"))]

        total_found   = 0
        total_missing = 0

        try:
            self._log(f"📂 Photos folder:  {os.path.basename(self._photos_folder)}")
            self._log(f"📋 Excel files:    {len(excels)}")
            self._log(f"🔑 Code column:    {col}\n")

            for idx, excel_file in enumerate(excels, 1):
                self.after(0, lambda v=idx / len(excels) * 0.9: self._prog.set(v))
                excel_path = os.path.join(self._excel_folder, excel_file)
                self._log(f"[{idx}/{len(excels)}]  {excel_file}")

                try:
                    df = pd.read_excel(excel_path)
                except Exception as e:
                    self._log(f"   ❌ Could not read: {e}")
                    continue

                if col not in df.columns:
                    self._log(f"   ❌ Column '{col}' not found — skipped")
                    self._log(f"      Available: {', '.join(df.columns)}")
                    continue

                codes  = set(df[col].dropna().astype(str).str.strip())
                folder = os.path.join(out_dir, Path(excel_file).stem)
                os.makedirs(folder, exist_ok=True)

                found   = 0
                missing = []
                for code in codes:
                    matched = False
                    for ext in PHOTO_EXTS:
                        src = os.path.join(self._photos_folder, code + ext)
                        if os.path.exists(src):
                            shutil.copy2(src, folder)
                            found += 1
                            matched = True
                            break
                    if not matched:
                        missing.append(code)

                if missing:
                    log_path = os.path.join(folder, "missing_images.txt")
                    with open(log_path, "w", encoding="utf-8") as lf:
                        lf.write("\n".join(sorted(missing)))
                    self._log(f"   ✅ {found} copied  |  ⚠️  {len(missing)} missing → missing_images.txt")
                else:
                    self._log(f"   ✅ {found} copied  |  All codes matched!")

                total_found   += found
                total_missing += len(missing)

            self.after(0, lambda: self._prog.set(1))
            self._log(f"\n🏁 Done!  {total_found} total photos copied, {total_missing} missing → {out_dir}")
            self.after(0, lambda: self._set_stat(
                f"Done! {total_found} photos copied · {total_missing} missing.", C["green"]))
            subprocess.Popen(["explorer", out_dir])

        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Split Photos"))


# ─── Embeddable Panel wrapper ─────────────────────────────────────────────────
class PhotoSplitterPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        PhotoSplitterPanelContent(self).pack(fill="both", expand=True, padx=16, pady=8)


# ─── Standalone App ───────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Photo Splitter")
        self.geometry("800x760")
        self.configure(fg_color=C["bg"])

        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)

        icon_f = ctk.CTkFrame(inn, width=44, height=44,
                              fg_color=TINT["mid"], corner_radius=10)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🗂️",
                     font=ctk.CTkFont("Segoe UI Emoji", 20)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(tx, text="Photo Splitter",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx, text="Distribute employee photos into folders per Excel roster",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        PhotoSplitterPanelContent(self).pack(fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
