"""
Tool: Photo to Black & White
Convert photos to grayscale while preserving transparency (no black background).
Embeddable Panel + standalone window.
"""

import os
import threading
import subprocess
from pathlib import Path
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "BW_Converter")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#38bdf8", "green":  "#30d158",
    "red":    "#ff375f",
}
TINT = {"bg": "#001e30", "mid": "#00304c", "bdr": "#00456e"}

VALID_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}


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


def _convert_bw(src_path, dst_path):
    """Convert visible area to grayscale, preserve alpha channel if present."""
    from PIL import Image

    img = Image.open(src_path)

    if img.mode == "RGBA":
        r, g, b, a = img.split()
        gray = Image.merge("RGB", (r, g, b)).convert("L")
        final = Image.merge("RGBA", (gray, gray, gray, a))
    elif img.mode == "P":
        img  = img.convert("RGBA")
        r, g, b, a = img.split()
        gray = Image.merge("RGB", (r, g, b)).convert("L")
        final = Image.merge("RGBA", (gray, gray, gray, a))
    else:
        img   = img.convert("RGB")
        gray  = img.convert("L")
        final = gray.convert("RGB")

    final.save(dst_path)


# ─── Embeddable Panel Content ─────────────────────────────────────────────────

class BwConverterPanelContent(ctk.CTkScrollableFrame):

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=C["border"], **kw)
        self._source_path = None   # file or folder
        self._build()

    def _build(self):
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
                     text="📁  Output → Desktop\\OUTPUT\\BW_Converter\\<timestamp>\\",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["accent"]).pack(anchor="w", padx=14, pady=8)

        # Info note
        note = ctk.CTkFrame(self, fg_color=C["card"], corner_radius=8,
                            border_width=1, border_color=C["border"])
        note.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(note,
                     text="ℹ️  Transparent backgrounds (PNG with alpha) are preserved — no black fill.",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w", padx=14, pady=8)

        # Step 1 — Mode
        self._sec("Step 1 — Mode")
        mode_row = ctk.CTkFrame(self, fg_color="transparent")
        mode_row.pack(fill="x", pady=(0, 10))
        self._mode_var = ctk.StringVar(value="folder")
        for lbl, val in [("Single image", "single"), ("Folder of images", "folder")]:
            ctk.CTkRadioButton(
                mode_row, text=lbl, variable=self._mode_var, value=val,
                font=ctk.CTkFont("Segoe UI", 12), text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"],
                border_color=C["border"],
                command=self._on_mode_change
            ).pack(side="left", padx=(0, 28))

        # Step 2 — Source
        self._sec("Step 2 — Select source")
        sr = ctk.CTkFrame(self, fg_color="transparent")
        sr.pack(fill="x", pady=(0, 10))
        self._src_lbl = ctk.CTkLabel(
            sr, text="Nothing selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._src_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(sr, text="Browse…", width=90, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"], command=self._pick).pack(side="right")

        # Step 3 — Run
        self._sec("Step 3 — Run")
        self._run_btn = ctk.CTkButton(
            self, text="▶  Convert to B&W",
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

    def _sec(self, txt):
        ctk.CTkLabel(self, text=txt.upper(),
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["muted"]).pack(anchor="w", pady=(8, 3))

    def _log(self, msg):
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")

    def _set_stat(self, msg, color=None):
        self._stat.configure(text=msg, text_color=color or C["muted"])

    def _on_mode_change(self):
        self._source_path = None
        self._src_lbl.configure(text="Nothing selected", text_color=C["muted"])

    def _pick(self):
        if self._mode_var.get() == "single":
            p = filedialog.askopenfilename(
                title="Select image",
                filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.tiff")])
        else:
            p = filedialog.askdirectory(title="Select folder of images")
        if not p:
            return
        self._source_path = p
        if os.path.isdir(p):
            n = sum(1 for f in os.listdir(p) if Path(f).suffix.lower() in VALID_EXTS)
            self._src_lbl.configure(
                text=f"{os.path.basename(p)}  ({n} images)", text_color=C["text"])
        else:
            self._src_lbl.configure(text=os.path.basename(p), text_color=C["text"])

    def _run(self):
        if not _check_pillow():
            messagebox.showerror("Missing Dependency",
                                 "Pillow is not installed.\n\nRun:  pip install Pillow")
            return
        if not self._source_path:
            messagebox.showwarning("No Source", "Please select an image or folder first.")
            return

        self._run_btn.configure(state="disabled", text="Converting…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        out_dir = get_output_dir()
        mode    = self._mode_var.get()

        try:
            if mode == "single":
                files = [self._source_path]
            else:
                files = [
                    os.path.join(self._source_path, f)
                    for f in os.listdir(self._source_path)
                    if Path(f).suffix.lower() in VALID_EXTS
                ]

            self._log(f"🖼️  Images to convert: {len(files)}\n")
            errors = 0

            for idx, fpath in enumerate(files, 1):
                fname    = os.path.basename(fpath)
                out_name = Path(fname).stem + ".png"
                dst      = os.path.join(out_dir, out_name)
                self.after(0, lambda v=idx / len(files) * 0.95: self._prog.set(v))
                try:
                    _convert_bw(fpath, dst)
                    self._log(f"[{idx}/{len(files)}]  ✅  {fname}  →  {out_name}")
                except Exception as e:
                    self._log(f"[{idx}/{len(files)}]  ❌  {fname}  →  {e}")
                    errors += 1

            self.after(0, lambda: self._prog.set(1))
            ok = len(files) - errors
            self._log(f"\n🏁 Done!  {ok} converted · {errors} failed → {out_dir}")
            self.after(0, lambda: self._set_stat(
                f"Done! {ok} image(s) converted.", C["green"]))
            subprocess.Popen(["explorer", out_dir])

        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Convert to B&W"))


# ─── Embeddable Panel wrapper ─────────────────────────────────────────────────
class BwConverterPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        BwConverterPanelContent(self).pack(fill="both", expand=True, padx=16, pady=8)


# ─── Standalone App ───────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Photo B&W Converter")
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
        ctk.CTkLabel(icon_f, text="🔲",
                     font=ctk.CTkFont("Segoe UI Emoji", 20)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(tx, text="Photo B&W Converter",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx, text="Convert photos to grayscale · transparency preserved · no black fill",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        BwConverterPanelContent(self).pack(fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
