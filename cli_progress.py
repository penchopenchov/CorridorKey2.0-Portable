"""Dependency-free, stage-based terminal progress for the launcher and worker."""
from __future__ import annotations

from contextlib import contextmanager
import os
import shutil
import sys
import threading
import time

_vram_provider = None


def set_vram_provider(provider):
    """Register a worker-local callback returning allocated/reserved CUDA bytes."""
    global _vram_provider
    previous = _vram_provider
    _vram_provider = provider
    return previous


def _vram_text():
    if _vram_provider is None:
        return '', ''
    try:
        allocated, reserved = (value / 1024**3 for value in _vram_provider())
        return (f' | VRAM {allocated:.1f}/{reserved:.1f} GiB alloc/resv',
                f' VRAM{allocated:.1f}/{reserved:.1f}GiB')
    except Exception:
        # Optional telemetry must never break the render or its progress heartbeat.
        return ' | VRAM unavailable', ' VRAM unavailable'


def _duration(seconds):
    seconds = max(0, int(seconds))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f'{hours:d}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:02d}:{seconds:02d}'


@contextmanager
def progress_job(label):
    """Keep a batch label consistent across this process and its inference child."""
    previous = os.environ.get('CORRIDORKEY_PROGRESS_CLIP')
    os.environ['CORRIDORKEY_PROGRESS_CLIP'] = label
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('CORRIDORKEY_PROGRESS_CLIP', None)
        else:
            os.environ['CORRIDORKEY_PROGRESS_CLIP'] = previous


class Progress:
    """Report actual completed work; unknown-length stages get an elapsed heartbeat.

    Percentages and ETA describe this stage, not the whole multi-stage job.
    A successful context exit never fabricates completed frames.
    """

    def __init__(self, stage, total=None, *, unit='frames', stream=None, interval=None):
        self.stage = stage
        self.total = total if total and total > 0 else None
        self.completed = 0
        self.unit = unit
        self.stream = sys.stderr if stream is None else stream
        self.tty = self.stream.isatty()
        self.interval = interval if interval is not None else (0.25 if self.tty else 5.0)
        self.label = os.environ.get('CORRIDORKEY_PROGRESS_CLIP', '1/1')
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._width = 0
        self._last_write = float('-inf')
        self._detail = ''
        self._status = ''

    def __enter__(self):
        self._started = time.monotonic()
        self._emit(force=True)
        self._thread = threading.Thread(target=self._heartbeat, daemon=True)
        self._thread.start()
        return self

    def update(self, completed, *, total=None, detail=''):
        with self._lock:
            if total is not None and total > 0:
                self.total = total
            self.completed = max(self.completed, int(completed), 0)
            if self.total is not None:
                self.completed = min(self.completed, self.total)
            self._detail = detail
            self._emit(force=self.total is not None and self.completed == self.total)

    def _heartbeat(self):
        while not self._stop.wait(self.interval):
            self._emit()

    def _emit(self, *, force=False, final=False):
        with self._lock:
            now = time.monotonic()
            if not force and now - self._last_write < self.interval:
                return
            elapsed = now - self._started
            percent = f'{100 * self.completed / self.total:5.1f}%' if self.total else ' --.-%'
            frames = (f'{self.completed}/{self.total or "?"} {self.unit}'
                      if self.unit else 'frames --')
            eta = (_duration(elapsed * (self.total - self.completed) / self.completed)
                   if self.total and self.completed else 'estimating')
            prefix = f'Clip {self.label} | '
            vram, compact_vram = _vram_text()
            metrics = f' | {percent} | {frames} | elapsed {_duration(elapsed)} | ETA {eta}' + vram
            suffix = f' | {self._status or self._detail}' if self._status or self._detail else ''
            stage = self.stage
            if self.tty:
                columns = max(1, shutil.get_terminal_size(fallback=(120, 24)).columns - 1)
                if len(prefix + metrics + suffix) + 12 > columns:
                    # Preserve counters/timing before optional window details on small consoles.
                    prefix = f'Clip {self.label} '
                    metrics = f' {percent.strip()} {frames} elapsed {_duration(elapsed)} ETA {eta}'
                    suffix = f' {self._status}' if self._status else ''
                    if vram:
                        prefix = f'[{self.label}] '
                        count = f'{self.completed}/{self.total or "?"}f' if self.unit else '--f'
                        metrics = f' {percent.strip()} {count} t{_duration(elapsed)} ETA{eta}' + compact_vram
                available = max(0, columns - len(prefix) - len(metrics) - len(suffix))
                if len(stage) > available:
                    stage = stage[:available - 3] + '...' if available > 3 else stage[:available]
            line = prefix + stage + metrics + suffix
            try:
                if self.tty:
                    line = line[:columns]
                    self.stream.write('\r' + line.ljust(min(self._width, columns)) + ('\n' if final else ''))
                    self._width = len(line)
                else:
                    self.stream.write(line + '\n')
                self.stream.flush()
            except (OSError, ValueError):
                # Losing a log consumer must not turn successful inference into a failure.
                self._stop.set()
            self._last_write = now

    def __exit__(self, exc_type, exc_value, traceback):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        self._status = ('canceled' if exc_type and issubclass(exc_type, KeyboardInterrupt)
                        else 'failed' if exc_type else 'done')
        self._emit(force=True, final=True)
