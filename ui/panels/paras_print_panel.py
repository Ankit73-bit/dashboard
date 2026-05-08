import os
import customtkinter as ctk

from ui.theme import C, t
from ui.cards import ServiceCard

# ─── Paras Print service definitions ─────────────────────────────────────────
HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PP_SCRIPTS = os.path.join(HERE, "paras_print_scripts")

PARAS_PRINT_SERVICES = [
    {
        "title":       "Grouped Excel",
        "description": "Group rows by a key column, join IDs with '/', and add an ID count — all in one click.",
        "icon":        "📊",
        "accent":      C["cyan"],
        "tag":         "Excel",
        "script":      os.path.join(PP_SCRIPTS, "grouped_excel.py"),
        "sample":      None,
        "docs": {
            "what": "Reads an Excel file, groups all rows by a chosen column (e.g. 'location code'), joins a selected ID column (e.g. 'Employee Code') with a configurable separator (default '/'), takes the first value for every other column, and appends an ID Count column showing how many IDs were merged per group.",
            "when": "Use this when you have multiple rows per location/department and want to consolidate them into one row per group with all employee codes listed together.",
            "steps": [
                ("Open the tool", "Click 'Launch →' on the Grouped Excel card."),
                ("Select input file", "Click 'Browse…' and pick your .xlsx or .xls source file. Column names are auto-detected and shown as a hint."),
                ("Group-by column", "Enter the exact column header to group on (e.g. 'location code'). Auto-filled if detected."),
                ("ID column", "Enter the exact column header whose values will be joined (e.g. 'Employee Code'). Auto-filled if detected."),
                ("Separator", "Choose the character to join IDs with. Default is '/'. You can change it to ', ' or any other string."),
                ("Click Run", "Click '▶  Group & Merge'. A progress bar and log track the operation. The output folder opens automatically when done."),
            ],
            "tips": [
                "Column names are case-sensitive — type them exactly as they appear in the header row.",
                "Output is saved to Desktop\\OUTPUT\\Grouped_Excel\\<timestamp>\\ — the original file is never modified.",
                "All columns other than the group and ID columns take their value from the first row in each group.",
                "The 'ID Count' column is always placed as the third column in the output.",
                "The tool runs in a background thread so the UI stays responsive on large files.",
            ],
            "output": "Desktop\\OUTPUT\\Grouped_Excel\\<timestamp>\\  (opens automatically after run).",
        },
    },
]


class ParasPrintPanel(ctk.CTkFrame):
    """Paras Print tab — shows all Paras Print service cards."""

    def __init__(self, master, open_docs_cb=None, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self.open_docs_cb = open_docs_cb
        self._build()

    def _build(self):
        # ── Topbar ────────────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, height=62, fg_color=C["sidebar"], corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="🖨️  Paras Print",
                     font=ctk.CTkFont("Segoe UI", 17, "bold"),
                     text_color=C["text"]).pack(side="left", padx=26)

        count_pill = ctk.CTkFrame(top, fg_color=t(C["cyan"], "mid"), corner_radius=10)
        count_pill.pack(side="right", padx=20)
        ctk.CTkLabel(count_pill,
                     text=f"  {len(PARAS_PRINT_SERVICES)} tool{'s' if len(PARAS_PRINT_SERVICES) != 1 else ''}  ",
                     font=ctk.CTkFont("Segoe UI", 11, "bold"),
                     text_color=C["cyan"]).pack(pady=4)

        # ── Section label ─────────────────────────────────────────────────────
        ctk.CTkLabel(self,
                     text="PARAS PRINT TOOLS",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["faint"]).pack(anchor="w", padx=28, pady=(14, 2))

        # ── Scrollable card grid ──────────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["cyan"])
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        scroll.columnconfigure(0, weight=1)
        scroll.columnconfigure(1, weight=1)
        scroll.columnconfigure(2, weight=1)

        for i, svc in enumerate(PARAS_PRINT_SERVICES):
            ServiceCard(scroll, svc, open_docs_cb=self.open_docs_cb).grid(
                row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")
