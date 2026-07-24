"""Adversarial tests for read-only Git worktree metadata resolution."""

from __future__ import annotations

import ast
import struct
import time
from pathlib import Path

import pytest

from jarvis.development.live_backend import (
    LiveReadOnlyBackend,
    resolve_git_metadata_paths,
    _read_git_snapshot,
)


def _write_index(path: Path, entries: list[tuple[str, int, int]]):
    body = b""
    for name, size, mtime in entries:
        name_b = name.encode("utf-8")
        flags = len(name_b) & 0xFFF
        fixed = struct.pack(
            ">IIIIIIIIII",
            mtime, 0, mtime, 0, 0, 0, 0o100644, 0, 0, size,
        )
        fixed += b"\x00" * 20
        fixed += struct.pack(">H", flags)
        payload = fixed + name_b + b"\x00"
        pad = (8 - (len(payload) % 8)) % 8
        body += payload + (b"\x00" * pad)
    path.write_bytes(b"DIRC" + struct.pack(">II", 2, len(entries)) + body)


def _make_main_git(main: Path):
    git = main / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "objects").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git / "refs" / "heads" / "main").write_text("a" * 40 + "\n", encoding="utf-8")
    return git


def _make_worktree(
    tmp_path: Path,
    *,
    branch: str = "feature/test",
    head: str = "b" * 40,
    files: dict[str, str] | None = None,
    gitdir_style: str = "absolute",
):
    """Build an isolated main repo + linked worktree without git CLI."""
    main = tmp_path / "main"
    main.mkdir()
    common = _make_main_git(main)
    # branch ref in common
    ref_path = common / "refs" / "heads" / Path(branch)
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    ref_path.write_text(head + "\n", encoding="utf-8")

    wt_name = "wt1"
    wt_git = common / "worktrees" / wt_name
    wt_git.mkdir(parents=True)
    (wt_git / "commondir").write_text("../..\n", encoding="utf-8")
    (wt_git / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
    (wt_git / "gitdir").write_text("ignored\n", encoding="utf-8")  # git writes this; we don't need it

    work = tmp_path / "work"
    work.mkdir()
    files = files or {"src/jarvis/ok.py": "ok\n"}
    entries = []
    for rel, content in files.items():
        fp = work / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        fp.write_bytes(data)
        entries.append((rel.replace("\\", "/"), len(data), int(fp.stat().st_mtime)))
    _write_index(wt_git / "index", entries)

    if gitdir_style == "absolute":
        pointer = f"gitdir: {wt_git.as_posix()}\n"
    elif gitdir_style == "relative":
        # relative from work/ to main/.git/worktrees/wt1
        rel = Path(os_path_rel(work, wt_git))
        pointer = f"gitdir: {rel.as_posix()}\n"
    else:
        pointer = gitdir_style
    (work / ".git").write_text(pointer, encoding="utf-8")
    return work, wt_git, common


def os_path_rel(from_dir: Path, to_dir: Path) -> str:
    import os
    return os.path.relpath(str(to_dir), str(from_dir))


# ---------------------------------------------------------------------------
# resolve_git_metadata_paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_normal_git_directory(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git = _make_main_git(root)
    (root / "src" / "jarvis").mkdir(parents=True)
    (root / "src" / "jarvis" / "a.py").write_text("a\n", encoding="utf-8")
    _write_index(git / "index", [("src/jarvis/a.py", 2, int(time.time()))])
    m = resolve_git_metadata_paths(root)
    assert m.error is None
    assert m.is_worktree is False
    assert m.git_dir == m.common_dir
    g = _read_git_snapshot(root.resolve())
    assert g.branch == "main"
    assert g.head_sha == "a" * 40
    assert g.status_reliable is True


@pytest.mark.unit
def test_worktree_git_file_absolute(tmp_path):
    work, wt_git, common = _make_worktree(tmp_path, gitdir_style="absolute")
    m = resolve_git_metadata_paths(work)
    assert m.error is None
    assert m.is_worktree is True
    assert m.git_dir.resolve() == wt_git.resolve()
    assert m.common_dir.resolve() == common.resolve()
    g = _read_git_snapshot(work.resolve())
    assert g.branch == "feature/test"
    assert g.head_sha == "b" * 40
    assert g.status_reliable is True
    assert g.working_tree_clean is True


@pytest.mark.unit
def test_worktree_gitdir_relative(tmp_path):
    work, wt_git, common = _make_worktree(tmp_path, gitdir_style="relative")
    m = resolve_git_metadata_paths(work)
    assert m.error is None
    assert m.is_worktree is True
    assert m.git_dir.resolve() == wt_git.resolve()


@pytest.mark.unit
def test_gitdir_target_missing(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / ".git").write_text(
        f"gitdir: {tmp_path.as_posix()}/nope/worktrees/x\n", encoding="utf-8"
    )
    m = resolve_git_metadata_paths(work)
    assert m.error is not None


@pytest.mark.unit
def test_gitdir_outside_worktrees(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    common = _make_main_git(main)
    outside = tmp_path / "outside"
    outside.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    (work / ".git").write_text(f"gitdir: {outside.as_posix()}\n", encoding="utf-8")
    m = resolve_git_metadata_paths(work)
    assert m.error is not None
    assert "worktrees" in (m.error or "")


@pytest.mark.unit
def test_unc_path_rejected(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / ".git").write_text("gitdir: //server/share/repo/.git/worktrees/x\n", encoding="utf-8")
    m = resolve_git_metadata_paths(work)
    assert m.error and "UNC" in m.error


@pytest.mark.unit
def test_device_path_rejected(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / ".git").write_text("gitdir: NUL\n", encoding="utf-8")
    m = resolve_git_metadata_paths(work)
    assert m.error and "device" in m.error


@pytest.mark.unit
def test_malformed_prefix(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / ".git").write_text("notgitdir: /tmp/x\n", encoding="utf-8")
    m = resolve_git_metadata_paths(work)
    assert m.error and "prefix" in m.error


@pytest.mark.unit
def test_multiple_lines_rejected(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / ".git").write_text(
        "gitdir: /tmp/a/.git/worktrees/x\ngitdir: /tmp/b\n", encoding="utf-8"
    )
    m = resolve_git_metadata_paths(work)
    assert m.error and "single line" in m.error


@pytest.mark.unit
def test_nul_binary_rejected(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / ".git").write_bytes(b"gitdir: /tmp/x\x00y\n")
    m = resolve_git_metadata_paths(work)
    assert m.error and "NUL" in m.error


@pytest.mark.unit
def test_git_file_too_large(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / ".git").write_text("gitdir: " + ("x" * 600) + "\n", encoding="utf-8")
    m = resolve_git_metadata_paths(work)
    assert m.error and "too large" in m.error


@pytest.mark.unit
def test_commondir_missing(tmp_path):
    work, wt_git, _ = _make_worktree(tmp_path)
    (wt_git / "commondir").unlink()
    m = resolve_git_metadata_paths(work)
    assert m.error and "commondir" in m.error


@pytest.mark.unit
def test_commondir_escape(tmp_path):
    work, wt_git, _ = _make_worktree(tmp_path)
    escape = tmp_path / "escape_git"
    escape.mkdir()
    (escape / "HEAD").write_text("ref: refs/heads/x\n", encoding="utf-8")
    (escape / "refs").mkdir()
    (wt_git / "commondir").write_text(escape.as_posix() + "\n", encoding="utf-8")
    m = resolve_git_metadata_paths(work)
    assert m.error is not None


@pytest.mark.unit
def test_head_missing_corrupt(tmp_path):
    work, wt_git, _ = _make_worktree(tmp_path)
    (wt_git / "HEAD").unlink()
    g = _read_git_snapshot(work.resolve())
    assert g.status_reliable is False
    (wt_git / "HEAD").write_text("not-a-ref\n", encoding="utf-8")
    # clear cache by new call
    g2 = _read_git_snapshot(work.resolve())
    assert g2.error == "corrupt HEAD" or g2.status_reliable is False


@pytest.mark.unit
def test_index_missing_corrupt(tmp_path):
    work, wt_git, _ = _make_worktree(tmp_path)
    (wt_git / "index").unlink()
    g = _read_git_snapshot(work.resolve())
    assert g.status_reliable is False
    (wt_git / "index").write_bytes(b"NOTDIRC")
    g2 = _read_git_snapshot(work.resolve())
    assert g2.status_reliable is False


@pytest.mark.unit
def test_packed_refs_fallback(tmp_path):
    work, wt_git, common = _make_worktree(tmp_path, branch="packed/branch", head="c" * 40)
    # remove loose ref; use packed-refs
    ref = common / "refs" / "heads" / "packed" / "branch"
    if ref.exists():
        ref.unlink()
    (common / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled\n"
        + ("c" * 40)
        + " refs/heads/packed/branch\n",
        encoding="utf-8",
    )
    (wt_git / "HEAD").write_text("ref: refs/heads/packed/branch\n", encoding="utf-8")
    g = _read_git_snapshot(work.resolve())
    assert g.head_sha == "c" * 40
    assert g.branch == "packed/branch"


@pytest.mark.unit
def test_detached_head_worktree(tmp_path):
    work, wt_git, _ = _make_worktree(tmp_path)
    (wt_git / "HEAD").write_text("d" * 40 + "\n", encoding="utf-8")
    g = _read_git_snapshot(work.resolve())
    assert g.detached is True
    assert g.head_sha == "d" * 40


@pytest.mark.unit
def test_index_lock_fail_closed(tmp_path):
    work, wt_git, _ = _make_worktree(tmp_path)
    (wt_git / "index.lock").write_text("", encoding="utf-8")
    g = _read_git_snapshot(work.resolve())
    assert g.status_reliable is False
    assert "index.lock" in g.status_summary


@pytest.mark.unit
def test_worktree_dirty_and_untracked(tmp_path):
    work, wt_git, _ = _make_worktree(
        tmp_path, files={"src/jarvis/ok.py": "ok\n"}
    )
    (work / "src" / "jarvis" / "ok.py").write_text("ok\n#dirty\n", encoding="utf-8")
    g = _read_git_snapshot(work.resolve())
    assert g.status_reliable is True
    assert g.working_tree_clean is False

    work2_base = tmp_path / "u"
    work2_base.mkdir()
    work2, _, _ = _make_worktree(
        work2_base, files={"src/jarvis/ok.py": "ok\n"}
    )
    (work2 / "src" / "jarvis" / "extra.py").write_text("x\n", encoding="utf-8")
    g2 = _read_git_snapshot(work2.resolve())
    assert g2.status_reliable is True
    assert g2.working_tree_clean is False
    assert "untracked" in g2.status_summary


def _expected_head_sha_from_worktree_metadata(git_dir: Path, common_dir: Path) -> str:
    """Read HEAD SHA from worktree metadata only (pathlib; no git CLI)."""
    import re

    head_raw = (git_dir / "HEAD").read_text(encoding="utf-8", errors="replace").strip()
    if head_raw.startswith("ref:"):
        ref = head_raw.split(":", 1)[1].strip()
        ref_file = common_dir / ref
        if ref_file.is_file():
            sha = ref_file.read_text(encoding="utf-8", errors="replace").strip()
        else:
            sha = ""
            packed = common_dir / "packed-refs"
            if packed.is_file():
                for line in packed.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not line or line.startswith("#") or line.startswith("^"):
                        continue
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == ref:
                        sha = parts[0].strip()
                        break
    elif re.fullmatch(r"[0-9a-fA-F]{40}", head_raw):
        sha = head_raw
    else:
        sha = ""
    assert re.fullmatch(r"[0-9a-fA-F]{40}", sha), f"invalid metadata HEAD: {sha!r}"
    return sha.lower()


@pytest.mark.unit
def test_canonical_workspace_worktree_live_pinning():
    """Live pin: real canonical worktree resolves branch/HEAD (may be dirty if WIP)."""
    import re

    from jarvis.development.models import CANONICAL_BRANCH, CANONICAL_WORKSPACE_ROOT

    root = Path(CANONICAL_WORKSPACE_ROOT)
    m = resolve_git_metadata_paths(root)
    assert m.error is None
    assert m.is_worktree is True
    assert m.git_dir.name == "cora-f-real-search-clean"
    assert m.git_dir.parent.name == "worktrees"
    assert m.common_dir.name == ".git"
    expected_sha = _expected_head_sha_from_worktree_metadata(m.git_dir, m.common_dir)
    g = _read_git_snapshot(root)
    assert g.branch == CANONICAL_BRANCH
    assert re.fullmatch(r"[0-9a-f]{40}", g.head_sha)
    assert g.head_sha == expected_sha
    assert g.status_reliable is True  # dirty-or-clean still reliable


@pytest.mark.unit
def test_ast_no_mutation_in_live_backend():
    py = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "jarvis"
        / "development"
        / "live_backend.py"
    )
    tree = ast.parse(py.read_text(encoding="utf-8"))
    forbidden = {"subprocess", "socket", "requests", "httpx", "aiohttp", "shutil"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in forbidden
        if isinstance(node, ast.ImportFrom) and node.module:
            assert node.module.split(".")[0] not in forbidden
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                assert node.func.attr not in {
                    "system", "remove", "replace", "rename", "mkdir", "makedirs",
                }
            if node.func.attr in ("write_text", "write_bytes", "mkdir", "touch"):
                raise AssertionError(f"mutating Path.{node.func.attr}")
    text = py.read_text(encoding="utf-8")
    assert "os.system" not in text
    assert "subprocess" not in text
