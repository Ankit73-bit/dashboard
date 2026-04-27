import os
import logging
import typst
import pandas as pd
import gc
import re
import shutil
from contextlib import contextmanager
from PyPDF2 import PdfReader, PdfWriter
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta


def normalize_placeholders(content: str) -> str:
    return re.sub(
        r'\{\{\s*([^}]+?)\s*\}\}',
        lambda m: "{{" + "".join(m.group(1).split()) + "}}",
        content
    )


@contextmanager
def typst_compiler_context():
    try:
        yield
    finally:
        gc.collect()


def initialize_temp_dir(output_folder: str) -> str:
    temp_dir = os.path.join(output_folder, "temp_shared")
    if os.path.isdir(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            logging.warning(f"Could not clean temp dir {temp_dir}: {e}")
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def cleanup_temp_dir(temp_dir: str) -> None:
    try:
        shutil.rmtree(temp_dir)
    except Exception as e:
        logging.warning(f"Failed to remove temp directory {temp_dir}: {e}")


def prepare_all_images(template_dict: Dict[str, str], output_folder: str, temp_dir: str) -> None:
    all_images = set()
    for content in template_dict.values():
        all_images.update(re.findall(r'#image\("([^\"]+)"', content))
    for img_name in all_images:
        src = os.path.join(output_folder, img_name)
        dst = os.path.join(temp_dir, img_name)
        if os.path.exists(src) and not os.path.exists(dst):
            try:
                shutil.copy(src, dst)
                logging.info(f"Copied image {img_name} to temp directory")
            except Exception as e:
                logging.warning(f"Failed to copy image {img_name}: {e}")


def get_template_for_row(row: pd.Series, template_dict: Dict[str, str], default_template: str) -> str:
    def _pick(*candidates: str) -> str:
        for c in candidates:
            v = row.get(c, "")
            if v is None:
                continue
            s = str(v).strip()
            if s:
                return s.upper()
        return ""

    key = _pick("State", "STATE", "state")
    if not key:
        key = _pick("Language", "LANGUAGE", "language")

    tpl = template_dict.get(key)
    if tpl:
        return tpl
    if key and key != "DEFAULT":
        logging.warning(f"No template found for key={key!r}. Falling back to DEFAULT.")
    return default_template


def resolve_output_id(row: pd.Series, notice_config: Dict[str, Any]) -> Tuple[str, str]:
    preferred = str(notice_config.get("id_field", "") or "").strip()
    candidates = [preferred, "cuid", "filename"]
    seen = set()
    ordered = []
    for c in candidates:
        key = c.lower()
        if not c or key in seen:
            continue
        seen.add(key)
        ordered.append(c)

    col_map = {str(c).strip().lower(): c for c in row.index}
    for c in ordered:
        col = col_map.get(c.lower())
        if not col:
            continue
        value = str(row.get(col, "")).strip()
        if value:
            return value, col

    if len(row.index) > 0:
        first_col = row.index[0]
        value = str(row.get(first_col, "")).strip()
        if value:
            return value, str(first_col)
    return "", "none"


def fix_image_paths(content: str) -> str:
    return re.sub(
        r'#image\("([^\"]+)"',
        lambda m: f'#image("{os.path.basename(m.group(1))}"',
        content
    )


def apply_pdf_password_protection(pdf_path: str, password: str) -> None:
    protected_path = pdf_path.replace('.pdf', '_protected.pdf')
    try:
        reader = PdfReader(pdf_path)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.encrypt(password)
        with open(protected_path, 'wb') as out:
            writer.write(out)
        os.replace(protected_path, pdf_path)
    except Exception as e:
        logging.error(f"Error applying password to {pdf_path}: {e}")
        raise


def remove_pdf_password(input_pdf: str) -> None:
    decrypted_path = input_pdf.replace('.pdf', '_decrypted.pdf')
    try:
        reader = PdfReader(input_pdf)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        with open(decrypted_path, 'wb') as out:
            writer.write(out)
        os.replace(decrypted_path, input_pdf)
    except Exception as e:
        logging.error(f"Error removing password from {input_pdf}: {e}")
        raise


def format_date(value, input_fmt: str, output_fmt: str) -> str:
    if isinstance(value, datetime):
        return value.strftime(output_fmt)
    try:
        excel_epoch = datetime(1899, 12, 30)
        if isinstance(value, (float, int)):
            return (excel_epoch + timedelta(days=float(value))).strftime(output_fmt)
    except Exception:
        pass
    try:
        return datetime.strptime(str(value).strip(), input_fmt).strftime(output_fmt)
    except Exception:
        return str(value)


def replace_placeholders(row: pd.Series, content: str, notice_config: Dict[str, Any]) -> str:
    for field in notice_config.get("decimal_fields", []):
        if field in row and pd.notnull(row[field]):
            placeholder = f"{{{{{field}}}}}"
            try:
                content = content.replace(placeholder, f"{float(row[field]):.2f}")
            except (ValueError, TypeError):
                content = content.replace(placeholder, str(row[field]))

    date_fields = notice_config.get("date_fields", [])
    date_in_fmt = notice_config.get("date_input_format", "%Y-%m-%d")
    date_out_fmt = notice_config.get("date_output_format", "%d-%m-%Y")
    for field in date_fields:
        if field in row and pd.notnull(row[field]):
            placeholder = f"{{{{{field}}}}}"
            formatted_date = format_date(str(row[field]), date_in_fmt, date_out_fmt)
            content = content.replace(placeholder, formatted_date)

    for col in row.index:
        placeholder = f"{{{{{col}}}}}"
        if placeholder in content:
            content = content.replace(placeholder, str(row[col]) if pd.notnull(row[col]) else "")

    for table_config in notice_config.get("tables", []):
        content = process_table(row, table_config, content)
    for list_config in notice_config.get("list_fields", []):
        content = process_list_field(row, list_config, content)

    return content


def process_row(
    row: pd.Series,
    output_folder: str,
    template_dict: Dict[str, str],
    notice_config: Dict[str, Any],
    temp_dir: str,
    default_template: str,
    enable_password: bool = False,
    password: Optional[str] = None
) -> Optional[str]:
    tpl_content = get_template_for_row(row, template_dict, default_template)
    tpl_content = normalize_placeholders(tpl_content)
    if not tpl_content:
        logging.error("No template content available for row")
        return None

    cuid, source = resolve_output_id(row, notice_config)
    if not cuid:
        logging.error("Row missing ID value after fallback (cuid/cuild/filename/first-column)")
        return None
    if source not in {"cuid", "cuild", "filename"}:
        logging.warning(f"Using fallback ID source '{source}' for output filename: {cuid}")

    pdf_path = os.path.join(output_folder, f"{cuid}.pdf")
    if os.path.exists(pdf_path):
        return pdf_path

    typ_path = os.path.join(temp_dir, f"{cuid}.typ")
    try:
        content = replace_placeholders(row, tpl_content, notice_config)
        content = fix_image_paths(content)
        with open(typ_path, 'w', encoding='utf-8') as f:
            f.write(content)
        with typst_compiler_context():
            typst.compile(typ_path, pdf_path)
        if enable_password:
            apply_pdf_password_protection(
                pdf_path, password or notice_config.get('default_password', 'password')
            )
        return pdf_path
    except Exception as e:
        logging.error(f"Error generating PDF for {cuid}: {e}")
        return None
    finally:
        try:
            if os.path.exists(typ_path):
                os.remove(typ_path)
        except Exception:
            pass


def process_table(row: pd.Series, table_config: Dict[str, Any], content: str) -> str:
    placeholder_pattern = table_config.get("placeholder_pattern")
    if placeholder_pattern not in content:
        return content
    columns = table_config.get("columns", [])
    table_row_entries = []
    row_num = 1
    id_column = table_config.get("id_column")
    max_rows = table_config.get("max_rows", 10)
    row_count_field = table_config.get("row_count_field")
    if row_count_field and row_count_field in row.index and pd.notnull(row[row_count_field]):
        try:
            max_rows = int(row[row_count_field])
        except (ValueError, TypeError):
            pass
    while row_num <= max_rows:
        row_id_field = f"{id_column}_{row_num}"
        if row_id_field in row.index and pd.notnull(row[row_id_field]):
            row_values = []
            has_data = False
            for col_config in columns:
                col_name = col_config.get("name")
                col_format = col_config.get("format", "str")
                field_name = f"{col_name}_{row_num}"
                if field_name in row.index and pd.notnull(row[field_name]):
                    value = row[field_name]
                    try:
                        if col_format == "int":
                            formatted_value = f"[{int(float(value))}]"
                        elif col_format == "float":
                            formatted_value = f"[{float(value):.2f}]"
                        else:
                            formatted_value = f"[{str(value)}]"
                        has_data = True
                    except (ValueError, TypeError):
                        formatted_value = f"[{str(value)}]"
                        has_data = True
                    row_values.append(formatted_value)
                else:
                    row_values.append("[]")
            if has_data:
                table_row_entries.append(", ".join(row_values) + ",")
        row_num += 1
    if table_row_entries:
        return content.replace(placeholder_pattern, "\n  ".join(table_row_entries))
    else:
        return content.replace(placeholder_pattern, "")


def process_list_field(row: pd.Series, list_config: Dict[str, Any], content: str) -> str:
    field_name = list_config.get("field_name")
    placeholder = list_config.get("placeholder")
    placeholder_pattern = f"{{{{{placeholder}}}}}"
    if placeholder_pattern not in content:
        return content
    max_items = list_config.get("max_items", 10)
    field_values = [
        str(row[f"{field_name}_{i}"])
        for i in range(1, max_items + 1)
        if f"{field_name}_{i}" in row.index and pd.notnull(row[f"{field_name}_{i}"])
    ]
    return content.replace(placeholder_pattern, ", ".join(field_values))


def _extract_rotation_entries(row: pd.Series, rotation_config: Dict[str, Any]) -> list:
    id_column = rotation_config.get("id_column")
    columns   = rotation_config.get("columns", [])
    max_rows  = rotation_config.get("max_rows", 30)
    entries = []
    for i in range(1, max_rows + 1):
        id_field = f"{id_column}_{i}"
        if (id_field not in row.index or pd.isnull(row[id_field]) or str(row[id_field]).strip() == ""):
            continue
        entry = {}
        for col_cfg in columns:
            col_name  = col_cfg["name"]
            field_key = f"{col_name}_{i}"
            entry[col_name] = (
                row[field_key] if field_key in row.index and pd.notnull(row[field_key]) else ""
            )
        entries.append(entry)
    return entries


def _build_rotated_row(base_row: pd.Series, ordered_entries: list, rotation_config: Dict[str, Any]) -> pd.Series:
    id_column = rotation_config.get("id_column")
    columns   = rotation_config.get("columns", [])
    max_rows  = rotation_config.get("max_rows", 30)
    new_row = base_row.copy()
    for slot, entry in enumerate(ordered_entries, start=1):
        id_field = f"{id_column}_{slot}"
        new_row[id_field] = entry.get(id_column, str(slot))
        for col_cfg in columns:
            col_name = col_cfg["name"]
            new_row[f"{col_name}_{slot}"] = entry.get(col_name, "")
    for slot in range(len(ordered_entries) + 1, max_rows + 1):
        id_field = f"{id_column}_{slot}"
        if id_field in new_row.index:
            new_row[id_field] = None
        for col_cfg in columns:
            field_key = f"{col_cfg['name']}_{slot}"
            if field_key in new_row.index:
                new_row[field_key] = None
    return new_row


def process_table_rotation(
    row: pd.Series,
    output_folder: str,
    template_dict: Dict[str, str],
    notice_config: Dict[str, Any],
    temp_dir: str,
    default_template: str,
    enable_password: bool = False,
    password: Optional[str] = None
) -> list:
    rotation_config = next(
        (tbl for tbl in notice_config.get("tables", []) if tbl.get("rotation", False)), None
    )
    if rotation_config is None:
        logging.warning("process_table_rotation: no rotation table found – falling back to process_row.")
        result = process_row(row, output_folder, template_dict, notice_config, temp_dir, default_template, enable_password, password)
        return [result] if result else []

    cuid, source = resolve_output_id(row, notice_config)
    if not cuid:
        logging.error("process_table_rotation: row missing ID value – skipping.")
        return []
    if source not in {"cuid", "cuild", "filename"}:
        logging.warning(f"process_table_rotation: using fallback ID source '{source}': {cuid}")

    entries = _extract_rotation_entries(row, rotation_config)
    n = len(entries)
    if n == 0:
        logging.warning(f"[{cuid}] No applicant entries found – skipping rotation.")
        return []

    if n == 1:
        rotations = [(1, entries)]
    else:
        rotations = [
            (i + 1, [entries[i]] + [e for j, e in enumerate(entries) if j != i])
            for i in range(n)
        ]

    tpl_content = get_template_for_row(row, template_dict, default_template)
    tpl_content = normalize_placeholders(tpl_content)
    if not tpl_content:
        logging.error(f"[{cuid}] No template content available – aborting rotation.")
        return []

    generated_paths = []
    for rotation_index, ordered_entries in rotations:
        pdf_filename = f"{cuid}_{rotation_index}.pdf"
        pdf_path     = os.path.join(output_folder, pdf_filename)
        typ_path     = os.path.join(temp_dir, f"{cuid}_{rotation_index}.typ")
        if os.path.exists(pdf_path):
            logging.info(f"[{cuid}] Rotation {rotation_index}/{n} already exists – skipping.")
            generated_paths.append(pdf_path)
            continue
        try:
            rotated_row = _build_rotated_row(row, ordered_entries, rotation_config)
            content     = replace_placeholders(rotated_row, tpl_content, notice_config)
            content     = fix_image_paths(content)
            with open(typ_path, "w", encoding="utf-8") as f:
                f.write(content)
            with typst_compiler_context():
                typst.compile(typ_path, pdf_path)
            if enable_password:
                apply_pdf_password_protection(
                    pdf_path, password or notice_config.get("default_password", "password")
                )
            logging.info(f"[{cuid}] Rotation {rotation_index}/{n} → {pdf_filename}")
            generated_paths.append(pdf_path)
        except Exception as e:
            logging.error(f"[{cuid}] Rotation {rotation_index} failed: {e}", exc_info=True)
        finally:
            try:
                if os.path.exists(typ_path):
                    os.remove(typ_path)
            except Exception:
                pass
    return generated_paths
