import logging
import sys

def setup_logging():
    log_filename = "process.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_filename, mode="a", encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.info("Logging is set up. Log file: %s", log_filename)
