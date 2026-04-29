import customtkinter as ctk
import subprocess
import sys
import os
from tkinter import messagebox
from datetime import datetime
import shutil

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ─── Colors ────────────────────────────────────────────────────────────────────
C = {
    "bg":       "#0a0a0f",
    "sidebar":  "#111118",
    "card":     "#16161f",
    "hover":    "#1e1e2e",
    "border":   "#2a2a3d",
    "text":     "#e8e8f0",
    "muted":    "#8888aa",
    "faint":    "#44445a",
    "cyan":     "#00f5ff",
    "green":    "#30d158",
    "purple":   "#bf5af2",
    "orange":   "#ff9f0a",
    "pink":     "#ff375f",
    "blue":     "#0a84ff",
}

TINTS = {
    "#00f5ff": {"bg": "#062d30", "mid": "#0a4a4e", "bdr": "#0d6b70"},
    "#30d158": {"bg": "#082a12", "mid": "#0f4020", "bdr": "#185c2e"},
    "#bf5af2": {"bg": "#2a1040", "mid": "#3d1860", "bdr": "#5a2580"},
    "#ff9f0a": {"bg": "#2e1e00", "mid": "#4a3000", "bdr": "#6b4500"},
    "#ff375f": {"bg": "#300a14", "mid": "#4e1020", "bdr": "#701830"},
    "#0a84ff": {"bg": "#001830", "mid": "#002850", "bdr": "#003d78"},
}

def t(accent, level="bg"):
    return TINTS.get(accent, {}).get(level, "#1a1a2e")


def download_sample(svc):
    """Copy the sample file to the user's Desktop and open it."""
    sample_path = svc.get("sample")
    if not sample_path:
        messagebox.showinfo("No Sample", f"No sample file is available for '{svc['title']}' yet.")
        return
    if not os.path.exists(sample_path):
        messagebox.showwarning(
            "Sample Not Found",
            f"The sample file for '{svc['title']}' has not been added yet.\n\n"
            f"Expected location:\n{sample_path}"
        )
        return
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    dest    = os.path.join(desktop, os.path.basename(sample_path))
    try:
        shutil.copy2(sample_path, dest)
        subprocess.Popen(["explorer", "/select,", dest])
        messagebox.showinfo(
            "Sample Downloaded",
            f"Sample file saved to your Desktop:\n{os.path.basename(sample_path)}"
        )
    except Exception as e:
        messagebox.showerror("Error", f"Could not copy sample file:\n{e}")

# ─── Folder paths (relative to this file) ─────────────────────────────────────
HERE    = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "scripts")
SAMPLES = os.path.join(HERE, "samples")

# ─── Group Definitions (each group card drills into sub-tool cards) ─────────
GROUPS = [
    {
        "title":       "PDF Downloads",
        "description": "Download PDFs from Excel URL lists — with or without renaming.",
        "icon":        "📥",
        "accent":      C["cyan"],
        "tag":         "PDF · Excel",
        "count":       "2 tools",
        "tools": [
            {
                "title":       "PDF Download & Rename",
                "description": "Download PDFs from an Excel list of URLs and rename each file using a custom ID column.",
                "icon":        "⚡",
                "accent":      C["green"],
                "tag":         "PDF · Excel",
                "script":      os.path.join(SCRIPTS, "pdf_downloader_rename.py"),
                "sample":      os.path.join(SAMPLES, "sample_pdf_download_rename.xlsx"),
                "docs": {
                    "what": "Downloads PDF files from a list of URLs stored in an Excel file, then renames each downloaded file using a unique ID from another column in the same sheet.",
                    "when": "Use this when you have an Excel sheet with a column of PDF URLs and a column of IDs/names, and you want each PDF saved with its matching ID as the filename.",
                    "steps": [
                        ("Open the tool", "Click 'Launch →' on the PDF Download & Rename card."),
                        ("Select your Excel file", "Click 'Browse' and choose the .xlsx or .xls file that contains your URL list."),
                        ("Enter the URL column name", "Type the exact column header that contains the PDF URLs (e.g. 'URL' or 'Link'). It is case-sensitive."),
                        ("Enter the ID column name", "Type the exact column header whose values will be used as filenames (e.g. 'ID' or 'File Name'). Each PDF will be saved as <ID>.pdf."),
                        ("Enter the sheet name (optional)", "If your data is not on the first sheet, type the exact sheet name. Leave blank to use the first sheet."),
                        ("Click 'Start Download'", "The tool will begin downloading. A progress bar shows how many files are done. The log area shows each file's status in real time."),
                        ("Find your files", "When complete, a folder will open automatically. Files are saved to: Desktop → OUTPUT → PDF_Downloads_Renamed → <timestamp folder>."),
                    ],
                    "tips": [
                        "Make sure column names match exactly — including spaces and capitalisation.",
                        "If a URL is invalid or the PDF cannot be reached, that row is skipped and logged as an error.",
                        "Each run creates a new timestamped folder, so old downloads are never overwritten.",
                        "You can close the tool after downloading — files stay in the OUTPUT folder.",
                    ],
                    "output": "Desktop\\OUTPUT\\PDF_Downloads_Renamed\\YYYY-MM-DD_HH-MM-SS\\",
                },
            },
            {
                "title":       "PDF Downloader",
                "description": "Download PDFs from an Excel URL list. Keeps original filenames — no renaming.",
                "icon":        "📄",
                "accent":      C["cyan"],
                "tag":         "PDF",
                "script":      os.path.join(SCRIPTS, "pdf_downloader_only.py"),
                "sample":      os.path.join(SAMPLES, "sample_pdf_download_only.xlsx"),
                "docs": {
                    "what": "Downloads PDF files from a list of URLs stored in an Excel file. Each file is saved using the filename from the URL itself — no renaming is applied.",
                    "when": "Use this when you just need to bulk-download PDFs and the original filename from the URL is fine to keep.",
                    "steps": [
                        ("Open the tool", "Click 'Launch →' on the PDF Downloader card."),
                        ("Select your Excel file", "Click 'Browse' and choose the .xlsx or .xls file that contains your URL list."),
                        ("Enter the URL column name", "Type the exact column header that contains the PDF URLs (e.g. 'URL' or 'Download Link'). It is case-sensitive."),
                        ("Enter the sheet name (optional)", "If your data is not on the first sheet, type the exact sheet name. Leave blank to use the first sheet."),
                        ("Click 'Start Download'", "The tool downloads each PDF. Progress and status are shown in real time in the log area below."),
                        ("Find your files", "When complete, the output folder opens automatically. Files are saved to: Desktop → OUTPUT → PDF_Downloads_Only → <timestamp folder>."),
                    ],
                    "tips": [
                        "If two URLs have the same filename, the second will overwrite the first — rename them after if needed.",
                        "URLs must point directly to a .pdf file for best results.",
                        "Rows with blank or invalid URLs are skipped and noted in the log.",
                        "Each run creates a fresh timestamped folder, so previous runs are always preserved.",
                    ],
                    "output": "Desktop\\OUTPUT\\PDF_Downloads_Only\\YYYY-MM-DD_HH-MM-SS\\",
                },
            },
        ],
    },
    {
        "title":       "Printing",
        "description": "Send PDFs and documents to your default printer with batch, duplex, and order controls.",
        "icon":        "🖨️",
        "accent":      C["green"],
        "tag":         "Print · PDF",
        "count":       "3 tools",
        "tools": [
            {
                "title":       "SR No Stamp & Print",
                "description": "Stamp serial numbers onto PDFs from an Excel list, then print them in order via the default printer.",
                "icon":        "🔢",
                "accent":      C["green"],
                "tag":         "Print · PDF",
                "script":      os.path.join(SCRIPTS, "srno_stamp_print.py"),
                "sample":      os.path.join(SAMPLES, "sample_srno_stamp.xlsx"),
                "docs": {
                    "what": "A two-phase pipeline tool. Phase 1 reads an Excel file, matches filenames to PDFs in a folder, and stamps each PDF's serial number on the first page. Phase 2 sends the stamped PDFs to the default Windows printer in numbered order, in configurable batches.",
                    "when": "Use this when you have a batch of PDFs that need a unique serial number stamped before printing — for example dispatch documents, certificates, or application forms.",
                    "steps": [
                        ("Set default printer", "Before opening the tool, go to Windows Settings → Bluetooth & devices → Printers and set your printer as the default."),
                        ("Select your Excel file", "The Excel must have a column with the PDF filename (or part of it) and a column with the serial number to stamp."),
                        ("Enter column names", "Type the exact column headers for the filename column and the SR No column."),
                        ("Select PDF source folder", "Pick the folder containing the original PDF files."),
                        ("Adjust stamp settings", "Set font size, left margin, and top margin for the stamped number position."),
                        ("Configure print settings", "Set batch size, delays, and duplex options."),
                        ("Click Stamp & Print", "Phase 1 stamps all PDFs into the output folder. Phase 2 prints them in order. Use Pause/Resume anytime."),
                        ("Find your files", "Stamped PDFs and a job log are saved to Desktop → OUTPUT → SrNo_Stamp_Print → <timestamp>."),
                    ],
                    "tips": [
                        "The filename column should contain a value that appears in the PDF filename — it does not need to be an exact match.",
                        "Missing PDFs are logged to missing.csv in the output folder and skipped.",
                        "Auto-detect duplex edge detects portrait/landscape per file automatically.",
                        "Use Pause to stop between batches and check print quality before resuming.",
                    ],
                    "output": "Desktop\\OUTPUT\\SrNo_Stamp_Print\\YYYY-MM-DD_HH-MM-SS\\",
                },
            },
            {
                "title":       "Excel Order Print",
                "description": "Print PDFs in the exact row order defined by an Excel list, with retry logic and missing file warnings.",
                "icon":        "📋",
                "accent":      C["purple"],
                "tag":         "Print · PDF",
                "script":      os.path.join(SCRIPTS, "excel_print.py"),
                "sample":      os.path.join(SAMPLES, "sample_excel_print.xlsx"),
                "docs": {
                    "what": "Reads an Excel file, matches each row to a PDF by filename, and prints them in the exact order the rows appear in the sheet. If any PDFs are missing, it warns you and lets you choose to continue or abort. Failed prints are retried up to 3 times.",
                    "when": "Use this when the print order matters and is defined in an Excel file — for example printing application forms in a specific sequence for filing or distribution.",
                    "steps": [
                        ("Set default printer", "Go to Windows Settings → Printers and set your target printer as the default."),
                        ("Select Excel file", "Pick the .xlsx file. The tool reads its columns and shows them as radio buttons."),
                        ("Select filename column", "Choose the column that contains the PDF filenames or identifiers."),
                        ("Select PDF folder", "Pick the folder containing the PDF files."),
                        ("Configure print settings", "Set batch size, delays, and duplex options."),
                        ("Click Print in Excel Order", "The tool matches each row to a PDF and prints in sequence. If missing PDFs are found, a warning dialog lets you continue or abort."),
                    ],
                    "tips": [
                        "Matching is partial — a row value of 'ABC123' will match a file named 'prospect_ABC123_form.pdf'.",
                        "Each failed print is retried 3 times automatically before being marked as failed.",
                        "A job.log file is saved to the output folder with a full timestamp record of every print.",
                        "Use Pause/Resume to stop mid-job without losing your place.",
                    ],
                    "output": "Desktop\\OUTPUT\\Excel_Print\\YYYY-MM-DD_HH-MM-SS\\",
                },
            },
            {
                "title":       "Quick Print",
                "description": "Add any files or folders and send them all to the default printer. Order doesn't matter.",
                "icon":        "⚡",
                "accent":      C["cyan"],
                "tag":         "Print",
                "script":      os.path.join(SCRIPTS, "quick_print.py"),
                "sample":      None,
                "docs": {
                    "what": "A simple bulk print tool. Add any mix of files or folders, configure batch and delay settings, and send everything to the default printer. No Excel file needed — just add and print.",
                    "when": "Use this when you have a pile of documents to print and the order doesn't matter. Supports PDFs and any file type Windows can print.",
                    "steps": [
                        ("Set default printer", "Go to Windows Settings → Printers and set your target printer as the default."),
                        ("Add files or folders", "Click 'Add Files' to pick individual files, or 'Add Folders' to include everything inside a folder (including subfolders). You can mix both."),
                        ("Configure print settings", "Set batch size, delay between prints, delay between batches, and duplex options."),
                        ("Click Print All", "All files are sent to the default printer in batches. Progress, stats, and per-file status update in real time."),
                        ("Use Pause/Resume", "Click Pause at any time to hold the queue. Click Resume to continue from where it stopped."),
                    ],
                    "tips": [
                        "Files are printed using Windows ShellExecute — any file type that has a default print handler will work.",
                        "Duplex settings only apply to PDF files. Other file types use their own default print settings.",
                        "A job.log is saved to Desktop → OUTPUT → Quick_Print → <timestamp> with a full record of the job.",
                        "Use a small delay (2-3 sec) for local printers and a larger one (5-10 sec) for network printers.",
                    ],
                    "output": "Desktop\\OUTPUT\\Quick_Print\\YYYY-MM-DD_HH-MM-SS\\",
                },
            },
        ],
    },
]

# ─── Service Definitions ───────────────────────────────────────────────────────
SERVICES = [
    {
        "title":       "PDF Watermark",
        "sample":      os.path.join(SAMPLES, "sample_pdf_watermark.pdf"),
        "description": "Add a diagonal watermark (text) to one or multiple PDF files in one go.",
        "icon":        "🔏",
        "accent":      C["purple"],
        "tag":         "PDF",
        "script":      os.path.join(SCRIPTS, "pdf_watermark.py"),
        "docs": {
            "what": "Adds a customisable diagonal watermark text (e.g. CONFIDENTIAL, MSME, DRAFT) to every page of one or more PDF files. You can control the text, font size, rotation angle, opacity, and colour.",
            "when": "Use this when you need to stamp PDFs before sharing them — for example marking documents as confidential, draft, or with a company/brand name.",
            "steps": [
                ("Open the tool", "Click 'Launch →' on the PDF Watermark card from the Home screen."),
                ("Select your PDF files", "Click 'Browse Files' to pick individual PDFs, or 'Browse Folder' to select all PDFs inside a folder at once. The file list will preview your selection."),
                ("Enter the watermark text", "Type the text you want stamped on every page (e.g. CONFIDENTIAL, DRAFT, MSME). Leave it clear and short for best results."),
                ("Adjust font size", "Use the Font Size slider to make the watermark larger or smaller. Default is 120 — increase for bolder stamps."),
                ("Adjust rotation", "Use the Rotation slider to set the angle of the text. 45° is the standard diagonal. Set to 0° for horizontal."),
                ("Adjust opacity", "Use the Opacity slider to control how visible the watermark is. Lower values (e.g. 10–20%) are subtle; higher values are more prominent."),
                ("Choose a colour", "Select Gray, Black, Red, or Blue for the watermark text colour."),
                ("Click 'Apply Watermark'", "The tool processes all selected files. Progress is shown in the bar and log. Each file keeps its original name."),
                ("Find your files", "When done, the output folder opens automatically. Watermarked PDFs are saved to: Desktop → OUTPUT → PDF_Watermark → <timestamp folder>."),
            ],
            "tips": [
                "Short, uppercase text works best — long phrases may overflow the page.",
                "Opacity around 10–20% gives a professional subtle stamp; above 50% is very bold.",
                "Original files are never modified — watermarked copies are always saved to the OUTPUT folder.",
                "You can process an entire folder of PDFs at once using 'Browse Folder'.",
                "If a file fails (e.g. password-protected PDF), it is skipped and logged — other files still process normally.",
            ],
            "output": "Desktop\\OUTPUT\\PDF_Watermark\\YYYY-MM-DD_HH-MM-SS\\",
        },
    },
    {
        "title":       "Sticker Tool",
        "sample":      os.path.join(SAMPLES, "sample_sticker.xlsx"),
        "description": "Format Excel data into sticker sheets and generate a merged PDF using a Typst template.",
        "icon":        "🏷️",
        "accent":      C["orange"],
        "tag":         "PDF · Excel",
        "script":      os.path.join(SCRIPTS, "sticker_tool.py"),
        "docs": {
            "what": "Takes an Excel file, lets you pick which columns to use, then reformats the data into a sticker sheet layout (N stickers per sheet). It then generates a PDF for every row using a Typst template and merges all pages into a single ready-to-print PDF.",
            "when": "Use this when you have a list of records (names, barcodes, addresses, etc.) and need to print them as physical stickers or labels in a sheet format.",
            "steps": [
                ("Open the tool", "Click 'Launch →' on the Sticker Tool card from the Home screen."),
                ("Select your Excel file", "Click 'Browse' and pick the .xlsx file containing your sticker data. The tool will immediately read and display all available column names."),
                ("Select columns", "Tick the columns you want to include on the sticker (e.g. name, barcode, address). Untick any columns you don't need. Use 'Select All' or 'Clear All' to toggle quickly."),
                ("Set stickers per sheet", "Use the slider to choose how many stickers fit on one sheet. Default is 12. Adjust to match your physical sticker sheet layout."),
                ("Select a Typst template", "Click 'Browse' and pick a .typ template file. The template defines how each sticker looks. Placeholders like {{name}}, {{barcode}} in the template are filled from your Excel data."),
                ("Click 'Generate'", "The tool formats the Excel, generates one PDF per row using the template, then merges everything into a single stickers_merged.pdf. Progress and status show in the log."),
                ("Find your files", "When done, the output folder opens automatically with two files: sticker_formatted.xlsx (the reformatted data) and stickers_merged.pdf (ready to print)."),
            ],
            "tips": [
                "Column names in your Excel must match the placeholders in your Typst template exactly (case-sensitive).",
                "The stickers per sheet number should match your physical label sheet — common sizes are 12, 16, 20, or 24.",
                "Each run creates a new timestamped folder so previous outputs are never overwritten.",
                "If PDF generation fails but Excel succeeds, check that Typst is installed and your template has no syntax errors.",
                "You can re-use the formatted Excel (sticker_formatted.xlsx) directly if you want to run the PDF step again with a different template.",
            ],
            "output": "Desktop\\OUTPUT\\Sticker_Tool\\YYYY-MM-DD_HH-MM-SS\\",
        },
    },
    {
        "title":       "Excel ↔ JSON Converter",
        "sample":      None,
        "description": "Convert Excel files to structured JSON (clientInfo envelope) or JSON back to Excel / CSV.",
        "icon":        "🔄",
        "accent":      C["cyan"],
        "tag":         "Excel · JSON",
        "script":      os.path.join(SCRIPTS, "excel_json_converter.py"),
        "docs": {
            "what": "A two-way converter. Excel → JSON wraps your spreadsheet rows into a structured JSON file with a clientInfo envelope (status, total, clientInfo array). JSON → Excel / CSV flattens that JSON back into a spreadsheet, normalising nested fields automatically.",
            "when": "Use Excel → JSON when an API or system needs your data as a JSON file. Use JSON → Excel when you receive a JSON response and need to work with it in Excel or share it as a CSV.",
            "steps": [
                ("Select mode", "Choose 'Excel → JSON' or 'JSON → Excel / CSV' using the radio buttons at the top."),
                ("Select your file", "Click 'Browse…' and pick an Excel file (.xlsx/.xls) for Excel→JSON mode, or a .json file for JSON→Excel mode."),
                ("Set options (Excel → JSON)", "Optionally enter a sheet name. Leave blank to use the first sheet."),
                ("Set options (JSON → Excel)", "Tick the output formats you want — .xlsx, .csv, or both."),
                ("Click Convert", "The file is processed instantly. The log shows row count and output filenames."),
                ("Find your files", "The output folder opens automatically. Files are saved to: Desktop → OUTPUT → Excel_JSON_Converter → <timestamp>."),
            ],
            "tips": [
                "Excel → JSON: columns named 'status' and 'total' are promoted to top-level fields; all other columns become rows inside clientInfo.",
                "JSON → Excel: nested fields are flattened with underscore separators (e.g. address_city).",
                "Comma-formatted numbers in the debtRecordsAmount column are automatically cleaned to plain numbers.",
                "Each conversion creates a new timestamped folder so previous outputs are never overwritten.",
            ],
            "output": "Desktop\\OUTPUT\\Excel_JSON_Converter\\YYYY-MM-DD_HH-MM-SS\\",
        },
    },
    {
        "title":       "Excel Deduplicator",
        "sample":      None,
        "description": "Remove duplicate rows from an Excel file based on any column. Shows count of duplicates removed.",
        "icon":        "🧹",
        "accent":      C["green"],
        "tag":         "Excel",
        "script":      os.path.join(SCRIPTS, "excel_deduplicator.py"),
        "docs": {
            "what": "Reads an Excel file, removes duplicate rows based on a column you choose, and saves the cleaned file. You can pick whether to keep the first or last occurrence of each duplicate. The log shows exactly how many rows were removed.",
            "when": "Use this when you have an Excel sheet with repeated entries — for example customer records with the same customer_id appearing more than once — and you need a clean unique list.",
            "steps": [
                ("Open the tool", "Click 'Launch →' on the Excel Deduplicator card from the Home screen."),
                ("Select your Excel file", "Click 'Browse…' and pick the .xlsx or .xls file you want to clean. The tool will read and display all available column names as a hint."),
                ("Enter the column name", "Type the exact column header to deduplicate on (e.g. customer_id). If the file has a customer_id column, it is filled in automatically."),
                ("Choose which duplicate to keep", "Select 'First occurrence' to keep the earliest row, or 'Last occurrence' to keep the most recent one."),
                ("Click 'Remove Duplicates'", "The tool processes the file. The log shows rows loaded, duplicates removed, and unique rows kept."),
                ("Find your file", "When done, the output folder opens automatically. The cleaned file is saved as <original_name>_unique.xlsx."),
            ],
            "tips": [
                "Column names are case-sensitive — type them exactly as they appear in the header row.",
                "When the file is selected, the tool lists all detected column names as a hint below the entry box.",
                "Original files are never modified — the cleaned copy is always saved to a new timestamped output folder.",
                "Each run creates a new timestamped folder so previous outputs are never overwritten.",
            ],
            "output": "Desktop\\OUTPUT\\Excel_Deduplicator\\YYYY-MM-DD_HH-MM-SS\\",
        },
    },
    {
        "title":       "PDF Generation Pipeline",
        "sample":      None,
        "description": "Generate PDFs from Excel data using Typst templates. Supports multi-language, table rotation, merging, and S3 upload.",
        "icon":        "⚙️",
        "accent":      C["pink"],
        "tag":         "PDF · Typst · Excel",
        "script":      os.path.join(SCRIPTS, "pdf_generator", "ui.py"),
        "docs": {
            "what": "A full PDF generation pipeline. Reads rows from an Excel or CSV file, fills Typst (.typ) templates with per-row data, compiles each row into a PDF, and optionally merges all PDFs into batched output files. Supports multi-language templates (one .typ per language/state), table rotation (one PDF per applicant), password protection, and S3 upload.",
            "when": "Use this when you need to mass-generate personalised PDFs from a spreadsheet — for example notices, certificates, demand letters, or any document where each row produces its own PDF with the same template layout.",
            "steps": [
                ("Select your data file", "Click '…' next to 'Data file' and choose your .xlsx or .csv file. Each row becomes one PDF."),
                ("Select Notice Config (optional)", "If your templates use a JSON config (date formats, table definitions, decimal fields), browse and select it here. Leave blank for simple templates."),
                ("Set output folders", "The 'Output folder' is where individual PDFs are saved. 'Merge folder' is where batched merged PDFs go. Both default to folders inside the scripts directory."),
                ("Select template folder", "Click '…' next to 'Template folder' and choose the folder containing your .typ files and a template.json mapping file. The preview box will show all state/language → file mappings."),
                ("Configure template.json", 'Inside your template folder, create a template.json with a `template_dict` key: {"DEFAULT": "default.typ", "HINDI": "hindi.typ", ...}. The DEFAULT key is required.'),
                ("Set processing options", "Toggle 'Generate PDFs' and 'Merge PDFs' as needed. Adjust chunk size, batch size, max workers, and memory limit for your machine."),
                ("Enable S3 Upload (optional)", "Tick 'Enable S3 Upload', enter your S3 URI prefix, and ensure AWS credentials are in the .env file."),
                ("Run the pipeline", "Click '▶ Run Pipeline'. The log panel shows live progress. Use 'Save Config' to save your settings for next time."),
            ],
            "tips": [
                "template.json must be inside the selected template folder (or the scripts folder as fallback). It must have a `template_dict` object with at least a `DEFAULT` key.",
                "Column names in your Excel map directly to {{ColumnName}} placeholders in the .typ template.",
                "The pipeline resumes automatically if interrupted — it saves state after every 10 rows.",
                "Use 'Save Config' to export your current settings to a JSON file, then 'Load Config' on the next run.",
                "Output PDFs are saved in the Output folder. Merged batches go in the Merge folder. S3 uploads happen after merging.",
                "AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, S3_BUCKET_NAME) should be in a .env file in the scripts folder.",
            ],
            "output": "Desktop\\OUTPUT\\  (individual PDFs)  |  MERGE_PDF\\  (batched merges)",
        },
    },
    {
        "title":       "S3 File Uploader",
        "sample":      None,
        "description": "Upload single or multiple files and folders to Amazon S3 with file type filtering.",
        "icon":        "\u2601\ufe0f",
        "accent":      C["blue"],
        "tag":         "Cloud \u00b7 S3",
        "script":      os.path.join(SCRIPTS, "s3_uploader.py"),
        "docs": {
            "what": "Uploads files to an Amazon S3 bucket in parallel. You can select individual files, multiple files, or entire folders (including subfolders). If your selection contains multiple file types, the tool lets you choose which types to upload.",
            "when": "Use this when you need to bulk-upload documents, PDFs, images, or any files to an S3 bucket without using the AWS console.",
            "steps": [
                ("Open the tool", "Click 'Launch \u2192' on the S3 File Uploader card from the Home screen."),
                ("Add files or folders", "Click 'Add Files' to pick individual files, or 'Add Folders' to select a folder. You can click both buttons multiple times to keep adding more. Each item shows in the list with a remove (\u2715) button."),
                ("Filter by file type", "If your selection has multiple file types (e.g. .pdf and .xlsx), checkboxes appear for each type. Tick the ones you want to upload. If all files are the same type, this step is skipped automatically."),
                ("Enter the S3 upload path", "Type the folder path inside the bucket where files should go (e.g. uploads/documents/2024). Do not include the bucket name \u2014 that is loaded automatically."),
                ("Click 'Upload to S3'", "Files upload in parallel. The progress bar, stats (Uploaded / Failed / Skipped), and log update in real time."),
                ("Failed files", "If any files fail, they are automatically copied to Desktop \u2192 OUTPUT \u2192 S3_Upload \u2192 <timestamp> \u2192 failed\\ so you can retry them later."),
            ],
            "tips": [
                "Folders are scanned recursively \u2014 all files in subfolders are included automatically.",
                "Files are uploaded with the correct Content-Type (PDF, Excel, image, etc.) set automatically.",
                "Up to 8 files upload simultaneously for speed.",
                "The .env file must contain AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, and S3_BUCKET_NAME.",
                "Original files are never moved or deleted \u2014 only copied to S3.",
            ],
            "output": "s3://<bucket>/<your-upload-path>/<filename>",
        },
    },
]


# ─── Group Card (clickable — opens sub-panel) ─────────────────────────────────
class GroupCard(ctk.CTkFrame):
    """Slim card on the home grid. Clicking it calls open_cb(grp)."""
    def __init__(self, parent, grp, open_cb, **kw):
        super().__init__(parent, **kw)
        self.grp     = grp
        self.accent  = grp["accent"]
        self.open_cb = open_cb
        self.configure(fg_color=C["card"], corner_radius=16,
                       border_width=1, border_color=C["border"],
                       cursor="hand2")
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

        # Tool count badge top-right
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

        # Footer row — tag pill + open button
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


# ─── Group Sub-Panel (shown when user clicks a group card) ────────────────────
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

        # ── Top bar ──
        top = ctk.CTkFrame(self, height=62, fg_color=C["sidebar"], corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        # Back button
        ctk.CTkButton(
            top, text="←  Back",
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color="transparent", hover_color=C["hover"],
            text_color=C["muted"], corner_radius=10,
            height=32, width=80,
            command=self.back_cb
        ).pack(side="left", padx=(16, 0))

        # Breadcrumb
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

        # Tool count
        ctk.CTkLabel(top, text=self.grp["count"],
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["muted"]).pack(side="right", padx=26)

        # ── Section label ──
        ctk.CTkLabel(self,
                     text=f"{self.grp['icon']}  {self.grp['title'].upper()} TOOLS",
                     font=ctk.CTkFont("Segoe UI", 10, "bold"),
                     text_color=C["faint"]).pack(anchor="w", padx=28, pady=(14, 2))

        # ── Scrollable card grid ──
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=acc)
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        scroll.columnconfigure(0, weight=1)
        scroll.columnconfigure(1, weight=1)
        scroll.columnconfigure(2, weight=1)

        tools = self.grp["tools"]
        for i, svc in enumerate(tools):
            ServiceCard(scroll, svc, open_docs_cb=self.open_docs_cb).grid(
                row=i // 3, column=i % 3, padx=8, pady=8, sticky="nsew")


# ─── Service Card ──────────────────────────────────────────────────────────────
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

        self.title_lbl = ctk.CTkLabel(
            body, text=self.svc["title"],
            font=ctk.CTkFont("Segoe UI", 14, "bold"),
            text_color=C["text"], anchor="w")
        self.title_lbl.pack(fill="x", pady=(10, 3))

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

        # Docs button (only if docs exist)
        if self.svc.get("docs") and self.open_docs_cb:
            ctk.CTkButton(
                ftr, text="Docs",
                font=ctk.CTkFont("Segoe UI", 11),
                fg_color="transparent",
                hover_color=C["hover"],
                text_color=C["muted"],
                corner_radius=20, height=30, width=52,
                command=lambda: self.open_docs_cb(self.svc)
            ).pack(side="right", padx=(0, 4))

        # Sample download button (only if sample is defined)
        if self.svc.get("sample") is not None:
            ctk.CTkButton(
                ftr, text="⭳ Sample",
                font=ctk.CTkFont("Segoe UI", 11),
                fg_color="transparent",
                hover_color=C["hover"],
                text_color=C["muted"],
                corner_radius=20, height=30, width=72,
                command=lambda s=self.svc: download_sample(s)
            ).pack(side="right", padx=(0, 2))

        btn_text = "Launch →" if self.svc["script"] else "Soon"
        self.btn = ctk.CTkButton(
            ftr, text=btn_text,
            font=ctk.CTkFont("Segoe UI", 12, "bold"),
            fg_color=t(self.accent, "mid"),
            hover_color=t(self.accent, "bdr"),
            text_color=self.accent,
            border_color=self.accent, border_width=1,
            corner_radius=20, height=30, width=90,
            command=self._launch)
        self.btn.pack(side="right")

    def _bind_hover(self):
        def bind_all(w):
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)
            for ch in w.winfo_children():
                bind_all(ch)
        bind_all(self)

    def _enter(self, _=None):
        self.configure(fg_color=C["hover"], border_color=self.accent)

    def _leave(self, _=None):
        self.configure(fg_color=C["card"], border_color=C["border"])

    def _launch(self):
        script = self.svc.get("script")
        if not script:
            messagebox.showinfo("Coming Soon",
                f"'{self.svc['title']}' is not yet available.\n"
                "It will be added in a future update.")
            return
        try:
            subprocess.Popen([sys.executable, script])
        except Exception as e:
            messagebox.showerror("Error", f"Could not launch:\n{e}")


# ─── Docs Panel ────────────────────────────────────────────────────────────────
class DocsPanel(ctk.CTkFrame):
    """Full documentation viewer — shown instead of the home grid."""

    def __init__(self, parent, services, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.services   = [s for s in services if s.get("docs")]
        self.selected   = None
        self._build()

    def _build(self):
        # Top bar
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

        # Right: content area
        self.right = ctk.CTkScrollableFrame(
            body, fg_color=C["card"], corner_radius=14,
            border_width=1, border_color=C["border"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["cyan"])
        self.right.pack(side="left", fill="both", expand=True)

        # Placeholder
        self._placeholder()

        # Auto-select first tool
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
        docs  = svc["docs"]
        acc   = svc["accent"]

        # Highlight nav button
        for s, btn in self.nav_btns:
            if s is svc:
                btn.configure(fg_color=t(acc, "mid"), text_color=acc)
            else:
                btn.configure(fg_color="transparent", text_color=C["muted"])

        # Clear content
        for w in self.right.winfo_children():
            w.destroy()

        pad = {"padx": 28}

        # ── Title bar ──
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

        # ── What it does ──
        self._section_head("📌  What it does", acc)
        self._body_text(docs["what"])

        # ── When to use ──
        self._section_head("🕐  When to use it", acc)
        self._body_text(docs["when"])

        self._divider()

        # ── Step-by-step ──
        self._section_head("🪜  Step-by-step guide", acc)

        for i, (title, detail) in enumerate(docs["steps"], 1):
            step_frame = ctk.CTkFrame(self.right,
                                      fg_color=t(acc, "bg"),
                                      corner_radius=12,
                                      border_width=1,
                                      border_color=t(acc, "bdr"))
            step_frame.pack(fill="x", pady=5, **pad)

            # Step number badge
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

        # ── Tips ──
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

        # ── Output location ──
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

        # ── Sample file download ──
        self._divider()
        self._section_head("📂  Sample file", acc)

        sample_row = ctk.CTkFrame(self.right, fg_color="transparent")
        sample_row.pack(fill="x", pady=(2, 28), **pad)

        has_sample = svc.get("sample") and os.path.exists(svc["sample"])
        sample_note = (
            f"Download a ready-made sample Excel file to test this tool immediately."
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

    # ── Helpers ────────────────────────────────────────────────────────────────
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


# ─── Home Panel ────────────────────────────────────────────────────────────────
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

        # Stats
        stats_bar = ctk.CTkFrame(self, fg_color="transparent")
        stats_bar.pack(fill="x", padx=26, pady=(18, 6))

        group_tool_count  = sum(len(g["tools"]) for g in GROUPS)
        active_scripts   = sum(1 for s in self.services if s["script"]) + group_tool_count
        coming_soon      = sum(1 for s in self.services if not s["script"])
        total_tools      = len(self.services) + group_tool_count
        for label, val, color in [
            ("Total Tools",   str(total_tools),    C["cyan"]),
            ("Active",        str(active_scripts), C["green"]),
            ("Coming Soon",   str(coming_soon),    C["orange"]),
            ("Output: Desktop/OUTPUT", "📁",      C["purple"]),
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

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                        scrollbar_button_color=C["border"],
                                        scrollbar_button_hover_color=C["cyan"])
        scroll.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        scroll.columnconfigure(0, weight=1)
        scroll.columnconfigure(1, weight=1)
        scroll.columnconfigure(2, weight=1)

        # Group cards first (each calls open_group_cb), then individual services
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


# ─── Dashboard ─────────────────────────────────────────────────────────────────
class Dashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Dashboard")
        self.geometry("1120x730")
        self.minsize(960, 620)
        self.configure(fg_color=C["bg"])
        self._build()

    def _build(self):
        # Sidebar
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

        self.nav_state = {}   # label -> button widget

        nav_items = [
            ("🏠", "Home",   self._show_home),
            ("📖", "Docs",   self._show_docs),
            ("⚙️", "Settings", None),
            ("❓", "Help",    None),
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

        # Main container
        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.pack(side="left", fill="both", expand=True)

        # Collect all sub-tool services for the docs panel (groups + individual)
        all_services_for_docs = (
            [tool for grp in GROUPS for tool in grp["tools"]]
            + SERVICES
        )

        # Pre-build panels
        self.home_panel = HomePanel(
            self.main, SERVICES,
            open_docs_cb=self._open_docs_for,
            open_group_cb=self._open_group
        )
        self.docs_panel  = DocsPanel(self.main, all_services_for_docs)
        self.sub_panel   = None   # created on demand per group

        # Show home by default
        self._show_home()

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

    def _show_home(self):
        if self.sub_panel:
            self.sub_panel.pack_forget()
        self.docs_panel.pack_forget()
        self.home_panel.pack(fill="both", expand=True)
        self._set_active_nav("Home")

    def _show_docs(self):
        if self.sub_panel:
            self.sub_panel.pack_forget()
        self.home_panel.pack_forget()
        self.docs_panel.pack(fill="both", expand=True)
        self._set_active_nav("Docs")

    def _open_group(self, grp):
        """Called when user clicks a group card — show sub-panel for that group."""
        # Destroy previous sub-panel if switching groups
        if self.sub_panel:
            self.sub_panel.destroy()
        self.sub_panel = GroupSubPanel(
            self.main, grp,
            back_cb=self._show_home,
            open_docs_cb=self._open_docs_for
        )
        self.home_panel.pack_forget()
        self.docs_panel.pack_forget()
        self.sub_panel.pack(fill="both", expand=True)
        self._set_active_nav("Home")   # keep Home highlighted in sidebar

    def _open_docs_for(self, svc):
        """Called from a card's Docs button — switch to Docs tab and highlight that tool."""
        self._show_docs()
        self.docs_panel._show(svc)

    def _nav_noop(self, label):
        messagebox.showinfo("Coming Soon", f"'{label}' section is not yet available.")


if __name__ == "__main__":
    Dashboard().mainloop()
