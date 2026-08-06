"""
Tool: Excel CUID Separator
Group multiple rows per CUID into wide columns (col_1, col_2, …),
format date columns, and add per-CUID sum columns.
"""

import os
import threading
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd
import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Excel_CUID_Separator")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#ff9f0a", "green":  "#30d158",
    "red":    "#ff375f",
}
TINT = {"bg": "#2e1e00", "mid": "#4a3000", "bdr": "#6b4500"}


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def clean_column_names(df):
    df.columns = df.columns.str.strip()
    return df


def format_date_columns(df, date_columns):
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%d-%m-%Y")
    return df


def create_separate_columns(df, groupby_col, sum_columns):
    df_grouped = pd.DataFrame()
    customer_counts = df.groupby(groupby_col).cumcount() + 1

    sums = df.groupby(groupby_col).agg({col: "sum" for col in sum_columns}).reset_index()
    sums.columns = [groupby_col] + [f"sum_{col}" for col in sum_columns]

    for idx, row in df.iterrows():
        customer_id = row[groupby_col]
        suffix = customer_counts[idx]

        if customer_id not in df_grouped.get(groupby_col, pd.Series([])).values:
            new_row = pd.DataFrame([{groupby_col: customer_id}], columns=[groupby_col])
            df_grouped = pd.concat([df_grouped, new_row], ignore_index=True)

        grouped_idx = df_grouped.index[df_grouped[groupby_col] == customer_id].tolist()[0]

        for col in df.columns:
            if col != groupby_col:
                new_col_name = f"{col}_{suffix}"
                if new_col_name not in df_grouped.columns:
                    df_grouped[new_col_name] = pd.Series(dtype=object)
                df_grouped.at[grouped_idx, new_col_name] = row[col]

        srno_col_name = f"SrNo_{suffix}"
        if srno_col_name not in df_grouped.columns:
            df_grouped[srno_col_name] = pd.Series(dtype=object)
        df_grouped.at[grouped_idx, srno_col_name] = suffix

        for col in sums.columns:
            if col != groupby_col:
                if col not in df_grouped.columns:
                    df_grouped[col] = pd.Series(dtype=object)
                df_grouped.at[grouped_idx, col] = sums.loc[
                    sums[groupby_col] == customer_id, col
                ].values[0]

    return df_grouped


class ExcelCuidSeparatorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Excel CUID Separator")
        self.geometry("820x700")
        self.minsize(700, 520)
        self.configure(fg_color=C["bg"])
        self._file_path = None
        self._columns = []
        self._date_vars = {}
        self._sum_vars = {}
        self._build()

    def _build(self):
        # Layout: header (top) · footer with run button (always visible) · middle fills rest
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(padx=28, pady=12)

        icon_f = ctk.CTkFrame(inner, width=44, height=44, fg_color=TINT["mid"], corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="↔️", font=ctk.CTkFont("Segoe UI Emoji", 20)).place(
            relx=0.5, rely=0.5, anchor="center")

        txt = ctk.CTkFrame(inner, fg_color="transparent")
        txt.pack(side="left")
        ctk.CTkLabel(txt, text="Excel CUID Separator",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(txt, text="Flatten multiple rows per CUID into wide columns with sums",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        # Footer packed first (side=bottom) so the run button never disappears
        footer = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0,
                              border_width=1, border_color=C["border"])
        footer.pack(side="bottom", fill="x")
        foot_inner = ctk.CTkFrame(footer, fg_color="transparent")
        foot_inner.pack(fill="x", padx=20, pady=12)

        self._prog = ctk.CTkProgressBar(foot_inner, height=6, fg_color=C["hover"],
                                        progress_color=C["accent"])
        self._prog.pack(fill="x", pady=(0, 6))
        self._prog.set(0)

        self._stat = ctk.CTkLabel(foot_inner, text="Ready.",
                                  font=ctk.CTkFont("Segoe UI", 11),
                                  text_color=C["muted"], anchor="w")
        self._stat.pack(fill="x", pady=(0, 8))

        self._run_btn = ctk.CTkButton(
            foot_inner, text="▶  Separate & Save",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"],
            border_color=C["accent"], border_width=1,
            corner_radius=24, height=44,
            command=self._start)
        self._run_btn.pack(fill="x")

        # Middle content — fills remaining space; column lists scroll inside it
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(10, 8))

        banner = ctk.CTkFrame(body, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\Excel_CUID_Separator\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"]
        ).pack(anchor="w", padx=14, pady=7)

        top = ctk.CTkFrame(body, fg_color="transparent")
        top.pack(fill="x", pady=(0, 6))

        self._section(top, "Step 1 — Select Excel File")
        fr = ctk.CTkFrame(top, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 6))
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

        self._section(top, "Step 2 — Group-by Column")
        gb = ctk.CTkFrame(top, fg_color="transparent")
        gb.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(gb, text="Column:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 12))
        self._groupby_cb = ctk.CTkComboBox(
            gb, values=["cuid"], width=260, height=34,
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["card"], border_color=C["border"],
            button_color=TINT["mid"], button_hover_color=TINT["bdr"],
            dropdown_fg_color=C["card"], dropdown_hover_color=C["hover"],
            dropdown_text_color=C["text"], text_color=C["text"])
        self._groupby_cb.set("cuid")
        self._groupby_cb.pack(side="left")

        self._section(body, "Step 3 — Select columns")
        cols_row = ctk.CTkFrame(body, fg_color="transparent")
        cols_row.pack(fill="both", expand=True, pady=(0, 6))
        cols_row.columnconfigure(0, weight=1)
        cols_row.columnconfigure(1, weight=1)
        cols_row.rowconfigure(1, weight=1)

        ctk.CTkLabel(cols_row, text="Date columns  (DD-MM-YYYY)",
                     font=ctk.CTkFont("Segoe UI", 11, "bold"),
                     text_color=C["muted"], anchor="w"
                     ).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 4))
        ctk.CTkLabel(cols_row, text="Sum columns  (total per group)",
                     font=ctk.CTkFont("Segoe UI", 11, "bold"),
                     text_color=C["muted"], anchor="w"
                     ).grid(row=0, column=1, sticky="w", padx=(8, 0), pady=(0, 4))

        self._date_frame = ctk.CTkScrollableFrame(
            cols_row, fg_color=C["card"],
            border_width=1, border_color=C["border"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"])
        self._date_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))

        self._sum_frame = ctk.CTkScrollableFrame(
            cols_row, fg_color=C["card"],
            border_width=1, border_color=C["border"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"])
        self._sum_frame.grid(row=1, column=1, sticky="nsew", padx=(8, 0))

        self._date_hint = ctk.CTkLabel(
            self._date_frame, text="Load a file to see columns",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"])
        self._date_hint.pack(anchor="w", padx=12, pady=10)
        self._sum_hint = ctk.CTkLabel(
            self._sum_frame, text="Load a file to see columns",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"])
        self._sum_hint.pack(anchor="w", padx=12, pady=10)

        self._section(body, "Log")
        self._log = ctk.CTkTextbox(body, height=80,
                                   font=ctk.CTkFont("Courier New", 11),
                                   fg_color=C["card"],
                                   border_color=C["border"], border_width=1,
                                   text_color=C["muted"], state="disabled")
        self._log.pack(fill="x")

    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w").pack(fill="x", pady=(6, 2))

    def _write_log(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _fill_checks(self, frame, vars_dict):
        for w in frame.winfo_children():
            w.destroy()
        vars_dict.clear()
        if not self._columns:
            ctk.CTkLabel(frame, text="Load a file to see columns",
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["faint"]).pack(anchor="w", padx=12, pady=10)
            return
        for col in self._columns:
            var = ctk.BooleanVar(value=False)
            vars_dict[col] = var
            ctk.CTkCheckBox(
                frame, text=col, variable=var,
                font=ctk.CTkFont("Segoe UI", 11),
                text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"]
            ).pack(anchor="w", padx=12, pady=3)

    def _pick(self):
        path = filedialog.askopenfilename(
            title="Select Excel file",
            filetypes=[("Excel files", "*.xlsx *.xls")])
        if not path:
            return
        try:
            df = pd.read_excel(path, nrows=0)
            df = clean_column_names(df)
            self._columns = list(df.columns)
            self._file_path = path
            self._file_lbl.configure(
                text=f"{os.path.basename(path)}  ({len(self._columns)} columns)",
                text_color=C["accent"])
            self._fill_checks(self._date_frame, self._date_vars)
            self._fill_checks(self._sum_frame, self._sum_vars)

            self._groupby_cb.configure(values=self._columns)
            lower_map = {c.lower(): c for c in self._columns}
            self._groupby_cb.set(lower_map.get("cuid", self._columns[0]))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load the file:\n{e}")

    def _selected(self, vars_dict):
        return [col for col, var in vars_dict.items() if var.get()]

    def _start(self):
        if not self._file_path:
            messagebox.showwarning("No File", "Please select an Excel file first.")
            return
        groupby = self._groupby_cb.get().strip()
        if not groupby:
            messagebox.showwarning("No Column", "Please select a group-by column.")
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._stat.configure(text="Starting…", text_color=C["muted"])
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run,
            args=(groupby, self._selected(self._date_vars), self._selected(self._sum_vars)),
            daemon=True
        ).start()

    def _run(self, groupby, date_cols, sum_cols):
        out_dir = get_output_dir()
        stem = Path(self._file_path).stem

        def log(msg):
            self.after(0, lambda m=msg: self._write_log(m))

        try:
            log(f"Input     → {self._file_path}")
            log(f"Group by  → {groupby}")
            log(f"Date cols → {', '.join(date_cols) or '(none)'}")
            log(f"Sum cols  → {', '.join(sum_cols) or '(none)'}")
            log(f"Output    → {out_dir}\n")
            self.after(0, lambda: self._prog.set(0.15))

            df = pd.read_excel(self._file_path, dtype=str)
            df = clean_column_names(df)
            log(f"Rows loaded: {len(df):,}  |  Columns: {len(df.columns)}")

            if groupby not in df.columns:
                raise ValueError(
                    f"Column '{groupby}' not found.\n"
                    f"Available: {', '.join(df.columns)}"
                )

            missing_dates = [c for c in date_cols if c not in df.columns]
            missing_sums = [c for c in sum_cols if c not in df.columns]
            if missing_dates or missing_sums:
                raise ValueError(
                    f"Missing columns: {', '.join(missing_dates + missing_sums)}"
                )

            self.after(0, lambda: self._prog.set(0.35))
            df = format_date_columns(df, date_cols)

            for col in sum_cols:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            before_groups = df[groupby].nunique()
            log(f"Unique {groupby} values: {before_groups:,}")
            self.after(0, lambda: self._prog.set(0.55))

            df_separated = create_separate_columns(df, groupby, sum_cols)
            self.after(0, lambda: self._prog.set(0.85))

            out_path = os.path.join(out_dir, f"{stem}_separated.xlsx")
            df_separated.to_excel(out_path, index=False)

            log(f"\nOutput rows:    {len(df_separated):,}")
            log(f"Output columns: {len(df_separated.columns)}")
            log(f"Saved: {out_path}")

            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {len(df):,} rows → {len(df_separated):,} groups.",
                text_color=C["green"]))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Separated {len(df):,} rows into {len(df_separated):,} "
                f"{groupby} group(s).\n\nSaved to:\n{out_path}"
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=f"Error: {e}", text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Separate & Save"))


if __name__ == "__main__":
    ExcelCuidSeparatorApp().mainloop()
