from tkinter import messagebox
import customtkinter as ctk

from ui.theme import C, t
from ui.data import GROUPS, SERVICES
from ui.panels.home_panel       import HomePanel
from ui.panels.docs_panel       import DocsPanel
from ui.panels.group_sub_panel  import GroupSubPanel
from ui.panels.paras_print_panel import ParasPrintPanel


class Dashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Dashboard")
        self.geometry("1120x730")
        self.minsize(960, 620)
        self.configure(fg_color=C["bg"])
        self._build()

    def _build(self):
        # ── Sidebar ──────────────────────────────────────────────────────────
        sb = ctk.CTkFrame(self, width=220, fg_color=C["sidebar"], corner_radius=0)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        logo = ctk.CTkFrame(sb, fg_color="transparent")
        logo.pack(fill="x", padx=20, pady=(24, 8))
        ctk.CTkLabel(logo, text="⬡", font=ctk.CTkFont(size=26),
                     text_color=C["cyan"]).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(logo, text="Dashboard",
                     font=ctk.CTkFont("Segoe UI", 19, "bold"),
                     text_color=C["text"]).pack(side="left")

        ctk.CTkFrame(sb, height=1, fg_color=C["border"]).pack(
            fill="x", padx=20, pady=(6, 18))

        self.nav_state = {}

        nav_items = [
            ("🏠", "Home",        self._show_home),
            ("🖨️", "Paras Print", self._show_paras_print),
            ("📖", "Docs",        self._show_docs),
            ("⚙️", "Settings",    None),
            ("❓", "Help",         None),
        ]

        for icon, label, cmd in nav_items:
            btn = ctk.CTkButton(
                sb, text=f"  {icon}   {label}", anchor="w",
                font=ctk.CTkFont("Segoe UI", 13),
                fg_color="transparent",
                hover_color=C["hover"],
                text_color=C["muted"],
                corner_radius=10, height=42,
                border_width=0,
                border_color=C["sidebar"],
                command=(cmd if cmd else lambda l=label: self._nav_noop(l))
            )
            btn.pack(fill="x", padx=12, pady=2)
            self.nav_state[label] = btn

        ctk.CTkLabel(sb, text="v1.0.0",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["faint"]).pack(side="bottom", pady=20)

        # ── Main container ────────────────────────────────────────────────────
        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.pack(side="left", fill="both", expand=True)

        all_services_for_docs = (
            [tool for grp in GROUPS for tool in grp["tools"]]
            + SERVICES
        )

        # Pre-build all panels
        self.home_panel        = HomePanel(
            self.main, SERVICES,
            open_docs_cb=self._open_docs_for,
            open_group_cb=self._open_group
        )
        self.docs_panel        = DocsPanel(self.main, all_services_for_docs)
        self.paras_print_panel = ParasPrintPanel(self.main)
        self.sub_panel         = None   # created on demand per group

        self._show_home()

    # ── Nav helpers ───────────────────────────────────────────────────────────
    def _all_panels(self):
        panels = [self.home_panel, self.docs_panel, self.paras_print_panel]
        if self.sub_panel:
            panels.append(self.sub_panel)
        return panels

    def _hide_all(self):
        for p in self._all_panels():
            p.pack_forget()

    def _set_active_nav(self, label):
        for lbl, btn in self.nav_state.items():
            if lbl == label:
                btn.configure(
                    fg_color=t(C["cyan"], "bg"),
                    text_color=C["cyan"],
                    border_width=1,
                    border_color=t(C["cyan"], "bdr"))
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=C["muted"],
                    border_width=0,
                    border_color=C["sidebar"])

    # ── Panel switches ────────────────────────────────────────────────────────
    def _show_home(self):
        self._hide_all()
        self.home_panel.pack(fill="both", expand=True)
        self._set_active_nav("Home")

    def _show_docs(self):
        self._hide_all()
        self.docs_panel.pack(fill="both", expand=True)
        self._set_active_nav("Docs")

    def _show_paras_print(self):
        self._hide_all()
        self.paras_print_panel.pack(fill="both", expand=True)
        self._set_active_nav("Paras Print")

    def _open_group(self, grp):
        if self.sub_panel:
            self.sub_panel.destroy()
        self.sub_panel = GroupSubPanel(
            self.main, grp,
            back_cb=self._show_home,
            open_docs_cb=self._open_docs_for
        )
        self._hide_all()
        self.sub_panel.pack(fill="both", expand=True)
        self._set_active_nav("Home")

    def _open_docs_for(self, svc):
        self._show_docs()
        self.docs_panel._show(svc)

    def _nav_noop(self, label):
        messagebox.showinfo("Coming Soon", f"'{label}' section is not yet available.")
