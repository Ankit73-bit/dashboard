import logging
import os
import sys

def setup_logging(output_folder: str = None):
    """
    Attach a FileHandler to the root logger.
    If output_folder is given the log lands there; otherwise falls back to Desktop.
    Calling this after the UI has already attached its TextHandler is safe —
    we add the FileHandler explicitly instead of using basicConfig (which is a
    no-op once any handler exists).
    """
    if output_folder:
        log_dir = output_folder
    else:
        log_dir = os.path.join(os.path.expanduser("~"), "Desktop")

    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "process.log")

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Remove any stale FileHandlers from a previous run so we don't double-write
    for h in root.handlers[:]:
        if isinstance(h, logging.FileHandler):
            h.close()
            root.removeHandler(h)

    fh = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.info("Logging initialised. Log file: %s", log_path)
    return log_path
