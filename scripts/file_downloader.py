"""
Tool: File Downloader (from Excel)
Download any file type from URL / Excel hyperlink columns.
Optional rename using an ID column. Handles large files (lakhs of rows).
"""

import os
import re
import csv
import zipfile
import mimetypes
import threading
import subprocess
from datetime import datetime
from urllib.parse import urlparse, unquote, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
from xml.etree import ElementTree as ET

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import customtkinter as ctk
from tkinter import filedialog, messagebox
from window_fit import fit_to_screen, add_run_footer, add_primary_run_button

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_OUT = os.path.join(DESKTOP, "OUTPUT", "File_Downloads")

C = {
    "bg": "#0a0a0f", "card": "#16161f", "hover": "#1e1e2e",
    "border": "#2a2a3d", "text": "#e8e8f0", "muted": "#8888aa",
    "faint": "#44445a", "accent": "#00f5ff", "green": "#30d158",
    "red": "#ff375f",
}
TINT = {"bg": "#062d30", "mid": "#0a4a4e", "bdr": "#0d6b70"}

EXT_FROM_MIME = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "application/zip": ".zip",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "text/plain": ".txt",
    "text/csv": ".csv",
}

_HYPERLINK_RE = re.compile(
    r"""HYPERLINK\s*\(\s*["'](https?://[^"']+)["']""",
    re.I,
)
_SCI_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?[eE][+-]?\d+$")
_CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
NS_PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"

URL_COL_HINTS = ("url", "link", "pod", "pdf", "image", "download", "file")
ID_COL_HINTS = ("awb", "barcode", "loan_account", "account", "cust_id", "id", "ref")

_thread_local = threading.local()


def get_output_dir(excel_path=None):
    """Stable folder per Excel file so a 2-lakh run can resume."""
    if excel_path:
        stem = sanitize_filename(os.path.splitext(os.path.basename(excel_path))[0])
        path = os.path.join(BASE_OUT, stem or "downloads")
    else:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        path = os.path.join(BASE_OUT, ts)
    os.makedirs(path, exist_ok=True)
    return path


def unique_path(folder, filename):
    dest = os.path.join(folder, filename)
    if not os.path.exists(dest):
        return dest, filename
    base, ext = os.path.splitext(filename)
    n = 1
    while True:
        name = f"{base}_{n}{ext}"
        dest = os.path.join(folder, name)
        if not os.path.exists(dest):
            return dest, name
        n += 1


def sanitize_filename(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.rstrip(". ")
    return name or "file"


def is_http_url(value: str) -> bool:
    v = (value or "").strip().lower()
    return v.startswith("http://") or v.startswith("https://")


def _norm(name) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip()).lower()


def _match_col(columns, wanted):
    if not wanted:
        return None
    w = _norm(wanted)
    for c in columns:
        if _norm(c) == w:
            return c
    for c in columns:
        cl = _norm(c)
        if w and (w in cl or cl in w):
            return c
    return None


def _best_col(columns, hints, fallback=None):
    matched = _match_col(columns, fallback) if fallback else None
    if matched:
        return matched
    cols_l = list(columns)
    for hint in hints:
        for c in cols_l:
            if hint in _norm(c):
                return c
    return cols_l[0] if cols_l else fallback


def format_id(val) -> str:
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return ""
    if _SCI_RE.match(s):
        try:
            f = float(s)
            if f.is_integer() and abs(f) < 1e16:
                return str(int(f))
        except ValueError:
            pass
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        return s[:-2]
    return s


def extract_url(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return ""
    if is_http_url(s):
        return s.split()[0].strip("<>\"'")
    m = _HYPERLINK_RE.search(s)
    if m:
        return m.group(1).strip()
    return ""


def list_sheets(excel_path: str):
    xl = pd.ExcelFile(excel_path)
    names = list(xl.sheet_names)
    xl.close()
    return names


def peek_columns(excel_path: str, sheet_name, header_row=0):
    df = pd.read_excel(
        excel_path, sheet_name=sheet_name, header=header_row,
        nrows=0, dtype=str,
    )
    return [str(c).strip() for c in df.columns]


def _detect_header_row(excel_path, sheet_name, url_col):
    peek = pd.read_excel(
        excel_path, sheet_name=sheet_name, header=None,
        nrows=25, dtype=str, keep_default_na=False,
    )
    wanted = _norm(url_col)
    for i, row in peek.iterrows():
        vals = [_norm(v) for v in row.tolist()]
        if wanted and wanted in vals:
            return int(i)
        if any("url" in v or v in ("link", "pod image", "pdf") for v in vals if v):
            if not wanted or any(wanted in v or v in wanted for v in vals):
                return int(i)
    return 0


def _col_letters_to_idx(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def _load_xlsx_hyperlinks(excel_path, sheet_name, col_idx_1based):
    """
    Read hyperlink targets from the xlsx zip (no full workbook load).
    Returns {excel_row_number: url}.
    """
    if not str(excel_path).lower().endswith((".xlsx", ".xlsm")):
        return {}
    out = {}
    try:
        zf = zipfile.ZipFile(excel_path)
    except Exception:
        return {}

    try:
        wb_xml = zf.read("xl/workbook.xml")
        rels_xml = zf.read("xl/_rels/workbook.xml.rels")
    except KeyError:
        zf.close()
        return {}

    rels = {}
    rel_root = ET.fromstring(rels_xml)
    for rel in rel_root:
        rid = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rid and target:
            rels[rid] = target.replace("\\", "/")

    sheet_path = None
    root = ET.fromstring(wb_xml)
    for sh in root.iter(f"{NS_MAIN}sheet"):
        name = sh.attrib.get("name")
        rid = sh.attrib.get(f"{NS_REL}id") or sh.attrib.get("r:id")
        if name == sheet_name and rid in rels:
            target = rels[rid]
            sheet_path = target if target.startswith("xl/") else "xl/" + target.lstrip("/")
            break
    if not sheet_path:
        zf.close()
        return {}

    rels_path = sheet_path.replace("worksheets/", "worksheets/_rels/") + ".rels"
    if rels_path.startswith("xl/worksheets/") and "/_rels/" not in rels_path:
        base = os.path.basename(sheet_path)
        rels_path = f"xl/worksheets/_rels/{base}.rels"

    hrefs = {}
    try:
        srels = ET.fromstring(zf.read(rels_path))
        for rel in srels:
            if rel.attrib.get("TargetMode", "").lower() != "external":
                typ = rel.attrib.get("Type", "")
                if "hyperlink" not in typ.lower():
                    continue
            rid = rel.attrib.get("Id")
            target = rel.attrib.get("Target")
            if rid and target and is_http_url(target):
                hrefs[rid] = target.strip()
    except KeyError:
        pass

    try:
        source = zf.open(sheet_path)
    except KeyError:
        zf.close()
        return {}

    try:
        for event, elem in ET.iterparse(source, events=("end",)):
            tag = elem.tag
            if tag.endswith("hyperlink"):
                ref = (elem.attrib.get("ref") or "").split(":")[0]
                m = _CELL_REF_RE.match(ref.upper())
                if m:
                    cidx = _col_letters_to_idx(m.group(1))
                    ridx = int(m.group(2))
                    if cidx == col_idx_1based:
                        rid = elem.attrib.get(f"{NS_REL}id") or elem.attrib.get("r:id")
                        loc = elem.attrib.get("location") or ""
                        url = hrefs.get(rid, "")
                        if not url and is_http_url(loc):
                            url = loc.strip()
                        if url:
                            out[ridx] = url
                elem.clear()
            elif tag.endswith("hyperlinks"):
                elem.clear()
    finally:
        source.close()
        zf.close()
    return out


def _load_one_sheet(excel_path, sheet_name, url_col, id_col, log_fn=None):
    def _log(msg):
        if log_fn:
            log_fn(msg)

    header_row = _detect_header_row(excel_path, sheet_name, url_col)
    cols = peek_columns(excel_path, sheet_name, header_row)
    url_m = _match_col(cols, url_col)
    if not url_m:
        return [], {
            "sheet": sheet_name,
            "columns": cols,
            "error": (
                f"URL column '{url_col}' not found on sheet '{sheet_name}'. "
                f"Columns: {', '.join(cols) if cols else '(none)'}"
            ),
        }
    id_m = _match_col(cols, id_col) if id_col else None
    usecols = [url_m] if not id_m or id_m == url_m else [url_m, id_m]

    _log(f"  Reading sheet '{sheet_name}' (header row {header_row + 1})…")
    df = pd.read_excel(
        excel_path,
        sheet_name=sheet_name,
        header=header_row,
        dtype=str,
        usecols=usecols,
        keep_default_na=False,
        na_filter=False,
    )
    df.columns = [str(c).strip() for c in df.columns]
    url_m = _match_col(df.columns, url_m)
    id_m = _match_col(df.columns, id_m) if id_m else None

    rows = []
    samples = []
    for i, rec in enumerate(df.itertuples(index=False, name=None)):
        raw_url = rec[0] if rec else ""
        raw_id = rec[1] if id_m and len(rec) > 1 else ""
        url = extract_url(raw_url)
        rid = format_id(raw_id) if id_m else ""
        excel_row = header_row + 2 + i
        if url or rid or (raw_url and str(raw_url).strip()):
            rows.append({
                "row": excel_row,
                "url": url,
                "id": rid or None,
                "raw": "" if raw_url is None else str(raw_url).strip(),
            })
        if len(samples) < 5 and str(raw_url).strip():
            samples.append(str(raw_url).strip()[:80])

    n_urls = sum(1 for r in rows if is_http_url(r["url"]))
    if n_urls < max(1, len(rows) // 2):
        col_idx = cols.index(url_m) + 1 if url_m in cols else 1
        _log("  Cell text is not a URL — reading Excel hyperlinks…")
        hrefs = _load_xlsx_hyperlinks(excel_path, sheet_name, col_idx)
        if hrefs:
            for r in rows:
                if not is_http_url(r["url"]) and r["row"] in hrefs:
                    r["url"] = hrefs[r["row"]]
            extra = set(hrefs) - {r["row"] for r in rows}
            for excel_row in sorted(extra):
                rows.append({
                    "row": excel_row,
                    "url": hrefs[excel_row],
                    "id": None,
                    "raw": "",
                })
            rows.sort(key=lambda r: r["row"])
            n_urls = sum(1 for r in rows if is_http_url(r["url"]))

    return rows, {
        "sheet": sheet_name,
        "columns": cols,
        "url_col": url_m,
        "id_col": id_m,
        "n_rows": len(rows),
        "n_urls": n_urls,
        "samples": samples,
        "header_row": header_row + 1,
    }


def load_urls_from_excel(excel_path: str, url_col: str, id_col: str | None,
                         sheet_name: str | None = None, log_fn=None):
    """
    Read URLs from a (possibly huge) workbook without loading every cell
    via openpyxl. Tries the chosen sheet, then other sheets if that one
    has no downloadable rows.
    """
    sheets = list_sheets(excel_path)
    if not sheets:
        raise ValueError("This Excel file has no sheets.")

    if sheet_name and sheet_name not in ("Auto", "", None):
        if sheet_name not in sheets:
            raise ValueError(
                f"Sheet '{sheet_name}' not found. Available: {', '.join(sheets)}"
            )
        order = [sheet_name]
    else:
        order = list(sheets)

    reports = []
    best = None
    best_info = None
    for name in order:
        rows, info = _load_one_sheet(excel_path, name, url_col, id_col, log_fn)
        reports.append(info)
        if info.get("n_urls", 0) > 0:
            if log_fn:
                log_fn(
                    f"  Sheet '{name}': {info['n_rows']:,} rows, "
                    f"{info['n_urls']:,} URLs  (column '{info['url_col']}')"
                )
            return rows, info
        if best is None or info.get("n_rows", 0) > best_info.get("n_rows", 0):
            best, best_info = rows, info

    if sheet_name in (None, "", "Auto") and len(order) > 1:
        # explicit empty first sheet — already tried all
        pass

    info = best_info or (reports[0] if reports else {})
    cols = info.get("columns") or []
    samples = info.get("samples") or []
    n_rows = info.get("n_rows", 0)
    sheet = info.get("sheet", sheets[0])
    sample_txt = "; ".join(samples) if samples else "(empty)"
    tried = ", ".join(r.get("sheet", "?") for r in reports)
    raise ValueError(
        f"No download URLs found.\n"
        f"Sheet tried: {tried}\n"
        f"Last sheet '{sheet}': {n_rows:,} data rows\n"
        f"Columns: {', '.join(cols) if cols else '(none)'}\n"
        f"URL column looked for: '{url_col}'"
        + (f" → matched '{info.get('url_col')}'" if info.get("url_col") else " (not matched)")
        + f"\nSample cell values: {sample_txt}\n"
        f"Use the sheet dropdown if the links are not on the first sheet, "
        f"and check the URL column name."
    )


def guess_ext_from_url(url: str) -> str:
    """Try path, then nested ?file= query param (common for POD gateways)."""
    try:
        parsed = urlparse(url)
        path = unquote(parsed.path)
        ext = os.path.splitext(path)[1].lower()
        if ext and len(ext) <= 6:
            return ext

        qs = parse_qs(parsed.query)
        for key in ("file", "url", "path", "src"):
            if key in qs and qs[key]:
                nested = unquote(qs[key][0])
                nested_path = urlparse(nested).path if "://" in nested else nested
                ext = os.path.splitext(nested_path)[1].lower()
                if ext and len(ext) <= 6:
                    return ext
    except Exception:
        pass
    return ""


def guess_ext_from_response(resp, url: str) -> str:
    cd = resp.headers.get("Content-Disposition") or resp.headers.get("content-disposition") or ""
    m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', cd, re.I)
    if m:
        ext = os.path.splitext(unquote(m.group(1).strip()))[1].lower()
        if ext:
            return ext

    ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if ctype in EXT_FROM_MIME:
        return EXT_FROM_MIME[ctype]
    guessed = mimetypes.guess_extension(ctype) if ctype else None
    if guessed:
        return guessed

    return guess_ext_from_url(url) or ".bin"


def filename_from_url(url: str, fallback: str) -> str:
    try:
        parsed = urlparse(url)
        name = os.path.basename(unquote(parsed.path))
        if name and "." in name:
            return sanitize_filename(name)
        qs = parse_qs(parsed.query)
        for key in ("file", "url", "path", "src"):
            if key in qs and qs[key]:
                nested = unquote(qs[key][0])
                nested_path = urlparse(nested).path if "://" in nested else nested
                name = os.path.basename(nested_path)
                if name and "." in name:
                    return sanitize_filename(name)
    except Exception:
        pass
    return sanitize_filename(fallback)


def _session():
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        try:
            retry = Retry(
                total=3, backoff_factor=0.4,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=("GET", "HEAD"),
            )
        except TypeError:
            retry = Retry(
                total=3, backoff_factor=0.4,
                status_forcelist=(429, 500, 502, 503, 504),
            )
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        s.headers["User-Agent"] = "Mozilla/5.0 FileDownloader"
        _thread_local.session = s
    return s


def planned_filename(url: str, rename_id: str | None) -> str:
    ext = guess_ext_from_url(url) or ".pdf"
    if rename_id:
        base = sanitize_filename(rename_id)
        if base.lower().endswith(ext.lower()):
            return base
        return f"{base}{ext}"
    name = filename_from_url(url, f"file{ext}")
    if not os.path.splitext(name)[1]:
        name = f"{name}{ext}"
    return name


def download_file(url: str, dest_folder: str, rename_id: str | None,
                  dest_path: str | None = None) -> str:
    resp = _session().get(url, timeout=90, stream=True, allow_redirects=True)
    resp.raise_for_status()

    if dest_path:
        path = dest_path
        final_name = os.path.basename(path)
        ext = os.path.splitext(final_name)[1]
        if not ext:
            ext = guess_ext_from_response(resp, url)
            final_name = f"{final_name}{ext}"
            path = os.path.join(dest_folder, final_name)
    else:
        ext = guess_ext_from_response(resp, url)
        if rename_id:
            base = sanitize_filename(rename_id)
            filename = base if base.lower().endswith(ext.lower()) else f"{base}{ext}"
        else:
            filename = filename_from_url(url, f"file{ext}")
            if not os.path.splitext(filename)[1]:
                filename = f"{filename}{ext}"
        path, final_name = unique_path(dest_folder, filename)

    tmp = path + ".part"
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if chunk:
                f.write(chunk)
    os.replace(tmp, path)
    return os.path.basename(path)


def _download_one(item, out_dir, rename):
    url = item["url"]
    rid = item["id"]
    name = planned_filename(url, rid if rename else None)
    dest = os.path.join(out_dir, name)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return "exists", item, name
    try:
        saved = download_file(
            url, out_dir,
            rename_id=rid if rename else None,
            dest_path=dest,
        )
        return "ok", item, saved
    except Exception as e:
        return "fail", item, str(e)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("File Downloader")
        self.configure(fg_color=C["bg"])
        fit_to_screen(self, 760, 720)
        self._path = None
        self._sheets = ["Auto"]
        self._build()

    def _build(self):
        hdr = ctk.CTkFrame(self, fg_color=TINT["bg"], corner_radius=0)
        hdr.pack(fill="x")
        inn = ctk.CTkFrame(hdr, fg_color="transparent")
        inn.pack(padx=28, pady=14)
        ctk.CTkLabel(
            inn, text="📥  File Downloader",
            font=ctk.CTkFont("Segoe UI", 18, "bold"), text_color=C["text"],
        ).pack(anchor="w")
        ctk.CTkLabel(
            inn,
            text="Download files from Excel URLs / hyperlinks · large files (2 lakh+) OK",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
        ).pack(anchor="w")

        _, fi, self._prog, self._stat = add_run_footer(self, C, TINT)
        self._run_btn = add_primary_run_button(
            fi, "▶  Start Download", self._start, C, TINT)

        body = ctk.CTkScrollableFrame(
            self, fg_color="transparent", scrollbar_button_color=C["border"],
        )
        body.pack(fill="both", expand=True, padx=24, pady=(12, 8))

        banner = ctk.CTkFrame(
            body, fg_color=TINT["bg"], corner_radius=10,
            border_width=1, border_color=C["accent"],
        )
        banner.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            banner,
            text="📁  Output → Desktop\\OUTPUT\\File_Downloads\\<excel name>\\  (resumes if re-run)",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["accent"],
        ).pack(anchor="w", padx=14, pady=8)

        self._sec(body, "Excel file")
        fr = ctk.CTkFrame(body, fg_color="transparent")
        fr.pack(fill="x", pady=(0, 10))
        self._file_lbl = ctk.CTkLabel(
            fr, text="No file selected", font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["muted"], anchor="w",
        )
        self._file_lbl.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            fr, text="Browse…", width=90, height=34,
            fg_color=C["card"], hover_color=C["hover"],
            border_color=C["border"], border_width=1,
            text_color=C["text"], command=self._pick,
        ).pack(side="right")

        self._sec(body, "Sheet")
        self._sheet_var = ctk.StringVar(value="Auto")
        self._sheet_om = ctk.CTkOptionMenu(
            body, variable=self._sheet_var, values=["Auto"],
            height=34, fg_color=C["card"], button_color=C["hover"],
            button_hover_color=C["border"], text_color=C["text"],
            dropdown_fg_color=C["card"], dropdown_text_color=C["text"],
            command=lambda _=None: self._on_sheet_change(),
        )
        self._sheet_om.pack(fill="x", pady=(0, 10))

        self._sec(body, "Columns")
        settings = ctk.CTkFrame(
            body, fg_color=C["card"], corner_radius=12,
            border_width=1, border_color=C["border"],
        )
        settings.pack(fill="x", pady=(0, 10))
        settings.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            settings, text="URL / link column",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], width=140,
        ).grid(row=0, column=0, padx=16, pady=(14, 8), sticky="w")
        self._url_e = ctk.CTkEntry(
            settings, height=34, fg_color=C["hover"],
            border_color=C["border"], text_color=C["text"],
        )
        self._url_e.grid(row=0, column=1, padx=16, pady=(14, 8), sticky="ew")
        self._url_e.insert(0, "POD IMAGE")

        ctk.CTkLabel(
            settings, text="ID column (rename)",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], width=140,
        ).grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")
        self._id_e = ctk.CTkEntry(
            settings, height=34, fg_color=C["hover"],
            border_color=C["border"], text_color=C["text"],
            placeholder_text="e.g. AWB NUMBER",
        )
        self._id_e.grid(row=1, column=1, padx=16, pady=(0, 8), sticky="ew")
        self._id_e.insert(0, "AWB NUMBER")

        ctk.CTkLabel(
            settings, text="Parallel downloads",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"], width=140,
        ).grid(row=2, column=0, padx=16, pady=(0, 14), sticky="w")
        self._workers_e = ctk.CTkEntry(
            settings, height=34, fg_color=C["hover"],
            border_color=C["border"], text_color=C["text"], width=80,
        )
        self._workers_e.grid(row=2, column=1, padx=16, pady=(0, 14), sticky="w")
        self._workers_e.insert(0, "8")

        opts = ctk.CTkFrame(
            body, fg_color=C["card"], corner_radius=12,
            border_width=1, border_color=C["border"],
        )
        opts.pack(fill="x", pady=(0, 12))
        self._rename_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts, text="Rename downloaded files using ID column",
            variable=self._rename_var,
            font=ctk.CTkFont("Segoe UI", 12),
            text_color=C["text"], fg_color=C["accent"],
            hover_color=TINT["bdr"], border_color=C["border"],
            command=self._toggle_rename,
        ).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkLabel(
            opts,
            text="Reads only the URL/ID columns (not the whole 2-lakh sheet into Excel). "
                 "Supports hyperlinks and plain URL text. Re-run skips files already saved.",
            font=ctk.CTkFont("Segoe UI", 11), text_color=C["muted"],
            wraplength=680, justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        self._log = ctk.CTkTextbox(
            body, height=200, font=ctk.CTkFont("Courier New", 11),
            fg_color=C["card"], border_color=C["border"],
            border_width=1, text_color=C["muted"], state="disabled",
        )
        self._log.pack(fill="x", pady=(0, 12))

    def _sec(self, p, t):
        ctk.CTkLabel(
            p, text=t, font=ctk.CTkFont("Segoe UI", 12, "bold"),
            text_color=C["text"], anchor="w",
        ).pack(fill="x", pady=(10, 2))

    def _toggle_rename(self):
        state = "normal" if self._rename_var.get() else "disabled"
        self._id_e.configure(state=state)

    def _write(self, msg):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _on_sheet_change(self):
        if self._path:
            self._suggest_columns()

    def _suggest_columns(self):
        if not self._path:
            return
        sheet = self._sheet_var.get()
        try:
            sheets = list_sheets(self._path)
            name = sheets[0] if sheet in ("Auto", "") else sheet
            if name not in sheets:
                name = sheets[0]
            cols = peek_columns(self._path, name, 0)
        except Exception:
            return
        url_guess = _best_col(cols, URL_COL_HINTS, self._url_e.get().strip())
        id_guess = _best_col(cols, ID_COL_HINTS, self._id_e.get().strip())
        if url_guess:
            self._url_e.delete(0, "end")
            self._url_e.insert(0, str(url_guess))
        if id_guess:
            self._id_e.delete(0, "end")
            self._id_e.insert(0, str(id_guess))

    def _pick(self):
        path = filedialog.askopenfilename(
            title="Select Excel file",
            filetypes=[("Excel files", "*.xlsx *.xlsm *.xls"), ("All files", "*.*")],
        )
        if not path:
            return
        self._path = path
        self._file_lbl.configure(
            text=os.path.basename(path), text_color=C["accent"],
        )
        try:
            sheets = list_sheets(path)
        except Exception as e:
            messagebox.showerror("Excel", f"Could not read sheets:\n{e}")
            return
        values = ["Auto"] + sheets
        self._sheet_om.configure(values=values)
        self._sheet_var.set("Auto")
        self._suggest_columns()

    def _workers(self):
        try:
            n = int((self._workers_e.get() or "8").strip())
        except ValueError:
            n = 8
        return max(1, min(n, 32))

    def _start(self):
        if not self._path:
            messagebox.showwarning("Missing", "Select an Excel file first.")
            return
        url_col = self._url_e.get().strip()
        if not url_col:
            messagebox.showwarning("Missing", "Enter the URL / link column name.")
            return
        rename = self._rename_var.get()
        id_col = self._id_e.get().strip() if rename else ""
        if rename and not id_col:
            messagebox.showwarning(
                "Missing",
                "Enter an ID column for renaming, or turn off rename.",
            )
            return
        sheet = self._sheet_var.get()
        workers = self._workers()

        self._run_btn.configure(state="disabled", text="Downloading…")
        self._prog.set(0)
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")
        threading.Thread(
            target=self._run,
            args=(url_col, id_col if rename else None, rename, sheet, workers),
            daemon=True,
        ).start()

    def _run(self, url_col, id_col, rename, sheet, workers):
        out_dir = get_output_dir(self._path)

        def log(m):
            self.after(0, lambda x=m: self._write(x))

        try:
            log(f"Excel    → {self._path}")
            log(f"Sheet    → {sheet}")
            log(f"URL col  → {url_col}")
            log(f"Rename   → {'ON (' + id_col + ')' if rename else 'OFF'}")
            log(f"Workers  → {workers}")
            log(f"Output   → {out_dir}\n")

            items, info = load_urls_from_excel(
                self._path, url_col, id_col,
                sheet_name=None if sheet == "Auto" else sheet,
                log_fn=log,
            )
            todo = [it for it in items if is_http_url(it.get("url") or "")]
            skipped_no_url = len(items) - len(todo)
            total = len(todo)
            log(
                f"\nReady    → {total:,} URLs"
                + (f"  ({skipped_no_url:,} rows without a URL skipped)" if skipped_no_url else "")
            )
            if total == 0:
                raise ValueError("No valid http(s) URLs to download.")

            log_csv = os.path.join(out_dir, "download_log.csv")
            new_log = not os.path.exists(log_csv)
            log_lock = threading.Lock()
            log_fh = open(log_csv, "a", newline="", encoding="utf-8")
            writer = csv.writer(log_fh)
            if new_log:
                writer.writerow(["row", "id", "url", "status", "file_or_error"])

            ok = fail = exists = 0
            done = 0

            def bump(status, item, detail):
                nonlocal ok, fail, exists, done
                done += 1
                if status == "ok":
                    ok += 1
                elif status == "exists":
                    exists += 1
                else:
                    fail += 1
                with log_lock:
                    writer.writerow([
                        item.get("row"), item.get("id") or "",
                        item.get("url") or "", status, detail,
                    ])
                    if done % 50 == 0:
                        log_fh.flush()
                if done <= 15 or done % 200 == 0 or status == "fail":
                    label = item.get("id") or f"row_{item.get('row')}"
                    if status == "ok":
                        log(f"  [{done}/{total}] saved {detail}")
                    elif status == "exists":
                        log(f"  [{done}/{total}] already have {detail}")
                    else:
                        log(f"  [{done}/{total}] ❌ {label}: {detail}")
                self.after(0, lambda d=done, t=total: self._prog.set(d / t))
                if done % 20 == 0 or done == total:
                    self.after(0, lambda d=done, t=total, o=ok, f=fail, e=exists: self._stat.configure(
                        text=f"{d:,} / {t:,}  ·  saved {o:,}  ·  exist {e:,}  ·  failed {f:,}",
                        text_color=C["muted"],
                    ))

            log(f"Downloading with {workers} parallel workers…\n")
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = [
                    pool.submit(_download_one, it, out_dir, rename)
                    for it in todo
                ]
                for fut in as_completed(futs):
                    status, item, detail = fut.result()
                    bump(status, item, detail)

            log_fh.flush()
            log_fh.close()

            log("\n========== SUMMARY ==========")
            log(f"Downloaded : {ok:,}")
            log(f"Already had: {exists:,}")
            log(f"Failed     : {fail:,}")
            log(f"No URL     : {skipped_no_url:,}")
            log(f"Folder     : {out_dir}")
            log(f"Log CSV    : {log_csv}")

            self.after(0, lambda: self._prog.set(1))
            self.after(0, lambda: self._stat.configure(
                text=f"Done — {ok:,} downloaded, {exists:,} already there, {fail:,} failed.",
                text_color=C["green"],
            ))
            self.after(0, lambda: subprocess.Popen(["explorer", out_dir]))
            self.after(0, lambda: messagebox.showinfo(
                "Complete",
                f"Downloaded: {ok:,}\nAlready had: {exists:,}\nFailed: {fail:,}\n\n{out_dir}",
            ))
        except Exception as e:
            log(f"\nError: {e}")
            self.after(0, lambda: self._stat.configure(text=str(e), text_color=C["red"]))
            self.after(0, lambda err=str(e): messagebox.showerror("Error", err))
        finally:
            self.after(0, lambda: self._run_btn.configure(
                state="normal", text="▶  Start Download",
            ))


if __name__ == "__main__":
    App().mainloop()
