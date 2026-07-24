"""Dedicated Brain Memory v2 JSON persistence (separate from StateStore / Owner Profile).

Safety:
  * atomic write via ``jarvis.utils.atomic_write`` (already on clean brain base)
  * process-local RLock
  * timestamped copies under ``backups/`` before overwrite (bounded retention)
  * corrupt-file recovery (valid ``.bak`` then newest valid backup, else empty)
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

_PathLike = Union[str, Path]

logger = logging.getLogger(__name__)

# Keep a bounded trail of timestamped backups (plus sibling .bak from atomic_write).
DEFAULT_MAX_BACKUPS = 10


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
    ) -> None:
        self.path = Path(path)
        self._empty_factory = empty_factory
        self.backups_dir = Path(backups_dir) if backups_dir is not None else self.path.parent / "backups"
        self.writable = bool(writable)
        self.max_backups = max(1, int(max_backups))
        self._lock = threading.RLock()
        self._doc: Dict[str, Any] = empty_factory()
        self.last_error: Optional[str] = None
        if self.writable:
            self._doc = self._load_from_disk()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._doc, ensure_ascii=False, sort_keys=True))

    def replace(self, document: Dict[str, Any]) -> bool:
        """Replace in-memory document and persist when writable."""
        if not isinstance(document, dict):
            self.last_error = "document_not_dict"
            return False
        with self._lock:
            self._doc = document
            return self._persist_unlocked()

    def mutate(self, mutator: Callable[[Dict[str, Any]], None]) -> bool:
        """Apply ``mutator`` to a copy, then swap + persist."""
        with self._lock:
            working = json.loads(json.dumps(self._doc, ensure_ascii=False, sort_keys=True))
            try:
                mutator(working)
            except Exception as exc:  # noqa: BLE001 - fail-safe
                self.last_error = scrub_secrets(f"mutate:{type(exc).__name__}:{exc}")
                _log_safe("brain_v2 mutate failed: %s", self.last_error)
                return False
            self._doc = working
            return self._persist_unlocked()

    def reload(self) -> Dict[str, Any]:
        with self._lock:
            if not self.writable:
                return self.snapshot()
            self._doc = self._load_from_disk()
            return self.snapshot()

    def _persist_unlocked(self) -> bool:
        if not self.writable:
            self.last_error = None
            return True
        try:
            self._backup_current()
            text = json.dumps(self._doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
            atomic_write_text(self.path, text, backup=True)
            self.last_error = None
            return True
        except Exception as exc:  # noqa: BLE001 - never crash callers
            self.last_error = scrub_secrets(f"persist:{type(exc).__name__}")
            _log_safe("brain_v2 persist failed path=%s err=%s", self.path.name, self.last_error)
            return False

    def _backup_current(self) -> None:
        if not self.path.exists():
            return
        try:
            data = self.path.read_bytes()
        except OSError:
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
        # Invalid JSON is skipped (never promoted).
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

        for cand in candidates:
            doc = self._try_read(cand)
            if doc is not None:
                if cand != self.path:
                    _log_safe("brain_v2 recovered %s from %s", self.path.name, cand.name)
                return doc
        return self._empty_factory()

    def _try_read(self, path: Path) -> Optional[Dict[str, Any]]:
        try:
            if not path.exists() or not path.is_file():
                return None
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            if "items" not in raw or not isinstance(raw.get("items"), dict):
                raw = dict(raw)
                raw.setdefault("items", {})
                if not isinstance(raw["items"], dict):
                    return None
            return raw
        except Exception:  # noqa: BLE001 - corrupt -> try next
            return None
