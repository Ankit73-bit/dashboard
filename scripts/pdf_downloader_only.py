"""
Tool: PDF Downloader (No Rename)
Reads an Excel file with a URL column,
downloads each PDF keeping the original filename from the URL.
All output goes to: Desktop/OUTPUT/PDF_Downloads_Only/<timestamp>/
"""

import pandas as pd
import requests
import os
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox
from datetime import datetime
from urllib.parse import urlparse

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "PDF_Downloads_Only")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "accent": "#00f5ff", "text":   "#e8e8f0",
    "muted":  "#8888aa", "red":    "#ff375f", "tint":   "#062d30",
}

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF Downloader (No Rename)")
        self.geometry("720x640")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self._path = None
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text="📄  PDF Downloader",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["accent"]).pack(side="left", padx=24, pady=16)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        ob = ctk.CTkFrame(body, fg_color=C["tint"], corner_radius=10,
                          border_width=1, border_color=C["accent"])
        ob.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(ob, text="📁  All files will be saved to:",
                     font=ctk.CTkFont("Segoe UI", 11, "bold"),
                     text_color=C["accent"]).pack(anchor="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(ob, text=BASE_OUT + "\\<timestamp>\\",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["text"]).pack(anchor="w", padx=14, pady=(0, 10))

        self._section(body, "Step 1 — Select Excel File")
        fr = ctk.CTkFrame(body, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 14))
        self.file_lbl = ctk.CTkLabel(fr, text="No file selected",
                                     font=ctk.CTkFont("Segoe UI", 12),
                                     text_color=C["muted"], anchor="w")
        self.file_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(fr, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"], command=self._pick).pack(side="right")

        self._section(body, "Step 2 — Column Names")
        gr = ctk.CTkFrame(body, fg_color="transparent")
        gr.pack(fill="x", pady=(0, 6))
        for lbl, attr, default, col in [
            ("URL Column", "url_e",   "url",    0),
            ("Sheet Name", "sheet_e", "Sheet1", 1),
        ]:
            c = ctk.CTkFrame(gr, fg_color="transparent")
            c.grid(row=0, column=col, padx=(0, 16))
            ctk.CTkLabel(c, text=lbl, font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["muted"]).pack(anchor="w")
            e = ctk.CTkEntry(c, placeholder_text=default, fg_color=C["card"],
                             border_color=C["border"], text_color=C["text"],
                             height=34, width=200)
            e.insert(0, default)
            e.pack()
            setattr(self, attr, e)

        self._section(body, "Step 3 — Run")
        self.run_btn = ctk.CTkButton(
            body, text="▶  Start Download",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=C["tint"], hover_color="#0a4a4e",
            border_color=C["accent"], border_width=1,
            text_color=C["accent"], height=44, command=self._run)
        self.run_btn.pack(fill="x", pady=(0, 12))

        self.prog = ctk.CTkProgressBar(body, fg_color=C["card"],
                                       progress_color=C["accent"], height=8)
        self.prog.set(0)
        self.prog.pack(fill="x", pady=(0, 6))

        self.stat = ctk.CTkLabel(body, text="Ready.",
                                 font=ctk.CTkFont("Segoe UI", 11),
                                 text_color=C["muted"], anchor="w")
        self.stat.pack(fill="x", pady=(0, 12))

        self._section(body, "Log")
        self.log = ctk.CTkTextbox(body, height=160, fg_color=C["card"],
                                  border_color=C["border"], border_width=1,
                                  text_color=C["text"],
                                  font=ctk.CTkFont("Consolas", 11))
        self.log.pack(fill="both", expand=True)

    def _section(self, p, t):
        ctk.CTkLabel(p, text=t.upper(),
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["muted"]).pack(anchor="w", pady=(10, 4))

    def _pick(self):
        p = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx *.xls")])
        if p:
            self._path = p
            self.file_lbl.configure(text=os.path.basename(p), text_color=C["text"])

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
                # Use filename from URL, fallback to row number
                fname = os.path.basename(urlparse(url).path) or f"file_{i}.pdf"
                if not fname.endswith(".pdf"):
                    fname += ".pdf"
                dst = os.path.join(out_dir, fname)

                self.after(0, lambda p=(i+1)/total: self.prog.set(p))
                self.after(0, lambda a=i+1, b=total: self.stat.configure(
                    text=f"Processing {a} / {b}…"))

                if not url.lower().startswith("http"):
                    self._log(f"⚠️  Skipped (bad URL) row {i+1}")
                    fail += 1
                    continue
                try:
                    r = requests.get(url, timeout=15)
                    r.raise_for_status()
                    with open(dst, "wb") as f:
                        f.write(r.content)
                    self._log(f"✅ {fname}")
                    ok += 1
                except Exception as e:
                    self._log(f"❌ Row {i+1} — {e}")
                    fail += 1

            self.after(0, lambda: self.prog.set(1))
            self.after(0, lambda: self.stat.configure(
                text=f"Done!  ✅ {ok} downloaded   ❌ {fail} failed",
                text_color=C["accent"]))
            self._log(f"\n🏁 Finished — {ok} ok, {fail} failed")
            self._log(f"📁 Saved to: {out_dir}")

        except Exception as e:
            self._log(f"\n💥 Error: {e}")
            self.after(0, lambda: self.stat.configure(
                text=f"Error: {e}", text_color=C["red"]))
        finally:
            self.after(0, lambda: self.run_btn.configure(
                state="normal", text="▶  Start Download"))


if __name__ == "__main__":
    App().mainloop()
