"""Dedicated Brain Memory v2 JSON persistence (separate from StateStore / Owner Profile).

Safety:
  * atomic write via ``jarvis.utils.atomic_write`` (already on clean brain base)
  * process-local RLock + cross-process exclusive file lock
  * timestamped copies under ``backups/`` before overwrite (bounded retention)
  * corrupt-file recovery (valid ``.bak`` then newest valid backup, else empty)
  * heal primary after recovery; never backup known-corrupt primaries
  * RAM not committed when persist fails
  * schema version gate via :mod:`migration`
  * document item/byte caps
  * no pickle; secrets scrubbed from log messages only (values on disk untouched)
  * ``writable=False`` -> zero disk I/O (in-memory document only)
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from ...utils.atomic_write import atomic_write_text
from ...utils.redact import scrub_secrets
from .file_lock import ExclusiveFileLock, LockTimeoutError
from .migration import SchemaUnsupportedError, migrate_document

_PathLike = Union[str, Path]

logger = logging.getLogger(__name__)

# Keep a bounded trail of timestamped backups (plus sibling .bak from atomic_write).
DEFAULT_MAX_BACKUPS = 10
MAX_ITEMS = 2_000
MAX_DOCUMENT_BYTES = 2_000_000
_LOCK_TIMEOUT_SEC = 2.0


def _log_safe(msg: str, *args: Any) -> None:
    try:
        text = msg % args if args else msg
    except Exception:
        text = msg
    logger.warning("%s", scrub_secrets(str(text)))


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class BrainV2JsonStore:
    """Load/save one JSON document under a brain_v2 root."""

    def __init__(
        self,
        path: _PathLike,
        *,
        empty_factory: Callable[[], Dict[str, Any]],
        backups_dir: Optional[_PathLike] = None,
        writable: bool = True,
        max_backups: int = DEFAULT_MAX_BACKUPS,
        max_items: int = MAX_ITEMS,
        max_document_bytes: int = MAX_DOCUMENT_BYTES,
        lock_timeout: float = _LOCK_TIMEOUT_SEC,
    ) -> None:
        self.path = Path(path)
        self._empty_factory = empty_factory
        self.backups_dir = Path(backups_dir) if backups_dir is not None else self.path.parent / "backups"
        self.writable = bool(writable)
        self.max_backups = max(1, int(max_backups))
        self.max_items = max(1, int(max_items))
        self.max_document_bytes = max(256, int(max_document_bytes))
        self._lock = threading.RLock()
        self._doc: Dict[str, Any] = empty_factory()
        self.last_error: Optional[str] = None
        self._file_lock: Optional[ExclusiveFileLock] = None
        self._healed_primary = False
        if self.writable:
            if not self._acquire_writer_lock(lock_timeout):
                self.writable = False
                self._doc = empty_factory()
                return
            self._doc = self._load_from_disk()

    def close(self) -> None:
        with self._lock:
            if self._file_lock is not None:
                try:
                    self._file_lock.release()
                except Exception:
                    pass
                self._file_lock = None

    def __del__(self) -> None:  # noqa: D105 - best-effort unlock
        try:
            self.close()
        except Exception:
            pass

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._doc, ensure_ascii=False, sort_keys=True))

    def replace(self, document: Dict[str, Any]) -> bool:
        """Replace in-memory document and persist when writable."""
        if not isinstance(document, dict):
            self.last_error = "document_not_dict"
            return False
        with self._lock:
            err = self._validate_document(document)
            if err:
                self.last_error = err
                return False
            previous = self._doc
            self._doc = document
            if self._persist_unlocked(backup=not self._healed_primary):
                self._healed_primary = False
                return True
            self._doc = previous
            return False

    def mutate(self, mutator: Callable[[Dict[str, Any]], None]) -> bool:
        """Apply ``mutator`` to a copy, then persist; RAM rolls back on failure."""
        with self._lock:
            working = json.loads(json.dumps(self._doc, ensure_ascii=False, sort_keys=True))
            try:
                mutator(working)
            except Exception as exc:  # noqa: BLE001 - fail-safe
                self.last_error = scrub_secrets(f"mutate:{type(exc).__name__}:{exc}")
                _log_safe("brain_v2 mutate failed: %s", self.last_error)
                return False
            err = self._validate_document(working)
            if err:
                self.last_error = err
                return False
            previous = self._doc
            self._doc = working
            if self._persist_unlocked(backup=True):
                return True
            self._doc = previous
            return False

    def reload(self) -> Dict[str, Any]:
        with self._lock:
            if not self.writable:
                return self.snapshot()
            self._doc = self._load_from_disk()
            return self.snapshot()

    def _acquire_writer_lock(self, timeout: float) -> bool:
        lock_path = self.path.with_name(self.path.name + ".lock")
        try:
            fl = ExclusiveFileLock(lock_path)
            fl.acquire(timeout=timeout)
            self._file_lock = fl
            return True
        except LockTimeoutError as exc:
            self.last_error = scrub_secrets(f"lock:{exc}")
            _log_safe("brain_v2 writer lock failed: %s", self.last_error)
            return False
        except Exception as exc:  # noqa: BLE001
            self.last_error = scrub_secrets(f"lock:{type(exc).__name__}")
            _log_safe("brain_v2 writer lock failed: %s", self.last_error)
            return False

    def _validate_document(self, document: Dict[str, Any]) -> Optional[str]:
        items = document.get("items")
        if not isinstance(items, dict):
            return "document_items_not_dict"
        if len(items) > self.max_items:
            return f"limit:max_items:{len(items)}>{self.max_items}"
        try:
            blob = json.dumps(document, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            return f"document_not_json:{type(exc).__name__}"
        size = len(blob.encode("utf-8"))
        if size > self.max_document_bytes:
            return f"limit:max_bytes:{size}>{self.max_document_bytes}"
        return None

    def _persist_unlocked(self, *, backup: bool) -> bool:
        if not self.writable:
            self.last_error = None
            return True
        try:
            if backup:
                self._backup_current_if_valid()
            text = json.dumps(self._doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            atomic_write_text(self.path, text, backup=True)
            self.last_error = None
            return True
        except Exception as exc:  # noqa: BLE001 - never crash callers
            self.last_error = scrub_secrets(f"persist:{type(exc).__name__}")
            _log_safe("brain_v2 persist failed path=%s err=%s", self.path.name, self.last_error)
            return False

    def _backup_current_if_valid(self) -> None:
        if not self.path.exists():
            return
        try:
            data = self.path.read_bytes()
        except OSError:
            return
        if not self._bytes_are_valid_document(data):
            _log_safe("brain_v2 backup skipped: primary invalid path=%s", self.path.name)
            return
        try:
            self.backups_dir.mkdir(parents=True, exist_ok=True)
            stamp = _stamp()
            dest = self.backups_dir / f"{self.path.stem}-{stamp}{self.path.suffix}"
            dest.resolve().relative_to(self.backups_dir.resolve())
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(dest)
            self._prune_backups()
        except Exception as exc:  # noqa: BLE001 - backup is best-effort
            _log_safe("brain_v2 backup skipped: %s", type(exc).__name__)

    @staticmethod
    def _bytes_are_valid_document(data: bytes) -> bool:
        try:
            raw = json.loads(data.decode("utf-8"))
            if not isinstance(raw, dict):
                return False
            migrate_document(raw)
            return True
        except Exception:
            return False

    def _prune_backups(self) -> None:
        try:
            patterned = sorted(
                self.backups_dir.glob(f"{self.path.stem}-*{self.path.suffix}"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            return
        for stale in patterned[self.max_backups :]:
            try:
                stale.unlink()
            except OSError:
                pass

    def _load_from_disk(self) -> Dict[str, Any]:
        # Order: primary, sibling .bak, then newest timestamped backups.
        # Invalid JSON / unsupported schema is skipped (never promoted).
        candidates = [self.path, self.path.with_name(self.path.name + ".bak")]
        try:
            if self.backups_dir.exists():
                patterned = sorted(
                    self.backups_dir.glob(f"{self.path.stem}-*{self.path.suffix}"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                candidates.extend(patterned)
        except OSError:
            pass

        unsupported_seen = False
        for cand in candidates:
            doc, unsupported = self._try_read(cand)
            if unsupported:
                unsupported_seen = True
                continue
            if doc is not None:
                if cand != self.path:
                    _log_safe("brain_v2 recovered %s from %s", self.path.name, cand.name)
                    self._heal_primary_unlocked(doc)
                return doc
        if unsupported_seen:
            self.last_error = "schema:unsupported"
        return self._empty_factory()

    def _heal_primary_unlocked(self, doc: Dict[str, Any]) -> None:
        """Rewrite primary from a recovered valid doc without backing up corrupt bytes."""
        if not self.writable:
            return
        try:
            text = json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            atomic_write_text(self.path, text, backup=False)
            self._healed_primary = True
            self.last_error = None
        except Exception as exc:  # noqa: BLE001
            _log_safe("brain_v2 heal skipped: %s", type(exc).__name__)

    def _try_read(self, path: Path) -> tuple[Optional[Dict[str, Any]], bool]:
        """Return ``(doc_or_none, unsupported_schema)``."""
        try:
            if not path.exists() or not path.is_file():
                return None, False
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None, False
            if "items" not in raw or not isinstance(raw.get("items"), dict):
                raw = dict(raw)
                raw.setdefault("items", {})
                if not isinstance(raw["items"], dict):
                    return None, False
            try:
                doc, _status = migrate_document(raw)
            except SchemaUnsupportedError:
                _log_safe("brain_v2 refusing unsupported schema path=%s", path.name)
                return None, True
            return doc, False
        except Exception:  # noqa: BLE001 - corrupt -> try next
            return None, False
