"""Read-only repository inspection backend for H Phase 1.

No subprocess. No git write libraries. No package managers. No network.
Phase 1 production path is expected to inject :class:`FakeReadOnlyBackend`
in tests; a thin pathlib backend may be used later but still must not shell out.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import Dict, List, Optional, Sequence, Tuple, Union

# files may hold str or raw bytes (binary / malformed UTF-8 fixtures)
FakeFileData = Union[str, bytes]


class AccessDenied(Exception):
    """Raised when a path is outside allowlist or matches a blocked pattern."""


# Hard limits (Phase 1)
MAX_FILES_LISTED = 80
MAX_FILES_READ = 12
MAX_BYTES_PER_FILE = 24_000
MAX_TOTAL_BYTES = 96_000
MAX_INSPECT_SECONDS = 5.0  # advisory for callers / fake clocks

ALLOWED_ROOT_PREFIXES = (
    "src/",
    "tests/",
    "docs/",
    "README.md",
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "requirements.txt",
    "requirements/",
    "Makefile",
    ".github/workflows/",
)

BLOCKED_PATH_FRAGMENTS = (
    ".env",
    "secrets",
    "credential",
    "owner_profile",
    ".config/jarvis",
    ".local/share/jarvis",
    "jarvis.db",
    ".db-wal",
    ".db-shm",
    "backups/",
    "/backups",
    "cora-integration",
    "security-center",
    "id_rsa",
    "id_ed25519",
    ".pem",
    "api_key",
    "token.json",
)

# Never traverse into these directory names
BLOCKED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".cursor",
    "backups",
}


def _norm_rel(path: str) -> str:
    p = (path or "").replace("\\", "/").lstrip("/")
    # Collapse .. attempts
    parts: List[str] = []
    for part in PurePosixPath(p).parts:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def is_path_allowed(rel_path: str) -> bool:
    rel = _norm_rel(rel_path)
    if not rel:
        return False
    low = rel.lower()
    for frag in BLOCKED_PATH_FRAGMENTS:
        if frag.lower() in low:
            return False
    name = PurePosixPath(rel).name.lower()
    if name in BLOCKED_DIR_NAMES or name.endswith(".db"):
        return False
    # Allow exact top-level docs / project files or under allowed prefixes
    for prefix in ALLOWED_ROOT_PREFIXES:
        if prefix.endswith("/"):
            if rel == prefix[:-1] or rel.startswith(prefix):
                return True
        elif rel == prefix or rel.startswith(prefix + "/"):
            return True
    return False


@dataclass
class RepoSnapshot:
    root: str
    branch: str
    head_sha: str
    working_tree_clean: bool
    status_summary: str = ""
    recent_log: Tuple[str, ...] = ()


class ReadOnlyRepoBackend(ABC):
    """Abstract Phase-1 inspection surface — intentionally has no write APIs."""

    # Explicitly absent (documented for reviewers / static checks):
    #   write_file, run_command, commit, push, create_pr, install_package

    @abstractmethod
    def snapshot(self) -> RepoSnapshot:
        ...

    @abstractmethod
    def list_files(self, *, limit: int = MAX_FILES_LISTED) -> List[str]:
        ...

    @abstractmethod
    def read_text(self, rel_path: str, *, max_bytes: int = MAX_BYTES_PER_FILE) -> str:
        ...

    def find_candidates(
        self,
        *,
        objective: str,
        component: str,
        limit: int = MAX_FILES_READ,
    ) -> List[Tuple[str, str]]:
        """Return (rel_path, reason) pairs scored by simple keyword overlap."""
        tokens = _tokens(f"{objective} {component}")
        files = self.list_files(limit=MAX_FILES_LISTED)
        scored: List[Tuple[int, str, str]] = []
        for f in files:
            if not is_path_allowed(f):
                continue
            score = 0
            low = f.lower()
            reasons = []
            for t in tokens:
                if len(t) < 3:
                    continue
                if t in low:
                    score += 3
                    reasons.append(f"path~{t}")
            # Prefer src/ and tests/
            if low.startswith("src/"):
                score += 1
            if low.startswith("tests/") or "/test_" in low:
                score += 1
                reasons.append("test-path")
            if score > 0:
                scored.append((score, f, ", ".join(reasons) or "keyword"))
        scored.sort(key=lambda x: (-x[0], x[1]))
        out: List[Tuple[str, str]] = []
        for _, path, reason in scored[:limit]:
            out.append((path, reason))
        return out

    def state_hash(self) -> str:
        snap = self.snapshot()
        blob = f"{snap.root}|{snap.branch}|{snap.head_sha}|{snap.working_tree_clean}"
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


_WORD = re.compile(r"[a-zA-Z0-9_ăâîșțÁÂÎȘȚ-]{3,}", re.UNICODE)


def _tokens(text: str) -> List[str]:
    return [m.group(0).lower() for m in _WORD.finditer(text or "")]


@dataclass
class FakeReadOnlyBackend(ReadOnlyRepoBackend):
    """In-memory fixture backend for unit tests — zero filesystem / shell."""

    root: str
    branch: str
    head_sha: str
    working_tree_clean: bool = True
    files: Dict[str, FakeFileData] = field(default_factory=dict)
    recent_log: Tuple[str, ...] = ()
    status_summary: str = "clean"
    read_log: List[str] = field(default_factory=list)
    list_calls: int = 0
    deny_outside: bool = True

    def snapshot(self) -> RepoSnapshot:
        return RepoSnapshot(
            root=self.root,
            branch=self.branch,
            head_sha=self.head_sha,
            working_tree_clean=self.working_tree_clean,
            status_summary=self.status_summary,
            recent_log=self.recent_log,
        )

    def list_files(self, *, limit: int = MAX_FILES_LISTED) -> List[str]:
        self.list_calls += 1
        allowed = [p for p in sorted(self.files) if is_path_allowed(p)]
        return allowed[:limit]

    def read_text(self, rel_path: str, *, max_bytes: int = MAX_BYTES_PER_FILE) -> str:
        rel = _norm_rel(rel_path)
        self.read_log.append(rel)
        # Absolute / drive / UNC / junction-style escapes
        raw = rel_path or ""
        if (
            self.deny_outside
            and (
                raw.startswith("/")
                or raw.startswith("\\")
                or re.match(r"^[A-Za-z]:[\\/]", raw)
                or raw.startswith("\\\\")
                or "\\..\\" in raw.replace("/", "\\")
                or "/../" in raw.replace("\\", "/")
            )
        ):
            raise AccessDenied("outside repository")
        if not is_path_allowed(rel):
            raise AccessDenied(f"blocked path: {rel}")
        if rel not in self.files:
            raise AccessDenied(f"missing or denied: {rel}")
        data = self.files[rel]
        if isinstance(data, (bytes, bytearray)):
            if b"\x00" in bytes(data[:4096]):
                raise AccessDenied(f"binary file blocked: {rel}")
            try:
                text = bytes(data).decode("utf-8")
            except UnicodeDecodeError:
                text = bytes(data).decode("utf-8", errors="replace")
        else:
            text = str(data)
            if "\x00" in text[:4096]:
                raise AccessDenied(f"binary file blocked: {rel}")
        return text[:max_bytes]


def assert_no_write_surface(cls: type) -> List[str]:
    """Return forbidden method names if present on a backend class."""
    forbidden = (
        "write_file",
        "write_text",
        "run_command",
        "run",
        "commit",
        "push",
        "create_pr",
        "open_pr",
        "install_package",
        "pip_install",
        "apply_patch",
        "checkout",
        "reset",
    )
    return [n for n in forbidden if hasattr(cls, n) and callable(getattr(cls, n))]
