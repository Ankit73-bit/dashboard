"""
Tool: Image to PDF
Convert a single image or a folder of images into PDF(s).
Supports common image types (JPG, PNG, BMP, GIF, TIFF, WEBP, …).
Embeddable Panel + standalone window.
"""

import os
import sys
import threading
import subprocess
from pathlib import Path
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox

_SCRIPTS = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
from window_fit import fit_to_screen, attach_panel_chrome

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "Image_to_PDF")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#ff9f0a", "green":  "#30d158",
    "red":    "#ff375f",
}
TINT = {"bg": "#2e1e00", "mid": "#4a3000", "bdr": "#6b4500"}

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff",
    ".webp", ".ico", ".jfif", ".heic", ".heif",
}

IMAGE_FILETYPES = [
    ("Image files", "*.jpg *.jpeg *.png *.bmp *.gif *.tif *.tiff *.webp *.ico *.jfif *.heic *.heif"),
    ("JPEG", "*.jpg *.jpeg *.jfif"),
    ("PNG", "*.png"),
    ("All files", "*.*"),
]


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


def _is_image(path):
    return Path(path).suffix.lower() in IMAGE_EXTS


def _collect_images(source_path, mode):
    if mode == "single":
        return [source_path] if _is_image(source_path) else []
    files = []
    for name in sorted(os.listdir(source_path)):
        full = os.path.join(source_path, name)
        if os.path.isfile(full) and _is_image(full):
            files.append(full)
    return files


def _open_rgb(path):
    """Open any Pillow-supported image and return an RGB image suitable for PDF."""
    from PIL import Image

    img = Image.open(path)
    # Animated GIF / multi-frame TIFF: use first frame
    try:
        img.seek(0)
    except Exception:
        pass
    img.load()

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        # Composite onto white so transparency doesn't become black in PDF
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    if img.mode != "RGB":
        return img.convert("RGB")
    return img


def images_to_pdfs(image_paths, out_dir, merge_all, log_fn, progress_fn):
    """
    Convert images to PDF.
    merge_all=True  → one PDF with all images as pages (images_merged.pdf)
    merge_all=False → one PDF per image (<stem>.pdf)
    Returns (pdf_count, image_count).
    """
    from PIL import Image  # noqa: F401 — ensure available

    total = len(image_paths)
    if total == 0:
        return 0, 0

    if merge_all:
        rgb_pages = []
        for idx, img_path in enumerate(image_paths, 1):
            name = os.path.basename(img_path)
            log_fn(f"[{idx}/{total}] Loading: {name}")
            progress_fn(idx / total * 0.85)
            try:
                rgb_pages.append(_open_rgb(img_path))
            except Exception as e:
                log_fn(f"   ❌ Skipped {name}: {e}")

        if not rgb_pages:
            return 0, 0

        out_path = os.path.join(out_dir, "images_merged.pdf")
        first, rest = rgb_pages[0], rgb_pages[1:]
        first.save(out_path, "PDF", resolution=100.0, save_all=bool(rest), append_images=rest)
        for im in rgb_pages:
            try:
                im.close()
            except Exception:
                pass
        log_fn(f"\n✅ Merged PDF → images_merged.pdf  ({len(rgb_pages)} page(s))")
        progress_fn(1.0)
        return 1, len(rgb_pages)

    pdf_count = 0
    for idx, img_path in enumerate(image_paths, 1):
        name = os.path.basename(img_path)
        stem = Path(img_path).stem
        log_fn(f"[{idx}/{total}] Converting: {name}")
        progress_fn(idx / total * 0.95)
        try:
            rgb = _open_rgb(img_path)
            out_path = os.path.join(out_dir, f"{stem}.pdf")
            # Avoid overwrite collisions
            if os.path.exists(out_path):
                n = 2
                while os.path.exists(os.path.join(out_dir, f"{stem}_{n}.pdf")):
                    n += 1
                out_path = os.path.join(out_dir, f"{stem}_{n}.pdf")
            rgb.save(out_path, "PDF", resolution=100.0)
            rgb.close()
            pdf_count += 1
            log_fn(f"   ✅ {os.path.basename(out_path)}")
        except Exception as e:
            log_fn(f"   ❌ Failed: {e}")

    progress_fn(1.0)
    return pdf_count, total


# ─── Embeddable Panel Content ─────────────────────────────────────────────────

class ImageToPdfPanelContent(ctk.CTkFrame):

    def __init__(self, parent, **kw):
        kw.pop("scrollbar_button_color", None)
        super().__init__(parent, fg_color="transparent", **kw)
        self._body, self._prog, self._stat, self._run_btn = attach_panel_chrome(
            self, C, TINT, '▶  Convert to PDF', self._run)
        self._source_path = None
        self._build()

    def _build(self):
        if not _check_pillow():
            warn = ctk.CTkFrame(self._body, fg_color="#300a14", corner_radius=10,
                                border_width=1, border_color=C["red"])
            warn.pack(fill="x", pady=(4, 10))
            ctk.CTkLabel(
                warn,
                text="⚠️  Pillow not installed.  Run:  pip install Pillow",
                font=ctk.CTkFont("Segoe UI", 11),
                text_color=C["red"],
            ).pack(anchor="w", padx=14, pady=8)

        banner = ctk.CTkFrame(self._body, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(4, 14))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\Image_to_PDF\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["accent"],
        ).pack(anchor="w", padx=14, pady=8)

        self._sec("Step 1 — Mode")
        mode_row = ctk.CTkFrame(self._body, fg_color="transparent")
        mode_row.pack(fill="x", pady=(0, 10))
        self._mode_var = ctk.StringVar(value="single")
        for lbl, val in [("Single image file", "single"), ("Folder of images", "folder")]:
            ctk.CTkRadioButton(
                mode_row, text=lbl, variable=self._mode_var, value=val,
                font=ctk.CTkFont("Segoe UI", 12), text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"],
                border_color=C["border"],
                command=self._on_mode_change,
            ).pack(side="left", padx=(0, 28))

        self._sec("Step 2 — Select source")
        src_row = ctk.CTkFrame(self._body, fg_color="transparent")
        src_row.pack(fill="x", pady=(0, 10))
        self._src_lbl = ctk.CTkLabel(
            src_row, text="Nothing selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w",
        )
        self._src_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            src_row, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick,
        ).pack(side="right")

        self._sec("Step 3 — Output style")
        out_row = ctk.CTkFrame(self._body, fg_color="transparent")
        out_row.pack(fill="x", pady=(0, 6))
        self._merge_var = ctk.StringVar(value="each")
        for lbl, val in [
            ("One PDF per image", "each"),
            ("Merge all into one PDF", "merge"),
        ]:
            ctk.CTkRadioButton(
                out_row, text=lbl, variable=self._merge_var, value=val,
                font=ctk.CTkFont("Segoe UI", 12), text_color=C["text"],
                fg_color=C["accent"], hover_color=TINT["bdr"],
                border_color=C["border"],
            ).pack(side="left", padx=(0, 28))

        ctk.CTkLabel(
            self._body,
            text="Accepts JPG, PNG, BMP, GIF, TIFF, WEBP, ICO, and other Pillow-supported formats.",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color=C["faint"],
            anchor="w",
        ).pack(fill="x", pady=(0, 10))

        self._sec("Log")
        self._log_box = ctk.CTkTextbox(
            self._body, height=200, fg_color=C["card"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], font=ctk.CTkFont("Consolas", 11),
        )
        self._log_box.pack(fill="both", expand=True, pady=(0, 16))

    def _sec(self, t):
        ctk.CTkLabel(
            self._body, text=t.upper(),
            font=ctk.CTkFont("Segoe UI", 10, "bold"),
            text_color=C["muted"],
        ).pack(anchor="w", pady=(8, 3))

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
                title="Select image file",
                filetypes=IMAGE_FILETYPES,
            )
        else:
            p = filedialog.askdirectory(title="Select folder containing images")
        if not p:
            return
        self._source_path = p
        self._src_lbl.configure(
            text=os.path.basename(p) or p, text_color=C["text"],
        )

    def _run(self):
        if not _check_pillow():
            messagebox.showerror(
                "Missing Dependency",
                "Pillow is not installed.\n\nRun:  pip install Pillow",
            )
            return
        if not self._source_path:
            messagebox.showwarning(
                "No Source", "Please select an image file or folder first.",
            )
            return

        self._run_btn.configure(state="disabled", text="Converting…")
        self._log_box.delete("1.0", "end")
        self._prog.set(0)
        threading.Thread(target=self._process, daemon=True).start()

    def _process(self):
        out_dir = get_output_dir()
        mode = self._mode_var.get()
        merge_all = self._merge_var.get() == "merge"

        try:
            images = _collect_images(self._source_path, mode)
            if not images:
                raise ValueError(
                    "No supported image files found. "
                    "Use JPG, PNG, BMP, GIF, TIFF, WEBP, etc."
                )

            self._log(f"🖼️  Images found: {len(images)}")
            self._log(
                f"📄 Output: {'one merged PDF' if merge_all else 'one PDF per image'}"
            )
            self._log("")

            pdf_count, img_count = images_to_pdfs(
                images,
                out_dir,
                merge_all,
                log_fn=self._log,
                progress_fn=lambda v: self.after(0, lambda x=v: self._prog.set(x)),
            )

            self.after(0, lambda: self._prog.set(1))
            self._log(f"\n🏁 Done!  {img_count} image(s) → {pdf_count} PDF(s) → {out_dir}")
            self.after(0, lambda: self._set_stat(
                f"Done! {img_count} image(s) → {pdf_count} PDF(s).", C["green"],
            ))
            subprocess.Popen(["explorer", out_dir])

        except Exception as e:
            err = str(e)
            self._log(f"\n💥 Error: {err}")
            self.after(0, lambda: self._set_stat(f"Error: {err}", C["red"]))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Convert to PDF",
            ))


# ─── Embeddable Panel wrapper ─────────────────────────────────────────────────
class ImageToPdfPanel(ctk.CTkFrame):
    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        ImageToPdfPanelContent(self).pack(fill="both", expand=True, padx=16, pady=8)


# ─── Standalone App ───────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Image to PDF")
        fit_to_screen(self, 800, 760)
        self.configure(fg_color=C["bg"])

        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)

        icon_f = ctk.CTkFrame(inn, width=44, height=44,
                              fg_color=TINT["mid"], corner_radius=10)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(
            icon_f, text="📄",
            font=ctk.CTkFont("Segoe UI Emoji", 20),
        ).place(relx=0.5, rely=0.5, anchor="center")

        tx = ctk.CTkFrame(inn, fg_color="transparent")
        tx.pack(side="left")
        ctk.CTkLabel(
            tx, text="Image to PDF",
            font=ctk.CTkFont("Segoe UI", 17, "bold"),
            text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            tx, text="Convert any image type (or a whole folder) to PDF",
            font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"],
        ).pack(anchor="w")

        ImageToPdfPanelContent(self).pack(fill="both", expand=True, padx=20, pady=12)


if __name__ == "__main__":
    App().mainloop()
