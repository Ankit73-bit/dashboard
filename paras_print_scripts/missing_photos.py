"""
Tool: Missing Photos
Find files present in SOURCE but absent in EDITED — copy them to output.
Embeddable Panel + standalone window.
"""

import os
import shutil
import threading
import subprocess
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Missing_Photos")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#ff375f", "green":  "#30d158",
    "red":    "#ff375f",
}
TINT = {"bg": "#300a14", "mid": "#4e1020", "bdr": "#701830"}


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


# ─── Embeddable Panel Content ─────────────────────────────────────────────────

class MissingPhotosPanelContent(ctk.CTkScrollableFrame):

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=C["border"], **kw)
        self._source_folder = None
        self._edited_folder = None
        self._build()

    def _build(self):
        # Output banner
        banner = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(4, 14))
        ctk.CTkLabel(banner,
                     text="📁  Output → Desktop\\OUTPUT\\Missing_Photos\\<timestamp>\\",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["accent"]).pack(anchor="w", padx=14, pady=8)

        # Info note
        note = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=8,
                            border_width=1, border_color=C["border"])
        note.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(note,
                     text="ℹ️  Compares folders by filename. Files in SOURCE but not in EDITED are copied out.",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"], justify="left"
                     ).pack(anchor="w", padx=14, pady=8)

        # Step 1 — Source folder
        self._sec("Step 1 — SOURCE folder (original / unedited)")
        sr = ctk.CTkFrame(self, fg_color="transparent")
        sr.pack(fill="x", pady=(0, 10))
        self._src_lbl = ctk.CTkLabel(
            sr, text="No folder selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._src_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(sr, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"],
                      command=self._pick_source).pack(side="right")

        # Step 2 — Edited folder
        self._sec("Step 2 — EDITED folder (processed / output)")
        er = ctk.CTkFrame(self, fg_color="transparent")
        er.pack(fill="x", pady=(0, 10))
        self._edited_lbl = ctk.CTkLabel(
            er, text="No folder selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._edited_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(er, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"],
                      command=self._pick_edited).pack(side="right")

        # Step 3 — Run
        self._sec("Step 3 — Run")
        self._run_btn = ctk.CTkButton(
            self, text="▶  Find & Copy Missing",
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

    def _sec(self, t):
        ctk.CTkLabel(self, text=t.upper(),
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["muted"]).pack(anchor="w", pady=(8, 3))

    def _log(self, msg):
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")

    def _set_stat(self, msg, color=None):
        self._stat.configure(text=msg, text_color=color or C["muted"])

    def _pick_source(self):
        p = filedialog.askdirectory(title="Select SOURCE folder")
        if p:
            self._source_folder = p
            n = len(os.listdir(p))
            self._src_lbl.configure(
                text=f"{os.path.basename(p)}  ({n} files)", text_color=C["text"])

    def _pick_edited(self):
        p = filedialog.askdirectory(title="Select EDITED folder")
        if p:
            self._edited_folder = p
            n = len(os.listdir(p))
            self._edited_lbl.configure(
                text=f"{os.path.basename(p)}  ({n} files)", text_color=C["text"])

    def _run(self):
        if not self._source_folder:
            messagebox.showwarning("Missing", "Please select the SOURCE folder.")
            return
        if not self._edited_folder:
            messagebox.showwarning("Missing", "Please select the EDITED folder.")
            return
        self._run_btn.configure(state="disabled", text="Scanning…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        out_dir = get_output_dir()
        try:
            source_files = set(os.listdir(self._source_folder))
            edited_files = set(os.listdir(self._edited_folder))
            missing      = sorted(source_files - edited_files)

            self._log(f"📂 Source files:  {len(source_files)}")
            self._log(f"✏️  Edited files:  {len(edited_files)}")
            self._log(f"🔍 Missing:       {len(missing)}\n")
            self.after(0, lambda: self._prog.set(0.2))

            if not missing:
                self._log("✅  All files accounted for — nothing to copy.")
                self.after(0, lambda: self._prog.set(1))
                self.after(0, lambda: self._set_stat(
                    "All files accounted for. Nothing missing.", C["green"]))
                return

            for idx, fname in enumerate(missing, 1):
                src = os.path.join(self._source_folder, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, os.path.join(out_dir, fname))
                    self._log(f"   📄 Copied: {fname}")
                self.after(0, lambda v=0.2 + 0.8 * idx / len(missing): self._prog.set(v))

            self.after(0, lambda: self._prog.set(1))
            self._log(f"\n🏁 Done!  {len(missing)} missing file(s) → {out_dir}")
            self.after(0, lambda: self._set_stat(
                f"Done! {len(missing)} missing file(s) copied.", C["green"]))
            subprocess.Popen(["explorer", out_dir])

        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Find & Copy Missing"))


# ─── Embeddable Panel wrapper ─────────────────────────────────────────────────
class MissingPhotosPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        MissingPhotosPanelContent(self).pack(fill="both", expand=True, padx=16, pady=8)


# ─── Standalone App ───────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Missing Photos")
        self.geometry("800x680")
        self.configure(fg_color=C["bg"])

        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)

        icon_f = ctk.CTkFrame(inn, width=44, height=44,
                              fg_color=TINT["mid"], corner_radius=10)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🔍",
                     font=ctk.CTkFont("Segoe UI Emoji", 20)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(tx, text="Missing Photos",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx, text="Find files in SOURCE missing from EDITED and copy them out",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        MissingPhotosPanelContent(self).pack(fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
