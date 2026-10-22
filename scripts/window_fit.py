"""
Shared window helpers so tool UIs fit laptops and keep the run action visible.
"""

import os
import sys
import customtkinter as ctk


def ensure_importable():
    """Allow paras_print_scripts/ and scan_letter/ to import this module."""
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def fit_to_screen(win, default_w=800, default_h=720, min_w=640, min_h=520):
    """Size and center a CTk window within the working screen (taskbar-safe)."""
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    w = min(default_w, max(min_w, sw - 80))
    h = min(default_h, max(min_h, sh - 100))
    w = min(w, max(min_w, sw - 40))
    h = min(h, max(min_h, sh - 80))
    x = max(10, (sw - w) // 2)
    y = max(10, (sh - h) // 6)
    try:
        win.minsize(min_w, min_h)
    except Exception:
        pass
    try:
        win.resizable(True, True)
    except Exception:
        pass
    win.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")


def _accent(C):
    return C.get("accent") or C.get("cyan") or "#00f5ff"


def add_run_footer(parent, C, TINT):
    """
    Pin a footer (progress + status). Pack BEFORE the scrollable body.
    Caller adds the run button (and optional Pause/Cancel) onto `inner`.
    Returns (footer, inner, prog, stat).
    """
    accent = _accent(C)
    footer = ctk.CTkFrame(
        parent, fg_color=C["card"], corner_radius=0,
        border_width=1, border_color=C["border"],
    )
    footer.pack(side="bottom", fill="x")
    inner = ctk.CTkFrame(footer, fg_color="transparent")
    inner.pack(fill="x", padx=16, pady=10)

    prog = ctk.CTkProgressBar(
        inner, height=6,
        fg_color=C.get("hover", C["card"]),
        progress_color=accent,
    )
    prog.pack(fill="x", pady=(0, 6))
    prog.set(0)

    stat = ctk.CTkLabel(
        inner, text="Ready.",
        font=ctk.CTkFont("Segoe UI", 11),
        text_color=C["muted"], anchor="w",
    )
    stat.pack(fill="x", pady=(0, 8))
    return footer, inner, prog, stat


def attach_panel_chrome(panel, C, TINT, run_text, run_command):
    """
    Sticky footer + inner scroll for embeddable PanelContent (CTkFrame).
    Call first in __init__. Returns (body, prog, stat, run_btn).
    """
    _, fi, prog, stat = add_run_footer(panel, C, TINT)
    run_btn = add_primary_run_button(fi, run_text, run_command, C, TINT)
    body = ctk.CTkScrollableFrame(
        panel, fg_color="transparent",
        scrollbar_button_color=C["border"],
    )
    body.pack(fill="both", expand=True, padx=4, pady=(8, 4))
    return body, prog, stat, run_btn


def add_primary_run_button(parent, text, command, C, TINT, height=42):
    accent = _accent(C)
    btn = ctk.CTkButton(
        parent, text=text,
        font=ctk.CTkFont("Segoe UI", 14, "bold"),
        fg_color=TINT.get("mid", accent),
        hover_color=TINT.get("bdr", accent),
        text_color=accent,
        border_color=accent, border_width=1,
        corner_radius=24, height=height,
        command=command,
    )
    btn.pack(fill="x")
    return btn
