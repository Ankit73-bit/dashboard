"""
Tool: Grouped Excel
Group rows by a key column, join IDs with '/', add ID count.
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
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Grouped_Excel")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "cyan":   "#00f5ff", "green":  "#30d158",
    "red":    "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#062d30", "mid": "#0a4a4e", "bdr": "#0d6b70"}


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


# ─── Embeddable Panel Content ─────────────────────────────────────────────────

class GroupedExcelPanelContent(ctk.CTkScrollableFrame):
    """The actual tool UI — embeddable inside dashboard or standalone."""

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
                              border_width=1, border_color=C["cyan"])
        banner.pack(fill="x", pady=(4, 14))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\Grouped_Excel\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["cyan"]
        ).pack(anchor="w", padx=14, pady=8)

        # Step 1 — File picker
        self._sec("Step 1 — Select Excel file")
        fr = ctk.CTkFrame(self, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 4))
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

        # Detected columns hint
        self._cols_hint = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=C["faint"], anchor="w",
            justify="left", wraplength=560)
        self._cols_hint.pack(fill="x", pady=(2, 10))

        # Step 2 — Group-by column
        self._sec("Step 2 — Group-by column")
        gb_row = ctk.CTkFrame(self, fg_color="transparent")
        gb_row.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(gb_row, text="Column name:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 12))
        self._group_var = ctk.StringVar(value="location code")
        self._group_entry = ctk.CTkEntry(
            gb_row, textvariable=self._group_var,
            placeholder_text="e.g. location code",
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], height=34, width=260)
        self._group_entry.pack(side="left")

        # Step 3 — ID column
        self._sec("Step 3 — ID column to join with '/'")
        id_row = ctk.CTkFrame(self, fg_color="transparent")
        id_row.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(id_row, text="Column name:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 12))
        self._id_var = ctk.StringVar(value="Employee Code")
        self._id_entry = ctk.CTkEntry(
            id_row, textvariable=self._id_var,
            placeholder_text="e.g. Employee Code",
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], height=34, width=260)
        self._id_entry.pack(side="left")

        # Step 4 — Separator option
        self._sec("Step 4 — ID separator (optional)")
        sep_row = ctk.CTkFrame(self, fg_color="transparent")
        sep_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(sep_row, text="Separator:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 12))
        self._sep_var = ctk.StringVar(value="/")
        self._sep_entry = ctk.CTkEntry(
            sep_row, textvariable=self._sep_var,
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], height=34, width=80)
        self._sep_entry.pack(side="left")
        ctk.CTkLabel(sep_row, text="   Default: /",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=C["faint"]).pack(side="left")

        # Step 5 — Run
        self._sec("Step 5 — Run")
        self._run_btn = ctk.CTkButton(
            self, text="▶  Group & Merge",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["bg"], hover_color=TINT["mid"],
            border_color=C["cyan"], border_width=1,
            text_color=C["cyan"], height=44,
            command=self._run)
        self._run_btn.pack(fill="x", pady=(0, 10))

        self._prog = ctk.CTkProgressBar(
            self, fg_color=C["card"], progress_color=C["cyan"], height=8)
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
            hint = "Detected columns:  " + "   |   ".join(self._columns)
            self._cols_hint.configure(text=hint, text_color=C["faint"])

            # Auto-fill if known columns exist
            if "location code" in self._columns:
                self._group_var.set("location code")
            if "Employee Code" in self._columns:
                self._id_var.set("Employee Code")
        except Exception as e:
            self._cols_hint.configure(
                text=f"Could not read columns: {e}", text_color=C["red"])

    # ── Run ────────────────────────────────────────────────────────────────────
    def _run(self):
        if not self._file_path:
            messagebox.showwarning("No File", "Please select an Excel file first.")
            return
        group_col = self._group_var.get().strip()
        id_col    = self._id_var.get().strip()
        if not group_col:
            messagebox.showwarning("Missing", "Please enter a Group-by column name.")
            return
        if not id_col:
            messagebox.showwarning("Missing", "Please enter an ID column name.")
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(
            target=self._process, args=(group_col, id_col), daemon=True).start()

    def _process(self, group_col, id_col):
        out_dir   = get_output_dir()
        stem      = Path(self._file_path).stem
        separator = self._sep_var.get() or "/"

        try:
            self._log(f"📂 Input:      {os.path.basename(self._file_path)}")
            self._log(f"🔑 Group by:   {group_col}")
            self._log(f"🆔 ID column:  {id_col}")
            self._log(f"🔗 Separator:  '{separator}'")
            self.after(0, lambda: self._prog.set(0.1))

            df = pd.read_excel(self._file_path)
            self._log(f"📊 Rows loaded: {len(df):,}")
            self.after(0, lambda: self._prog.set(0.25))

            # Validate columns
            missing = [c for c in [group_col, id_col] if c not in df.columns]
            if missing:
                raise ValueError(
                    f"Column(s) not found: {', '.join(missing)}\n"
                    f"Available: {', '.join(df.columns)}")

            self._log("⚙️  Grouping rows…")
            self.after(0, lambda: self._prog.set(0.5))

            other_cols = [c for c in df.columns
                          if c not in [group_col, id_col, 'ID Count']]

            grouped = df.groupby(group_col, as_index=False).agg(
                **{id_col:   (id_col, lambda x: separator.join(x.astype(str)))},
                **{col:      (col, 'first') for col in other_cols}
            )

            # ID Count column
            id_counts = df.groupby(group_col)[id_col].count().reset_index(name='ID Count')
            grouped   = pd.merge(grouped, id_counts, on=group_col)

            # Reorder columns: group | id | count | rest
            desired = [group_col, id_col, 'ID Count'] + [
                c for c in grouped.columns
                if c not in [group_col, id_col, 'ID Count']]
            grouped = grouped[desired]

            self._log(f"✅ Groups created: {len(grouped):,}  (from {len(df):,} rows)")
            self.after(0, lambda: self._prog.set(0.8))

            out_path = os.path.join(out_dir, f"{stem}_grouped.xlsx")
            with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
                grouped.to_excel(writer, index=False, sheet_name='Merged')

            self._log(f"💾 Saved:  {stem}_grouped.xlsx")
            self._log(f"📁 Folder: {out_dir}")
            self.after(0, lambda: self._prog.set(1))

            self._log(f"\n🏁 Done!  {len(grouped):,} groups → {out_path}")
            self.after(0, lambda: self._set_stat(
                f"Done! {len(df):,} rows → {len(grouped):,} groups saved.",
                C["green"]))
            subprocess.Popen(["explorer", out_dir])

        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Group & Merge"))


# ─── Embeddable Panel wrapper (used by dashboard) ─────────────────────────────
class GroupedExcelPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        GroupedExcelPanelContent(self).pack(
            fill="both", expand=True, padx=16, pady=8)


# ─── Standalone window ────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Grouped Excel")
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
        ctk.CTkLabel(icon_f, text="📊",
                     font=ctk.CTkFont("Segoe UI Emoji", 20)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(tx, text="Grouped Excel",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx, text="Group rows by a key column · join IDs with '/' · add ID count",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        GroupedExcelPanelContent(self).pack(
            fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
