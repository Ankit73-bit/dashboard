"""
Tool: PDF Compress
Compress selected PDF files and/or all PDFs from folders.
Uses Ghostscript when available; falls back to pypdf stream compression.
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

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "PDF_Compress")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#64d2ff", "green": "#30d158",
    "red": "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#062030", "mid": "#0a3550", "bdr": "#0f5070"}

QUALITY_PRESETS = {
    # Aggressive — similar to I Love PDF “extreme / recommended”
    "Maximum (smallest)": {
        "pdf_settings": "/screen",
        "color_dpi": 72,
        "gray_dpi": 72,
        "mono_dpi": 72,
        "qfactor": 1.0,
    },
    "Strong (I Love PDF-like)": {
        "pdf_settings": "/screen",
        "color_dpi": 96,
        "gray_dpi": 96,
        "mono_dpi": 120,
        "qfactor": 0.75,
    },
    "eBook (balanced)": {
        "pdf_settings": "/ebook",
        "color_dpi": 150,
        "gray_dpi": 150,
        "mono_dpi": 150,
        "qfactor": 0.4,
    },
    "Printer (good quality)": {
        "pdf_settings": "/printer",
        "color_dpi": 300,
        "gray_dpi": 300,
        "mono_dpi": 300,
        "qfactor": 0.15,
    },
    "Prepress (best quality)": {
        "pdf_settings": "/prepress",
        "color_dpi": 300,
        "gray_dpi": 300,
        "mono_dpi": 300,
        "qfactor": 0.1,
    },
}

DEFAULT_PRESET = "Strong (I Love PDF-like)"

GS_CANDIDATES = (
    "gswin64c",
    "gswin32c",
    "gs",
    r"C:\Program Files\gs\gs10.04.0\bin\gswin64c.exe",
    r"C:\Program Files\gs\gs10.03.1\bin\gswin64c.exe",
    r"C:\Program Files\gs\gs10.02.1\bin\gswin64c.exe",
    r"C:\Program Files\gs\gs10.01.2\bin\gswin64c.exe",
    r"C:\Program Files\gs\gs9.56.1\bin\gswin64c.exe",
    r"C:\Program Files (x86)\gs\gs9.56.1\bin\gswin32c.exe",
)


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def find_ghostscript():
    for cand in GS_CANDIDATES:
        if os.path.sep in cand or (len(cand) > 1 and cand[1] == ":"):
            if os.path.isfile(cand):
                return cand
        else:
            found = shutil.which(cand)
            if found:
                return found
    for base in (r"C:\Program Files\gs", r"C:\Program Files (x86)\gs"):
        if not os.path.isdir(base):
            continue
        try:
            versions = sorted(os.listdir(base), reverse=True)
        except OSError:
            continue
        for ver in versions:
            for exe in ("gswin64c.exe", "gswin32c.exe"):
                path = os.path.join(base, ver, "bin", exe)
                if os.path.isfile(path):
                    return path
    return None


def collect_pdfs(items, include_subfolders=True):
    seen = set()
    pdfs = []

    def add(path):
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            return
        seen.add(key)
        pdfs.append(path)

    for kind, path in items:
        if kind == "file":
            if path.lower().endswith(".pdf") and os.path.isfile(path):
                add(path)
            continue
        if not os.path.isdir(path):
            continue
        if include_subfolders:
            for root, _, files in os.walk(path):
                for name in sorted(files):
                    if name.lower().endswith(".pdf") and not name.startswith("~$"):
                        add(os.path.join(root, name))
        else:
            for name in sorted(os.listdir(path)):
                full = os.path.join(path, name)
                if os.path.isfile(full) and name.lower().endswith(".pdf"):
                    add(full)
    return pdfs


def fmt_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n:.1f} GB"


def build_gs_command(gs_path, src, dst, preset):
    """
    Build Ghostscript pdfwrite command with aggressive downsample + JPEG
    overrides (PDFSETTINGS alone often leaves scanned PDFs larger than web tools).
    """
    pdf_settings = preset["pdf_settings"]
    color_dpi = int(preset["color_dpi"])
    gray_dpi = int(preset["gray_dpi"])
    mono_dpi = int(preset["mono_dpi"])
    qfactor = float(preset["qfactor"])

    cmd = [
        gs_path,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        "-dSAFER",
        f"-dPDFSETTINGS={pdf_settings}",
        # Force image downsample (threshold 1.0 = always if above target DPI)
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dDownsampleMonoImages=true",
        "-dColorImageDownsampleType=/Bicubic",
        "-dGrayImageDownsampleType=/Bicubic",
        "-dMonoImageDownsampleType=/Bicubic",
        f"-dColorImageResolution={color_dpi}",
        f"-dGrayImageResolution={gray_dpi}",
        f"-dMonoImageResolution={mono_dpi}",
        "-dColorImageDownsampleThreshold=1.0",
        "-dGrayImageDownsampleThreshold=1.0",
        "-dMonoImageDownsampleThreshold=1.0",
        # Force JPEG (DCT) instead of Flate for photos/scans
        "-dEncodeColorImages=true",
        "-dEncodeGrayImages=true",
        "-dAutoFilterColorImages=false",
        "-dAutoFilterGrayImages=false",
        "-dColorImageFilter=/DCTEncode",
        "-dGrayImageFilter=/DCTEncode",
        "-dCompressFonts=true",
        "-dSubsetFonts=true",
        "-dDetectDuplicateImages=true",
        "-dConvertCMYKImagesToRGB=true",
        "-dColorConversionStrategy=/sRGB",
        "-dProcessColorModel=/DeviceRGB",
        f"-sOutputFile={dst}",
    ]

    # Higher QFactor = smaller / lower quality (I Love PDF-style)
    distiller = (
        f"<</ColorImageDict<</QFactor {qfactor} /Blend 1 /HSample [2 1 1 2] "
        f"/VSample [2 1 1 2]>> /GrayImageDict<</QFactor {qfactor} /Blend 1 "
        f"/HSample [2 1 1 2] /VSample [2 1 1 2]>> "
        f"/ColorACSImageDict<</QFactor {qfactor} /Blend 1 /HSample [2 1 1 2] "
        f"/VSample [2 1 1 2]>> /GrayACSImageDict<</QFactor {qfactor} /Blend 1 "
        f"/HSample [2 1 1 2] /VSample [2 1 1 2]>>>> setdistillerparams"
    )
    cmd.extend(["-c", distiller, "-f", src])
    return cmd


def compress_with_ghostscript(gs_path, src, dst, preset):
    cmd = build_gs_command(gs_path, src, dst, preset)
    result = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0 or not os.path.isfile(dst) or os.path.getsize(dst) == 0:
        err = (result.stderr or b"").decode(errors="ignore").strip()
        # Fallback: preset without -c distiller block (older GS quirks)
        simple = [
            gs_path,
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-dPDFSETTINGS={preset['pdf_settings']}",
            "-dDownsampleColorImages=true",
            "-dDownsampleGrayImages=true",
            "-dDownsampleMonoImages=true",
            f"-dColorImageResolution={int(preset['color_dpi'])}",
            f"-dGrayImageResolution={int(preset['gray_dpi'])}",
            f"-dMonoImageResolution={int(preset['mono_dpi'])}",
            "-dColorImageDownsampleThreshold=1.0",
            "-dGrayImageDownsampleThreshold=1.0",
            "-dMonoImageDownsampleThreshold=1.0",
            "-dAutoFilterColorImages=false",
            "-dAutoFilterGrayImages=false",
            "-dColorImageFilter=/DCTEncode",
            "-dGrayImageFilter=/DCTEncode",
            "-dDetectDuplicateImages=true",
            "-dConvertCMYKImagesToRGB=true",
            f"-sOutputFile={dst}",
            src,
        ]
        result2 = subprocess.run(
            simple, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result2.returncode != 0 or not os.path.isfile(dst) or os.path.getsize(dst) == 0:
            err2 = (result2.stderr or b"").decode(errors="ignore").strip()
            raise RuntimeError(err or err2 or f"Ghostscript failed (code {result.returncode})")


def compress_with_pypdf(src, dst):
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(src)
    writer = PdfWriter()
    for page in reader.pages:
        try:
            page.compress_content_streams()
        except Exception:
            pass
        writer.add_page(page)
    try:
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
    except Exception:
        pass
    with open(dst, "wb") as f:
        writer.write(f)


def compress_one(src, dst, gs_path, preset):
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    tmp = dst + ".tmp.pdf"
    try:
        if gs_path:
            compress_with_ghostscript(gs_path, src, tmp, preset)
            method = "ghostscript"
        else:
            compress_with_pypdf(src, tmp)
            method = "pypdf"

        before = os.path.getsize(src)
        after = os.path.getsize(tmp)
        # Keep smaller file; if compression grew the file, keep original copy
        if after < before:
            os.replace(tmp, dst)
            return before, after, method, True
        else:
            shutil.copy2(src, dst)
            if os.path.isfile(tmp):
                os.remove(tmp)
            return before, before, method, False
    except Exception:
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        raise


def unique_out_path(out_dir, name):
    base, ext = os.path.splitext(name)
    path = os.path.join(out_dir, name)
    n = 2
    while os.path.exists(path):
        path = os.path.join(out_dir, f"{base}_{n}{ext}")
        n += 1
    return path


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF Compress")
        self.geometry("780x780")
        self.minsize(680, 640)
        self.configure(fg_color=C["bg"])
        self._items = []
        self._gs = find_ghostscript()
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)
        ctk.CTkLabel(
            inn, text="🗜️  PDF Compress",
            font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            inn, text="Add PDF files and/or folders — compress each file (keeps original names)",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(anchor="w")

        footer = ctk.CTkFrame(
            self, fg_color=C["card"], corner_radius=0,
            border_width=1, border_color=C["border"],
        )
        footer.pack(side="bottom", fill="x")
        fi = ctk.CTkFrame(footer, fg_color="transparent")
        fi.pack(fill="x", padx=20, pady=12)
        self._prog = ctk.CTkProgressBar(
            fi, height=6, fg_color=C["hover"], progress_color=C["accent"],
        )
        self._prog.pack(fill="x", pady=(0, 6))
        self._prog.set(0)
        self._stat = ctk.CTkLabel(
            fi, text="Ready.", font=ctk.CTkFont("Segoe UI", 11),
            text_color=C["muted"], anchor="w",
        )
        self._stat.pack(fill="x", pady=(0, 8))
        self._run_btn = ctk.CTkButton(
            fi, text="▶  Compress PDFs",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            corner_radius=24, height=44, command=self._start,
        )
        self._run_btn.pack(fill="x")

        body = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C["border"],
        )
        body.pack(fill="both", expand=True, padx=24, pady=16)

        banner = ctk.CTkFrame(
            body, fg_color=TINT["bg"], corner_radius=10,
            border_width=1, border_color=C["accent"],
        )
        banner.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\PDF_Compress\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"],
        ).pack(anchor="w", padx=14, pady=8)

        engine = "Ghostscript (best)" if self._gs else "pypdf (basic — install Ghostscript for smaller files)"
        ctk.CTkLabel(
            body, text=f"Engine: {engine}",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"], anchor="w",
        ).pack(fill="x", pady=(0, 6))

        self._sec(body, "Add PDFs")
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 6))
        ctk.CTkButton(
            btn_row, text="＋ Add Files", width=120, height=34,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            command=self._add_files,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="＋ Add Folder", width=120, height=34,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            command=self._add_folder,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="Clear All", width=90, height=34,
            fg_color="transparent", hover_color=C["hover"],
            text_color=C["muted"], command=self._clear,
        ).pack(side="right")

        self._list_card = ctk.CTkFrame(
            body, fg_color=C["card"], corner_radius=12,
            border_width=1, border_color=C["border"],
        )
        self._list_card.pack(fill="x", pady=(0, 6))
        self._list_inner = ctk.CTkFrame(self._list_card, fg_color="transparent")
        self._list_inner.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(
            self._list_inner, text="No files or folders added yet",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"],
        ).pack(padx=8, pady=8)
        self._count_lbl = ctk.CTkLabel(
            body, text="", font=ctk.CTkFont("Segoe UI", 11, "bold"),
            text_color=C["muted"], anchor="w",
        )
        self._count_lbl.pack(fill="x", pady=(0, 8))

        self._sec(body, "Options")
        opt = ctk.CTkFrame(
            body, fg_color=C["card"], corner_radius=12,
            border_width=1, border_color=C["border"],
        )
        opt.pack(fill="x", pady=(0, 10))
        orow = ctk.CTkFrame(opt, fg_color="transparent")
        orow.pack(fill="x", padx=14, pady=10)
        ctk.CTkLabel(
            orow, text="Quality",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], width=80,
        ).pack(side="left")
        self._quality_cb = ctk.CTkComboBox(
            orow, values=list(QUALITY_PRESETS.keys()), state="readonly",
            font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["hover"], border_color=C["border"],
            button_color=TINT["mid"], button_hover_color=TINT["bdr"],
            dropdown_fg_color=C["card"], dropdown_hover_color=C["hover"],
            dropdown_text_color=C["text"], text_color=C["text"], height=32,
        )
        self._quality_cb.set(DEFAULT_PRESET)
        self._quality_cb.pack(side="left", fill="x", expand=True)
        if not self._gs:
            self._quality_cb.configure(state="disabled")
        ctk.CTkLabel(
            opt,
            text="Tip: use Strong or Maximum for scanned PDFs (closer to I Love PDF sizes).",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"], anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 4))
        self._sub_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opt, text="Include PDFs in subfolders",
            variable=self._sub_var,
            font=ctk.CTkFont("Segoe UI", 12), text_color=C["text"],
            fg_color=C["accent"], hover_color=TINT["bdr"],
            command=self._refresh_count,
        ).pack(anchor="w", padx=14, pady=(0, 12))

        self._sec(body, "Log")
        self._log = ctk.CTkTextbox(
            body, height=180, font=ctk.CTkFont("Courier New", 11),
            fg_color=C["card"], border_color=C["border"],
            border_width=1, text_color=C["muted"], state="disabled",
        )
        self._log.pack(fill="x", pady=(0, 8))

    def _sec(self, p, t):
        ctk.CTkLabel(
            p, text=t, font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color=C["text"], anchor="w",
        ).pack(fill="x", pady=(10, 2))

    def _write(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select PDF files",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not paths:
            return
        for p in paths:
            self._items.append(("file", p))
        self._rebuild_list()

    def _add_folder(self):
        folder = filedialog.askdirectory(title="Select folder of PDFs")
        if not folder:
            return
        self._items.append(("folder", folder))
        self._rebuild_list()

    def _clear(self):
        self._items.clear()
        self._rebuild_list()

    def _remove_item(self, index):
        if 0 <= index < len(self._items):
            self._items.pop(index)
            self._rebuild_list()

    def _rebuild_list(self):
        for w in self._list_inner.winfo_children():
            w.destroy()
        if not self._items:
            ctk.CTkLabel(
                self._list_inner, text="No files or folders added yet",
                font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"],
            ).pack(padx=8, pady=8)
            self._refresh_count()
            return
        for i, (kind, path) in enumerate(self._items):
            row = ctk.CTkFrame(self._list_inner, fg_color="transparent")
            row.pack(fill="x", pady=2)
            icon = "📄" if kind == "file" else "📁"
            label = os.path.basename(path) or path
            if kind == "folder":
                label = f"{label}\\"
            ctk.CTkLabel(
                row, text=f"{icon}  {label}",
                font=ctk.CTkFont("Segoe UI", 12), text_color=C["text"],
                anchor="w",
            ).pack(side="left", fill="x", expand=True, padx=6)
            ctk.CTkButton(
                row, text="✕", width=32, height=28,
                fg_color="transparent", hover_color=C["hover"],
                text_color=C["muted"],
                command=lambda idx=i: self._remove_item(idx),
            ).pack(side="right")
        self._refresh_count()

    def _refresh_count(self):
        pdfs = collect_pdfs(self._items, include_subfolders=self._sub_var.get())
        n = len(pdfs)
        self._count_lbl.configure(
            text=f"{n} PDF(s) ready to compress" if n else "",
            text_color=C["accent"] if n else C["muted"],
        )

    def _start(self):
        pdfs = collect_pdfs(self._items, include_subfolders=self._sub_var.get())
        if not pdfs:
            messagebox.showwarning(
                "Missing", "Add at least one PDF file or a folder that contains PDFs.",
            )
            return
        quality_label = self._quality_cb.get()
        preset = QUALITY_PRESETS.get(quality_label) or QUALITY_PRESETS[DEFAULT_PRESET]

        self._run_btn.configure(state="disabled", text="Compressing…")
        self._prog.set(0)
        self._stat.configure(text="Compressing…", text_color=C["accent"])
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run, args=(pdfs, quality_label, preset), daemon=True,
        ).start()

    def _run(self, pdfs, quality_label, preset):
        out_dir = get_output_dir()
        gs = self._gs

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        def prog(p):
            self.after(0, lambda v=p: self._prog.set(v))

        ok = skipped = errors = 0
        total_before = total_after = 0

        try:
            log(f"Files   → {len(pdfs)}")
            log(f"Engine  → {'Ghostscript' if gs else 'pypdf (basic)'}")
            if gs:
                log(
                    f"Preset  → {quality_label}  "
                    f"(DPI {preset['color_dpi']}, QFactor {preset['qfactor']})"
                )
            log(f"Output  → {out_dir}\n")

            for i, src in enumerate(pdfs, 1):
                name = os.path.basename(src)
                dst = unique_out_path(out_dir, name)
                try:
                    before, after, method, shrunk = compress_one(src, dst, gs, preset)
                    total_before += before
                    total_after += after
                    if shrunk:
                        ok += 1
                        saved = before - after
                        pct = (saved / before * 100) if before else 0
                        log(
                            f"  ✓ {name}  {fmt_size(before)} → {fmt_size(after)} "
                            f"(-{pct:.0f}%)  [{method}]"
                        )
                    else:
                        skipped += 1
                        log(f"  ≈ {name}  already small / no gain — copied as-is")
                except Exception as e:
                    errors += 1
                    log(f"  ✗ {name}: {e}")
                prog(i / len(pdfs))

            saved_total = max(0, total_before - total_after)
            pct_total = (saved_total / total_before * 100) if total_before else 0
            log("\n========== SUMMARY ==========")
            log(f"Compressed : {ok}")
            log(f"No gain    : {skipped}")
            log(f"Errors     : {errors}")
            log(f"Total size : {fmt_size(total_before)} → {fmt_size(total_after)} "
                f"(-{pct_total:.0f}%, saved {fmt_size(saved_total)})")

            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {ok} compressed, saved {fmt_size(saved_total)}",
                text_color=C["green"],
            ))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Compressed: {ok}\nNo gain: {skipped}\nErrors: {errors}\n"
                f"Saved: {fmt_size(saved_total)}\n\n{out_dir}",
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Compress PDFs",
            ))


if __name__ == "__main__":
    App().mainloop()
