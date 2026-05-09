"""
Tool: Photo Background Changer
Resize photos to exact mm dimensions, remove background with rembg, and apply a new solid colour.
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

# Built-in quick-select background colours
PRESET_COLOURS = [
    ("#FFFFFF", "White"),
    ("#000000", "Black"),
    ("#FF0000", "Red"),
    ("#0000FF", "Blue"),
    ("#008000", "Green"),
    ("#FFD700", "Gold"),
    ("#808080", "Gray"),
    ("#FFA500", "Orange"),
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
        missing.append("Pillow  (pip install Pillow)")
    try:
        from rembg import remove  # noqa: F401
    except ImportError:
        missing.append("rembg  (pip install rembg)")
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
                         text="⚠️  Missing dependencies:\n" + "\n".join(f"   • {m}" for m in missing),
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["red"], justify="left"
                         ).pack(anchor="w", padx=14, pady=8)

        # Output banner
        banner = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(4, 14))
        ctk.CTkLabel(banner,
                     text="📁  Output → Desktop\\OUTPUT\\BG_Changer\\<timestamp>\\",
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
                      command=self._pick_photos).pack(side="right")

        # Step 2 — Resize dimensions
        self._sec("Step 2 — Target size (mm) & DPI")
        dim_row = ctk.CTkFrame(self, fg_color="transparent")
        dim_row.pack(fill="x", pady=(0, 10))

        for label, var_name, default, width in [
            ("Width (mm)",  "_w_var",   "24",  70),
            ("Height (mm)", "_h_var",   "28",  70),
            ("DPI",         "_dpi_var", "300", 70),
        ]:
            grp = ctk.CTkFrame(dim_row, fg_color="transparent")
            grp.pack(side="left", padx=(0, 20))
            ctk.CTkLabel(grp, text=label,
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color=C["muted"]).pack(anchor="w")
            setattr(self, var_name, ctk.StringVar(value=default))
            ctk.CTkEntry(grp, textvariable=getattr(self, var_name),
                         fg_color=C["card"], border_color=C["border"],
                         text_color=C["text"], height=34, width=width
                         ).pack()

        # Step 3 — Background colour
        self._sec("Step 3 — Background colour")

        # Preset swatches
        swatch_row = ctk.CTkFrame(self, fg_color="transparent")
        swatch_row.pack(fill="x", pady=(0, 8))
        self._swatch_btns = []
        for hex_c, name in PRESET_COLOURS:
            btn = ctk.CTkButton(
                swatch_row, text=name, width=72, height=30,
                font=ctk.CTkFont("Segoe UI", 10, "bold"),
                fg_color=hex_c,
                hover_color=hex_c,
                text_color="#000000" if hex_c in ("#FFFFFF", "#FFD700", "#FFA500") else "#ffffff",
                corner_radius=6,
                command=lambda h=hex_c: self._set_color(h))
            btn.pack(side="left", padx=(0, 6))
            self._swatch_btns.append(btn)

        # Custom colour row
        custom_row = ctk.CTkFrame(self, fg_color="transparent")
        custom_row.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(custom_row, text="Custom hex:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=(0, 10))
        self._hex_var = ctk.StringVar(value="#FFFFFF")
        self._hex_entry = ctk.CTkEntry(
            custom_row, textvariable=self._hex_var,
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"], height=34, width=110)
        self._hex_entry.pack(side="left")
        ctk.CTkButton(
            custom_row, text="Pick colour…", width=110, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"],
            command=self._pick_color
        ).pack(side="left", padx=(8, 0))

        # Live preview swatch
        self._preview_frame = ctk.CTkFrame(
            custom_row, width=34, height=34,
            fg_color=self._hex_color, corner_radius=6,
            border_width=1, border_color=C["border"])
        self._preview_frame.pack(side="left", padx=(10, 0))
        self._preview_frame.pack_propagate(False)

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
    def _sec(self, txt):
        ctk.CTkLabel(self, text=txt.upper(),
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
            n = sum(1 for f in os.listdir(p)
                    if Path(f).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"})
            self._photos_lbl.configure(
                text=f"{os.path.basename(p)}  ({n} images)",
                text_color=C["text"])

    def _set_color(self, hex_c):
        self._hex_color = hex_c
        self._hex_var.set(hex_c)
        try:
            self._preview_frame.configure(fg_color=hex_c)
        except Exception:
            pass

    def _pick_color(self):
        result = colorchooser.askcolor(color=self._hex_color, title="Pick background colour")
        if result and result[1]:
            self._set_color(result[1].upper())

    # ── Run ────────────────────────────────────────────────────────────────────
    def _run(self):
        missing = _check_deps()
        if missing:
            messagebox.showerror("Missing Dependencies",
                                 "Install required packages first:\n\n" +
                                 "\n".join(f"  • {m}" for m in missing))
            return
        if not self._photos_folder:
            messagebox.showwarning("No Folder", "Please select a photos folder first.")
            return
        hex_c = self._hex_var.get().strip()
        if not hex_c.startswith("#") or len(hex_c) not in (4, 7):
            messagebox.showwarning("Bad Colour", "Enter a valid hex colour (e.g. #FFFFFF).")
            return
        try:
            w   = float(self._w_var.get())
            h   = float(self._h_var.get())
            dpi = int(self._dpi_var.get())
        except ValueError:
            messagebox.showwarning("Bad Values", "Width, height and DPI must be numbers.")
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        self._hex_color = hex_c
        threading.Thread(
            target=self._process, args=(hex_c, w, h, dpi), daemon=True).start()

    def _process(self, hex_c, w_mm, h_mm, dpi):
        from PIL import Image, ImageColor
        from rembg import remove

        out_dir    = get_output_dir()
        masked_dir = os.path.join(out_dir, "_masked_temp")
        resize_dir = os.path.join(out_dir, "_resized_temp")
        final_dir  = os.path.join(out_dir, "output")
        for d in (masked_dir, resize_dir, final_dir):
            os.makedirs(d, exist_ok=True)

        bg_rgb = ImageColor.getrgb(hex_c)
        w_px   = int(w_mm * dpi / 25.4)
        h_px   = int(h_mm * dpi / 25.4)

        photos = [f for f in os.listdir(self._photos_folder)
                  if Path(f).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}]

        try:
            self._log(f"📂 Folder:   {os.path.basename(self._photos_folder)}")
            self._log(f"🖼️  Images:   {len(photos)}")
            self._log(f"📐 Size:      {w_mm}mm × {h_mm}mm @ {dpi} DPI  →  {w_px}×{h_px}px")
            self._log(f"🎨 BG colour: {hex_c}\n")

            errors = 0
            for idx, fname in enumerate(photos, 1):
                src = os.path.join(self._photos_folder, fname)
                self._log(f"[{idx}/{len(photos)}]  {fname}")
                self.after(0, lambda v=idx / len(photos) * 0.95: self._prog.set(v))

                try:
                    # ── Step A: resize ─────────────────────────────────────
                    with Image.open(src) as img:
                        if img.mode == "RGBA":
                            img = img.convert("RGB")
                        resized = img.resize((w_px, h_px), Image.LANCZOS)
                        resize_path = os.path.join(resize_dir, fname)
                        resized.save(resize_path)

                    # ── Step B: remove background ──────────────────────────
                    masked_path = os.path.join(masked_dir, Path(fname).stem + ".png")
                    with open(resize_path, "rb") as f:
                        raw = f.read()
                    subject = remove(
                        raw,
                        alpha_matting=True,
                        alpha_matting_foreground_threshold=50,
                        post_process_mask=True,
                    )
                    with open(masked_path, "wb") as f:
                        f.write(subject)

                    # ── Step C: composite on new background ────────────────
                    bg   = Image.new("RGBA", (w_px, h_px), bg_rgb + (255,))
                    fg   = Image.open(masked_path).convert("RGBA").resize((w_px, h_px))
                    comp = Image.alpha_composite(bg, fg)
                    out_name = Path(fname).stem + ".png"
                    comp.save(os.path.join(final_dir, out_name), "PNG")
                    self._log(f"   ✅ Saved: {out_name}")

                except Exception as e:
                    self._log(f"   ❌ Failed: {e}")
                    errors += 1

            self.after(0, lambda: self._prog.set(1))
            ok = len(photos) - errors
            self._log(f"\n🏁 Done!  {ok} succeeded · {errors} failed → {final_dir}")
            self.after(0, lambda: self._set_stat(
                f"Done! {ok}/{len(photos)} images processed.", C["green"]))
            subprocess.Popen(["explorer", final_dir])

        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
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
        self.title("Photo Background Changer")
        self.geometry("820x820")
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
        ctk.CTkLabel(tx, text="Photo Background Changer",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(tx, text="Resize to exact mm · remove background with AI · apply new colour",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        BgChangerPanelContent(self).pack(fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
