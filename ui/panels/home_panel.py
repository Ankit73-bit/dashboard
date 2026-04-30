from datetime import datetime
import customtkinter as ctk

from ui.theme import C, t
from ui.data import GROUPS
from ui.cards import GroupCard, ServiceCard


class HomePanel(ctk.CTkFrame):
    def __init__(self, parent, services, open_docs_cb, open_group_cb, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.services      = services
        self.open_docs_cb  = open_docs_cb
        self.open_group_cb = open_group_cb
        self._build()

    def _build(self):
        # Topbar
        top = ctk.CTkFrame(self, height=62, fg_color=C["sidebar"], corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="All Services",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(side="left", padx=26)

        self.clock_lbl = ctk.CTkLabel(top, text="",
                                      font=ctk.CTkFont("Segoe UI", 11),
                                      text_color=C["muted"])
        self.clock_lbl.pack(side="right", padx=26)
        self._tick()

        # Stats bar
        stats_bar = ctk.CTkFrame(self, fg_color="transparent")
        stats_bar.pack(fill="x", padx=26, pady=(18, 6))

        group_tool_count = sum(len(g["tools"]) for g in GROUPS)
        active_scripts   = sum(1 for s in self.services if s["script"]) + group_tool_count
        coming_soon      = sum(1 for s in self.services if not s["script"])
        total_tools      = len(self.services) + group_tool_count

        for label, val, color in [
            ("Total Tools",            str(total_tools),    C["cyan"]),
            ("Active",                 str(active_scripts), C["green"]),
            ("Coming Soon",            str(coming_soon),    C["orange"]),
            ("Output: Desktop/OUTPUT", "📁",               C["purple"]),
        ]:
            sc = ctk.CTkFrame(stats_bar, fg_color=C["card"], corner_radius=12,
                              border_width=1, border_color=C["border"])
            sc.pack(side="left", padx=(0, 10))
            ctk.CTkLabel(sc, text=val,
                         font=ctk.CTkFont("Segoe UI", 20, "bold"),
                         text_color=color).pack(padx=18, pady=(8, 0))
            ctk.CTkLabel(sc, text=label,
                         font=ctk.CTkFont("Segoe UI", 10),
                         text_color=C["muted"]).pack(padx=18, pady=(0, 8))

        ctk.CTkLabel(self, text="AVAILABLE TOOLS",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["faint"]).pack(anchor="w", padx=28, pady=(6, 2))

        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["cyan"])
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        scroll.columnconfigure(0, weight=1)
        scroll.columnconfigure(1, weight=1)
        scroll.columnconfigure(2, weight=1)

        all_cards = [("group", g) for g in GROUPS] + [("service", s) for s in self.services]
        for i, (kind, item) in enumerate(all_cards):
            if kind == "group":
                GroupCard(scroll, item, open_cb=self.open_group_cb).grid(
                    row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")
            else:
                ServiceCard(scroll, item, open_docs_cb=self.open_docs_cb).grid(
                    row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")

    def _tick(self):
        self.clock_lbl.configure(
            text=datetime.now().strftime("%a, %d %b %Y  •  %H:%M:%S"))
        self.after(1000, self._tick)
