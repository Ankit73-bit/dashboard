import re
import shutil
import pandas as pd
import logging
import os
import gc
import psutil
import json
import concurrent.futures
from typing import Callable, Dict, Any, Optional, List


def convert_excel_to_csv(excel_file):
    try:
        df = pd.read_excel(excel_file)
        csv_file = os.path.splitext(excel_file)[0] + ".csv"
        df.to_csv(csv_file, index=False)
        return csv_file
    except Exception as e:
        logging.error(f"Error converting Excel to CSV: {e}")
        raise


def log_memory_usage(prefix: str = "") -> None:
    process = psutil.Process(os.getpid())
    logging.info(f"{prefix} Memory: {process.memory_info().rss / (1024 * 1024):.2f} MB")


def prepare_images(content: str, temp_dir: str, output_folder: str) -> None:
    image_pattern = re.compile(r'#image\("([^"]+)"')
    image_matches = set(image_pattern.findall(content))
    for img_name in image_matches:
        possible_sources = [
            os.path.join(output_folder, img_name),
            os.path.join(os.path.dirname(output_folder), img_name),
            img_name
        ]
        dst_img_path = os.path.join(temp_dir, os.path.basename(img_name))
        if os.path.exists(dst_img_path):
            continue
        copied = False
        for src_path in possible_sources:
            if os.path.exists(src_path):
                try:
                    shutil.copy(src_path, dst_img_path)
                    logging.info(f"Copied image {src_path} to {dst_img_path}")
                    copied = True
                    break
                except Exception as e:
                    logging.warning(f"Failed to copy image {src_path}: {e}")
        if not copied:
            logging.error(f"Could not find image file: {img_name}")
            raise FileNotFoundError(f"Required image not found: {img_name}")


def cleanup_temp_dir(temp_dir: str) -> None:
    try:
        shutil.rmtree(temp_dir)
    except Exception as e:
        logging.warning(f"Failed to remove temporary directory {temp_dir}: {e}")


def process_row_wrapper(args):
    row, output_folder, template_dict, notice_config, temp_dir, default_template, enable_password, password = args
    has_rotation = any(
        tbl.get("rotation", False)
        for tbl in notice_config.get("tables", [])
    )
    if has_rotation:
        from pdf_generator.pdf_generator import process_table_rotation
        return process_table_rotation(
            row, output_folder, template_dict, notice_config,
            temp_dir, default_template, enable_password=enable_password, password=password
        )
    else:
        from pdf_generator.pdf_generator import process_row
        return process_row(
            row, output_folder, template_dict, notice_config,
            temp_dir, default_template, enable_password=enable_password, password=password
        )


def process_in_chunks(
    data_file: str,
    chunksize: int,
    process_row_func: Callable,
    output_folder: str,
    template_dict: Dict[str, str],
    notice_config: Dict[str, Any],
    max_workers: int,
    default_template: str,
    state_file: str = "processing_state.json",
    enable_password: bool = False,
    password_field: Optional[str] = None
) -> Optional[List[tuple]]:

    temp_dir = os.path.join(output_folder, "temp_shared")
    os.makedirs(temp_dir, exist_ok=True)

    from pdf_generator.pdf_generator import prepare_all_images, resolve_output_id
    prepare_all_images(template_dict, output_folder, temp_dir)

    state_dir = os.path.join(output_folder, "state")
    os.makedirs(state_dir, exist_ok=True)
    state_path = os.path.join(state_dir, state_file)

    processed_ids = []
    last_processed_index = -1

    if os.path.exists(state_path):
        try:
            with open(state_path, 'r') as f:
                state = json.load(f)
                last_processed_index = state.get('last_processed_index', -1)
                processed_ids = state.get('processed_ids', [])
                logging.info(f"Resuming from index {last_processed_index}")
        except Exception as e:
            logging.error(f"Error loading state: {e}")

    try:
        df_reader = pd.read_csv(
            data_file, dtype=str, chunksize=chunksize,
            encoding='utf-8', on_bad_lines='skip',
            skiprows=range(1, last_processed_index + 2) if last_processed_index >= 0 else None
        )

        for chunk_idx, chunk in enumerate(df_reader):
            chunk_start = last_processed_index + 1
            logging.info(f"Processing chunk {chunk_idx+1} (rows {chunk_start}-{chunk_start + len(chunk) - 1})")

            with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
                args_list = [
                    (
                        row, output_folder, template_dict, notice_config, temp_dir, default_template,
                        enable_password,
                        str(row[password_field]) if password_field and password_field in row else None
                    )
                    for _, row in chunk.iterrows()
                ]
                future_to_index = {
                    executor.submit(process_row_wrapper, args): idx
                    for idx, args in enumerate(args_list)
                }
                for future in concurrent.futures.as_completed(future_to_index):
                    idx = future_to_index[future]
                    row = chunk.iloc[idx]
                    row_id, _ = resolve_output_id(row, notice_config)
                    srno = row.get("SrNo", 0)
                    try:
                        result = future.result()
                        if isinstance(result, list):
                            for pdf_path in result:
                                if pdf_path:
                                    pdf_stem = os.path.splitext(os.path.basename(pdf_path))[0]
                                    processed_ids.append((srno, pdf_stem))
                        elif result:
                            processed_ids.append((srno, row_id))
                        if len(processed_ids) % 10 == 0:
                            with open(state_path, 'w') as f:
                                json.dump({'last_processed_index': chunk_start + idx, 'processed_ids': processed_ids}, f)
                    except Exception as e:
                        logging.error(f"Error processing row {chunk_start + idx}: {e}")

            last_processed_index = chunk_start + len(chunk) - 1
            with open(state_path, 'w') as f:
                json.dump({'last_processed_index': last_processed_index, 'processed_ids': processed_ids}, f)
            gc.collect()
            log_memory_usage(f"After chunk {chunk_idx+1}")

        return processed_ids

    except Exception as e:
        logging.error(f"Processing failed: {e}")
        if 'last_processed_index' in locals():
            with open(state_path, 'w') as f:
                json.dump({'last_processed_index': last_processed_index, 'processed_ids': processed_ids}, f)
        raise
