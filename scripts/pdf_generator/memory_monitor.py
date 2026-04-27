import os
import psutil
import logging
import gc
from typing import Optional, Callable
import threading
import time

class MemoryMonitor:
    def __init__(
        self,
        warning_threshold_mb: int = 1024,
        critical_threshold_mb: int = 1536,
        check_interval_sec: int = 5,
        warning_callback: Optional[Callable] = None,
        critical_callback: Optional[Callable] = None
    ):
        self.warning_threshold = warning_threshold_mb * 1024 * 1024
        self.critical_threshold = critical_threshold_mb * 1024 * 1024
        self.check_interval = check_interval_sec
        self.warning_callback = warning_callback or self._default_warning
        self.critical_callback = critical_callback or self._default_critical
        self.stop_flag = False
        self.monitor_thread = None

    def _default_warning(self):
        logging.warning(
            f"Memory usage warning: {self.get_memory_usage_mb():.2f} MB. "
            f"Triggering garbage collection."
        )
        gc.collect()

    def _default_critical(self):
        logging.error(
            f"Memory usage critical: {self.get_memory_usage_mb():.2f} MB. "
            f"Forcing aggressive garbage collection."
        )
        gc.collect(2)

    def get_memory_usage_mb(self) -> float:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)

    def _monitor_loop(self):
        while not self.stop_flag:
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            if mem_info.rss >= self.critical_threshold:
                self.critical_callback()
            elif mem_info.rss >= self.warning_threshold:
                self.warning_callback()
            time.sleep(self.check_interval)

    def start(self):
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            self.stop_flag = False
            self.monitor_thread = threading.Thread(target=self._monitor_loop)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
            logging.info("Memory monitoring started")

    def stop(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.stop_flag = True
            self.monitor_thread.join(timeout=self.check_interval * 2)
            logging.info("Memory monitoring stopped")
