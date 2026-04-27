import os
import shutil
import logging
import gc
import traceback
import time
from multiprocessing import cpu_count
from typing import Dict
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

from capri_pipeline.logging_config import setup_logging
from capri_pipeline.config import AppConfig
from capri_pipeline.data_processor import process_in_chunks, log_memory_usage, convert_excel_to_csv
from capri_pipeline.pdf_generator import process_row
from capri_pipeline.pdf_merger import merge_pdfs
from capri_pipeline.memory_monitor import MemoryMonitor
from capri_pipeline.s3_uploader import upload_files_to_s3


@contextmanager
def error_recovery_context(config):
    try:
        yield
    except Exception as e:
        logging.error(f"Error in processing: {e}")
        logging.error(traceback.format_exc())
        gc.collect()
        time.sleep(2)
        raise


def main(config: AppConfig = None):
    """Run the PDF generation pipeline with a given AppConfig."""
    if not config:
        raise ValueError("config must be provided — use the UI to build and pass AppConfig.")

    memory_monitor = MemoryMonitor(
        warning_threshold_mb=config.processing.max_memory_mb * 0.7,
        critical_threshold_mb=config.processing.max_memory_mb
    )
    memory_monitor.start()

    try:
        config.load_notice_config()

        template_dict: Dict[str, str] = {}
        missing_templates = []

        for state_name, template_path in config.paths.templates.items():
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    template_dict[state_name.upper()] = f.read()
                logging.info(f"Loaded template: {template_path}")
            except FileNotFoundError:
                missing_templates.append((state_name, template_path))
            except Exception as e:
                logging.error(f"Error loading template {template_path}: {e}")

        if missing_templates:
            logging.warning("Missing templates:")
            for state, path in missing_templates:
                logging.warning(f" - {state}: {path}")

        default_template = template_dict.get('DEFAULT')
        if not default_template:
            logging.error("Missing DEFAULT template")
            raise SystemExit("Cannot continue without DEFAULT template")

        os.makedirs(config.paths.output, exist_ok=True)

        if config.paths.images and os.path.exists(config.paths.images):
            for img_file in os.listdir(config.paths.images):
                src_path = os.path.join(config.paths.images, img_file)
                dst_path = os.path.join(config.paths.output, img_file)
                if os.path.isfile(src_path):
                    shutil.copy(src_path, dst_path)
            logging.info(f"Copied images to {config.paths.output}")

        data_file = config.paths.data
        if data_file.lower().endswith(('.xlsx', '.xls')):
            logging.info(f"Converting {data_file} to CSV...")
            data_file = convert_excel_to_csv(data_file)
            config.paths.data = data_file

        processed_ids = None

        if config.processing.generate_pdfs:
            log_memory_usage("Before PDF generation")
            with error_recovery_context(config):
                processed_ids = process_in_chunks(
                    data_file=config.paths.data,
                    chunksize=config.processing.chunksize,
                    process_row_func=process_row,
                    output_folder=config.paths.output,
                    template_dict=template_dict,
                    notice_config=config.notice_config,
                    max_workers=config.processing.max_workers,
                    default_template=default_template,
                    enable_password=config.processing.pdf_protection.enabled,
                    password_field=config.processing.pdf_protection.password_field
                )
            log_memory_usage("After PDF generation")
            gc.collect()

        if config.processing.merge_pdfs and processed_ids:
            log_memory_usage("Before merging")
            with error_recovery_context(config):
                merge_pdfs(
                    processed_ids=processed_ids,
                    output_folder=config.paths.output,
                    merge_folder=config.paths.merge,
                    typst_content=default_template,
                    notice_config=config.notice_config,
                    template_path=list(config.paths.templates.values())[0],
                    batch_size=config.processing.batch_size,
                    generate_missing=True,
                    max_workers=config.processing.max_workers
                )
            log_memory_usage("After merging")

        if config.upload.enabled:
            log_memory_usage("Before upload")
            success_count, failed_files = upload_files_to_s3(config.paths.output, config)
            logging.info(f"Uploaded {success_count} files, {len(failed_files)} failed")
            log_memory_usage("After upload")

        logging.info("Process completed successfully")

    except Exception as e:
        logging.error(f"Fatal error: {e}")
        logging.error(traceback.format_exc())
        raise
    finally:
        memory_monitor.stop()
        gc.collect()
