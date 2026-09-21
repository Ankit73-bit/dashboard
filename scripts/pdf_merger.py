"""
Tool: Simple PDF Merger
Merge selected PDF files and/or all PDFs from selected folders into one PDF.
"""

import os
import re
import threading
import subprocess
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PyPDF2 import PdfMerger

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "PDF_Merger")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#bf5af2", "green": "#30d158",
    "red": "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"}


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def safe_filename(name: str) -> str:
    name = (name or "merged").strip()
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return (name or "merged") + ".pdf"


def collect_pdfs(items, include_subfolders=True):
    """
    items: list of (kind, path) where kind is 'file' or 'folder'
    Returns ordered unique PDF paths.
    """
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


def merge_pdfs(pdf_paths, out_path, log_fn, progress_fn):
    if not pdf_paths:
        raise ValueError("No PDF files to merge.")

    merger = PdfMerger()
    errors = []
    total = len(pdf_paths)

    for i, pdf in enumerate(pdf_paths, 1):
        try:
            merger.append(pdf)
            log_fn(f"  + {os.path.basename(pdf)}")
        except Exception as e:
            errors.append((pdf, str(e)))
            log_fn(f"  ✗ Skip {os.path.basename(pdf)}: {e}")
        progress_fn(i / total * 0.9)

    if len(errors) == total:
        merger.close()
        raise ValueError("All PDFs failed to open — nothing to merge.")

    with open(out_path, "wb") as f:
        merger.write(f)
    merger.close()
    progress_fn(1.0)
    return {"merged_from": total - len(errors), "skipped": len(errors), "errors": errors}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF Merger")
        self.geometry("780x760")
        self.minsize(680, 640)
        self.configure(fg_color=C["bg"])
        self._items = []  # (kind, path)
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)
        ctk.CTkLabel(
            inn, text="📎  PDF Merger",
            font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            inn, text="Add PDF files and/or folders — merge everything into one PDF",
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
            fi, text="▶  Merge PDFs",
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
            text="📁  Output → Desktop\\OUTPUT\\PDF_Merger\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"],
        ).pack(anchor="w", padx=14, pady=8)

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
        self._empty_lbl = ctk.CTkLabel(
            self._list_inner, text="No files or folders added yet",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"],
        )
        self._empty_lbl.pack(padx=8, pady=8)
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
            orow, text="Output filename",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], width=120,
        ).pack(side="left")
        self._name_e = ctk.CTkEntry(
            orow, height=32, font=ctk.CTkFont("Segoe UI", 12),
            fg_color=C["hover"], border_color=C["border"], text_color=C["text"],
        )
        self._name_e.pack(side="left", fill="x", expand=True)
        self._name_e.insert(0, "merged.pdf")

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
            self._empty_lbl = ctk.CTkLabel(
                self._list_inner, text="No files or folders added yet",
                font=ctk.CTkFont("Segoe UI", 11), text_color=C["faint"],
            )
            self._empty_lbl.pack(padx=8, pady=8)
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
            text=f"{n} PDF(s) ready to merge" if n else "",
            text_color=C["accent"] if n else C["muted"],
        )

    def _start(self):
        pdfs = collect_pdfs(self._items, include_subfolders=self._sub_var.get())
        if not pdfs:
            messagebox.showwarning("Missing", "Add at least one PDF file or a folder that contains PDFs.")
            return
        out_name = safe_filename(self._name_e.get())

        self._run_btn.configure(state="disabled", text="Merging…")
        self._prog.set(0)
        self._stat.configure(text="Merging…", text_color=C["accent"])
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run, args=(pdfs, out_name), daemon=True,
        ).start()

    def _run(self, pdfs, out_name):
        out_dir = get_output_dir()
        out_path = os.path.join(out_dir, out_name)

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        def prog(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"Files   → {len(pdfs)}")
            log(f"Output  → {out_path}\n")
            stats = merge_pdfs(pdfs, out_path, log, prog)
            log("\n========== SUMMARY ==========")
            log(f"Merged from : {stats['merged_from']}")
            log(f"Skipped     : {stats['skipped']}")
            log(f"Saved       : {out_path}")
            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {stats['merged_from']} PDFs → {out_name}",
                text_color=C["green"],
            ))
            self.after(0, lambda: subprocess.Popen(["explorer", "/select,", out_path]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Merged {stats['merged_from']} PDF(s)\n"
                f"Skipped: {stats['skipped']}\n\n{out_path}",
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Merge PDFs",
            ))


if __name__ == "__main__":
    App().mainloop()
