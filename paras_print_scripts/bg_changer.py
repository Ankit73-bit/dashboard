"""
Tool: BG Changer
Resize photos to exact mm size, remove background with AI (rembg),
and apply any solid colour background.
Embeddable Panel + standalone window.
"""

import os
import threading
import subprocess
from pathlib import Path
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox, colorchooser

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "BG_Changer")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#00c7a8", "green":  "#30d158",
    "red":    "#ff375f",
}
TINT = {"bg": "#042820", "mid": "#084038", "bdr": "#0c5c50"}

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}

# Preset background swatches: (label, hex)
PRESETS = [
    ("⬜ White",   "#FFFFFF"),
    ("🟥 Red",     "#FF0000"),
    ("🟦 Blue",    "#003399"),
    ("🟨 Yellow",  "#FFD700"),
    ("⬛ Black",   "#000000"),
    ("🩶 Grey",    "#808080"),
    ("🟩 Green",   "#008000"),
    ("🟫 Brown",   "#8B4513"),
]


def get_output_dir():
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def _check_deps():
    missing = []
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        missing.append("Pillow  →  pip install Pillow")
    try:
        from rembg import remove  # noqa: F401
    except ImportError:
        missing.append("rembg   →  pip install rembg")
    return missing


# ─── Embeddable Panel Content ─────────────────────────────────────────────────

class BgChangerPanelContent(ctk.CTkScrollableFrame):

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=C["border"], **kw)
        self._photos_folder = None
        self._hex_color     = "#FFFFFF"
        self._build()

    def _build(self):
        # Dependency warnings
        missing = _check_deps()
        if missing:
            warn = ctk.CTkFrame(self, fg_color="#300a14", corner_radius=10,
                                border_width=1, border_color=C["red"])
            warn.pack(fill="x", pady=(4, 10))
            ctk.CTkLabel(warn,
                         text="⚠️  Missing dependencies:\n" + "\n".join(missing),
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["red"], justify="left"
                         ).pack(anchor="w", padx=14, pady=8)

        # Output banner
        banner = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(4, 14))
        ctk.CTkLabel(banner,
                     text="📁  Output → Desktop\\OUTPUT\\BG_Changer\\<timestamp>\\output\\",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["accent"]).pack(anchor="w", padx=14, pady=8)

        # Step 1 — Photos folder
        self._sec("Step 1 — Select photos folder")
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
                      command=self._pick_folder).pack(side="right")

        # Step 2 — Size & DPI
        self._sec("Step 2 — Target size & DPI")
        dims = ctk.CTkFrame(self, fg_color="transparent")
        dims.pack(fill="x", pady=(0, 10))

        for label, var_name, default, width in [
            ("Width (mm):", "_width_var",  "24",  70),
            ("Height (mm):", "_height_var", "28",  70),
            ("DPI:",         "_dpi_var",    "300", 70),
        ]:
            ctk.CTkLabel(dims, text=label,
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["muted"]).pack(side="left", padx=(0, 4))
            var = ctk.StringVar(value=default)
            setattr(self, var_name, var)
            ctk.CTkEntry(dims, textvariable=var,
                         fg_color=C["card"], border_color=C["border"],
                         text_color=C["text"], height=34, width=width
                         ).pack(side="left", padx=(0, 16))

        # Step 3 — Background colour
        self._sec("Step 3 — Background colour")

        # Swatch grid
        swatch_outer = ctk.CTkFrame(self, fg_color="transparent")
        swatch_outer.pack(fill="x", pady=(0, 8))
        for i, (label, hex_val) in enumerate(PRESETS):
            ctk.CTkButton(
                swatch_outer, text=label, width=110, height=32,
                font=ctk.CTkFont("Segoe UI", 11),
                fg_color=C["card"], hover_color=C["hover"],
                border_color=C["border"], border_width=1,
                text_color=C["text"],
                command=lambda h=hex_val: self._set_color(h)
            ).grid(row=i // 4, column=i % 4, padx=4, pady=3, sticky="ew")
        for col in range(4):
            swatch_outer.columnconfigure(col, weight=1)

        # Custom hex row
        custom_row = ctk.CTkFrame(self, fg_color="transparent")
        custom_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(custom_row, text="Custom hex:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 8))
        self._hex_var = ctk.StringVar(value="#FFFFFF")
        ctk.CTkEntry(custom_row, textvariable=self._hex_var,
                     fg_color=C["card"], border_color=C["border"],
                     text_color=C["text"], height=34, width=110
                     ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(custom_row, text="🎨 Pick colour", width=120, height=34,
                      fg_color=C["card"], hover_color=C["hover"],
                      border_color=C["border"], border_width=1,
                      text_color=C["text"],
                      command=self._pick_color).pack(side="left", padx=(0, 12))
        # Preview swatch
        self._preview = ctk.CTkFrame(custom_row, width=34, height=34,
                                     fg_color="#FFFFFF", corner_radius=6,
                                     border_width=1, border_color=C["border"])
        self._preview.pack(side="left")

        # Step 4 — Run
        self._sec("Step 4 — Run")
        self._run_btn = ctk.CTkButton(
            self, text="▶  Change Background",
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

    def _set_color(self, hex_val):
        self._hex_color = hex_val
        self._hex_var.set(hex_val)
        self._preview.configure(fg_color=hex_val)

    def _pick_color(self):
        result = colorchooser.askcolor(color=self._hex_color, title="Pick Background Colour")
        if result and result[1]:
            self._set_color(result[1].upper())

    def _pick_folder(self):
        p = filedialog.askdirectory(title="Select photos folder")
        if p:
            self._photos_folder = p
            n = sum(1 for f in os.listdir(p)
                    if Path(f).suffix.lower() in PHOTO_EXTS)
            self._photos_lbl.configure(
                text=f"{os.path.basename(p)}  ({n} image(s) detected)",
                text_color=C["text"])

    def _run(self):
        missing = _check_deps()
        if missing:
            messagebox.showerror("Missing Dependencies",
                                 "Install missing packages:\n\n" + "\n".join(missing))
            return
        if not self._photos_folder:
            messagebox.showwarning("No Folder", "Please select a photos folder first.")
            return
        try:
            w   = float(self._width_var.get())
            h   = float(self._height_var.get())
            dpi = int(self._dpi_var.get())
        except ValueError:
            messagebox.showwarning("Bad Values",
                                   "Width, height, and DPI must be numbers.")
            return
        hex_color = self._hex_var.get().strip()
        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color
        self._hex_color = hex_color
        self._preview.configure(fg_color=hex_color)

        self._run_btn.configure(state="disabled", text="Processing…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(
            target=self._process,
            args=(w, h, dpi, hex_color),
            daemon=True).start()

    def _process(self, width_mm, height_mm, dpi, hex_color):
        from PIL import Image, ImageColor
        from rembg import remove

        out_dir     = get_output_dir()
        resize_dir  = os.path.join(out_dir, "_resized_temp")
        masked_dir  = os.path.join(out_dir, "_masked_temp")
        output_dir  = os.path.join(out_dir, "output")
        for d in [resize_dir, masked_dir, output_dir]:
            os.makedirs(d, exist_ok=True)

        target_w = int(width_mm  * dpi / 25.4)
        target_h = int(height_mm * dpi / 25.4)
        bg_rgb   = ImageColor.getrgb(hex_color)

        photos = [
            f for f in os.listdir(self._photos_folder)
            if Path(f).suffix.lower() in PHOTO_EXTS
        ]

        self._log(f"📂 Photos folder:  {os.path.basename(self._photos_folder)}")
        self._log(f"📐 Target size:    {width_mm}×{height_mm} mm  @  {dpi} DPI  "
                  f"→  {target_w}×{target_h} px")
        self._log(f"🎨 BG colour:      {hex_color}")
        self._log(f"🖼️  Images found:   {len(photos)}\n")

        ok = 0
        errors = []

        try:
            for idx, fname in enumerate(photos, 1):
                self._log(f"[{idx}/{len(photos)}]  {fname}")
                self.after(0, lambda v=idx / len(photos) * 0.9: self._prog.set(v))

                try:
                    src = os.path.join(self._photos_folder, fname)

                    # ── Step A: Resize ─────────────────────────────────────
                    with Image.open(src) as img:
                        if img.mode == "RGBA":
                            img = img.convert("RGB")
                        resized = img.resize((target_w, target_h), Image.LANCZOS)
                        resize_path = os.path.join(resize_dir, fname)
                        resized.save(resize_path)

                    # ── Step B: Remove background ──────────────────────────
                    masked_path = os.path.join(masked_dir, Path(fname).stem + ".png")
                    with open(resize_path, "rb") as f_in:
                        subject = remove(
                            f_in.read(),
                            alpha_matting=True,
                            alpha_matting_foreground_threshold=50,
                            discard_threshold=1e-5,
                            shift=1e-1,
                        )
                    with open(masked_path, "wb") as f_out:
                        f_out.write(subject)

                    # ── Step C: Composite onto solid colour ────────────────
                    bg   = Image.new("RGBA", (target_w, target_h),
                                     bg_rgb + (255,))
                    fg   = Image.open(masked_path).convert("RGBA")
                    fg   = fg.resize((target_w, target_h), Image.LANCZOS)
                    comp = Image.alpha_composite(bg, fg)

                    out_name = Path(fname).stem + ".png"
                    comp.save(os.path.join(output_dir, out_name), "PNG")
                    self._log(f"   ✅  Saved: {out_name}")
                    ok += 1

                except Exception as e:
                    self._log(f"   ❌  Error: {e}")
                    errors.append(fname)

            self.after(0, lambda: self._prog.set(1))
            self._log(f"\n🏁 Done!  {ok} succeeded  ·  {len(errors)} failed  →  {output_dir}")
            self.after(0, lambda: self._set_stat(
                f"Done! {ok} image(s) processed · {len(errors)} error(s).", C["green"]))
            subprocess.Popen(["explorer", output_dir])

        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Fatal error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Change Background"))


# ─── Embeddable Panel wrapper ─────────────────────────────────────────────────
class BgChangerPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        BgChangerPanelContent(self).pack(fill="both", expand=True, padx=16, pady=8)


# ─── Standalone App ───────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("BG Changer")
        self.geometry("820x860")
        self.configure(fg_color=C["bg"])

        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)

        icon_f = ctk.CTkFrame(inn, width=44, height=44,
                              fg_color=TINT["mid"], corner_radius=10)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🎨",
                     font=ctk.CTkFont("Segoe UI Emoji", 20)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(tx, text="BG Changer",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx,
                     text="Resize → AI background removal (rembg) → solid colour composite",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        BgChangerPanelContent(self).pack(fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
