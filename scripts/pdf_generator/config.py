from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import os
import json
import logging

@dataclass
class PathConfig:
    data: str
    config: str
    templates: Dict[str, str]
    output: str
    merge: str
    images: str

    def __post_init__(self):
        for template_path in self.templates.values():
            if not os.path.exists(template_path):
                logging.warning(f"Template path does not exist: {template_path}")
        for name, path in [('data', self.data), ('config', self.config)]:
            if path and not os.path.exists(path):
                logging.warning(f"Path does not exist: {path} ({name})")

@dataclass
class PDFProtectionConfig:
    enabled: bool = False
    password_field: Optional[str] = None
    default_password: str = "password"
    remove_password: bool = False

@dataclass
class UploadConfig:
    enabled: bool = False
    bucket_name: Optional[str] = None
    s3_uri: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: Optional[str] = None
    upload_entire_folder: bool = False
    failed_files_dir: str = "failed_uploads"

@dataclass
class CompressionConfig:
    enabled: bool = False
    compress_output: bool = True
    compress_merge: bool = True
    gs_path: str = "gswin64c"
    compatibility_level: str = "1.4"
    quality: str = "printer"
    compression_level: int = 3

@dataclass
class ProcessingConfig:
    generate_pdfs: bool = True
    merge_pdfs: bool = True
    chunksize: int = 500
    batch_size: int = 100
    max_memory_mb: int = 1024
    retry_attempts: int = 3
    max_workers: int = max(1, os.cpu_count() - 2)
    pdf_protection: PDFProtectionConfig = field(default_factory=PDFProtectionConfig)
    compress: CompressionConfig = field(default_factory=CompressionConfig)

@dataclass
class AppConfig:
    paths: PathConfig
    processing: ProcessingConfig
    upload: UploadConfig = field(default_factory=UploadConfig)
    notice_config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'AppConfig':
        paths = PathConfig(**config_dict.get('paths', {}))

        processing_dict = config_dict.get('processing', {})
        pdf_protection_dict = processing_dict.pop('pdf_protection', {})
        pdf_protection = PDFProtectionConfig(**pdf_protection_dict)
        compress_dict = processing_dict.pop('compress', {})
        compress_config = CompressionConfig(**compress_dict)
        processing = ProcessingConfig(
            **processing_dict,
            pdf_protection=pdf_protection,
            compress=compress_config
        )

        upload_dict = config_dict.get('upload', {})
        upload = UploadConfig(**upload_dict)

        return cls(paths=paths, processing=processing, upload=upload)

    def load_notice_config(self) -> None:
        if not self.paths.config or not str(self.paths.config).strip():
            self.notice_config = {}
            logging.info("No notice config provided; using defaults from code.")
            return
        logging.info(f"Loading notice configuration from {self.paths.config}")
        try:
            with open(self.paths.config, 'r', encoding='utf-8') as file:
                self.notice_config = json.load(file)
        except Exception as e:
            logging.error(f"Failed to load notice config: {e}")
            raise
