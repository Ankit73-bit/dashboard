import customtkinter as ctk

from ui.theme import C


class ParasPrintPanel(ctk.CTkFrame):
    """Placeholder panel for Paras Print — services will be added here."""

    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._build()

    def _build(self):
        # Topbar
        top = ctk.CTkFrame(self, height=62, fg_color=C["sidebar"], corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="Paras Print",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(side="left", padx=26)

        # Coming-soon body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        ctk.CTkLabel(body, text="🖨️",
                     font=ctk.CTkFont(size=52)).pack(pady=(80, 12))
        ctk.CTkLabel(body, text="Paras Print",
                     font=ctk.CTkFont("Segoe UI", 26, "bold"),
                     text_color=C["text"]).pack()
        ctk.CTkLabel(body, text="Services coming soon.",
                     font=ctk.CTkFont("Segoe UI", 14),
                     text_color=C["muted"]).pack(pady=(8, 0))
