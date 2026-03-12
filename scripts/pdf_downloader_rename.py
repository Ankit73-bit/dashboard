"""
Tool: PDF Downloader & Renamer
Embeddable panel + standalone window support.
"""

import pandas as pd
import requests
import os
import threading
import base64
import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "PDF_Downloads_Renamed")

C = {
    "bg":    "#0a0a0f", "card":  "#16161f", "hover": "#1e1e2e",
    "bdr":   "#2a2a3d", "acc":   "#30d158", "text":  "#e8e8f0",
    "muted": "#8888aa", "red":   "#ff375f", "tint":  "#082a12",
    "tint2": "#0f4020", "sidebar": "#111118",
}

SAMPLE_B64 = "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"


# ─── Embeddable Panel ─────────────────────────────────────────────────────────
class PDFDownloadRenamePanelContent(ctk.CTkScrollableFrame):
    """The actual tool UI — embeddable inside any parent frame."""
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=C["bdr"], **kw)
        self._path = None
        self._build()

    def _build(self):
        # Output banner
        ob = ctk.CTkFrame(self, fg_color=C["tint"], corner_radius=10,
                          border_width=1, border_color=C["acc"])
        ob.pack(fill="x", pady=(4, 12), padx=2)
        ctk.CTkLabel(ob, text="📁  Output → Desktop\\OUTPUT\\PDF_Downloads_Renamed\\<timestamp>\\",
                     font=ctk.CTkFont("Segoe UI", 11), text_color=C["acc"]
                     ).pack(anchor="w", padx=14, pady=8)

        # Step 1
        self._sec("Step 1 — Select your Excel file")
        fr = ctk.CTkFrame(self, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 10))
        self.file_lbl = ctk.CTkLabel(fr, text="No file selected",
                                     font=ctk.CTkFont("Segoe UI", 12),
                                     text_color=C["muted"], anchor="w")
        self.file_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(fr, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["bdr"], border_width=1,
                      text_color=C["text"], command=self._pick).pack(side="right")

        # Step 2
        self._sec("Step 2 — Column names in your Excel")
        gr = ctk.CTkFrame(self, fg_color="transparent")
        gr.pack(fill="x", pady=(0, 4))
        for lbl, attr, default, col in [
            ("URL Column",  "url_e",   "url",         0),
            ("ID Column",   "id_e",    "prospect_no", 1),
            ("Sheet Name",  "sheet_e", "Sheet1",      2),
        ]:
            c = ctk.CTkFrame(gr, fg_color="transparent")
            c.grid(row=0, column=col, padx=(0, 14))
            ctk.CTkLabel(c, text=lbl, font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["muted"]).pack(anchor="w")
            e = ctk.CTkEntry(c, placeholder_text=default, fg_color=C["card"],
                             border_color=C["bdr"], text_color=C["text"],
                             height=34, width=180)
            e.insert(0, default)
            e.pack()
            setattr(self, attr, e)

        # Sample button
        ctk.CTkButton(self, text="📥  Download Sample Excel",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["bdr"], border_width=1,
                      text_color=C["muted"], height=36,
                      command=self._save_sample).pack(fill="x", pady=(4, 10))

        # Step 3
        self._sec("Step 3 — Run")
        self.run_btn = ctk.CTkButton(
            self, text="▶  Start Download & Rename",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=C["tint"], hover_color=C["tint2"],
            border_color=C["acc"], border_width=1,
            text_color=C["acc"], height=44, command=self._run)
        self.run_btn.pack(fill="x", pady=(0, 10))

        self.prog = ctk.CTkProgressBar(self, fg_color=C["card"],
                                       progress_color=C["acc"], height=8)
        self.prog.set(0)
        self.prog.pack(fill="x", pady=(0, 4))
        self.stat = ctk.CTkLabel(self, text="Ready.",
                                 font=ctk.CTkFont("Segoe UI", 11),
                                 text_color=C["muted"], anchor="w")
        self.stat.pack(fill="x", pady=(0, 10))

        self._sec("Log")
        self.log = ctk.CTkTextbox(self, height=200, fg_color=C["card"],
                                  border_color=C["bdr"], border_width=1,
                                  text_color=C["text"],
                                  font=ctk.CTkFont("Consolas", 11))
        self.log.pack(fill="both", expand=True, pady=(0, 16))

    def _sec(self, t):
        ctk.CTkLabel(self, text=t.upper(),
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["muted"]).pack(anchor="w", pady=(8, 3))

    def _pick(self):
        p = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if p:
            self._path = p
            self.file_lbl.configure(text=os.path.basename(p), text_color=C["text"])

    def _save_sample(self):
        dest = filedialog.asksaveasfilename(
            title="Save Sample File As",
            defaultextension=".xlsx",
            initialfile="sample_pdf_download_rename.xlsx",
            filetypes=[("Excel files", "*.xlsx")]
        )
        if dest:
            try:
                with open(dest, "wb") as f:
                    f.write(base64.b64decode(SAMPLE_B64))
                messagebox.showinfo("✅ Sample Saved", f"Saved to:\n{dest}")
            except Exception as e:
                messagebox.showerror("Error", f"Could not save sample:\n{e}")

    def _log(self, msg):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def _run(self):
        if not self._path:
            messagebox.showwarning("No File", "Please select an Excel file first.")
            return
        self.run_btn.configure(state="disabled", text="Running…")
        self.log.delete("1.0", "end")
        self.prog.set(0)
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        try:
            url_col = self.url_e.get().strip()
            id_col  = self.id_e.get().strip()
            sheet   = self.sheet_e.get().strip()
            ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = os.path.join(BASE_OUT, ts)
            os.makedirs(out_dir, exist_ok=True)
            self._log(f"📂 Saving to: {out_dir}")
            df    = pd.read_excel(self._path, sheet_name=sheet)
            total = len(df)
            ok = fail = 0
            for i, (_, row) in enumerate(df.iterrows()):
                url = str(row.get(url_col, "")).strip()
                rid = str(row.get(id_col,  f"row_{i}")).strip()
                dst = os.path.join(out_dir, f"{rid}.pdf")
                self.after(0, lambda p=(i+1)/total: self.prog.set(p))
                self.after(0, lambda a=i+1, b=total: self.stat.configure(text=f"Processing {a} / {b}…"))
                if not url.lower().startswith("http"):
                    self._log(f"⚠️  Skipped (bad URL): {rid}")
                    fail += 1
                    continue
                try:
                    r = requests.get(url, timeout=15)
                    r.raise_for_status()
                    with open(dst, "wb") as f:
                        f.write(r.content)
                    self._log(f"✅ {rid}.pdf")
                    ok += 1
                except Exception as e:
                    self._log(f"❌ {rid} — {e}")
                    fail += 1
            self.after(0, lambda: self.prog.set(1))
            self.after(0, lambda: self.stat.configure(
                text=f"Done!  ✅ {ok} downloaded   ❌ {fail} failed", text_color=C["acc"]))
            self._log(f"\n🏁 Finished — {ok} ok, {fail} failed\n📁 {out_dir}")
            import subprocess
            subprocess.Popen(["explorer", out_dir])
        except Exception as e:
            self._log(f"\n💥 Error: {e}")
            self.after(0, lambda: self.stat.configure(text=f"Error: {e}", text_color=C["red"]))
        finally:
            self.after(0, lambda: self.run_btn.configure(
                state="normal", text="▶  Start Download & Rename"))


# ─── Standalone window (for direct launch) ────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF Downloader & Renamer")
        self.geometry("800x750")
        self.configure(fg_color=C["bg"])
        hdr = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="⚡  PDF Downloader & Renamer",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["acc"]).pack(side="left", padx=24, pady=14)
        PDFDownloadRenamePanelContent(self).pack(fill="both", expand=True, padx=16, pady=8)

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    App().mainloop()
