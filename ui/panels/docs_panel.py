import os
import customtkinter as ctk

from ui.theme import C, t
from ui.utils import download_sample


class DocsPanel(ctk.CTkFrame):
    """Full documentation viewer."""

    def __init__(self, parent, services, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.services = [s for s in services if s.get("docs")]
        self.selected = None
        self._build()

    def _build(self):
        # Topbar
        top = ctk.CTkFrame(self, height=62, fg_color=C["sidebar"], corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="Documentation",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(side="left", padx=26)
        ctk.CTkLabel(top, text="Step-by-step guides for every tool",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="left", padx=6)

        # Body — two-pane layout
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # Left: tool list
        left = ctk.CTkFrame(body, width=230, fg_color=C["card"],
                            corner_radius=14, border_width=1,
                            border_color=C["border"])
        left.pack(side="left", fill="y", padx=(0, 14))
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="  TOOLS",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["faint"], anchor="w"
                     ).pack(fill="x", pady=(14, 6), padx=10)

        self.nav_btns = []
        for svc in self.services:
            btn = ctk.CTkButton(
                left,
                text=f"  {svc['icon']}  {svc['title']}",
                anchor="w",
                font=ctk.CTkFont("Segoe UI", 12),
                fg_color="transparent",
                hover_color=C["hover"],
                text_color=C["muted"],
                corner_radius=10, height=40,
                command=lambda s=svc: self._show(s)
            )
            btn.pack(fill="x", padx=8, pady=2)
            self.nav_btns.append((svc, btn))

        # Right: scrollable content
        self.right = ctk.CTkScrollableFrame(
            body, fg_color=C["card"], corner_radius=14,
            border_width=1, border_color=C["border"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["cyan"])
        self.right.pack(side="left", fill="both", expand=True)

        self._placeholder()
        if self.services:
            self._show(self.services[0])

    def _placeholder(self):
        for w in self.right.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.right,
                     text="← Select a tool to view its guide",
                     font=ctk.CTkFont("Segoe UI", 14),
                     text_color=C["faint"]).pack(expand=True, pady=60)

    def _show(self, svc):
        self.selected = svc
        docs = svc["docs"]
        acc  = svc["accent"]

        for s, btn in self.nav_btns:
            if s is svc:
                btn.configure(fg_color=t(acc, "mid"), text_color=acc)
            else:
                btn.configure(fg_color="transparent", text_color=C["muted"])

        for w in self.right.winfo_children():
            w.destroy()

        pad = {"padx": 28}

        # Title bar
        title_row = ctk.CTkFrame(self.right, fg_color="transparent")
        title_row.pack(fill="x", pady=(22, 4), **pad)

        icon_f = ctk.CTkFrame(title_row, width=48, height=48,
                              fg_color=t(acc, "mid"), corner_radius=12)
        icon_f.pack(side="left", padx=(0, 14))
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text=svc["icon"],
                     font=ctk.CTkFont("Segoe UI Emoji", 20)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        txt_col = ctk.CTkFrame(title_row, fg_color="transparent")
        txt_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(txt_col, text=svc["title"],
                     font=ctk.CTkFont("Segoe UI", 18, "bold"),
                     text_color=C["text"], anchor="w").pack(fill="x")
        tag_pill = ctk.CTkFrame(txt_col, fg_color=t(acc, "bg"), corner_radius=20)
        tag_pill.pack(anchor="w", pady=(4, 0))
        ctk.CTkLabel(tag_pill, text=f"  {svc['tag']}  ",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=acc).pack(pady=2)

        self._divider()
        self._section_head("📌  What it does", acc)
        self._body_text(docs["what"])
        self._section_head("🕐  When to use it", acc)
        self._body_text(docs["when"])
        self._divider()
        self._section_head("🪜  Step-by-step guide", acc)

        for i, (title, detail) in enumerate(docs["steps"], 1):
            step_frame = ctk.CTkFrame(self.right,
                                      fg_color=t(acc, "bg"),
                                      corner_radius=12,
                                      border_width=1,
                                      border_color=t(acc, "bdr"))
            step_frame.pack(fill="x", pady=5, **pad)
            inner = ctk.CTkFrame(step_frame, fg_color="transparent")
            inner.pack(fill="x", padx=14, pady=10)

            badge = ctk.CTkFrame(inner, width=28, height=28,
                                 fg_color=t(acc, "mid"), corner_radius=14)
            badge.pack(side="left", anchor="n", pady=2)
            badge.pack_propagate(False)
            ctk.CTkLabel(badge, text=str(i),
                         font=ctk.CTkFont("Segoe UI", 11, "bold"),
                         text_color=acc).place(relx=0.5, rely=0.5, anchor="center")

            text_col = ctk.CTkFrame(inner, fg_color="transparent")
            text_col.pack(side="left", fill="x", expand=True, padx=(12, 0))
            ctk.CTkLabel(text_col, text=title,
                         font=ctk.CTkFont("Segoe UI", 12, "bold"),
                         text_color=C["text"], anchor="w").pack(fill="x")
            ctk.CTkLabel(text_col, text=detail,
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["muted"], anchor="w",
                         justify="left", wraplength=560
                         ).pack(fill="x", pady=(2, 0))

        self._divider()
        self._section_head("💡  Tips & notes", acc)
        for tip in docs["tips"]:
            row = ctk.CTkFrame(self.right, fg_color="transparent")
            row.pack(fill="x", pady=3, **pad)
            ctk.CTkLabel(row, text="•",
                         font=ctk.CTkFont("Segoe UI", 13, "bold"),
                         text_color=acc, width=16).pack(side="left", anchor="n", pady=1)
            ctk.CTkLabel(row, text=tip,
                         font=ctk.CTkFont("Segoe UI", 11),
                         text_color=C["muted"], anchor="w",
                         justify="left", wraplength=560
                         ).pack(side="left", fill="x", expand=True, padx=(6, 0))

        self._divider()
        self._section_head("📁  Output location", acc)
        out_frame = ctk.CTkFrame(self.right,
                                 fg_color=t(acc, "bg"),
                                 corner_radius=10,
                                 border_width=1,
                                 border_color=t(acc, "bdr"))
        out_frame.pack(fill="x", pady=(4, 16), **pad)
        ctk.CTkLabel(out_frame, text=docs["output"],
                     font=ctk.CTkFont("Courier New", 12),
                     text_color=acc).pack(padx=16, pady=12, anchor="w")

        self._divider()
        self._section_head("📂  Sample file", acc)
        sample_row = ctk.CTkFrame(self.right, fg_color="transparent")
        sample_row.pack(fill="x", pady=(2, 28), **pad)

        has_sample = svc.get("sample") and os.path.exists(svc["sample"])
        sample_note = (
            "Download a ready-made sample Excel file to test this tool immediately."
            if has_sample else
            "The sample file for this tool has not been added yet. It will appear here once available."
        )
        ctk.CTkLabel(sample_row, text=sample_note,
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"], anchor="w",
                     justify="left", wraplength=430
                     ).pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            sample_row,
            text="⭳  Download Sample",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=t(acc, "mid"),
            hover_color=t(acc, "bdr"),
            text_color=acc,
            border_color=acc, border_width=1,
            corner_radius=20, height=36, width=180,
            state="normal" if has_sample else "disabled",
            command=lambda s=svc: download_sample(s)
        ).pack(side="right", padx=(16, 0))

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _divider(self):
        ctk.CTkFrame(self.right, height=1, fg_color=C["border"]
                     ).pack(fill="x", padx=28, pady=(12, 8))

    def _section_head(self, text, accent):
        ctk.CTkLabel(self.right, text=text,
                     font=ctk.CTkFont("Segoe UI", 13, "bold"),
                     text_color=C["text"], anchor="w"
                     ).pack(fill="x", padx=28, pady=(8, 6))

    def _body_text(self, text):
        ctk.CTkLabel(self.right, text=text,
                     font=ctk.CTkFont("Segoe UI", 12),
                     text_color=C["muted"], anchor="w",
                     justify="left", wraplength=620
                     ).pack(fill="x", padx=28, pady=(0, 10))
