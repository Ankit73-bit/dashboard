import os
import shutil
import pandas as pd
import csv
import traceback
import re
from collections import defaultdict
from difflib import SequenceMatcher

try:
    from rapidfuzz import fuzz, process
    from rapidfuzz.distance import Levenshtein as RFLevenshtein
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

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

# Fuzzy match settings
MAX_EDIT_DISTANCE = 2
MIN_SIMILARITY_RATIO = 0.88

# Progress print every N PDFs (0 = print every file)
PROGRESS_EVERY = 100

# Prefix length used to bucket candidates (India Post: first 2 letters)
PREFIX_LEN = 2


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
# LEVENSHTEIN (fallback when rapidfuzz is unavailable)
# =========================================================
def levenshtein(a: str, b: str, max_dist: int = None) -> int:
    """Levenshtein distance with optional early exit."""
    a, b = a or "", b or ""
    n, m = len(a), len(b)

    if abs(n - m) > (max_dist if max_dist is not None else max(n, m)):
        return (max_dist + 1) if max_dist is not None else abs(n - m)

    if n == 0:
        return m
    if m == 0:
        return n

    if n > m:
        a, b, n, m = b, a, m, n

    prev_row = list(range(m + 1))

    for i in range(1, n + 1):
        curr_row = [i] + [0] * m
        row_min = i

        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr_row[j] = min(
                prev_row[j] + 1,
                curr_row[j - 1] + 1,
                prev_row[j - 1] + cost,
            )
            if curr_row[j] < row_min:
                row_min = curr_row[j]

        if max_dist is not None and row_min > max_dist:
            return max_dist + 1

        prev_row = curr_row

    return prev_row[m]


def similarity_ratio(a, b):
    if HAS_RAPIDFUZZ:
        return fuzz.ratio(a, b) / 100.0
    return SequenceMatcher(None, a, b).ratio()


# =========================================================
# CANDIDATE INDEX (length + prefix buckets)
# =========================================================
def build_candidate_index(barcodes):
    by_prefix_len = defaultdict(list)
    by_len = defaultdict(list)

    for bc in barcodes:
        by_len[len(bc)].append(bc)
        prefix = bc[:PREFIX_LEN] if len(bc) >= PREFIX_LEN else bc
        by_prefix_len[(prefix, len(bc))].append(bc)

    return by_prefix_len, by_len


def _near_lengths(n):
    max_len_delta = max(
        MAX_EDIT_DISTANCE,
        int((1.0 - MIN_SIMILARITY_RATIO) * max(n, 1)) + 1,
    )
    return range(max(0, n - max_len_delta), n + max_len_delta + 1)


def candidates_same_prefix(pdf_barcode, by_prefix_len):
    n = len(pdf_barcode)
    prefix = pdf_barcode[:PREFIX_LEN] if n >= PREFIX_LEN else pdf_barcode
    subset = []
    for length in _near_lengths(n):
        bucket = by_prefix_len.get((prefix, length))
        if bucket:
            subset.extend(bucket)
    return subset


def candidates_similar_length(pdf_barcode, by_len):
    subset = []
    for length in _near_lengths(len(pdf_barcode)):
        bucket = by_len.get(length)
        if bucket:
            subset.extend(bucket)
    return subset


# =========================================================
# FUZZY MATCH FINDER
# =========================================================
def find_best_fuzzy(pdf_barcode, by_prefix_len, by_len):
    matcher = (
        _find_best_fuzzy_rapidfuzz if HAS_RAPIDFUZZ
        else _find_best_fuzzy_python
    )

    narrow = candidates_same_prefix(pdf_barcode, by_prefix_len)
    if narrow:
        result = matcher(pdf_barcode, narrow)
        if result[0] is not None:
            return result

    broad = candidates_similar_length(pdf_barcode, by_len)
    if not broad:
        return None, None, None

    if narrow and len(broad) == len(narrow):
        return None, None, None

    return matcher(pdf_barcode, broad)


def _find_best_fuzzy_rapidfuzz(pdf_barcode, candidates):
    dist_hit = process.extractOne(
        pdf_barcode,
        candidates,
        scorer=RFLevenshtein.distance,
        score_cutoff=MAX_EDIT_DISTANCE,
    )

    if dist_hit is not None:
        match, distance, _ = dist_hit
        ratio = fuzz.ratio(pdf_barcode, match) / 100.0
        return match, int(distance), ratio

    ratio_hit = process.extractOne(
        pdf_barcode,
        candidates,
        scorer=fuzz.ratio,
        score_cutoff=MIN_SIMILARITY_RATIO * 100,
    )

    if ratio_hit is not None:
        match, score, _ = ratio_hit
        distance = RFLevenshtein.distance(pdf_barcode, match)
        return match, int(distance), score / 100.0

    return None, None, None


def _find_best_fuzzy_python(pdf_barcode, candidates):
    best_match = None
    best_distance = None
    best_ratio = -1.0

    for candidate in candidates:
        distance = levenshtein(
            pdf_barcode, candidate, max_dist=MAX_EDIT_DISTANCE
        )

        if distance <= MAX_EDIT_DISTANCE:
            ratio = similarity_ratio(pdf_barcode, candidate)
        else:
            longer = max(len(pdf_barcode), len(candidate), 1)
            if abs(len(pdf_barcode) - len(candidate)) / longer > (
                1.0 - MIN_SIMILARITY_RATIO
            ):
                continue
            ratio = similarity_ratio(pdf_barcode, candidate)
            if ratio < MIN_SIMILARITY_RATIO:
                continue
            distance = levenshtein(pdf_barcode, candidate)

        if (
            best_match is None
            or distance < best_distance
            or (distance == best_distance and ratio > best_ratio)
        ):
            best_match = candidate
            best_distance = distance
            best_ratio = ratio

            if distance == 0:
                break

    if best_match and (
        best_distance <= MAX_EDIT_DISTANCE
        or best_ratio >= MIN_SIMILARITY_RATIO
    ):
        return best_match, best_distance, best_ratio

    return None, None, None


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
                "EditDistance",
                "SimilarityRatio",
            ])


def append_log_rows(rows):
    if not rows:
        return
    with open(RENAME_LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)


# =========================================================
# PROCESS PDFs
# =========================================================
def process_pdfs(excel_barcode_to_files):
    pdf_files = [
        f for f in os.listdir(PDF_FOLDER)
        if f.lower().endswith('.pdf')
    ]

    print(f"\n📄 Found {len(pdf_files)} PDF files")
    if HAS_RAPIDFUZZ:
        print("⚡ Fuzzy engine: rapidfuzz (C)")
    else:
        print("⚠ Fuzzy engine: pure Python (pip install rapidfuzz for speed)")

    found_barcodes = set()
    exact_count = 0
    fuzzy_count = 0
    moved_count = 0
    duplicate_conflict_count = 0
    errors = []

    by_prefix_len, by_len = build_candidate_index(
        excel_barcode_to_files.keys()
    )

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
                    0,
                    '1.000',
                ])
                if PROGRESS_EVERY and idx % PROGRESS_EVERY == 0:
                    print(
                        f"… {idx}/{total} "
                        f"(exact={exact_count}, fuzzy={fuzzy_count}, "
                        f"moved={moved_count})"
                    )
                continue

            match, distance, ratio = find_best_fuzzy(
                pdf_barcode, by_prefix_len, by_len
            )

            if match:
                new_name = f"{match}.pdf"
                new_path = os.path.join(PDF_FOLDER, new_name)

                if os.path.exists(new_path):
                    duplicate_conflict_count += 1
                    duplicate_destination = unique_destination(
                        DUPLICATE_MATCH_FOLDER, pdf_file
                    )
                    shutil.move(old_path, duplicate_destination)
                    log_buffer.append([
                        pdf_file,
                        os.path.basename(duplicate_destination),
                        match,
                        ';'.join(excel_barcode_to_files[match]),
                        'Duplicate Conflict',
                        distance,
                        f"{ratio:.3f}",
                    ])
                else:
                    os.rename(old_path, new_path)
                    found_barcodes.add(match)
                    fuzzy_count += 1
                    log_buffer.append([
                        pdf_file,
                        new_name,
                        match,
                        ';'.join(excel_barcode_to_files[match]),
                        'Fuzzy',
                        distance,
                        f"{ratio:.3f}",
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
                    f"(exact={exact_count}, fuzzy={fuzzy_count}, "
                    f"moved={moved_count})"
                )

        except Exception as e:
            errors.append((pdf_file, str(e)))
            print(f"⚠ Error processing {pdf_file}: {e}")
            print(traceback.format_exc())

    append_log_rows(log_buffer)

    return (
        exact_count,
        fuzzy_count,
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
        distance = row.get("EditDistance", "")
        ratio = row.get("SimilarityRatio", "")

        if match_type == "Exact":
            remark_map[barcode] = "Exact Match"
        elif match_type == "Fuzzy":
            remark_map[barcode] = (
                f"Fuzzy Match (dist={distance}, ratio={ratio})"
            )
        elif match_type == "Duplicate Conflict":
            remark_map[barcode] = (
                f"Duplicate Conflict (dist={distance}, ratio={ratio})"
            )

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
    print("\n🚀 INDIA POST BARCODE PDF MATCHER")
    print("=" * 60)

    excel_barcode_to_files, excel_files = load_excel_barcodes()
    prepare_log()

    (
        exact_count,
        fuzzy_count,
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
    print(f"🔄 Fuzzy Matches        : {fuzzy_count}")
    print(f"🔁 Duplicate Conflicts  : {duplicate_conflict_count}")
    print(f"📦 Moved Not Found      : {moved_count}")
    print(f"⚠ Errors               : {len(errors)}")

    if errors:
        print("\nERROR DETAILS:")
        for filename, message in errors:
            print(f" - {filename}: {message}")

    print(f"\n📑 Log File → {RENAME_LOG_FILE}")
    print("✅ Process Completed")
