"""Brain V3 runtime config (separate from live jarvis Settings)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .limits import BrainV3Limits

SCHEMA_VERSION = 1


@dataclass
class BrainV3Config:
    enabled: bool = False
    root_dir: Optional[Path] = None
    limits: BrainV3Limits = field(default_factory=BrainV3Limits)
    read_only: bool = False

    @property
    def db_path(self) -> Optional[Path]:
        if self.root_dir is None:
            return None
        return Path(self.root_dir) / "brain_v3.db"
