"""Cross-process exclusive writer lock for Brain Memory v2 stores.

Uses an OS advisory lock on a sibling ``*.lock`` file so a crashed process
releases the lock automatically (no stale-PID surgery required).

Same-process re-open shares one underlying OS lock via a refcounted registry
so restart/reload inside one interpreter still works; a second OS process is
refused.
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

_PathLike = Union[str, Path]

_registry_guard = threading.RLock()
# resolved lock path -> (ExclusiveFileLock, refcount)
_REGISTRY: Dict[str, Tuple["ExclusiveFileLock", int]] = {}


class LockTimeoutError(TimeoutError):
    """Could not acquire the exclusive writer lock within the timeout."""


class ExclusiveFileLock:
    """Exclusive writer lock held for the lifetime of the store."""

    def __init__(self, path: _PathLike) -> None:
        self.path = Path(path)
        self._key = str(self.path.resolve()) if self.path.parent.exists() else str(self.path)
        self._fh = None
        self._held = False
        self._shared = False

    @property
    def held(self) -> bool:
        return bool(self._held)

    def acquire(self, *, timeout: float = 2.0, poll: float = 0.05) -> None:
        if self._held:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._key = str(self.path.resolve())
        with _registry_guard:
            existing = _REGISTRY.get(self._key)
            if existing is not None:
                lock, count = existing
                _REGISTRY[self._key] = (lock, count + 1)
                # Alias the shared OS handle.
                self._fh = lock._fh
                self._held = True
                self._shared = True
                return

        deadline = time.monotonic() + max(0.0, float(timeout))
        last_exc: Optional[BaseException] = None
        while True:
            try:
                fh = open(self.path, "a+b")  # noqa: SIM115 - kept open while held
                self._try_lock(fh)
                self._fh = fh
                self._held = True
                self._shared = False
                with _registry_guard:
                    # Another thread may have registered meanwhile.
                    existing = _REGISTRY.get(self._key)
                    if existing is not None:
                        self._unlock(fh)
                        fh.close()
                        lock, count = existing
                        _REGISTRY[self._key] = (lock, count + 1)
                        self._fh = lock._fh
                        self._shared = True
                        return
                    _REGISTRY[self._key] = (self, 1)
                return
            except OSError as exc:
                last_exc = exc
                try:
                    fh.close()  # type: ignore[name-defined]
                except Exception:
                    pass
                if time.monotonic() >= deadline:
                    break
                time.sleep(poll)
        raise LockTimeoutError(
            f"brain_v2 lock busy path={self.path.name} err={type(last_exc).__name__ if last_exc else 'timeout'}"
        )

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        with _registry_guard:
            existing = _REGISTRY.get(self._key)
            if existing is not None:
                lock, count = existing
                if count > 1:
                    _REGISTRY[self._key] = (lock, count - 1)
                    self._fh = None
                    return
                _REGISTRY.pop(self._key, None)
                owner = lock
            else:
                owner = self
        fh = owner._fh
        owner._fh = None
        self._fh = None
        if fh is None:
            return
        try:
            self._unlock(fh)
        except Exception:
            pass
        try:
            fh.close()
        except Exception:
            pass

    def __enter__(self) -> "ExclusiveFileLock":
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()

    @staticmethod
    def _try_lock(fh) -> None:
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)
            if fh.read(1) == b"":
                fh.write(b"\0")
                fh.flush()
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock(fh) -> None:
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
