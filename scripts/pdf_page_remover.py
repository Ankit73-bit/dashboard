"""
Tool: PDF Page Remover
Remove selected pages / page ranges from a PDF and write a cleaned copy.
Example: 3-4, 11-14, 16
"""

import os
import re
import threading
import subprocess
from datetime import datetime

import customtkinter as ctk
from tkinter import filedialog, messagebox
from pypdf import PdfReader, PdfWriter

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP  = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "PDF_Page_Remover")

C = {
    "bg":     "#0a0a0f", "card":   "#16161f", "hover":  "#1e1e2e",
    "border": "#2a2a3d", "text":   "#e8e8f0", "muted":  "#8888aa",
    "faint":  "#44445a", "accent": "#ff375f", "green":  "#30d158",
    "red":    "#ff375f", "orange": "#ff9f0a",
}
TINT = {"bg": "#300a14", "mid": "#4e1020", "bdr": "#701830"}


def get_output_dir():
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def parse_pages_to_remove(spec: str, total_pages: int) -> set:
    """
    Parse a page-removal string into a set of 1-based page numbers.
    Accepts: 3-4, 11-14, 16  (spaces optional; commas or semicolons).
    Raises ValueError on bad tokens or out-of-range pages.
    """
    if not spec or not spec.strip():
        raise ValueError("Enter at least one page or range to remove.")

    pages = set()
    cleaned = spec.replace(";", ",").replace(" ", "")
    parts = [p for p in cleaned.split(",") if p]

    if not parts:
        raise ValueError("Enter at least one page or range to remove.")

    for part in parts:
        if re.fullmatch(r"\d+", part):
            n = int(part)
            if n < 1 or n > total_pages:
                raise ValueError(f"Page {n} is out of range (1–{total_pages}).")
            pages.add(n)
        elif re.fullmatch(r"\d+-\d+", part):
            a_str, b_str = part.split("-", 1)
            a, b = int(a_str), int(b_str)
            if a > b:
                a, b = b, a
            if a < 1 or b > total_pages:
                raise ValueError(
                    f"Range {part} is out of range (PDF has {total_pages} pages)."
                )
            pages.update(range(a, b + 1))
        else:
            raise ValueError(
                f"Invalid token '{part}'. Use pages like 16 or ranges like 3-4."
            )

    return pages


def remove_pages(pdf_path: str, pages_to_remove: set, output_path: str, log_fn):
    reader = PdfReader(pdf_path)
    total = len(reader.pages)
    writer = PdfWriter()

    kept = 0
    for i in range(total):
        page_no = i + 1
        if page_no in pages_to_remove:
            continue
        writer.add_page(reader.pages[i])
        kept += 1

    if kept == 0:
        raise ValueError("All pages would be removed — nothing left to save.")

    with open(output_path, "wb") as f:
        writer.write(f)

    removed_sorted = sorted(pages_to_remove)
    log_fn(f"Total pages : {total}")
    log_fn(f"Removed     : {len(removed_sorted)} → {removed_sorted}")
    log_fn(f"Kept        : {kept}")
    log_fn(f"Saved       : {output_path}")
    return total, len(removed_sorted), kept


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PDF Page Remover")
        self.geometry("720x640")
        self.configure(fg_color=C["bg"])
        self._pdf = None
        self._page_count = 0
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(padx=28, pady=16)

        icon_f = ctk.CTkFrame(inner, width=48, height=48, fg_color=TINT["mid"], corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text="🗑️", font=ctk.CTkFont("Segoe UI Emoji", 22)).place(
            relx=0.5, rely=0.5, anchor="center")

        txt = ctk.CTkFrame(inner, fg_color="transparent")
        txt.pack(side="left")
        ctk.CTkLabel(txt, text="PDF Page Remover",
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(txt, text="Remove page numbers / ranges · write a cleaned PDF",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                      scrollbar_button_color=C["border"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        banner = ctk.CTkFrame(body, fg_color=TINT["bg"], corner_radius=10,
                              border_width=1, border_color=C["accent"])
        banner.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\PDF_Page_Remover\\<timestamp>\\",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"]
        ).pack(anchor="w", padx=14, pady=8)

        self._section(body, "Step 1 — Select PDF")
        fr = ctk.CTkFrame(body, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 10))
        self._pdf_lbl = ctk.CTkLabel(
            fr, text="No PDF selected",
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w")
        self._pdf_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick
        ).pack(side="right")

        self._section(body, "Step 2 — Pages to remove")
        tip = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=10,
                           border_width=1, border_color=C["border"])
        tip.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(
            tip,
            text="Examples:  3-4, 11-14, 16    or    1,5,8-10\n"
                 "Page numbers are 1-based (first page = 1).",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
            justify="left", anchor="w",
        ).pack(anchor="w", padx=14, pady=10)

        self._pages_e = ctk.CTkEntry(
            body, height=40,
            fg_color=C["card"], border_color=C["border"],
            text_color=C["text"],
            placeholder_text="e.g. 3-4, 11-14, 16",
        )
        self._pages_e.pack(fill="x", pady=(0, 14))

        self._section(body, "Progress")
        self._prog = ctk.CTkProgressBar(body, height=8, fg_color=C["card"],
                                        progress_color=C["accent"])
        self._prog.pack(fill="x", pady=(4, 8))
        self._prog.set(0)
        self._stat = ctk.CTkLabel(body, text="Ready.",
                                  font=ctk.CTkFont("Segoe UI", 11),
                                  text_color=C["muted"], anchor="w")
        self._stat.pack(fill="x", pady=(0, 8))
        self._log = ctk.CTkTextbox(body, height=180,
                                   font=ctk.CTkFont("Courier New", 11),
                                   fg_color=C["card"],
                                   border_color=C["border"], border_width=1,
                                   text_color=C["muted"], state="disabled")
        self._log.pack(fill="x", pady=(0, 16))

        self._run_btn = ctk.CTkButton(
            body, text="▶  Remove Pages",
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            fg_color=TINT["mid"], hover_color=TINT["bdr"],
            text_color=C["accent"],
            border_color=C["accent"], border_width=1,
            corner_radius=24, height=48,
            command=self._start)
        self._run_btn.pack(fill="x", pady=(0, 20))

    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=text,
                     font=ctk.CTkFont("Segoe UI", 12, "bold"),
                     text_color=C["text"], anchor="w").pack(fill="x", pady=(10, 2))

    def _write(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _pick(self):
        path = filedialog.askopenfilename(
            title="Select PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            total = len(PdfReader(path).pages)
        except Exception as e:
            messagebox.showerror("Error", f"Could not read PDF:\n{e}")
            return
        self._pdf = path
        self._page_count = total
        self._pdf_lbl.configure(
            text=f"{path}  ({total} pages)",
            text_color=C["accent"],
        )

    def _start(self):
        if not self._pdf:
            messagebox.showwarning("Missing", "Select a PDF first.")
            return
        spec = self._pages_e.get().strip()
        try:
            pages = parse_pages_to_remove(spec, self._page_count)
        except ValueError as e:
            messagebox.showwarning("Invalid pages", str(e))
            return

        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.set(0)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(target=self._run, args=(pages,), daemon=True).start()

    def _run(self, pages_to_remove):
        out_dir = get_output_dir()
        base = os.path.splitext(os.path.basename(self._pdf))[0]
        out_path = os.path.join(out_dir, f"{base}_pages_removed.pdf")

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        try:
            log(f"PDF     → {self._pdf}")
            log(f"Remove  → {sorted(pages_to_remove)}")
            log(f"Output  → {out_dir}\n")
            self.after(0, lambda: self._prog.set(0.3))

            total, removed, kept = remove_pages(
                self._pdf, pages_to_remove, out_path, log
            )

            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — removed {removed}, kept {kept} of {total}.",
                text_color=C["green"]))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Removed: {removed} page(s)\n"
                f"Kept: {kept} page(s)\n\n{out_path}"
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Remove Pages"))


if __name__ == "__main__":
    App().mainloop()
