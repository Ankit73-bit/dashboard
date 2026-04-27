import json
import os
import logging
import pandas as pd
from PyPDF2 import PdfMerger, PdfReader
import gc
import psutil
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import tempfile
import shutil
import time
import concurrent.futures


def log_memory_usage(prefix: str = "") -> None:
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    logging.info(f"{prefix} Memory usage: {mem_info.rss / (1024 * 1024):.2f} MB")


@contextmanager
def pdf_merger_context():
    merger = PdfMerger()
    try:
        yield merger
    finally:
        merger.close()
        gc.collect()


def merge_pdfs_with_retry(
    pdf_paths: List[str],
    output_path: str,
    max_retries: int = 3,
    memory_threshold_mb: int = 1024
) -> bool:
    for attempt in range(max_retries):
        temp_path = None
        try:
            process = psutil.Process(os.getpid())
            current_memory_mb = process.memory_info().rss / (1024 * 1024)
            if current_memory_mb > memory_threshold_mb:
                logging.warning(f"Memory usage high ({current_memory_mb:.2f} MB). Forcing GC before merge.")
                gc.collect()

            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                temp_path = temp_file.name

            with pdf_merger_context() as merger:
                for pdf_path in pdf_paths:
                    with open(pdf_path, 'rb') as f:
                        reader = PdfReader(f)
                        merger.append(reader)
                        reader = None
                        gc.collect()
                merger.write(temp_path)

            shutil.move(temp_path, output_path)
            return True

        except MemoryError:
            logging.error(f"Memory error during merge attempt {attempt+1}/{max_retries}")
            gc.collect()
            time.sleep(1)
        except Exception as e:
            logging.error(f"Error during merge attempt {attempt+1}/{max_retries}: {e}")
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
            if attempt < max_retries - 1:
                gc.collect()
                time.sleep(1)
            else:
                logging.error(f"Failed to merge PDFs after {max_retries} attempts")
                return False
    return False


def process_batch(batch_data):
    batch_idx, batch_ids, output_folder, merge_folder, typst_content, notice_config, template_path, generate_missing = batch_data
    batch_id = f"batch_{batch_idx + 1}"
    pdf_paths = []

    for cuid in batch_ids:
        pdf_path = os.path.join(output_folder, f"{cuid}.pdf")
        if not os.path.exists(pdf_path) and generate_missing:
            try:
                csv_file = None
                for file in os.listdir(output_folder):
                    if file.endswith('.csv') and 'data' in file:
                        csv_file = os.path.join(output_folder, file)
                        break
                if csv_file:
                    id_field = notice_config.get("id_field", "cuid")
                    for chunk in pd.read_csv(csv_file, dtype=str, chunksize=1000):
                        matching_rows = chunk[chunk[id_field] == cuid]
                        if not matching_rows.empty:
                            row = matching_rows.iloc[0]
                            logging.info(f"Generating missing PDF for {cuid}")
                            from capri_pipeline.pdf_generator import process_row
                            generated_path = process_row(
                                row=row,
                                output_folder=output_folder,
                                typst_content=typst_content,
                                notice_config=notice_config,
                                template_path=template_path,
                                temp_dir=os.path.join(output_folder, "temp_shared")
                            )
                            if generated_path:
                                pdf_path = generated_path
                            break
            except Exception as e:
                logging.error(f"Failed to generate missing PDF for {cuid}: {e}")

        if os.path.exists(pdf_path):
            pdf_paths.append(pdf_path)
        else:
            logging.warning(f"PDF not found and not generated: {pdf_path}")

    if pdf_paths:
        merged_path = os.path.join(merge_folder, f"merged_{batch_id}.pdf")
        success = merge_pdfs_with_retry(pdf_paths, merged_path)
        if success:
            logging.info(f"Successfully created merged batch: {merged_path}")
            return batch_id, merged_path
        else:
            logging.error(f"Failed to create merged batch: {merged_path}")
            return batch_id, None
    else:
        logging.warning(f"No PDFs were merged for batch {batch_id}")
        return batch_id, None


def merge_pdfs(
    processed_ids: List[tuple],
    output_folder: str,
    merge_folder: str,
    typst_content: str,
    notice_config: Dict[str, Any],
    template_path: str,
    batch_size: int = 500,
    generate_missing: bool = True,
    max_workers: int = max(1, os.cpu_count() - 2)
) -> List[str]:
    processed_ids = sorted(processed_ids, key=lambda x: int(x[0]) if processed_ids else [])
    processed_ids = [t[1] for t in processed_ids]

    os.makedirs(merge_folder, exist_ok=True)
    merged_files = []

    state_dir = os.path.join(merge_folder, "state")
    os.makedirs(state_dir, exist_ok=True)
    state_path = os.path.join(state_dir, "merge_state.json")

    completed_batches = set()
    if os.path.exists(state_path):
        try:
            with open(state_path, 'r') as f:
                state = json.load(f)
                completed_batches = set(state.get('completed_batches', []))
                logging.info(f"Resuming merge from state with {len(completed_batches)} completed batches")
        except Exception as e:
            logging.error(f"Error loading merge state file: {e}")

    if processed_ids and isinstance(processed_ids[0], (list, tuple)):
        processed_ids = sorted(processed_ids, key=lambda x: x[0])
        processed_ids = [t[1] for t in processed_ids]

    total_batches = (len(processed_ids) + batch_size - 1) // batch_size
    batch_data = []
    for batch_idx in range(total_batches):
        batch_id = f"batch_{batch_idx + 1}"
        if batch_id in completed_batches:
            logging.info(f"Skipping already completed {batch_id}")
            continue
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(processed_ids))
        batch_ids = processed_ids[start_idx:end_idx]
        batch_data.append((
            batch_idx, batch_ids, output_folder, merge_folder,
            typst_content, notice_config, template_path, generate_missing
        ))

    merged_files = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_batch, data) for data in batch_data]
        for future in concurrent.futures.as_completed(futures):
            try:
                batch_id, merged_path = future.result()
                if merged_path:
                    merged_files.append(merged_path)
                    completed_batches.add(batch_id)
                    with open(state_path, 'w') as f:
                        json.dump({'completed_batches': list(completed_batches)}, f)
            except Exception as e:
                logging.error(f"Error processing batch: {e}")

    merged_files.sort(key=lambda x: int(x.split('_')[-1].split('.')[0]))
    return merged_files
