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
            "what": "Reads an Excel file, groups all rows by a chosen column (e.g. 'location code'), joins a selected ID column (e.g. 'Employee Code') with a configurable separator (default '/'), takes the first value for every other column, and appends an ID Count column.",
            "when": "Use this when you have multiple rows per location/department and want one row per group with all employee codes listed together.",
            "steps": [
                ("Select input file", "Click 'Browse…' and pick your .xlsx or .xls source file. Column names are auto-detected."),
                ("Group-by column", "Enter the exact column header to group on (e.g. 'location code'). Auto-filled if detected."),
                ("ID column", "Enter the exact column header whose values will be joined (e.g. 'Employee Code'). Auto-filled if detected."),
                ("Separator", "Choose the character to join IDs with. Default is '/'."),
                ("Click Run", "Click '▶  Group & Merge'. The output folder opens automatically."),
            ],
            "tips": [
                "Column names are case-sensitive — type them exactly as they appear in the header row.",
                "Output is saved to Desktop\\OUTPUT\\Grouped_Excel\\<timestamp>\\",
                "The 'ID Count' column is always placed as the third column in the output.",
            ],
            "output": "Desktop\\OUTPUT\\Grouped_Excel\\<timestamp>\\",
        },
    },
    {
        "title":       "PDF to JPG",
        "description": "Convert a single PDF or an entire folder of PDFs to JPG images — one image per page.",
        "icon":        "🖼️",
        "accent":      C["orange"],
        "tag":         "PDF",
        "script":      os.path.join(PP_SCRIPTS, "pdf_to_jpg.py"),
        "sample":      None,
        "docs": {
            "what": "Uses pdf2image (poppler) to convert each page of one or more PDF files into high-quality JPG images. Supports single-file mode and batch folder mode.",
            "when": "Use this when you need image versions of PDF pages — e.g. for printing, uploading to systems that don't accept PDFs, or creating previews.",
            "steps": [
                ("Select mode", "Choose 'Single PDF file' for one file, or 'Folder of PDFs' to batch-convert a whole folder."),
                ("Browse source", "Click 'Browse…' to pick the PDF file or folder."),
                ("Set DPI", "Enter the desired resolution. 150 is a good default; use 300 for print quality."),
                ("Click Run", "Click '▶  Convert to JPG'. Output folder opens when done."),
            ],
            "tips": [
                "Requires pdf2image: pip install pdf2image",
                "Also requires Poppler installed and added to your system PATH.",
                "DPI 72 = screen quality, 150 = good balance, 300 = high print quality.",
                "Output files are named <pdf_name>_page_001.jpg, _page_002.jpg, etc.",
            ],
            "output": "Desktop\\OUTPUT\\PDF_to_JPG\\<timestamp>\\",
        },
    },
    {
        "title":       "Photo Splitter",
        "description": "Match employee photos to Excel lists and copy them into separate folders per Excel file.",
        "icon":        "🗂️",
        "accent":      C["purple"],
        "tag":         "Photos",
        "script":      os.path.join(PP_SCRIPTS, "photo_splitter.py"),
        "sample":      None,
        "docs": {
            "what": "Reads each Excel file in a folder, extracts employee codes, then copies matching photos from a source folder into a dedicated subfolder per Excel file. Writes a missing_images.txt log for any codes without a matching photo.",
            "when": "Use this when you have a master photo pool and need to distribute photos into location- or group-specific folders based on Excel rosters.",
            "steps": [
                ("Select photos folder", "Browse to the folder containing all employee photos (named by employee code)."),
                ("Select Excel folder", "Browse to the folder containing one or more .xlsx/.xls files."),
                ("Employee Code column", "Enter the column name in the Excel files that holds the employee code. Default: 'Employee Code'."),
                ("Click Run", "Click '▶  Split Photos'. A subfolder is created per Excel file inside the output folder."),
            ],
            "tips": [
                "Photo files must be named exactly as the employee code (e.g. 'EMP001.jpg').",
                "Supports .jpg, .jpeg, .png (case-insensitive extensions).",
                "A missing_images.txt file is written inside each subfolder listing unmatched codes.",
            ],
            "output": "Desktop\\OUTPUT\\Photo_Splitter\\<timestamp>\\<excel_name>\\",
        },
    },
    {
        "title":       "Missing Photos",
        "description": "Find photos present in SOURCE but absent in EDITED/OUTPUT — copy them out instantly.",
        "icon":        "🔍",
        "accent":      C["pink"],
        "tag":         "Photos",
        "script":      os.path.join(PP_SCRIPTS, "missing_photos.py"),
        "sample":      None,
        "docs": {
            "what": "Compares two folders by filename. Any file that exists in the SOURCE folder but is missing from the EDITED folder is copied to the output folder. Useful for finding photos that weren't processed or edited.",
            "when": "Use this after editing a batch of photos when you want to quickly identify and isolate the ones that were skipped or missed.",
            "steps": [
                ("Select SOURCE folder", "Browse to the original/unedited photos folder."),
                ("Select EDITED folder", "Browse to the folder containing the processed/edited versions."),
                ("Click Run", "Click '▶  Find & Copy Missing'. Missing files are copied to the output folder."),
            ],
            "tips": [
                "Comparison is done by filename — file contents are not compared.",
                "If all files are accounted for, the tool reports success and nothing is copied.",
            ],
            "output": "Desktop\\OUTPUT\\Missing_Photos\\<timestamp>\\",
        },
    },
    {
        "title":       "Photo Renamer",
        "description": "Rename employee photos to their IDs from Excel/CSV, convert to PNG, log duplicates and missing rows.",
        "icon":        "✏️",
        "accent":      C["gold"],
        "tag":         "Photos",
        "script":      os.path.join(PP_SCRIPTS, "photo_renamer.py"),
        "sample":      None,
        "docs": {
            "what": "Loads an Excel or CSV file, reads employee IDs from a chosen column, then renames and converts matching photos to PNG files named by employee ID. Generates logs.txt (not-found + duplicates) and not_found_rows.xlsx (rows with no matching photo).",
            "when": "Use this when you receive photos with arbitrary filenames and need to rename them to match a canonical employee ID list.",
            "steps": [
                ("Select data file", "Browse to your .xlsx, .xls, or .csv file. Columns are auto-detected."),
                ("Select ID column", "Enter or confirm the employee ID column. Auto-filled if a common name is detected."),
                ("Select photos folder", "Browse to the folder of photos to rename."),
                ("Click Run", "Click '▶  Rename & Convert'. Renamed PNGs, logs.txt, and not_found_rows.xlsx are saved to the output folder."),
            ],
            "tips": [
                "Requires Pillow: pip install Pillow",
                "Matching checks if the photo filename starts with or contains the employee ID (case-insensitive).",
                "Duplicate matches (multiple photos for one ID) are logged in logs.txt.",
                "not_found_rows.xlsx contains all Excel rows whose IDs had no matching photo.",
            ],
            "output": "Desktop\\OUTPUT\\Photo_Renamer\\<timestamp>\\renamed\\",
        },
    },
    {
        "title":       "BG Changer",
        "description": "Resize photos to exact mm size, remove background with AI (rembg), and apply any solid colour.",
        "icon":        "🎨",
        "accent":      C["teal"],
        "tag":         "Photos",
        "script":      os.path.join(PP_SCRIPTS, "bg_changer.py"),
        "sample":      None,
        "docs": {
            "what": "Resizes each photo to a precise mm × mm size at a given DPI, removes the background using the rembg AI model, then composites the subject onto a solid colour background of your choice. Preset swatches (white, red, blue, etc.) plus a full colour picker are provided.",
            "when": "Use this to produce passport/ID photos with a standard background colour, or whenever you need clean AI-cutout photos on a specific colour.",
            "steps": [
                ("Select photos folder", "Browse to the folder of photos to process."),
                ("Set size & DPI", "Enter target width (mm), height (mm), and DPI. Default is 24×28mm at 300 DPI."),
                ("Pick background colour", "Click a preset swatch or use the colour picker for a custom hex value."),
                ("Click Run", "Click '▶  Change Background'. Progress is shown per image. Output folder opens when done."),
            ],
            "tips": [
                "Requires Pillow (pip install Pillow) and rembg (pip install rembg).",
                "rembg downloads a model on first use — this takes a moment but only happens once.",
                "24×28mm @ 300 DPI is a common passport photo size — adjust as needed.",
                "Output PNGs are saved inside an 'output' subfolder inside the timestamped output directory.",
                "Temporary resize and mask files are saved in _resized_temp and _masked_temp subfolders.",
            ],
            "output": "Desktop\\OUTPUT\\BG_Changer\\<timestamp>\\output\\",
        },
    },
    {
        "title":       "B&W Converter",
        "description": "Convert photos to grayscale — transparent backgrounds (PNG alpha) are preserved, no black fill.",
        "icon":        "🔲",
        "accent":      C["sky"],
        "tag":         "Photos",
        "script":      os.path.join(PP_SCRIPTS, "bw_converter.py"),
        "sample":      None,
        "docs": {
            "what": "Converts each image's visible area to grayscale using luminance weighting, while keeping any existing alpha channel intact. PNG files with transparent backgrounds stay transparent — they don't get a black background.",
            "when": "Use this after BG Changer (or any background-removal step) to produce black-and-white versions without losing the transparent cutout.",
            "steps": [
                ("Select mode", "Choose 'Single image' for one file, or 'Folder of images' for batch."),
                ("Browse source", "Click 'Browse…' to pick the image or folder."),
                ("Click Run", "Click '▶  Convert to B&W'. All output is saved as PNG to the output folder."),
            ],
            "tips": [
                "Requires Pillow: pip install Pillow",
                "Output is always PNG to preserve alpha channel quality.",
                "Works on .png, .jpg, .jpeg, .webp, .bmp, .tiff inputs.",
                "Pair with BG Changer: run BG Changer first (white background removal), then B&W Converter.",
            ],
            "output": "Desktop\\OUTPUT\\BW_Converter\\<timestamp>\\",
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
                     text=f"  {len(PARAS_PRINT_SERVICES)} tools  ",
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
