import subprocess
import sys
from tkinter import messagebox
import customtkinter as ctk

from ui.theme import C, t
from ui.utils import download_sample


# ─── Group Card ───────────────────────────────────────────────────────────────
class GroupCard(ctk.CTkFrame):
    """Slim card on the home grid. Clicking it calls open_cb(grp)."""

    def __init__(self, parent, grp, open_cb, **kw):
        super().__init__(parent, **kw)
        self.grp     = grp
        self.accent  = grp["accent"]
        self.open_cb = open_cb
        self.configure(
            fg_color=C["card"], corner_radius=16,
            border_width=1, border_color=C["border"],
            cursor="hand2"
        )
        self._build()
        self._bind_hover()

    def _build(self):
        ctk.CTkFrame(self, height=3, fg_color=self.accent, corner_radius=0).pack(fill="x")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=14)

        # Header
        hdr = ctk.CTkFrame(body, fg_color="transparent")
        hdr.pack(fill="x")

        icon_f = ctk.CTkFrame(hdr, width=42, height=42,
                              fg_color=t(self.accent, "mid"), corner_radius=10)
        icon_f.pack(side="left")
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text=self.grp["icon"],
                     font=ctk.CTkFont("Segoe UI Emoji", 18)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        count_f = ctk.CTkFrame(hdr, fg_color=t(self.accent, "mid"), corner_radius=10)
        count_f.pack(side="right")
        ctk.CTkLabel(count_f, text=f"  {self.grp['count']}  ",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=self.accent).pack(pady=3)

        ctk.CTkLabel(body, text=self.grp["title"],
                     font=ctk.CTkFont("Segoe UI", 14, "bold"),
                     text_color=C["text"], anchor="w"
                     ).pack(fill="x", pady=(10, 3))

        ctk.CTkLabel(body, text=self.grp["description"],
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"], anchor="w",
                     justify="left", wraplength=205
                     ).pack(fill="x")

        # Footer
        ftr = ctk.CTkFrame(body, fg_color="transparent")
        ftr.pack(fill="x", pady=(14, 0))

        pill = ctk.CTkFrame(ftr, fg_color=t(self.accent, "bg"), corner_radius=20)
        pill.pack(side="left")
        ctk.CTkLabel(pill, text=f"  {self.grp['tag']}  ",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=self.accent).pack(pady=3)

        ctk.CTkButton(
            ftr, text="Open →",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=t(self.accent, "mid"),
            hover_color=t(self.accent, "bdr"),
            text_color=self.accent,
            border_color=self.accent, border_width=1,
            corner_radius=20, height=30, width=90,
            command=lambda: self.open_cb(self.grp)
        ).pack(side="right")

    def _bind_hover(self):
        def bind_all(w):
            w.bind("<Button-1>", self._clicked)
            w.bind("<Enter>",    self._enter)
            w.bind("<Leave>",    self._leave)
            for ch in w.winfo_children():
                bind_all(ch)
        bind_all(self)

    def _clicked(self, _=None): self.open_cb(self.grp)
    def _enter(self,   _=None): self.configure(fg_color=C["hover"], border_color=self.accent)
    def _leave(self,   _=None): self.configure(fg_color=C["card"],  border_color=C["border"])


# ─── Service Card ─────────────────────────────────────────────────────────────
class ServiceCard(ctk.CTkFrame):
    def __init__(self, parent, svc, open_docs_cb=None, **kw):
        super().__init__(parent, **kw)
        self.svc          = svc
        self.accent       = svc["accent"]
        self.open_docs_cb = open_docs_cb
        self.configure(fg_color=C["card"], corner_radius=16,
                       border_width=1, border_color=C["border"])
        self._build()
        self._bind_hover()

    def _build(self):
        ctk.CTkFrame(self, height=3, fg_color=self.accent, corner_radius=0).pack(fill="x")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=14)

        # Header row
        hdr = ctk.CTkFrame(body, fg_color="transparent")
        hdr.pack(fill="x")

        icon_f = ctk.CTkFrame(hdr, width=42, height=42,
                              fg_color=t(self.accent, "mid"), corner_radius=10)
        icon_f.pack(side="left")
        icon_f.pack_propagate(False)
        ctk.CTkLabel(icon_f, text=self.svc["icon"],
                     font=ctk.CTkFont("Segoe UI Emoji", 18)
                     ).place(relx=0.5, rely=0.5, anchor="center")

        dot_color = C["green"] if self.svc["script"] else C["faint"]
        ctk.CTkFrame(hdr, width=8, height=8,
                     fg_color=dot_color, corner_radius=4
                     ).pack(side="right", pady=6)

        ctk.CTkLabel(body, text=self.svc["title"],
                     font=ctk.CTkFont("Segoe UI", 14, "bold"),
                     text_color=C["text"], anchor="w"
                     ).pack(fill="x", pady=(10, 3))

        ctk.CTkLabel(body, text=self.svc["description"],
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"], anchor="w",
                     justify="left", wraplength=205
                     ).pack(fill="x")

        # Footer
        ftr = ctk.CTkFrame(body, fg_color="transparent")
        ftr.pack(fill="x", pady=(14, 0))

        pill = ctk.CTkFrame(ftr, fg_color=t(self.accent, "bg"), corner_radius=20)
        pill.pack(side="left")
        ctk.CTkLabel(pill, text=f"  {self.svc['tag']}  ",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=self.accent).pack(pady=3)

        if self.svc.get("docs") and self.open_docs_cb:
            ctk.CTkButton(
                ftr, text="Docs",
                font=ctk.CTkFont("Segoe UI", 11),
                fg_color="transparent", hover_color=C["hover"],
                text_color=C["muted"],
                corner_radius=20, height=30, width=52,
                command=lambda: self.open_docs_cb(self.svc)
            ).pack(side="right", padx=(0, 4))

        if self.svc.get("sample") is not None:
            ctk.CTkButton(
                ftr, text="⭳ Sample",
                font=ctk.CTkFont("Segoe UI", 11),
                fg_color="transparent", hover_color=C["hover"],
                text_color=C["muted"],
                corner_radius=20, height=30, width=72,
                command=lambda s=self.svc: download_sample(s)
            ).pack(side="right", padx=(0, 2))

        btn_text = "Launch →" if self.svc["script"] else "Soon"
        ctk.CTkButton(
            ftr, text=btn_text,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=t(self.accent, "mid"),
            hover_color=t(self.accent, "bdr"),
            text_color=self.accent,
            border_color=self.accent, border_width=1,
            corner_radius=20, height=30, width=90,
            command=self._launch
        ).pack(side="right")

    def _bind_hover(self):
        def bind_all(w):
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)
            for ch in w.winfo_children():
                bind_all(ch)
        bind_all(self)

    def _enter(self, _=None): self.configure(fg_color=C["hover"], border_color=self.accent)
    def _leave(self, _=None): self.configure(fg_color=C["card"],  border_color=C["border"])

    def _launch(self):
        script = self.svc.get("script")
        if not script:
            messagebox.showinfo(
                "Coming Soon",
                f"'{self.svc['title']}' is not yet available.\n"
                "It will be added in a future update."
            )
            return
        try:
            subprocess.Popen([sys.executable, script])
        except Exception as e:
            messagebox.showerror("Error", f"Could not launch:\n{e}")
