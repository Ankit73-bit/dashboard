"""
Tool: Excel ↔ JSON Converter
Convert Excel files to structured JSON (with clientInfo envelope),
or convert JSON files back to Excel / CSV.
Embeddable Panel + standalone window.
"""

import json
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
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Excel_JSON_Converter")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#00f5ff", "green":  "#30d158",
    "red":    "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#062d30", "mid": "#0a4a4e", "bdr": "#0d6b70"}


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


# ─── Core logic ───────────────────────────────────────────────────────────────

def excel_to_json(excel_path, sheet=None):
    df = pd.read_excel(excel_path, sheet_name=sheet or 0)

    status = str(df["status"].iloc[0]) if "status" in df.columns else "success"
    total = len(df)

    client_df = df.drop(columns=[c for c in ["status", "total"] if c in df.columns])

    # Convert datetime columns
    for col in client_df.select_dtypes(include=["datetime64[ns]"]).columns:
        client_df[col] = client_df[col].dt.strftime("%Y-%m-%d %H:%M:%S")

    # Replace NaN with None
    client_df = client_df.replace({pd.NA: None})
    client_df = client_df.where(pd.notnull(client_df), None)

    return {
        "status": status,
        "total": total,
        "clientInfo": client_df.to_dict(orient="records"),
    }


def json_to_tabular(json_path):
    """Convert JSON → flat DataFrame (handles clientInfo envelope)."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data.get("clientInfo"), list):
        df = pd.json_normalize(
            data,
            record_path="clientInfo",
            meta=["status", "total"],
            sep="_",
            errors="ignore",
        )
    else:
        df = pd.json_normalize(data, sep="_", errors="ignore")

    # Clean numeric columns with comma-formatted numbers
    if "debtRecordsAmount" in df.columns:
        df["debtRecordsAmount"] = (
            df["debtRecordsAmount"]
            .astype(str)
            .str.replace(",", "", regex=False)
            .pipe(pd.to_numeric, errors="coerce")
        )
    return df


# ─── Embeddable Panel Content ─────────────────────────────────────────────────

class ExcelJsonConverterPanelContent(ctk.CTkScrollableFrame):
    """The actual tool UI — mode-switchable, embeddable."""

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=C["border"], **kw)
        self._file_path = None
        self._mode      = ctk.StringVar(value="excel_to_json")
        self._build()

    # ── Build ──────────────────────────────────────────────────────────────────
    def _build(self):
        # Mode toggle
        toggle = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=12,
                              border_width=1, border_color=C["border"])
        toggle.pack(fill="x", pady=(4, 14))

        inner = ctk.CTkFrame(toggle, fg_color="transparent")
        inner.pack(padx=14, pady=12)

        ctk.CTkLabel(inner, text="Mode:",
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=C["muted"]).pack(side="left", padx=(0, 16))

        for label, val in [("Excel → JSON", "excel_to_json"),
                            ("JSON → Excel / CSV", "json_to_excel")]:
            ctk.CTkRadioButton(
                inner, text=label, variable=self._mode, value=val,
                font=ctk.CTkFont("Segoe UI", 12),
                text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"],
                border_color=C["border"],
                command=self._on_mode_change
            ).pack(side="left", padx=(0, 24))

        # Output banner
        self._out_banner = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=10,
                                        border_width=1, border_color=C["accent"])
        self._out_banner.pack(fill="x", pady=(0, 12))
        self._out_lbl = ctk.CTkLabel(
            self._out_banner,
            text="📁  Output → Desktop\\OUTPUT\\Excel_JSON_Converter\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"])
        self._out_lbl.pack(anchor="w", padx=14, pady=8)

        # Step 1 — File picker
        self._sec("Step 1 — Select file")
        fr = ctk.CTkFrame(self, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 10))
        self._file_lbl = ctk.CTkLabel(fr, text="No file selected",
                                      font=ctk.CTkFont("Segoe UI", 12),
                                      text_color=C["muted"], anchor="w")
        self._file_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(fr, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"], command=self._pick).pack(side="right")

        # Step 2 — Options (mode-specific, rebuilt on toggle)
        self._sec("Step 2 — Options")
        self._opts_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._opts_frame.pack(fill="x", pady=(0, 4))
        self._build_opts()

        # Step 3 — Run
        self._sec("Step 3 — Convert")
        self._run_btn = ctk.CTkButton(
            self, text="▶  Convert",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["bg"], hover_color=TINT["mid"],
            border_color=C["accent"], border_width=1,
            text_color=C["accent"], height=44,
            command=self._run)
        self._run_btn.pack(fill="x", pady=(0, 10))

        self._prog = ctk.CTkProgressBar(self, fg_color=C["card"],
                                        progress_color=C["accent"], height=8)
        self._prog.set(0)
        self._prog.pack(fill="x", pady=(0, 4))

        self._stat = ctk.CTkLabel(self, text="Ready.",
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

    def _build_opts(self):
        """Rebuild the options area based on current mode."""
        for w in self._opts_frame.winfo_children():
            w.destroy()

        mode = self._mode.get()

        if mode == "excel_to_json":
            # Sheet name input
            row = ctk.CTkFrame(self._opts_frame, fg_color="transparent")
            row.pack(fill="x")
            ctk.CTkLabel(row, text="Sheet name (optional):",
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["muted"]).pack(side="left", padx=(0, 12))
            self._sheet_e = ctk.CTkEntry(
                row, placeholder_text="Leave blank for first sheet",
                fg_color=C["card"], border_color=C["border"],
                text_color=C["text"], height=34, width=260)
            self._sheet_e.pack(side="left")

        else:
            # JSON → Excel: output format checkboxes
            row = ctk.CTkFrame(self._opts_frame, fg_color="transparent")
            row.pack(fill="x")
            ctk.CTkLabel(row, text="Output formats:",
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["muted"]).pack(side="left", padx=(0, 16))
            self._fmt_xlsx = ctk.BooleanVar(value=True)
            self._fmt_csv  = ctk.BooleanVar(value=True)
            ctk.CTkCheckBox(row, text=".xlsx", variable=self._fmt_xlsx,
                            font=ctk.CTkFont("Segoe UI", 11), text_color=C["text"],
                            fg_color=C["accent"], hover_color=TINT["bdr"],
                            border_color=C["border"], checkmark_color=C["bg"]
                            ).pack(side="left", padx=(0, 16))
            ctk.CTkCheckBox(row, text=".csv", variable=self._fmt_csv,
                            font=ctk.CTkFont("Segoe UI", 11), text_color=C["text"],
                            fg_color=C["accent"], hover_color=TINT["bdr"],
                            border_color=C["border"], checkmark_color=C["bg"]
                            ).pack(side="left")

    def _on_mode_change(self):
        # Reset file selection
        self._file_path = None
        self._file_lbl.configure(text="No file selected", text_color=C["muted"])
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        self._stat.configure(text="Ready.", text_color=C["muted"])
        self._build_opts()

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _sec(self, t):
        ctk.CTkLabel(self, text=t.upper(),
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["muted"]).pack(anchor="w", pady=(8, 3))

    def _pick(self):
        mode = self._mode.get()
        if mode == "excel_to_json":
            p = filedialog.askopenfilename(
                title="Select Excel file",
                filetypes=[("Excel files", "*.xlsx *.xls")])
        else:
            p = filedialog.askopenfilename(
                title="Select JSON file",
                filetypes=[("JSON files", "*.json")])
        if p:
            self._file_path = p
            self._file_lbl.configure(
                text=os.path.basename(p), text_color=C["text"])

    def _log(self, msg):
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")

    def _set_stat(self, msg, color=None):
        self._stat.configure(text=msg,
                             text_color=color or C["muted"])

    # ── Run ────────────────────────────────────────────────────────────────────
    def _run(self):
        if not self._file_path:
            messagebox.showwarning("No File", "Please select a file first.")
            return
        self._run_btn.configure(state="disabled", text="Converting…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        mode    = self._mode.get()
        out_dir = get_output_dir()
        stem    = Path(self._file_path).stem

        try:
            if mode == "excel_to_json":
                self._run_excel_to_json(out_dir, stem)
            else:
                self._run_json_to_excel(out_dir, stem)
        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Convert"))

    def _run_excel_to_json(self, out_dir, stem):
        sheet = getattr(self, "_sheet_e", None)
        sheet_val = sheet.get().strip() if sheet else ""

        self._log(f"📂 Input: {os.path.basename(self._file_path)}")
        self._log(f"📄 Sheet: {sheet_val or '(first sheet)'}")
        self.after(0, lambda: self._prog.set(0.3))

        data = excel_to_json(self._file_path, sheet_val or None)
        self._log(f"✅ Parsed {data['total']} rows")
        self.after(0, lambda: self._prog.set(0.7))

        out_path = os.path.join(out_dir, f"{stem}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        self.after(0, lambda: self._prog.set(1))
        self._log(f"💾 Saved: {stem}.json")
        self._log(f"\n🏁 Done!  {data['total']} records → {out_path}")
        self.after(0, lambda: self._set_stat(
            f"Done!  {data['total']} rows → {stem}.json", C["green"]))
        subprocess.Popen(["explorer", out_dir])

    def _run_json_to_excel(self, out_dir, stem):
        want_xlsx = self._fmt_xlsx.get()
        want_csv  = self._fmt_csv.get()
        if not want_xlsx and not want_csv:
            messagebox.showwarning("No Format", "Please select at least one output format.")
            return

        self._log(f"📂 Input: {os.path.basename(self._file_path)}")
        self.after(0, lambda: self._prog.set(0.3))

        df = json_to_tabular(self._file_path)
        self._log(f"✅ Parsed {len(df)} rows, {len(df.columns)} columns")
        self.after(0, lambda: self._prog.set(0.6))

        written = []
        if want_xlsx:
            p = os.path.join(out_dir, f"{stem}.xlsx")
            df.to_excel(p, index=False, engine="openpyxl")
            written.append(f"{stem}.xlsx")
            self._log(f"💾 Saved: {stem}.xlsx")

        if want_csv:
            p = os.path.join(out_dir, f"{stem}.csv")
            df.to_csv(p, index=False, encoding="utf-8-sig")
            written.append(f"{stem}.csv")
            self._log(f"💾 Saved: {stem}.csv")

        self.after(0, lambda: self._prog.set(1))
        self._log(f"\n🏁 Done!  {len(df)} rows → {', '.join(written)}")
        self.after(0, lambda: self._set_stat(
            f"Done!  {len(df)} rows → {', '.join(written)}", C["green"]))
        subprocess.Popen(["explorer", out_dir])


# ─── Embeddable Panel wrapper (used by dashboard) ─────────────────────────────
class ExcelJsonConverterPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        ExcelJsonConverterPanelContent(self).pack(
            fill="both", expand=True, padx=16, pady=8)


# ─── Standalone window ────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Excel ↔ JSON Converter")
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
        ctk.CTkLabel(icon_f, text="🔄",
                     font=ctk.CTkFont("Segoe UI Emoji", 20)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(tx, text="Excel ↔ JSON Converter",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx, text="Convert Excel ↔ JSON with clientInfo envelope support",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        ExcelJsonConverterPanelContent(self).pack(
            fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
