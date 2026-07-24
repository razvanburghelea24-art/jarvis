"""Strict read-only live workspace backend (H Phase 1.5).

Filesystem: pathlib / os.stat / open(read-only).
Git metadata: direct reads of ``.git/HEAD``, refs, and a minimal index parser.
Never shells out, never writes, never creates directories, never touches the network.
"""

from __future__ import annotations

import hashlib
import os
import re
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .models import CANONICAL_BRANCH, CANONICAL_WORKSPACE_ROOT, normalize_workspace_root
from .read_only_backend import (
    MAX_BYTES_PER_FILE,
    MAX_FILES_LISTED,
    MAX_FILES_READ,
    MAX_TOTAL_BYTES,
    AccessDenied,
    ReadOnlyRepoBackend,
    RepoSnapshot,
    _norm_rel,
    _tokens,
    is_path_allowed,
)

try:
    from ..utils.redact import scrub_secrets as _scrub
except Exception:  # pragma: no cover
    def _scrub(text: str) -> str:  # type: ignore
        return text

# Resource limits (Phase 1.5)
MAX_DIR_DEPTH = 8
MAX_INSPECT_SECONDS = 5.0
TEXT_EXTENSIONS = frozenset({
    ".py", ".md", ".txt", ".toml", ".cfg", ".ini", ".yml", ".yaml",
    ".json", ".html", ".css", ".js", ".ts", ".tsx", ".rst", ".in",
    ".toml", ".lock", ".gitignore", ".gitattributes",
})
TEXT_BASENAMES = frozenset({
    "makefile", "dockerfile", "readme", "license", "authors", "changelog",
})

BLOCKED_DIR_NAMES = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".cursor",
    "backups", "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "htmlcov", ".eggs",
})


@dataclass
class FileMetadata:
    path: str
    size: int
    mtime: float
    is_symlink: bool
    is_file: bool


@dataclass
class InventoryResult:
    files: List[str]
    truncated: bool = False
    reasons: List[str] = field(default_factory=list)
    total_bytes_seen: int = 0


@dataclass
class GitSnapshotInfo:
    root: str
    branch: str
    head_sha: str
    working_tree_clean: bool
    status_reliable: bool
    status_summary: str
    detached: bool = False
    error: Optional[str] = None


class LiveReadOnlyBackend(ReadOnlyRepoBackend):
    """Pathlib-only live inspector. Construct only after owner confirmation."""

    def __init__(
        self,
        root: str,
        *,
        require_canonical: bool = False,
        max_files: int = MAX_FILES_LISTED,
        max_bytes_per_file: int = MAX_BYTES_PER_FILE,
        max_total_bytes: int = MAX_TOTAL_BYTES,
        max_depth: int = MAX_DIR_DEPTH,
        max_seconds: float = MAX_INSPECT_SECONDS,
        deadline_monotonic: Optional[float] = None,
    ) -> None:
        raw = str(root or "").strip()
        if not raw:
            raise AccessDenied("empty workspace root")
        if require_canonical:
            norm, err = normalize_workspace_root(raw)
            if err:
                raise AccessDenied(f"workspace rejected: {err}")
        else:
            # Fixture / non-canonical roots: still block known contaminated trees
            # and path traversal, but allow temporary test directories.
            try:
                norm = os.path.normpath(raw)
            except Exception as e:
                raise AccessDenied(f"invalid root: {e}") from e
            low = os.path.normcase(norm).lower()
            for marker in ("cora-integration", "security-center", "pr-551"):
                if marker in low:
                    raise AccessDenied(f"blocked checkout marker: {marker}")
            if ".." in Path(norm).parts:
                raise AccessDenied("path traversal in workspace root")
        self._root = Path(norm)
        if not self._root.is_dir():
            raise AccessDenied("workspace root is not a directory")
        try:
            self._root_resolved = self._root.resolve()
        except Exception as e:
            raise AccessDenied(f"cannot resolve workspace root: {e}") from e
        self.max_files = max_files
        self.max_bytes_per_file = max_bytes_per_file
        self.max_total_bytes = max_total_bytes
        self.max_depth = max_depth
        self.max_seconds = max_seconds
        self._deadline = deadline_monotonic
        self._truncated = False
        self._truncation_reasons: List[str] = []
        self.list_calls = 0
        self.read_log: List[str] = []
        self._inventory_cache: Optional[InventoryResult] = None
        self._git_cache: Optional[GitSnapshotInfo] = None

    # ------------------------------------------------------------------ factory

    @classmethod
    def for_canonical(cls, **kw: Any) -> "LiveReadOnlyBackend":
        return cls(CANONICAL_WORKSPACE_ROOT, require_canonical=True, **kw)

    # ------------------------------------------------------------------ limits

    def _timed_out(self) -> bool:
        if self._deadline is None:
            return False
        return time.monotonic() >= self._deadline

    def _mark_truncated(self, reason: str) -> None:
        self._truncated = True
        if reason not in self._truncation_reasons:
            self._truncation_reasons.append(reason)

    # ------------------------------------------------------------------ path safety

    def _safe_abs(self, rel_path: str) -> Path:
        rel = _norm_rel(rel_path)
        if not rel or not is_path_allowed(rel):
            raise AccessDenied(f"blocked path: {rel_path}")
        # Reject absolute / drive / unc in the raw input
        raw = rel_path or ""
        if (
            raw.startswith("/")
            or raw.startswith("\\")
            or re.match(r"^[A-Za-z]:[\\/]", raw)
            or raw.startswith("\\\\")
        ):
            raise AccessDenied("absolute path denied")
        candidate = (self._root / Path(*PureRel(rel))).resolve()
        try:
            candidate.relative_to(self._root_resolved)
        except ValueError as e:
            raise AccessDenied("path escapes workspace root") from e
        # Symlink / junction escape: every parent must stay under root
        cur = candidate
        for _ in range(64):
            if cur == self._root_resolved or cur == cur.parent:
                break
            if cur.is_symlink():
                try:
                    target = cur.resolve()
                    target.relative_to(self._root_resolved)
                except Exception as e:
                    raise AccessDenied("symlink/junction escape blocked") from e
            cur = cur.parent
        return candidate

    # ------------------------------------------------------------------ API (requested)

    def get_workspace_info(self) -> Dict[str, Any]:
        g = self.get_git_snapshot()
        return {
            "root": str(self._root_resolved),
            "branch": g.branch,
            "head_sha": g.head_sha,
            "working_tree_clean": g.working_tree_clean,
            "status_reliable": g.status_reliable,
            "detached": g.detached,
            "truncated": self._truncated,
            "truncation_reasons": list(self._truncation_reasons),
        }

    def list_candidate_files(self, *, limit: int = MAX_FILES_READ) -> List[str]:
        inv = self.build_inventory()
        return inv.files[:limit]

    def read_text_file(self, path: str, max_bytes: Optional[int] = None) -> str:
        return self.read_text(path, max_bytes=max_bytes or self.max_bytes_per_file)

    def file_metadata(self, path: str) -> FileMetadata:
        abs_path = self._safe_abs(path)
        if not abs_path.exists():
            raise AccessDenied(f"missing: {path}")
        st = abs_path.lstat()  # do not follow symlink for metadata
        return FileMetadata(
            path=_norm_rel(path),
            size=int(st.st_size),
            mtime=float(st.st_mtime),
            is_symlink=abs_path.is_symlink(),
            is_file=abs_path.is_file() and not abs_path.is_symlink(),
        )

    def compute_file_hash(self, path: str, *, max_bytes: Optional[int] = None) -> str:
        abs_path = self._safe_abs(path)
        limit = max_bytes or self.max_bytes_per_file
        h = hashlib.sha256()
        read = 0
        with abs_path.open("rb") as fh:  # read-only binary
            while read < limit:
                chunk = fh.read(min(8192, limit - read))
                if not chunk:
                    break
                if b"\x00" in chunk and read == 0:
                    raise AccessDenied(f"binary file blocked: {path}")
                h.update(chunk)
                read += len(chunk)
        return h.hexdigest()

    def get_git_snapshot(self) -> GitSnapshotInfo:
        if self._git_cache is not None:
            return self._git_cache
        info = _read_git_snapshot(self._root_resolved)
        self._git_cache = info
        return info

    def build_inventory(self) -> InventoryResult:
        if self._inventory_cache is not None:
            return self._inventory_cache
        if self._deadline is None:
            self._deadline = time.monotonic() + self.max_seconds
        files: List[str] = []
        total = 0
        truncated = False
        reasons: List[str] = []

        def walk(dir_path: Path, depth: int, rel_prefix: str) -> None:
            nonlocal truncated, total
            if self._timed_out():
                truncated = True
                reasons.append("inspect timeout")
                return
            if depth > self.max_depth:
                truncated = True
                reasons.append("directory depth limit")
                return
            try:
                entries = sorted(dir_path.iterdir(), key=lambda p: p.name.lower())
            except PermissionError:
                truncated = True
                reasons.append(f"permission denied: {rel_prefix or '.'}")
                return
            except OSError as e:
                truncated = True
                reasons.append(f"os error: {type(e).__name__}")
                return
            for entry in entries:
                if self._timed_out():
                    truncated = True
                    reasons.append("inspect timeout")
                    return
                name = entry.name
                if name in BLOCKED_DIR_NAMES or name.startswith(".env"):
                    continue
                rel = f"{rel_prefix}/{name}" if rel_prefix else name
                rel = rel.replace("\\", "/")
                try:
                    if entry.is_symlink():
                        # Only allow if resolved target stays in root; still skip dirs
                        try:
                            resolved = entry.resolve()
                            resolved.relative_to(self._root_resolved)
                        except Exception:
                            continue
                        if entry.is_dir():
                            continue  # do not traverse symlinked dirs
                    if entry.is_dir() and not entry.is_symlink():
                        if name.lower() in BLOCKED_DIR_NAMES:
                            continue
                        walk(entry, depth + 1, rel)
                        continue
                    if not entry.is_file():
                        continue
                    if not is_path_allowed(rel):
                        continue
                    if not _is_text_candidate(rel, entry):
                        continue
                    try:
                        size = entry.stat().st_size
                    except OSError:
                        continue
                    if size > self.max_bytes_per_file:
                        # listed but will be truncated on read — still count as candidate
                        pass
                    if len(files) >= self.max_files:
                        truncated = True
                        reasons.append("file count limit")
                        return
                    if total + min(size, self.max_bytes_per_file) > self.max_total_bytes:
                        truncated = True
                        reasons.append("total byte limit")
                        return
                    files.append(rel)
                    total += min(int(size), self.max_bytes_per_file)
                except OSError:
                    continue

        walk(self._root_resolved, 0, "")
        if truncated:
            for r in reasons:
                self._mark_truncated(r)
        result = InventoryResult(
            files=files,
            truncated=truncated,
            reasons=list(dict.fromkeys(reasons)),
            total_bytes_seen=total,
        )
        self._inventory_cache = result
        return result

    # ------------------------------------------------------------------ ABC

    def snapshot(self) -> RepoSnapshot:
        g = self.get_git_snapshot()
        summary = g.status_summary
        if self._truncated:
            summary = (summary + "; inventory truncated").strip("; ")
        return RepoSnapshot(
            root=str(self._root_resolved),
            branch=g.branch,
            head_sha=g.head_sha,
            working_tree_clean=g.working_tree_clean if g.status_reliable else False,
            status_summary=summary,
            recent_log=(),
            git_status_reliable=g.status_reliable,
            inventory_truncated=self._truncated,
            truncation_reasons=tuple(self._truncation_reasons),
            detached_head=g.detached,
            git_error=g.error,
        )

    def list_files(self, *, limit: int = MAX_FILES_LISTED) -> List[str]:
        self.list_calls += 1
        inv = self.build_inventory()
        return inv.files[:limit]

    def read_text(self, rel_path: str, *, max_bytes: int = MAX_BYTES_PER_FILE) -> str:
        if self._timed_out():
            self._mark_truncated("inspect timeout")
            raise AccessDenied("inspect timeout")
        rel = _norm_rel(rel_path)
        self.read_log.append(rel)
        abs_path = self._safe_abs(rel)
        if abs_path.is_symlink():
            raise AccessDenied("refusing to read through symlink file")
        if not abs_path.is_file():
            raise AccessDenied(f"not a file: {rel}")
        try:
            meta_before = abs_path.stat()
        except OSError as e:
            raise AccessDenied(f"stat failed: {e}") from e
        if meta_before.st_size > max(max_bytes * 32, 1_000_000):
            # Extremely large — refuse rather than allocate
            self._mark_truncated("oversized file")
            raise AccessDenied(f"file too large: {rel}")
        try:
            with abs_path.open("rb") as fh:
                raw = fh.read(max_bytes + 1)
        except PermissionError as e:
            raise AccessDenied(f"permission denied: {rel}") from e
        except OSError as e:
            raise AccessDenied(f"read failed: {e}") from e
        try:
            meta_after = abs_path.stat()
        except OSError:
            meta_after = meta_before
        if (
            meta_after.st_size != meta_before.st_size
            or meta_after.st_mtime != meta_before.st_mtime
        ):
            self._mark_truncated("file changed during read (race)")
        if b"\x00" in raw[:4096]:
            raise AccessDenied(f"binary file blocked: {rel}")
        if len(raw) > max_bytes:
            raw = raw[:max_bytes]
            self._mark_truncated("per-file byte limit")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
            self._mark_truncated("invalid utf-8 replaced")
        return _scrub(text)

    def find_candidates(
        self,
        *,
        objective: str,
        component: str,
        limit: int = MAX_FILES_READ,
    ) -> List[Tuple[str, str]]:
        tokens = _tokens(f"{objective} {component}")
        files = self.list_files(limit=self.max_files)
        scored: List[Tuple[int, str, str]] = []
        for f in files:
            score = 0
            low = f.lower()
            reasons: List[str] = []
            for t in tokens:
                if len(t) < 3:
                    continue
                if t in low:
                    score += 3
                    reasons.append(f"path~{t}")
            if low.startswith("src/"):
                score += 1
            if low.startswith("tests/") or "/test_" in low:
                score += 1
                reasons.append("test-path")
            if score > 0:
                scored.append((score, f, ", ".join(reasons) or "keyword"))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [(p, r) for _, p, r in scored[:limit]]

    def state_hash(self) -> str:
        snap = self.snapshot()
        blob = (
            f"{snap.root}|{snap.branch}|{snap.head_sha}|"
            f"{snap.working_tree_clean}|{snap.git_status_reliable}|"
            f"{snap.inventory_truncated}"
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def PureRel(rel: str) -> Tuple[str, ...]:
    return tuple(p for p in rel.replace("\\", "/").split("/") if p and p != ".")


def _is_text_candidate(rel: str, entry: Path) -> bool:
    name = entry.name.lower()
    if name in TEXT_BASENAMES:
        return True
    suf = entry.suffix.lower()
    if suf in TEXT_EXTENSIONS:
        return True
    # extensionless project files already gated by allowlist (Makefile etc.)
    if not suf and is_path_allowed(rel):
        return name in TEXT_BASENAMES or rel in {
            "Makefile", "README", "LICENSE", "CHANGELOG",
        }
    return False


# ------------------------------------------------------------------ git (files only)


MAX_GITDIR_FILE_BYTES = 512
_DEVICE_NAMES = frozenset({
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
})


@dataclass(frozen=True)
class GitMetadataPaths:
    """Resolved read-only locations for HEAD/index (git_dir) and refs (common_dir)."""

    workspace_root: Path
    git_dir: Path
    common_dir: Path
    is_worktree: bool
    error: Optional[str] = None


def resolve_git_metadata_paths(workspace_root: Path | str) -> GitMetadataPaths:
    """Resolve git metadata dirs for a normal repo or a linked worktree.

    Read-only. Never shells out, never follows unsafe gitdir targets, never
    creates locks. On any ambiguity returns ``error`` set and empty dirs.
    """
    try:
        root = Path(workspace_root).resolve()
    except Exception:
        return GitMetadataPaths(Path(), Path(), Path(), False, "unresolvable workspace root")

    git_entry = root / ".git"
    if not git_entry.exists():
        return GitMetadataPaths(root, Path(), Path(), False, "missing .git")

    if git_entry.is_dir():
        # Normal repository
        if git_entry.is_symlink():
            try:
                resolved = git_entry.resolve()
                resolved.relative_to(root)
            except Exception:
                return GitMetadataPaths(root, Path(), Path(), False, "symlink .git escape")
        return GitMetadataPaths(root, git_entry.resolve(), git_entry.resolve(), False, None)

    if not git_entry.is_file():
        return GitMetadataPaths(root, Path(), Path(), False, "unsupported .git type")

    # --- worktree pointer file ---
    try:
        st = git_entry.stat()
    except OSError as e:
        return GitMetadataPaths(root, Path(), Path(), True, f".git unreadable: {e}")
    if st.st_size > MAX_GITDIR_FILE_BYTES:
        return GitMetadataPaths(root, Path(), Path(), True, ".git file too large")
    try:
        raw_bytes = git_entry.read_bytes()
    except OSError as e:
        return GitMetadataPaths(root, Path(), Path(), True, f".git read failed: {e}")
    if b"\x00" in raw_bytes:
        return GitMetadataPaths(root, Path(), Path(), True, ".git contains NUL")
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw_bytes.decode("ascii")
        except UnicodeDecodeError:
            return GitMetadataPaths(root, Path(), Path(), True, ".git not utf-8/ascii")

    # Exactly one meaningful line
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) != 1:
        return GitMetadataPaths(root, Path(), Path(), True, "gitdir must be a single line")
    line = lines[0]
    if not line.lower().startswith("gitdir:"):
        return GitMetadataPaths(root, Path(), Path(), True, "missing gitdir: prefix")
    target_raw = line.split(":", 1)[1].strip()
    if not target_raw:
        return GitMetadataPaths(root, Path(), Path(), True, "empty gitdir path")

    err = _validate_gitdir_path_syntax(target_raw)
    if err:
        return GitMetadataPaths(root, Path(), Path(), True, err)

    # Resolve relative to workspace root (location of the .git file)
    try:
        candidate = Path(target_raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        git_dir = candidate.resolve()
    except Exception as e:
        return GitMetadataPaths(root, Path(), Path(), True, f"gitdir resolve failed: {e}")

    if not git_dir.is_dir():
        return GitMetadataPaths(root, Path(), Path(), True, "gitdir target not a directory")

    if not _is_under_git_worktrees(git_dir):
        return GitMetadataPaths(
            root, Path(), Path(), True, "gitdir not under .git/worktrees/"
        )

    # commondir → main repository .git
    common, cerr = _resolve_commondir(git_dir)
    if cerr or common is None:
        return GitMetadataPaths(root, Path(), Path(), True, cerr or "commondir failed")

    # worktree dir must live under common/worktrees/
    try:
        git_dir.relative_to((common / "worktrees").resolve())
    except Exception:
        return GitMetadataPaths(
            root, Path(), Path(), True, "worktree not under common/worktrees"
        )

    return GitMetadataPaths(root, git_dir, common, True, None)


def _validate_gitdir_path_syntax(path: str) -> Optional[str]:
    p = path.strip()
    if not p:
        return "empty path"
    if "\x00" in p:
        return "NUL in path"
    # No env / shell / URL
    if any(ch in p for ch in ("$", "`", "|", ";", "&", "<", ">", "\n", "\r")):
        return "forbidden character in gitdir path"
    if "%" in p:
        return "env-style % in gitdir path"
    low = p.replace("\\", "/").lower()
    if "://" in low:
        return "URL gitdir rejected"
    if low.startswith("//") or p.startswith("\\\\"):
        return "UNC/network path rejected"
    if low.startswith("//?/") or p.startswith("\\\\?\\"):
        return "device/extended path rejected"
    # Windows device names as a path component
    for part in re.split(r"[\\/]", p):
        base = part.split(".")[0].lower()
        if base in _DEVICE_NAMES:
            return "device path rejected"
    return None


def _is_under_git_worktrees(path: Path) -> bool:
    parts = [x.lower() for x in path.parts]
    for i in range(len(parts) - 2):
        if parts[i] == ".git" and parts[i + 1] == "worktrees":
            # must have a worktree name component
            if i + 2 < len(parts) and parts[i + 2]:
                return True
    return False


def _resolve_commondir(git_dir: Path) -> Tuple[Optional[Path], Optional[str]]:
    """Read worktree ``commondir`` and resolve to the main Git directory."""
    cfile = git_dir / "commondir"
    if not cfile.is_file():
        return None, "commondir missing"
    try:
        if cfile.stat().st_size > MAX_GITDIR_FILE_BYTES:
            return None, "commondir too large"
        raw = cfile.read_bytes()
    except OSError as e:
        return None, f"commondir unreadable: {e}"
    if b"\x00" in raw:
        return None, "commondir contains NUL"
    try:
        text = raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None, "commondir not utf-8"
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) != 1:
        return None, "commondir must be a single line"
    target = lines[0]
    err = _validate_gitdir_path_syntax(target)
    if err:
        return None, f"commondir {err}"
    try:
        cand = Path(target)
        if not cand.is_absolute():
            cand = git_dir / cand
        common = cand.resolve()
    except Exception as e:
        return None, f"commondir resolve failed: {e}"
    if not common.is_dir():
        return None, "commondir not a directory"
    # Must look like a Git common dir (has refs/ or HEAD or objects/)
    if not (
        (common / "HEAD").exists()
        or (common / "refs").is_dir()
        or (common / "objects").is_dir()
    ):
        return None, "commondir is not a git directory"
    # Prevent escape: common must be an ancestor of git_dir via .../.git/worktrees/
    try:
        git_dir.resolve().relative_to((common / "worktrees").resolve())
    except Exception:
        return None, "commondir escape blocked"
    return common, None


def _read_git_snapshot(root: Path) -> GitSnapshotInfo:
    meta = resolve_git_metadata_paths(root)
    if meta.error or not meta.git_dir or not meta.common_dir:
        return GitSnapshotInfo(
            root=str(root),
            branch="",
            head_sha="",
            working_tree_clean=False,
            status_reliable=False,
            status_summary=meta.error or "git metadata unresolved",
            error=meta.error or "git metadata unresolved",
        )

    git_dir = meta.git_dir
    common_dir = meta.common_dir

    head_path = git_dir / "HEAD"
    try:
        head_raw = head_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError as e:
        return GitSnapshotInfo(
            root=str(root),
            branch="",
            head_sha="",
            working_tree_clean=False,
            status_reliable=False,
            status_summary="HEAD unreadable",
            error=str(e),
        )

    detached = False
    branch = ""
    head_sha = ""
    if head_raw.startswith("ref:"):
        ref = head_raw.split(":", 1)[1].strip()
        if ref.startswith("refs/heads/"):
            branch = ref[len("refs/heads/") :]
        else:
            branch = ref
            detached = True
        # Refs live in the common directory for worktrees
        ref_file = common_dir / ref
        try:
            resolved_ref = ref_file.resolve()
            resolved_ref.relative_to(common_dir.resolve())
        except Exception:
            return GitSnapshotInfo(
                root=str(root),
                branch=branch or "UNKNOWN",
                head_sha="",
                working_tree_clean=False,
                status_reliable=False,
                status_summary="ref path escape blocked",
                detached=detached,
                error="ref path escape",
            )
        try:
            if ref_file.is_file():
                head_sha = ref_file.read_text(encoding="utf-8", errors="replace").strip()
            else:
                head_sha = _lookup_packed_ref(common_dir, ref) or ""
        except OSError as e:
            return GitSnapshotInfo(
                root=str(root),
                branch=branch,
                head_sha="",
                working_tree_clean=False,
                status_reliable=False,
                status_summary="ref unreadable",
                detached=detached,
                error=str(e),
            )
    elif re.fullmatch(r"[0-9a-fA-F]{40}", head_raw):
        detached = True
        branch = "HEAD"
        head_sha = head_raw.lower()
    else:
        return GitSnapshotInfo(
            root=str(root),
            branch="",
            head_sha="",
            working_tree_clean=False,
            status_reliable=False,
            status_summary="corrupt HEAD",
            error="corrupt HEAD",
        )

    if not head_sha or not re.fullmatch(r"[0-9a-fA-F]{40}", head_sha):
        return GitSnapshotInfo(
            root=str(root),
            branch=branch or "UNKNOWN",
            head_sha=head_sha or "",
            working_tree_clean=False,
            status_reliable=False,
            status_summary="invalid HEAD sha",
            detached=detached,
            error="invalid HEAD sha",
        )

    head_sha = head_sha.lower()
    # Dirty detection uses the *worktree* index (git_dir), never the main repo index
    clean, reliable, summary = _assess_worktree_clean(root, git_dir)
    return GitSnapshotInfo(
        root=str(root),
        branch=branch,
        head_sha=head_sha,
        working_tree_clean=clean if reliable else False,
        status_reliable=reliable,
        status_summary=summary,
        detached=detached,
    )


def _lookup_packed_ref(git_dir: Path, ref: str) -> Optional[str]:
    packed = git_dir / "packed-refs"
    if not packed.is_file():
        return None
    try:
        text = packed.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if not line or line.startswith("#") or line.startswith("^"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] == ref:
            sha = parts[0].strip()
            if re.fullmatch(r"[0-9a-fA-F]{40}", sha):
                return sha.lower()
    return None


def _assess_worktree_clean(root: Path, git_dir: Path) -> Tuple[bool, bool, str]:
    """Return (clean, reliable, summary) without shell.

    Uses a minimal git-index reader. If the index cannot be parsed safely,
    returns reliable=False (caller must not pretend the tree is clean).
    """
    # Refuse if index.lock exists — another git process may be mutating
    if (git_dir / "index.lock").exists():
        return False, False, "index.lock present — status unreliable"
    index_path = git_dir / "index"
    if not index_path.is_file():
        return False, False, "missing index — status unreliable"
    try:
        entries = _parse_git_index_paths(index_path)
    except Exception as e:
        return False, False, f"index parse failed: {type(e).__name__}"

    # Check allowlisted tracked paths for size/mtime drift vs index
    dirty_reasons: List[str] = []
    checked = 0
    for path, size, mtime_s in entries:
        rel = path.replace("\\", "/")
        if not is_path_allowed(rel):
            continue
        checked += 1
        if checked > MAX_FILES_LISTED:
            break
        fp = root / Path(*PureRel(rel))
        try:
            if not fp.exists():
                dirty_reasons.append(f"missing:{rel}")
                break
            if fp.is_symlink():
                continue
            st = fp.stat()
            if int(st.st_size) != int(size):
                dirty_reasons.append(f"size:{rel}")
                break
            # mtime compare (integer seconds as stored in index)
            if int(st.st_mtime) != int(mtime_s):
                # size match but mtime differs — treat as potentially dirty
                dirty_reasons.append(f"mtime:{rel}")
                break
        except OSError:
            dirty_reasons.append(f"stat:{rel}")
            break

    # Untracked allowlisted files (present on disk, not in index)
    indexed: Set[str] = {p.replace("\\", "/") for p, _, _ in entries}
    try:
        for rel in _quick_list_allowlisted(root, limit=MAX_FILES_LISTED):
            if rel not in indexed and is_path_allowed(rel):
                dirty_reasons.append(f"untracked:{rel}")
                break
    except OSError:
        return False, False, "worktree scan failed"

    if dirty_reasons:
        return False, True, "dirty: " + dirty_reasons[0]
    return True, True, "clean"


def _quick_list_allowlisted(root: Path, *, limit: int) -> List[str]:
    out: List[str] = []

    def walk(d: Path, depth: int, prefix: str) -> None:
        if len(out) >= limit or depth > MAX_DIR_DEPTH:
            return
        try:
            for entry in d.iterdir():
                if len(out) >= limit:
                    return
                name = entry.name
                if name in BLOCKED_DIR_NAMES or name.startswith(".env"):
                    continue
                rel = f"{prefix}/{name}" if prefix else name
                rel = rel.replace("\\", "/")
                if entry.is_dir() and not entry.is_symlink():
                    walk(entry, depth + 1, rel)
                elif entry.is_file() and not entry.is_symlink() and is_path_allowed(rel):
                    out.append(rel)
        except OSError:
            return

    walk(root, 0, "")
    return out


def _parse_git_index_paths(index_path: Path) -> List[Tuple[str, int, int]]:
    """Parse git index v2/v3 enough to get (path, size, mtime_seconds). Read-only."""
    data = index_path.read_bytes()
    if len(data) < 12 or data[0:4] != b"DIRC":
        raise ValueError("bad index signature")
    version, n_entries = struct.unpack(">II", data[4:12])
    if version not in (2, 3, 4):
        raise ValueError(f"unsupported index version {version}")
    # Cap entries to avoid memory abuse
    if n_entries > 50_000:
        raise ValueError("index too large")
    out: List[Tuple[str, int, int]] = []
    pos = 12
    for _ in range(n_entries):
        if pos + 62 > len(data):
            raise ValueError("truncated index entry")
        # ctime(8) mtime(8) dev(4) ino(4) mode(4) uid(4) gid(4) size(4) sha(20) flags(2)
        mtime_s = struct.unpack(">I", data[pos + 8 : pos + 12])[0]
        size = struct.unpack(">I", data[pos + 36 : pos + 40])[0]
        flags = struct.unpack(">H", data[pos + 60 : pos + 62])[0]
        namelen = flags & 0xFFF
        entry_start = pos
        pos = pos + 62
        if namelen == 0xFFF:
            # long name — read until NUL
            end = data.find(b"\x00", pos)
            if end < 0:
                raise ValueError("unterminated long name")
            name = data[pos:end].decode("utf-8", errors="replace")
            pos = end + 1
        else:
            name = data[pos : pos + namelen].decode("utf-8", errors="replace")
            pos = pos + namelen + 1  # expect NUL
        # pad to 8-byte boundary from entry_start
        entry_len = pos - entry_start
        pad = (8 - (entry_len % 8)) % 8
        pos += pad
        # skip extended flags if any (version 3)
        if version >= 3 and (flags & 0x4000):
            if pos + 2 > len(data):
                raise ValueError("truncated extended flags")
            pos += 2
        if name and not name.startswith(".git/"):
            out.append((name, size, mtime_s))
    return out


# ------------------------------------------------------------------ factory


def create_live_backend_after_confirm(
    cfg,
    *,
    root: Optional[str] = None,
    injected: Optional[ReadOnlyRepoBackend] = None,
) -> Optional[ReadOnlyRepoBackend]:
    """Create live backend only when H is enabled. Tests may inject a fake.

    Must be called only after both owner gates pass. Flag OFF ⇒ None (no I/O).
    """
    if injected is not None:
        return injected
    if not bool(getattr(cfg, "owner_triggered_development_enabled", False)):
        return None
    target = root or CANONICAL_WORKSPACE_ROOT
    return LiveReadOnlyBackend(target, require_canonical=(root is None))
