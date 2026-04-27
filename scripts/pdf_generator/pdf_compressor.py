import os
import logging
import subprocess
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from capri_pipeline.config import CompressionConfig


class PDFCompressor:
    def __init__(self, config: CompressionConfig):
        self.config = config
        self.gs_command = self._build_gs_command()

    def _build_gs_command(self) -> List[str]:
        base_cmd = [
            self.config.gs_path,
            "-sDEVICE=pdfwrite",
            f"-dCompatibilityLevel={self.config.compatibility_level}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH"
        ]
        if hasattr(self.config, 'compression_level'):
            level = self.config.compression_level
            if level > 6:
                base_cmd.extend(["-dPDFSETTINGS=/prepress"])
            elif level > 4:
                base_cmd.extend(["-dPDFSETTINGS=/printer"])
            elif level > 2:
                base_cmd.extend(["-dPDFSETTINGS=/ebook"])
            else:
                base_cmd.extend(["-dPDFSETTINGS=/screen"])
        elif hasattr(self.config, 'quality'):
            quality_map = {
                "screen":   "/screen",
                "ebook":    "/ebook",
                "printer":  "/printer",
                "prepress": "/prepress",
            }
            setting = quality_map.get(self.config.quality, "/printer")
            base_cmd.extend([f"-dPDFSETTINGS={setting}"])
        return base_cmd

    def compress_pdf(self, input_path: str, output_path: str) -> bool:
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            cmd = self.gs_command + [f"-sOutputFile={output_path}", input_path]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            if result.returncode == 0:
                logging.info(f"Successfully compressed: {input_path}")
                return True
            else:
                logging.error(f"Ghostscript error for {input_path}: {result.stderr.decode()}")
                return False
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to compress {input_path}: {e.stderr.decode()}")
            return False
        except Exception as e:
            logging.error(f"Unexpected error compressing {input_path}: {str(e)}")
            return False

    def compress_folder(self, source_folder: str, dest_folder: str) -> int:
        success_count = 0
        pdf_files = [f for f in os.listdir(source_folder) if f.lower().endswith('.pdf')]
        if not pdf_files:
            logging.warning(f"No PDFs found in {source_folder}")
            return 0
        logging.info(f"Compressing {len(pdf_files)} PDFs from {source_folder}")
        os.makedirs(dest_folder, exist_ok=True)

        def task(pdf_file):
            input_path  = os.path.join(source_folder, pdf_file)
            output_path = os.path.join(dest_folder, pdf_file)
            return self.compress_pdf(input_path, output_path)

        with ThreadPoolExecutor() as executor:
            futures = {executor.submit(task, f): f for f in pdf_files}
            for future in as_completed(futures):
                if future.result():
                    success_count += 1

        logging.info(f"Compressed {success_count}/{len(pdf_files)} PDFs successfully")
        return success_count
