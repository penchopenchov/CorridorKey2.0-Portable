"""Owned temporary job caches with leases inherited by processing children."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
import copy
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid

from cli_progress import Progress


_REGISTRY = '.corridorkey-jobs'
_OWNER = 'corridorkey-portable-cache-v1'
_JOB_NAME = re.compile(r'job_[0-9a-f]{32}\Z')
_CURRENT = ContextVar('corridorkey_cache', default=None)


def _warning(message):
    print(f'WARNING: {message}', file=sys.stderr, flush=True)


def _linked(path):
    """Also reject Windows junctions (Path.is_junction needs Python 3.12)."""
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


class _Lease:
    def __init__(self, fd):
        self.fd = fd

    @classmethod
    def acquire(cls, path):
        if path.exists() and _linked(path):
            raise OSError(f'Refusing a linked cache lease: {path}')
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            import msvcrt

            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            create = kernel.CreateFileW
            create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                               wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
            create.restype = wintypes.HANDLE
            # Share mode zero makes ownership last until the FINAL inherited
            # handle closes, even if the launcher itself is forcibly killed.
            handle = create(str(path), 0xC0000000, 0, None, 4, 0x80, None)
            if handle == ctypes.c_void_p(-1).value:
                error = ctypes.get_last_error()
                if error in (32, 33):
                    return None
                raise ctypes.WinError(error)
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_RDWR)
            except BaseException:
                close = kernel.CloseHandle
                close.argtypes = (wintypes.HANDLE,)
                close(handle)
                raise
        else:
            import fcntl
            fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                return None
            except BaseException:
                os.close(fd)
                raise
        os.set_inheritable(fd, False)
        return cls(fd)

    def close(self):
        if self.fd is not None:
            # Do not explicitly unlock flock: children share the open-file
            # description and must keep the lock after this descriptor closes.
            os.close(self.fd)
            self.fd = None

    def popen(self, *args, **kwargs):
        child_fd = os.dup(self.fd)
        try:
            if os.name == 'nt':
                import msvcrt
                os.set_inheritable(child_fd, True)
                startup = copy.copy(kwargs.get('startupinfo')) if kwargs.get('startupinfo') else subprocess.STARTUPINFO()
                startup.lpAttributeList = dict(startup.lpAttributeList or {})
                handles = list(startup.lpAttributeList.get('handle_list', []))
                handles.append(msvcrt.get_osfhandle(child_fd))
                startup.lpAttributeList['handle_list'] = handles
                kwargs.update(startupinfo=startup, close_fds=True)
            else:
                kwargs['pass_fds'] = (*kwargs.get('pass_fds', ()), child_fd)
            return subprocess.Popen(*args, **kwargs)
        finally:
            os.close(child_fd)


def _registry(root, *, create=False):
    registry = root / _REGISTRY
    if create:
        root.mkdir(parents=True, exist_ok=True)
    if registry.exists() and (_linked(registry) or not registry.is_dir()):
        raise OSError(f'Refusing an invalid cache registry: {registry}')
    if create:
        registry.mkdir(exist_ok=True)
    return registry


def _remove(path):
    """Transient Windows locks may outlive a process exit briefly."""
    for delay in (0, 0.2, 0.5, 1.0):
        if delay:
            time.sleep(delay)
        try:
            if not path.exists():
                return True
            if _linked(path) or not path.is_dir():
                raise OSError('Cache path is a link or is not a directory')
            # Python 3.11 rmtree removes directory links/junctions themselves,
            # without descending into the linked directory.
            shutil.rmtree(path)
            return True
        except OSError as exc:
            error = exc
    _warning(f'Could not remove temporary cache {path}: {error}. It will be retried on the next launch.')
    return False


def _unregister(registry, name):
    # The data directory is already gone. Never unlink a lease for live data.
    for suffix in ('.json', '.lock'):
        try:
            (registry / (name + suffix)).unlink(missing_ok=True)
        except OSError:
            pass


@dataclass
class CleanupResult:
    removed: int = 0
    active: int = 0
    failed: list[Path] = field(default_factory=list)


def cleanup_abandoned(cache_root):
    """Only delete registered caches whose exclusive lease can be acquired."""
    result = CleanupResult()
    root = Path(cache_root).resolve()
    try:
        registry = _registry(root)
        if not registry.exists():
            return result
        records = list(registry.glob('job_*.json'))
    except OSError as exc:
        _warning(f'Cannot inspect temporary caches in {root}: {exc}')
        result.failed.append(root)
        return result
    for record in records:
        name = record.stem
        if not _JOB_NAME.fullmatch(name):
            continue
        lease = None
        removed = False
        try:
            if _linked(record) or record.stat().st_size > 4096:
                continue
            marker = json.loads(record.read_text(encoding='utf-8'))
            if not isinstance(marker, dict) or marker.get('owner') != _OWNER or marker.get('directory') != name:
                continue
            lease = _Lease.acquire(registry / (name + '.lock'))
            if lease is None:
                result.active += 1
                continue
            # Metadata is outside the data tree so a partially failed deletion
            # remains recoverable on the next attempt.
            removed = _remove(root / name)
            if removed:
                result.removed += 1
            else:
                result.failed.append(root / name)
        except (OSError, ValueError) as exc:
            _warning(f'Skipping cache record {record}: {exc}')
            result.failed.append(root / name)
        finally:
            if lease is not None:
                lease.close()
            if removed:
                _unregister(registry, name)
    return result


class JobCache:
    def __init__(self, cache_root):
        self.root = Path(cache_root).resolve()
        self.path = self.root / ('job_' + uuid.uuid4().hex)
        self._lease = None

    def __enter__(self):
        self._registry = _registry(self.root, create=True)
        self._lease = _Lease.acquire(self._registry / (self.path.name + '.lock'))
        if self._lease is None:
            raise OSError(f'Cache lease already in use: {self.path}')
        created = registered = False
        try:
            self.path.mkdir()
            created = True
            record = self._registry / (self.path.name + '.json')
            with record.open('x', encoding='utf-8') as stream:
                registered = True
                json.dump({'owner': _OWNER, 'directory': self.path.name}, stream)
        except BaseException:
            try:
                if created:
                    self.path.rmdir()  # No processing files exist before registration.
            finally:
                self._lease.close()
                if registered:
                    _unregister(self._registry, self.path.name)
            raise
        self._token = _CURRENT.set(self)
        return self

    def popen(self, *args, **kwargs):
        return self._lease.popen(*args, **kwargs)

    def __exit__(self, *exc):
        _CURRENT.reset(self._token)
        removed = False
        # Reacquire ownership for deletion. Child handles are authoritative,
        # including a child spawned just before an interrupt, before Popen
        # returned to its caller. A Python process list cannot close that race.
        self._lease.close()
        cleanup_lease = None
        try:
            with Progress('Cleaning temporary cache', unit=None):
                cleanup_lease = _Lease.acquire(self._registry / (self.path.name + '.lock'))
                if cleanup_lease is None:
                    _warning(f'Temporary cache {self.path} is still in use; keeping it until its processing child exits.')
                else:
                    removed = _remove(self.path)
        except OSError as error:
            _warning(f'Could not acquire cleanup ownership for {self.path}: {error}. Retaining the cache for a later launch.')
        finally:
            if cleanup_lease is not None:
                cleanup_lease.close()
            if removed:
                _unregister(self._registry, self.path.name)


def cache_popen(*args, **kwargs):
    cache = _CURRENT.get()
    return cache.popen(*args, **kwargs) if cache is not None else subprocess.Popen(*args, **kwargs)
