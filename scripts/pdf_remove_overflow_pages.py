"""
Tool: Remove Overflow Pages
When a notice’s last line(s) slip onto a new page, that extra page is
mostly letterhead plus a leftover footer. This strips those short pages
from one PDF or a folder of PDFs. Full notice pages are kept.
"""

import os
import csv
import threading
import subprocess
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox
from pypdf import PdfReader, PdfWriter
from window_fit import fit_to_screen, add_run_footer, add_primary_run_button

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "PDF_Remove_Overflow_Pages")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#ff375f", "green": "#30d158",
    "red": "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#300a14", "mid": "#4e1020", "bdr": "#701830"}

# Real notice pages in the sample are ~5–6k chars; spilled last-line pages ~192.
KEEP_MARKERS = (
    "without prejudice",
    "loan recall",
    "email / whatsapp",
    "dear customer",
)
FULL_PAGE_MIN = 1500
DEFAULT_MAX_CHARS = 800


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def unique_path(folder, filename):
    dest = os.path.join(folder, filename)
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(filename)
    n = 1
    while True:
        cand = os.path.join(folder, f"{base}_{n}{ext}")
        if not os.path.exists(cand):
            return cand
        n += 1


def looks_like_full_notice(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in KEEP_MARKERS)


def extract_page_text(page):
    try:
        return page.extract_text() or ""
    except Exception:
        return ""


def overflow_threshold(texts, max_chars=None):
    """
    Cut-off for 'this page is only leftover lines'.
    Uses the median length of full notice pages in this file, so a
    1-line spill (~200 chars) is dropped while 5k-char notices stay.
    """
    if max_chars is not None:
        return max(50, int(max_chars))
    full = [
        len(t.strip())
        for t in texts
        if looks_like_full_notice(t) or len(t.strip()) >= FULL_PAGE_MIN
    ]
    if not full:
        nonempty = [len(t.strip()) for t in texts if t.strip()]
        if not nonempty:
            return DEFAULT_MAX_CHARS
        typical = sorted(nonempty)[len(nonempty) // 2]
        return min(DEFAULT_MAX_CHARS, max(200, int(typical * 0.18)))
    typical = sorted(full)[len(full) // 2]
    return min(DEFAULT_MAX_CHARS, max(250, int(typical * 0.18)))


def is_overflow_page(text: str, cap: int) -> bool:
    if looks_like_full_notice(text):
        return False
    return len((text or "").strip()) <= cap


def format_page_list(pages):
    """Readable page numbers so 88,91,102… is not read as one giant value."""
    return ", ".join(str(int(p)) for p in pages) if pages else ""


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


def strip_overflow_pages(pdf_path, output_path, log_fn, max_chars=None):
    reader = PdfReader(pdf_path)
    texts = [extract_page_text(p) for p in reader.pages]
    total = len(texts)
    cap = overflow_threshold(texts, max_chars=max_chars)
    log_fn(f"  overflow if page text ≤ {cap} chars (and not a full notice)")

    writer = PdfWriter()
    removed = []
    for i, (page, text) in enumerate(zip(reader.pages, texts), 1):
        if is_overflow_page(text, cap):
            removed.append(i)
            continue
        writer.add_page(page)

    kept = total - len(removed)
    if kept == 0:
        raise ValueError("All pages looked like overflow — nothing left to save.")

    with open(output_path, "wb") as f:
        writer.write(f)

    return total, removed, kept, cap


def process_pdfs(pdf_paths, out_dir, log_fn, progress_fn, max_chars=None):
    log_csv = os.path.join(out_dir, "removed_pages_log.csv")
    with open(log_csv, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            ["Source", "Output", "Total pages", "Removed count",
             "Removed pages", "Kept", "Char limit"]
        )

    files_ok = files_skip = pages_removed = 0
    n = len(pdf_paths)

    for i, pdf_path in enumerate(pdf_paths, 1):
        name = os.path.basename(pdf_path)
        log_fn(f"\n[{i}/{n}] {name}")
        out_path = unique_path(out_dir, name)
        try:
            total, removed, kept, cap = strip_overflow_pages(
                pdf_path, out_path, log_fn, max_chars=max_chars,
            )
        except Exception as e:
            files_skip += 1
            log_fn(f"  Error: {e}")
            with open(log_csv, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([pdf_path, "", "", "", str(e), "", ""])
            progress_fn(i / n)
            continue

        files_ok += 1
        pages_removed += len(removed)
        pages_str = format_page_list(removed)
        if removed:
            log_fn(f"  {total} pages → removed {len(removed)} → kept {kept}")
            log_fn(f"  extra pages: {pages_str}")
        else:
            log_fn(f"  {total} pages → no overflow pages → copied {kept}")
        with open(log_csv, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(
                [pdf_path, out_path, total, len(removed), pages_str, kept, cap]
            )
        progress_fn(i / n)

    return {
        "files_ok": files_ok,
        "files_skip": files_skip,
        "pages_removed": pages_removed,
        "log_csv": log_csv,
    }


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Remove Overflow Pages")
        self.configure(fg_color=C["bg"])
        fit_to_screen(self, 760, 700)
        self._items = []
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)
        ctk.CTkLabel(
            inn, text="🧹  Remove Overflow Pages",
            font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            inn,
            text="Drop extra pages where only leftover last lines spilled over",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(anchor="w")

        _, fi, self._prog, self._stat = add_run_footer(self, C, TINT)
        self._run_btn = add_primary_run_button(
            fi, "▶  Remove Overflow Pages", self._start, C, TINT)

        body = ctk.CTkScrollableFrame(
            self, fg_color="transparent", scrollbar_button_color=C["border"],
        )
        body.pack(fill="both", expand=True, padx=24, pady=(12, 8))

        banner = ctk.CTkFrame(
            body, fg_color=TINT["bg"], corner_radius=10,
            border_width=1, border_color=C["accent"],
        )
        banner.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\PDF_Remove_Overflow_Pages\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"],
        ).pack(anchor="w", padx=14, pady=8)

        self._sec(body, "Add PDFs")
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, 6))
        ctk.CTkButton(
            btn_row, text="＋ File…", width=110, height=34,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"], border_color=C["accent"], border_width=1,
            command=self._add_files,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="＋ Folder…", width=110, height=34,
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
        self._sub_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opt, text="Include PDFs in subfolders",
            variable=self._sub_var,
            font=ctk.CTkFont("Segoe UI", 12), text_color=C["text"],
            fg_color=C["accent"], hover_color=TINT["bdr"],
            command=self._refresh_count,
        ).pack(anchor="w", padx=14, pady=(12, 8))

        lim = ctk.CTkFrame(opt, fg_color="transparent")
        lim.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(
            lim, text="Max leftover chars",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], width=140,
        ).pack(side="left")
        self._max_e = ctk.CTkEntry(
            lim, width=90, height=32,
            fg_color=C["hover"], border_color=C["border"], text_color=C["text"],
            placeholder_text="auto",
        )
        self._max_e.pack(side="left")
        ctk.CTkLabel(
            lim, text="  blank = auto from this PDF",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
        ).pack(side="left")

        ctk.CTkLabel(
            opt,
            text="A page is removed if it is much shorter than the notices in that file\n"
                 "(leftover last line + letterhead). Full notices are always kept.",
            font=ctk.CTkFont("Segoe UI", 10), text_color=C["faint"],
            justify="left", anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 12))

        self._sec(body, "Log")
        self._log = ctk.CTkTextbox(
            body, height=200, font=ctk.CTkFont("Courier New", 11),
            fg_color=C["card"], border_color=C["border"],
            border_width=1, text_color=C["muted"], state="disabled",
        )
        self._log.pack(fill="x", pady=(0, 12))

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
            title="Select PDF file(s)",
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
        self._count_lbl.configure(text=f"{n} PDF{'s' if n != 1 else ''} ready")

    def _max_chars(self):
        raw = (self._max_e.get() or "").strip()
        if not raw:
            return None
        try:
            n = int(raw)
            if n < 1:
                raise ValueError
            return n
        except ValueError:
            raise ValueError("Max leftover chars must be a positive number, or leave blank for auto.")

    def _start(self):
        pdfs = collect_pdfs(self._items, include_subfolders=self._sub_var.get())
        if not pdfs:
            messagebox.showwarning("Missing", "Add a PDF file or a folder of PDFs.")
            return
        try:
            max_chars = self._max_chars()
        except ValueError as e:
            messagebox.showwarning("Invalid", str(e))
            return
        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run, args=(pdfs, max_chars), daemon=True,
        ).start()

    def _run(self, pdfs, max_chars):
        out_dir = get_output_dir()

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        def prog(p):
            self.after(0, lambda v=p: self._prog.set(v))

        try:
            log(f"Files   → {len(pdfs)}")
            log(f"Limit   → {'auto' if max_chars is None else max_chars}")
            log(f"Output  → {out_dir}\n")
            stats = process_pdfs(
                pdfs, out_dir, log, prog, max_chars=max_chars,
            )
            log("\n========== SUMMARY ==========")
            log(f"PDFs processed : {stats['files_ok']}")
            log(f"PDFs skipped   : {stats['files_skip']}")
            log(f"Pages removed  : {stats['pages_removed']}")
            log(f"Log            : {stats['log_csv']}")
            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — removed {stats['pages_removed']} overflow page(s) from {stats['files_ok']} PDF(s).",
                text_color=C["green"]))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"PDFs: {stats['files_ok']}\n"
                f"Overflow pages removed: {stats['pages_removed']}\n\n{out_dir}"
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Remove Overflow Pages"))


if __name__ == "__main__":
    App().mainloop()
