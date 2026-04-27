import os
import shutil
import logging
import boto3
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed


def upload_file_to_s3(
    local_file_path: str,
    bucket: str,
    s3_key: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    aws_region: Optional[str] = None
) -> Tuple[str, bool]:
    try:
        s3 = boto3.client('s3',
                          aws_access_key_id=aws_access_key_id,
                          aws_secret_access_key=aws_secret_access_key,
                          region_name=aws_region)
        extra_args = {}
        if local_file_path.lower().endswith('.pdf'):
            extra_args = {'ContentType': 'application/pdf', 'ContentDisposition': 'inline'}
        s3.upload_file(local_file_path, bucket, s3_key, ExtraArgs=extra_args)
        logging.info(f"Uploaded {local_file_path} to s3://{bucket}/{s3_key}")
        return (local_file_path, True)
    except Exception as e:
        logging.error(f"Failed to upload {local_file_path}: {e}")
        return (local_file_path, False)


def upload_folder_to_s3(
    local_folder: str,
    s3_prefix: str,
    bucket: str,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    aws_region: Optional[str] = None
) -> Tuple[str, bool]:
    try:
        s3 = boto3.client('s3',
                          aws_access_key_id=aws_access_key_id,
                          aws_secret_access_key=aws_secret_access_key,
                          region_name=aws_region)
        for root, _, files in os.walk(local_folder):
            for file in files:
                local_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_path, local_folder)
                s3_path = os.path.join(s3_prefix, relative_path).replace("\\", "/")
                extra_args = {}
                if file.lower().endswith('.pdf'):
                    extra_args = {'ContentType': 'application/pdf', 'ContentDisposition': 'inline'}
                s3.upload_file(local_path, bucket, s3_path, ExtraArgs=extra_args)
        logging.info(f"Uploaded folder {local_folder} to s3://{bucket}/{s3_prefix}")
        return (local_folder, True)
    except Exception as e:
        logging.error(f"Failed to upload folder {local_folder}: {e}")
        return (local_folder, False)


def get_upload_items(output_dir: str, upload_entire_folder: bool) -> List[Tuple[str, str, bool]]:
    items = []
    for item in os.listdir(output_dir):
        full_path = os.path.join(output_dir, item)
        if upload_entire_folder:
            if os.path.isdir(full_path):
                items.append((full_path, item, True))
            else:
                items.append((full_path, item, False))
        elif item.lower().endswith('.pdf'):
            items.append((full_path, item, False))
    return items


def handle_failed_uploads(failed_items: List[str], failed_files_dir: str) -> None:
    if not failed_items:
        return
    os.makedirs(failed_files_dir, exist_ok=True)
    for item in failed_items:
        try:
            if os.path.isfile(item):
                shutil.copy(item, os.path.join(failed_files_dir, os.path.basename(item)))
            elif os.path.isdir(item):
                dest = os.path.join(failed_files_dir, os.path.basename(item))
                shutil.copytree(item, dest)
        except Exception as e:
            logging.error(f"Failed to backup {item}: {e}")


def upload_files_to_s3(output_dir: str, config) -> Tuple[int, List[str]]:
    if not config.upload.enabled:
        logging.info("S3 upload disabled in config")
        return 0, []
    upload_items = get_upload_items(output_dir, config.upload.upload_entire_folder)
    if not upload_items:
        logging.warning("No files found to upload")
        return 0, []
    success_count = 0
    failed_items = []
    with ThreadPoolExecutor(max_workers=config.processing.max_workers) as executor:
        futures = []
        for local_path, s3_name, is_folder in upload_items:
            full_s3_path = os.path.join(config.upload.s3_uri, s3_name).replace("\\", "/")
            if is_folder:
                futures.append(executor.submit(
                    upload_folder_to_s3, local_path, full_s3_path,
                    config.upload.bucket_name, config.upload.aws_access_key_id,
                    config.upload.aws_secret_access_key, config.upload.aws_region
                ))
            else:
                futures.append(executor.submit(
                    upload_file_to_s3, local_path, config.upload.bucket_name, full_s3_path,
                    config.upload.aws_access_key_id, config.upload.aws_secret_access_key,
                    config.upload.aws_region
                ))
        for future in as_completed(futures):
            item_path, success = future.result()
            if success:
                success_count += 1
            else:
                failed_items.append(item_path)
    handle_failed_uploads(failed_items, config.upload.failed_files_dir)
    logging.info(f"Upload complete. Success: {success_count}, Failed: {len(failed_items)}")
    return success_count, failed_items
