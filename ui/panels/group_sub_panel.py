import customtkinter as ctk

from ui.theme import C, t
from ui.cards import ServiceCard


class GroupSubPanel(ctk.CTkFrame):
    """Full-page panel showing the individual tool cards inside a group."""

    def __init__(self, parent, grp, back_cb, open_docs_cb, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.grp          = grp
        self.back_cb      = back_cb
        self.open_docs_cb = open_docs_cb
        self._build()

    def _build(self):
        acc = self.grp["accent"]

        # Topbar
        top = ctk.CTkFrame(self, height=62, fg_color=C["sidebar"], corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkButton(
            top, text="←  Back",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color="transparent", hover_color=C["hover"],
            text_color=C["muted"], corner_radius=10,
            height=32, width=80,
            command=self.back_cb
        ).pack(side="left", padx=(16, 0))

        crumb = ctk.CTkFrame(top, fg_color="transparent")
        crumb.pack(side="left", padx=8)
        ctk.CTkLabel(crumb, text="Home",
                     font=ctk.CTkFont("Segoe UI", 13),
                     text_color=C["faint"]).pack(side="left")
        ctk.CTkLabel(crumb, text="  /  ",
                     font=ctk.CTkFont("Segoe UI", 13),
                     text_color=C["faint"]).pack(side="left")
        ctk.CTkLabel(crumb, text=self.grp["title"],
                     font=ctk.CTkFont("Segoe UI", 13, "bold"),
                     text_color=acc).pack(side="left")

        ctk.CTkLabel(top, text=self.grp["count"],
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="right", padx=26)

        # Section label
        ctk.CTkLabel(self,
                     text=f"{self.grp['icon']}  {self.grp['title'].upper()} TOOLS",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["faint"]).pack(anchor="w", padx=28, pady=(14, 2))

        # Card grid
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=acc)
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        scroll.columnconfigure(0, weight=1)
        scroll.columnconfigure(1, weight=1)
        scroll.columnconfigure(2, weight=1)

        for i, svc in enumerate(self.grp["tools"]):
            ServiceCard(scroll, svc, open_docs_cb=self.open_docs_cb).grid(
                row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")
