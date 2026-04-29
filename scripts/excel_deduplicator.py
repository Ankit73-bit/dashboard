"""
Tool: Excel Deduplicator
Remove duplicate rows from an Excel file based on a selected column.
Embeddable Panel + standalone window.
"""

import os
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
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Excel_Deduplicator")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#30d158", "green":  "#30d158",
    "red":    "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#082a12", "mid": "#0f4020", "bdr": "#185c2e"}


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


# ─── Embeddable Panel Content ─────────────────────────────────────────────────

class ExcelDeduplicatorPanelContent(ctk.CTkScrollableFrame):
    """The actual tool UI — embeddable."""

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=C["border"], **kw)
        self._file_path = None
        self._columns   = []
        self._build()

    # ── Build ──────────────────────────────────────────────────────────────────
    def _build(self):
        # Output banner
        banner = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(4, 14))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\Excel_Deduplicator\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"]
        ).pack(anchor="w", padx=14, pady=8)

        # Step 1 — File picker
        self._sec("Step 1 — Select Excel file")
        fr = ctk.CTkFrame(self, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 10))
        self._file_lbl = ctk.CTkLabel(
            fr, text="No file selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._file_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick
        ).pack(side="right")

        # Step 2 — Column selector
        self._sec("Step 2 — Column to deduplicate on")
        col_row = ctk.CTkFrame(self, fg_color="transparent")
        col_row.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(col_row, text="Column name:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 12))

        self._col_var = ctk.StringVar(value="")
        self._col_entry = ctk.CTkEntry(
            col_row,
            textvariable=self._col_var,
            placeholder_text="e.g. customer_id",
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], height=34, width=220)
        self._col_entry.pack(side="left")

        # Detected columns hint
        self._cols_hint = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=C["faint"], anchor="w",
            justify="left", wraplength=560)
        self._cols_hint.pack(fill="x", pady=(2, 8))

        # Step 3 — Keep option
        self._sec("Step 3 — Which duplicate to keep")
        keep_row = ctk.CTkFrame(self, fg_color="transparent")
        keep_row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(keep_row, text="Keep:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 16))

        self._keep_var = ctk.StringVar(value="first")
        for label, val in [("First occurrence", "first"), ("Last occurrence", "last")]:
            ctk.CTkRadioButton(
                keep_row, text=label, variable=self._keep_var, value=val,
                font=ctk.CTkFont("Segoe UI", 12),
                text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"],
                border_color=C["border"]
            ).pack(side="left", padx=(0, 24))

        # Step 4 — Run
        self._sec("Step 4 — Run")
        self._run_btn = ctk.CTkButton(
            self, text="▶  Remove Duplicates",
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
            self, height=200, fg_color=C["card"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], font=ctk.CTkFont("Consolas", 11))
        self._log_box.pack(fill="both", expand=True, pady=(0, 16))

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _sec(self, t):
        ctk.CTkLabel(self, text=t.upper(),
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["muted"]).pack(anchor="w", pady=(8, 3))

    def _log(self, msg):
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")

    def _set_stat(self, msg, color=None):
        self._stat.configure(text=msg, text_color=color or C["muted"])

    def _pick(self):
        p = filedialog.askopenfilename(
            title="Select Excel file",
            filetypes=[("Excel files", "*.xlsx *.xls")])
        if not p:
            return
        self._file_path = p
        self._file_lbl.configure(text=os.path.basename(p), text_color=C["text"])

        # Read columns and show hint
        try:
            df = pd.read_excel(p, nrows=0)
            self._columns = list(df.columns)
            hint = "Detected columns: " + ",  ".join(self._columns)
            self._cols_hint.configure(text=hint, text_color=C["faint"])

            # Auto-fill if 'customer_id' exists
            if "customer_id" in self._columns:
                self._col_var.set("customer_id")
        except Exception as e:
            self._cols_hint.configure(
                text=f"Could not read columns: {e}", text_color=C["red"])

    # ── Run ────────────────────────────────────────────────────────────────────
    def _run(self):
        if not self._file_path:
            messagebox.showwarning("No File", "Please select an Excel file first.")
            return
        col = self._col_var.get().strip()
        if not col:
            messagebox.showwarning("No Column", "Please enter a column name to deduplicate on.")
            return
        self._run_btn.configure(state="disabled", text="Processing…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(target=self._process, args=(col,), daemon=True).start()

    def _process(self, col):
        out_dir = get_output_dir()
        stem    = Path(self._file_path).stem
        keep    = self._keep_var.get()

        try:
            self._log(f"📂 Input:  {os.path.basename(self._file_path)}")
            self._log(f"🔑 Column: {col}")
            self._log(f"📌 Keep:   {keep} occurrence")
            self.after(0, lambda: self._prog.set(0.2))

            df = pd.read_excel(self._file_path)
            self._log(f"📊 Rows loaded: {len(df):,}")
            self.after(0, lambda: self._prog.set(0.5))

            if col not in df.columns:
                raise ValueError(
                    f"Column '{col}' not found.\n"
                    f"Available columns: {', '.join(df.columns)}")

            before = len(df)
            df_unique = df.drop_duplicates(subset=[col], keep=keep)
            removed = before - len(df_unique)
            self._log(f"✅ Duplicates removed: {removed:,}  |  Unique rows kept: {len(df_unique):,}")
            self.after(0, lambda: self._prog.set(0.8))

            out_path = os.path.join(out_dir, f"{stem}_unique.xlsx")
            df_unique.to_excel(out_path, index=False)
            self._log(f"💾 Saved:  {stem}_unique.xlsx")
            self.after(0, lambda: self._prog.set(1))

            self._log(f"\n🏁 Done!  {len(df_unique):,} unique rows → {out_path}")
            self.after(0, lambda: self._set_stat(
                f"Done! {removed:,} duplicates removed · {len(df_unique):,} rows saved.",
                C["green"]))
            subprocess.Popen(["explorer", out_dir])

        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Remove Duplicates"))


# ─── Embeddable Panel wrapper (used by dashboard) ─────────────────────────────
class ExcelDeduplicatorPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        ExcelDeduplicatorPanelContent(self).pack(
            fill="both", expand=True, padx=16, pady=8)


# ─── Standalone window ────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Excel Deduplicator")
        self.geometry("800x720")
        self.configure(fg_color=C["bg"])

        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)

        icon_f = ctk.CTkFrame(inn, width=44, height=44,
                              fg_color=TINT["mid"], corner_radius=10)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🧹",
                     font=ctk.CTkFont("Segoe UI Emoji", 20)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(tx, text="Excel Deduplicator",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx, text="Remove duplicate rows by any column — fast and non-destructive",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        ExcelDeduplicatorPanelContent(self).pack(
            fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
