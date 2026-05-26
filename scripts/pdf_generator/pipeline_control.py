"""Cooperative pause / resume / stop / restart for batch-based pipeline steps."""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from typing import Optional


class PipelineStopped(Exception):
    """Raised when the user stops the pipeline after the current batch finishes."""


class PipelineRestart(Exception):
    """Raised when the user restarts the pipeline after the current batch finishes."""


class PipelineControl:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pause_requested = False
        self._stop_requested = False
        self._restart_requested = False
        self._paused = False
        self._stopped = False
        self._status_callback = None

    def set_status_callback(self, callback) -> None:
        self._status_callback = callback

    def _notify(self, event: str) -> None:
        if self._status_callback:
            try:
                self._status_callback(event)
            except Exception:
                pass

    @property
    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    @property
    def is_stopped(self) -> bool:
        with self._lock:
            return self._stopped

    @property
    def restart_requested(self) -> bool:
        with self._lock:
            return self._restart_requested

    def request_pause(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._pause_requested = True

    def request_stop(self) -> None:
        with self._lock:
            self._stop_requested = True

    def request_restart(self) -> None:
        with self._lock:
            self._restart_requested = True
            self._stop_requested = True

    def resume(self) -> None:
        with self._lock:
            self._pause_requested = False
            self._paused = False

    def reset(self) -> None:
        with self._lock:
            self._pause_requested = False
            self._stop_requested = False
            self._restart_requested = False
            self._paused = False
            self._stopped = False

    def wait_before_batch(self) -> None:
        """Block if paused; raise if stopped or restart was requested."""
        while True:
            with self._lock:
                if self._restart_requested:
                    raise PipelineRestart()
                if self._stop_requested or self._stopped:
                    self._stopped = True
                    raise PipelineStopped()
                if not self._paused:
                    return
            time.sleep(0.25)

    def on_batch_complete(self, phase: str = "batch") -> None:
        """Call after a chunk/merge batch finishes. May pause, stop, or restart."""
        enter_pause = False
        with self._lock:
            if self._restart_requested:
                raise PipelineRestart()
            if self._stop_requested:
                self._stopped = True
                logging.info(f"Stop requested — {phase} stopped after completing the current batch.")
                raise PipelineStopped()
            if self._pause_requested:
                self._paused = True
                self._pause_requested = False
                enter_pause = True

        if enter_pause:
            logging.info(f"Paused after completing the current {phase}.")
            self._notify("paused")
            while True:
                with self._lock:
                    if self._restart_requested:
                        raise PipelineRestart()
                    if self._stop_requested:
                        self._stopped = True
                        logging.info(f"Stop requested while paused — {phase} stopped.")
                        raise PipelineStopped()
                    if not self._paused:
                        logging.info(f"Resuming {phase}…")
                        self._notify("resumed")
                        return
                time.sleep(0.25)


_active_control: Optional[PipelineControl] = None


def get_control() -> PipelineControl:
    global _active_control
    if _active_control is None:
        _active_control = PipelineControl()
    return _active_control


def reset_control() -> PipelineControl:
    global _active_control
    _active_control = PipelineControl()
    return _active_control


def clear_run_output(output_folder: str, merge_folder: str) -> None:
    """Remove generated PDFs, temp dirs, and state for a fresh restart."""
    for folder in (output_folder, merge_folder):
        if not folder or not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            try:
                if os.path.isfile(path):
                    os.remove(path)
                else:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError as e:
                logging.warning(f"Could not remove {path}: {e}")
    logging.info("Cleared output folders for restart.")
