"""Path helpers for Brain Memory v2 local JSON stores."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

_PathLike = Union[str, Path]

# Allowed leaf filenames under the brain_v2 root.
ALLOWED_STORE_FILES = frozenset({"preferences.json", "projects.json"})


def default_config_dir() -> Path:
    """Mirror ``config.default_config_path().parent`` without importing Settings."""
    env = os.environ.get("JARVIS_CONFIG_PATH")
    if env:
        return Path(env).expanduser().resolve().parent
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg).expanduser().resolve() / "jarvis"
    return Path.home() / ".config" / "jarvis"


def default_brain_v2_root() -> Path:
    """``~/.config/jarvis/memory/brain_v2`` (or under JARVIS_CONFIG_PATH parent)."""
    return default_config_dir() / "memory" / "brain_v2"


def resolve_brain_v2_root(root_dir: Optional[_PathLike] = None) -> Path:
    if root_dir is None:
        return default_brain_v2_root()
    return Path(root_dir).expanduser().resolve()


def safe_store_path(root: Path, filename: str) -> Path:
    """Join ``root/filename`` rejecting traversal and unexpected names."""
    name = Path(filename).name  # strip any directory components
    if name != filename or name not in ALLOWED_STORE_FILES:
        raise ValueError(f"unsafe store filename: {filename!r}")
    root_res = root.resolve()
    target = (root_res / name).resolve()
    try:
        target.relative_to(root_res)
    except ValueError as exc:
        raise ValueError("path escapes brain_v2 root") from exc
    return target


def safe_backups_dir(root: Path) -> Path:
    root_res = root.resolve()
    bak = (root_res / "backups").resolve()
    try:
        bak.relative_to(root_res)
    except ValueError as exc:
        raise ValueError("backups path escapes brain_v2 root") from exc
    return bak
