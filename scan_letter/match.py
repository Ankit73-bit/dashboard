import os
import shutil
import pandas as pd
import csv
import traceback
import re

# =========================================================
# CONFIGURATION
# =========================================================
PDF_FOLDER = "renamed_pdfs"
EXCEL_FOLDER = "excel"
NOT_FOUND_FOLDER = "not_found_barcodes"
DUPLICATE_MATCH_FOLDER = "duplicate_match_conflicts"

RENAME_LOG_FILE = "rename_match_log.csv"

# India Post barcode settings
# Example: EK123456789IN
INDIA_POST_REGEX = re.compile(r'^[A-Z]{2}[0-9]{9}[A-Z]{2}$')

# Progress print every N PDFs (0 = print every file)
PROGRESS_EVERY = 100


# =========================================================
# CREATE REQUIRED FOLDERS (call from main / UI as needed)
# =========================================================
def ensure_folders():
    os.makedirs(PDF_FOLDER, exist_ok=True)
    os.makedirs(EXCEL_FOLDER, exist_ok=True)
    os.makedirs(NOT_FOUND_FOLDER, exist_ok=True)
    os.makedirs(DUPLICATE_MATCH_FOLDER, exist_ok=True)


# =========================================================
# HELPER FUNCTIONS
# =========================================================
def clean_barcode(barcode):
    """Normalize barcode values."""
    if pd.isna(barcode):
        return ""

    barcode = str(barcode).strip().upper().replace('.PDF', '')
    return re.sub(r'[^A-Z0-9]', '', barcode)


def is_valid_indiapost_barcode(barcode):
    """Validate India Post tracking barcode."""
    return bool(INDIA_POST_REGEX.match(barcode))


def unique_destination(folder, filename):
    """Return a non-colliding path inside folder."""
    destination = os.path.join(folder, filename)
    if not os.path.exists(destination):
        return destination

    base, ext = os.path.splitext(filename)
    counter = 1
    while True:
        destination = os.path.join(folder, f"{base}_dup{counter}{ext}")
        if not os.path.exists(destination):
            return destination
        counter += 1


# =========================================================
# LOAD EXCEL BARCODES
# =========================================================
def load_excel_barcodes():
    excel_barcode_to_files = {}

    excel_files = [
        f for f in os.listdir(EXCEL_FOLDER)
        if f.lower().endswith((".xls", ".xlsx"))
    ]

    print(f"\n📘 Found {len(excel_files)} Excel files")

    possible_columns = (
        "barcode",
        "awb",
        "tracking",
        "trackingno",
        "tracking_no",
        "article_number",
        "consignment",
    )

    for excel_file in excel_files:
        path = os.path.join(EXCEL_FOLDER, excel_file)

        try:
            df = pd.read_excel(path, dtype=str)
        except Exception as e:
            print(f"⚠ Error reading {excel_file}: {e}")
            continue

        df.columns = [str(col).strip().lower() for col in df.columns]

        barcode_column = next(
            (col for col in possible_columns if col in df.columns), None
        )

        if not barcode_column:
            print(f"⏭ Skipping {excel_file} → No barcode column found")
            continue

        print(f"✅ Using column '{barcode_column}' in {excel_file}")

        cleaned = (
            df[barcode_column]
            .dropna()
            .astype(str)
            .map(clean_barcode)
        )
        values = cleaned[cleaned != ""].unique()

        valid_count = 0
        for barcode in values:
            if is_valid_indiapost_barcode(barcode):
                valid_count += 1
            excel_barcode_to_files.setdefault(barcode, set()).add(excel_file)

        print(
            f"   Loaded {len(values)} barcodes "
            f"({valid_count} India Post format)"
        )

    print(
        f"\n✅ Total unique barcodes loaded: "
        f"{len(excel_barcode_to_files)}"
    )

    return excel_barcode_to_files, excel_files


# =========================================================
# PREPARE LOG FILE
# =========================================================
def prepare_log():
    if not os.path.exists(RENAME_LOG_FILE):
        with open(RENAME_LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "OldFilename",
                "NewFilename",
                "MatchedBarcode",
                "ExcelFiles",
                "MatchType",
            ])


def append_log_rows(rows):
    if not rows:
        return
    with open(RENAME_LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


# =========================================================
# PROCESS PDFs (exact match only)
# =========================================================
def process_pdfs(excel_barcode_to_files):
    pdf_files = [
        f for f in os.listdir(PDF_FOLDER)
        if f.lower().endswith('.pdf')
    ]

    print(f"\n📄 Found {len(pdf_files)} PDF files")
    print("🔎 Match mode: exact only")

    found_barcodes = set()
    exact_count = 0
    moved_count = 0
    duplicate_conflict_count = 0
    errors = []

    log_buffer = []
    LOG_FLUSH_EVERY = 200
    total = len(pdf_files)

    for idx, pdf_file in enumerate(pdf_files, 1):
        try:
            old_path = os.path.join(PDF_FOLDER, pdf_file)
            pdf_barcode = clean_barcode(os.path.splitext(pdf_file)[0])

            if not pdf_barcode:
                continue

            if pdf_barcode in excel_barcode_to_files:
                found_barcodes.add(pdf_barcode)
                exact_count += 1
                log_buffer.append([
                    pdf_file,
                    pdf_file,
                    pdf_barcode,
                    ';'.join(excel_barcode_to_files[pdf_barcode]),
                    'Exact',
                ])
            else:
                destination = unique_destination(NOT_FOUND_FOLDER, pdf_file)
                shutil.move(old_path, destination)
                moved_count += 1

            if len(log_buffer) >= LOG_FLUSH_EVERY:
                append_log_rows(log_buffer)
                log_buffer.clear()

            if PROGRESS_EVERY and idx % PROGRESS_EVERY == 0:
                print(
                    f"… {idx}/{total} "
                    f"(exact={exact_count}, moved={moved_count})"
                )

        except Exception as e:
            errors.append((pdf_file, str(e)))
            print(f"⚠ Error processing {pdf_file}: {e}")
            print(traceback.format_exc())

    append_log_rows(log_buffer)

    return (
        exact_count,
        0,  # fuzzy_count kept for caller compatibility
        moved_count,
        duplicate_conflict_count,
        found_barcodes,
        errors,
    )


# =========================================================
# UPDATE EXCEL REMARKS
# =========================================================
def update_excel_remarks(excel_files):
    print("\n📝 Updating Excel remarks...")

    if not os.path.exists(RENAME_LOG_FILE):
        print("⚠ Log file not found")
        return

    log_df = pd.read_csv(RENAME_LOG_FILE, dtype=str)

    remark_map = {}
    for _, row in log_df.iterrows():
        barcode = clean_barcode(row.get("MatchedBarcode", ""))
        match_type = row.get("MatchType", "")

        if match_type == "Exact":
            remark_map[barcode] = "Exact Match"

    possible_columns = (
        "barcode",
        "awb",
        "tracking",
        "trackingno",
        "tracking_no",
        "article_number",
        "consignment",
    )

    for excel_file in excel_files:
        path = os.path.join(EXCEL_FOLDER, excel_file)

        try:
            df = pd.read_excel(path, dtype=str)
            original_columns = list(df.columns)
            df.columns = [str(col).strip().lower() for col in df.columns]

            barcode_column = next(
                (col for col in possible_columns if col in df.columns), None
            )

            if not barcode_column:
                print(f"⏭ Skipping {excel_file}")
                continue

            cleaned = df[barcode_column].astype(str).map(clean_barcode)

            if 'remark' not in df.columns:
                df['remark'] = ''

            df['remark'] = cleaned.map(remark_map).fillna(df['remark'])

            for i in range(min(len(original_columns), len(df.columns))):
                df.columns.values[i] = original_columns[i]

            df.to_excel(path, index=False)
            print(f"✅ Updated {excel_file}")

        except Exception as e:
            print(f"⚠ Error updating {excel_file}: {e}")


# =========================================================
# MAIN
# =========================================================
if __name__ == "__main__":
    ensure_folders()
    print("\n🚀 INDIA POST BARCODE PDF MATCHER (EXACT ONLY)")
    print("=" * 60)

    excel_barcode_to_files, excel_files = load_excel_barcodes()
    prepare_log()

    (
        exact_count,
        _fuzzy_count,
        moved_count,
        duplicate_conflict_count,
        found_barcodes,
        errors,
    ) = process_pdfs(excel_barcode_to_files)

    update_excel_remarks(excel_files)

    print("\n" + "=" * 60)
    print("📊 FINAL SUMMARY")
    print("=" * 60)
    print(f"✅ Exact Matches        : {exact_count}")
    print(f"🔁 Duplicate Conflicts  : {duplicate_conflict_count}")
    print(f"📦 Moved Not Found      : {moved_count}")
    print(f"⚠ Errors               : {len(errors)}")

    if errors:
        print("\nERROR DETAILS:")
        for filename, message in errors:
            print(f" - {filename}: {message}")

    print(f"\n📑 Log File → {RENAME_LOG_FILE}")
    print("✅ Process Completed")
