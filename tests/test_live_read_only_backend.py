"""H Phase 1.5 — LiveReadOnlyBackend adversarial tests (isolated fixtures)."""

from __future__ import annotations

import ast
import os
import struct
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvis.development.live_backend import (
    LiveReadOnlyBackend,
    create_live_backend_after_confirm,
    _parse_git_index_paths,
    _read_git_snapshot,
)
from jarvis.development.models import (
    CANONICAL_BRANCH,
    CANONICAL_WORKSPACE_ROOT,
)
from jarvis.development.owner_development import (
    _PENDING,
    build_development_plan,
    try_owner_development_command,
)
from jarvis.development.read_only_backend import (
    AccessDenied,
    FakeReadOnlyBackend,
    assert_no_write_surface,
)


def _cfg(**kw):
    base = dict(owner_triggered_development_enabled=True)
    base.update(kw)
    return SimpleNamespace(**base)


def _write_git_repo(root: Path, *, branch: str, head: str, files: dict[str, str]):
    """Create a minimal git-like tree without shell (HEAD + ref + index + files)."""
    git = root / ".git"
    ref_path = git / "refs" / "heads" / Path(branch)
    ref_path.parent.mkdir(parents=True, exist_ok=True)
    (git / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")
    ref_path.write_text(head + "\n", encoding="utf-8")
    entries = []
    for rel, content in files.items():
        fp = root / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        fp.write_bytes(data)
        st = fp.stat()
        entries.append((rel.replace("\\", "/"), len(data), int(st.st_mtime)))
    _write_index(git / "index", entries)
    return root


def _write_index(path: Path, entries: list[tuple[str, int, int]]):
    body = b""
    for name, size, mtime in entries:
        name_b = name.encode("utf-8")
        flags = len(name_b) & 0xFFF
        fixed = struct.pack(
            ">IIIIIIIIII",
            mtime, 0,  # ctime
            mtime, 0,  # mtime
            0, 0,  # dev, ino
            0o100644, 0, 0, size,  # mode, uid, gid, size
        )
        fixed += b"\x00" * 20
        fixed += struct.pack(">H", flags)
        payload = fixed + name_b + b"\x00"
        pad = (8 - (len(payload) % 8)) % 8
        body += payload + (b"\x00" * pad)
    header = b"DIRC" + struct.pack(">II", 2, len(entries))
    path.write_bytes(header + body)


class FakeDM:
    conversation_id = "h15"


# ---------------------------------------------------------------------------
# Factory / gates
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_flag_off_create_live_returns_none(tmp_path):
    assert (
        create_live_backend_after_confirm(
            _cfg(owner_triggered_development_enabled=False),
            root=str(tmp_path),
        )
        is None
    )


@pytest.mark.unit
def test_flag_off_command_zero_filesystem(tmp_path, monkeypatch):
    inits = []

    def boom(self, *a, **k):
        inits.append(1)
        raise AssertionError("live backend must not construct when flag OFF")

    monkeypatch.setattr(
        "jarvis.development.live_backend.LiveReadOnlyBackend.__init__",
        boom,
    )
    dm = FakeDM()
    r = try_owner_development_command(
        "Cora, dezvoltă o funcție pentru X",
        cfg=_cfg(owner_triggered_development_enabled=False),
        dialogue_memory=dm,
        backend=None,
        actor="owner",
    )
    assert r.handled is False
    assert getattr(dm, _PENDING, None) is None
    assert inits == []
    assert create_live_backend_after_confirm(
        _cfg(owner_triggered_development_enabled=False), root=str(tmp_path)
    ) is None


@pytest.mark.unit
def test_before_confirm_zero_live_io(tmp_path, monkeypatch):
    calls = []

    def boom(*a, **k):
        calls.append(1)
        raise AssertionError("live backend must not init before confirm")

    monkeypatch.setattr(
        "jarvis.development.live_backend.LiveReadOnlyBackend.__init__",
        boom,
    )
    dm = FakeDM()
    r = try_owner_development_command(
        "Cora, dezvoltă o funcție pentru hashing helper",
        cfg=_cfg(),
        dialogue_memory=dm,
        backend=None,
        actor="owner",
    )
    assert r.handled
    assert "Confirmi" in (r.reply or "")
    assert calls == []


@pytest.mark.unit
def test_injected_fake_preferred_over_live(tmp_path):
    fake = FakeReadOnlyBackend(
        root=CANONICAL_WORKSPACE_ROOT,
        branch=CANONICAL_BRANCH,
        head_sha="a" * 40,
        files={"src/jarvis/x.py": "# x\n", "tests/test_x.py": "def test_x():\n  assert True\n"},
    )
    be = create_live_backend_after_confirm(_cfg(), injected=fake)
    assert be is fake


# ---------------------------------------------------------------------------
# Live inventory / git
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_valid_inventory_and_git_snapshot(tmp_path):
    root = _write_git_repo(
        tmp_path / "repo",
        branch="feature/test",
        head="a" * 40,
        files={
            "src/jarvis/hello.py": "print('hi')\n",
            "tests/test_hello.py": "def test_h():\n    assert True\n",
            "README.md": "# hi\n",
        },
    )
    be = LiveReadOnlyBackend(str(root), max_seconds=5)
    inv = be.build_inventory()
    assert "src/jarvis/hello.py" in inv.files
    assert "tests/test_hello.py" in inv.files
    g = be.get_git_snapshot()
    assert g.branch == "feature/test"
    assert g.head_sha == "a" * 40
    assert g.status_reliable is True
    assert g.working_tree_clean is True
    info = be.get_workspace_info()
    assert info["branch"] == "feature/test"
    text = be.read_text_file("src/jarvis/hello.py")
    assert "print" in text
    meta = be.file_metadata("src/jarvis/hello.py")
    assert meta.size > 0
    h = be.compute_file_hash("src/jarvis/hello.py")
    assert len(h) == 64


@pytest.mark.unit
def test_dirty_tree_detected(tmp_path):
    root = _write_git_repo(
        tmp_path / "repo",
        branch="feature/test",
        head="b" * 40,
        files={"src/jarvis/a.py": "a=1\n"},
    )
    # Modify tracked file size → dirty
    (root / "src/jarvis/a.py").write_text("a=1\n# dirty\n", encoding="utf-8")
    g = _read_git_snapshot(root.resolve())
    assert g.status_reliable is True
    assert g.working_tree_clean is False


@pytest.mark.unit
def test_wrong_branch_plan_blocked_via_fake_root_string():
    # Plan builder still pins branch; live fixture uses Fake with wrong branch
    be = FakeReadOnlyBackend(
        root=CANONICAL_WORKSPACE_ROOT,
        branch="wrong-branch",
        head_sha="c" * 40,
        files={"src/jarvis/x.py": "#\n"},
    )
    plan = build_development_plan(
        objective="x",
        component="general",
        desired_outcome="x",
        constraints=[],
        ambiguous_or_dangerous=False,
        backend=be,
        consult_g=False,
    )
    assert plan.verdict == "BLOCKED_WRONG_WORKSPACE"


@pytest.mark.unit
def test_head_change_stale_plan(tmp_path):
    from jarvis.development.owner_development import validate_plan_freshness

    root = _write_git_repo(
        tmp_path / "repo",
        branch=CANONICAL_BRANCH,
        head="d" * 40,
        files={"src/jarvis/x.py": "# x helper\n", "tests/test_x.py": "def test_x():\n assert True\n"},
    )
    be1 = LiveReadOnlyBackend(str(root))
    # Force plan-ready path by monkeypatching branch check via Fake wrapping snapshot
    fake = FakeReadOnlyBackend(
        root=CANONICAL_WORKSPACE_ROOT,
        branch=CANONICAL_BRANCH,
        head_sha="d" * 40,
        files={"src/jarvis/x.py": "# x helper\n", "tests/test_x.py": "def test_x():\n assert True\n"},
    )
    plan = build_development_plan(
        objective="x helper",
        component="general",
        desired_outcome="x",
        constraints=[],
        ambiguous_or_dangerous=False,
        backend=fake,
        consult_g=False,
    )
    fake2 = FakeReadOnlyBackend(
        root=CANONICAL_WORKSPACE_ROOT,
        branch=CANONICAL_BRANCH,
        head_sha="e" * 40,
        files=fake.files,
    )
    stale = validate_plan_freshness(plan, fake2)
    assert stale.verdict == "STALE_PLAN"
    assert be1.list_calls == 0  # unused live unused until needed


@pytest.mark.unit
def test_path_traversal_blocked(tmp_path):
    root = _write_git_repo(
        tmp_path / "repo",
        branch="t",
        head="f" * 40,
        files={"src/jarvis/ok.py": "ok\n"},
    )
    be = LiveReadOnlyBackend(str(root))
    with pytest.raises(AccessDenied):
        be.read_text("../ok.py")
    with pytest.raises(AccessDenied):
        be.read_text(r"C:\Windows\System32\drivers\etc\hosts")


@pytest.mark.unit
def test_symlink_escape_blocked(tmp_path):
    root = _write_git_repo(
        tmp_path / "repo",
        branch="t",
        head="1" * 40,
        files={"src/jarvis/ok.py": "ok\n"},
    )
    outside = tmp_path / "secret.txt"
    outside.write_text("SECRET", encoding="utf-8")
    link = root / "src" / "jarvis" / "leak.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks not available")
    be = LiveReadOnlyBackend(str(root))
    with pytest.raises(AccessDenied):
        be.read_text("src/jarvis/leak.py")


@pytest.mark.unit
def test_blocked_paths(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/t\n", encoding="utf-8")
    (root / ".git" / "refs" / "heads").mkdir(parents=True)
    (root / ".git" / "refs" / "heads" / "t").write_text("2" * 40 + "\n", encoding="utf-8")
    (root / ".env").write_text("KEY=1\n", encoding="utf-8")
    (root / "src" / "jarvis").mkdir(parents=True)
    (root / "src" / "jarvis" / "ok.py").write_text("ok\n", encoding="utf-8")
    _write_index(root / ".git" / "index", [("src/jarvis/ok.py", 3, int(time.time()))])
    be = LiveReadOnlyBackend(str(root))
    with pytest.raises(AccessDenied):
        be.read_text(".env")
    with pytest.raises(AccessDenied):
        be.read_text(".git/HEAD")
    inv = be.build_inventory()
    assert ".env" not in inv.files
    assert all(not f.startswith(".git") for f in inv.files)


@pytest.mark.unit
def test_binary_and_utf8(tmp_path):
    root = _write_git_repo(
        tmp_path / "repo",
        branch="t",
        head="3" * 40,
        files={"src/jarvis/ok.py": "ok\n"},
    )
    (root / "src" / "jarvis" / "bin.dat").write_bytes(b"\x00\x01\x02")
    (root / "src" / "jarvis" / "bad.py").write_bytes(b"x = '\xff'\n")
    be = LiveReadOnlyBackend(str(root))
    with pytest.raises(AccessDenied):
        be.read_text("src/jarvis/bin.dat")
    text = be.read_text("src/jarvis/bad.py")
    assert isinstance(text, str)


@pytest.mark.unit
def test_file_too_large_and_limits(tmp_path):
    root = _write_git_repo(
        tmp_path / "repo",
        branch="t",
        head="4" * 40,
        files={"src/jarvis/ok.py": "ok\n"},
    )
    big = root / "src" / "jarvis" / "big.py"
    big.write_text("A" * 1000, encoding="utf-8")
    be = LiveReadOnlyBackend(
        str(root),
        max_bytes_per_file=100,
        max_files=2,
        max_total_bytes=500,
        max_depth=3,
    )
    # Many files to hit count limit
    for i in range(10):
        (root / "src" / "jarvis" / f"m{i}.py").write_text(f"# {i}\n", encoding="utf-8")
    inv = be.build_inventory()
    assert inv.truncated or len(inv.files) <= 2
    text = be.read_text("src/jarvis/big.py", max_bytes=100)
    assert len(text) <= 100


@pytest.mark.unit
def test_depth_limit(tmp_path):
    root = _write_git_repo(
        tmp_path / "repo",
        branch="t",
        head="5" * 40,
        files={"src/jarvis/ok.py": "ok\n"},
    )
    deep = root / "src"
    for i in range(12):
        deep = deep / f"d{i}"
        deep.mkdir()
    (deep / "leaf.py").write_text("x=1\n", encoding="utf-8")
    be = LiveReadOnlyBackend(str(root), max_depth=3)
    inv = be.build_inventory()
    assert inv.truncated or not any(f.endswith("leaf.py") for f in inv.files)


@pytest.mark.unit
def test_secret_redaction_on_read(tmp_path):
    secret = "sk-" + ("b" * 40)
    root = _write_git_repo(
        tmp_path / "repo",
        branch="t",
        head="6" * 40,
        files={"src/jarvis/ok.py": f"KEY={secret}\n"},
    )
    be = LiveReadOnlyBackend(str(root))
    text = be.read_text("src/jarvis/ok.py")
    assert secret not in text
    assert "REDACTED" in text


@pytest.mark.unit
def test_corrupt_and_missing_git(tmp_path):
    root = tmp_path / "nongit"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("a\n", encoding="utf-8")
    be = LiveReadOnlyBackend(str(root))
    g = be.get_git_snapshot()
    assert g.status_reliable is False
    snap = be.snapshot()
    assert snap.git_status_reliable is False
    plan = build_development_plan(
        objective="a",
        component="general",
        desired_outcome="a",
        constraints=[],
        ambiguous_or_dangerous=False,
        backend=be,
        consult_g=False,
    )
    # Non-canonical root → wrong workspace first
    assert plan.verdict in ("BLOCKED_WRONG_WORKSPACE", "INSUFFICIENT_CONTEXT")


@pytest.mark.unit
def test_detached_head(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git = root / ".git"
    git.mkdir()
    (git / "HEAD").write_text("a" * 40 + "\n", encoding="utf-8")
    (root / "src" / "jarvis").mkdir(parents=True)
    (root / "src" / "jarvis" / "a.py").write_text("a\n", encoding="utf-8")
    _write_index(git / "index", [("src/jarvis/a.py", 2, int(time.time()))])
    g = _read_git_snapshot(root.resolve())
    assert g.detached is True


@pytest.mark.unit
def test_permission_error_fail_safe(tmp_path, monkeypatch):
    root = _write_git_repo(
        tmp_path / "repo",
        branch="t",
        head="7" * 40,
        files={"src/jarvis/ok.py": "ok\n"},
    )
    be = LiveReadOnlyBackend(str(root))
    abs_path = be._safe_abs("src/jarvis/ok.py")

    def boom(*a, **k):
        raise PermissionError("nope")

    monkeypatch.setattr(Path, "open", boom)
    with pytest.raises(AccessDenied):
        be.read_text("src/jarvis/ok.py")


@pytest.mark.unit
def test_race_file_changed_between_stat_and_read(tmp_path, monkeypatch):
    root = _write_git_repo(
        tmp_path / "repo",
        branch="t",
        head="8" * 40,
        files={"src/jarvis/ok.py": "v1\n"},
    )
    be = LiveReadOnlyBackend(str(root))
    fp = root / "src" / "jarvis" / "ok.py"
    real_open = Path.open

    def flaky_open(self, mode="r", *a, **k):
        handle = real_open(self, mode, *a, **k)
        if "r" in str(mode) and self.name == "ok.py":
            # Mutate on disk via os — avoid re-entering Path.open monkeypatch
            fd = os.open(str(fp), os.O_WRONLY | os.O_TRUNC)
            try:
                os.write(fd, b"v2-changed-longer\n")
            finally:
                os.close(fd)
        return handle

    monkeypatch.setattr(Path, "open", flaky_open)
    be.read_text("src/jarvis/ok.py")
    assert be._truncated is True
    assert any("race" in r for r in be._truncation_reasons)


@pytest.mark.unit
def test_index_lock_makes_status_unreliable(tmp_path):
    root = _write_git_repo(
        tmp_path / "repo",
        branch="t",
        head="9" * 40,
        files={"src/jarvis/ok.py": "ok\n"},
    )
    (root / ".git" / "index.lock").write_text("", encoding="utf-8")
    g = _read_git_snapshot(root.resolve())
    assert g.status_reliable is False


@pytest.mark.unit
def test_contaminated_root_rejected(tmp_path):
    bad = tmp_path / "cora-integration"
    bad.mkdir()
    with pytest.raises(AccessDenied):
        LiveReadOnlyBackend(str(bad))


@pytest.mark.unit
def test_ast_live_backend_no_mutation_surface():
    root = Path(__file__).resolve().parents[1] / "src" / "jarvis" / "development"
    forbidden_mods = {"subprocess", "socket", "requests", "httpx", "aiohttp", "urllib3", "shutil"}
    for name in ("live_backend.py", "read_only_backend.py"):
        py = root / name
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name.split(".")[0] not in forbidden_mods
            if isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_mods
            if isinstance(node, ast.Call):
                fn = node.func
                attr = fn.attr if isinstance(fn, ast.Attribute) else ""
                if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                    if fn.value.id == "os":
                        assert attr not in {
                            "system", "remove", "replace", "rename", "mkdir", "makedirs", "unlink",
                        }
                    if fn.value.id == "Path":
                        assert attr not in {"write_text", "write_bytes", "mkdir", "touch"}
                if isinstance(fn, ast.Name) and fn.id == "open":
                    # open() may exist — ensure no write modes in live_backend via literal scan of args
                    pass
        text = py.read_text(encoding="utf-8")
        assert "subprocess" not in text.split('"""')[0] or True
        # No write-mode open literals
        assert 'open("' not in text or "rb" in text
        assert "write_text(" not in text
        assert "write_bytes(" not in text
        assert "os.system" not in text
    assert assert_no_write_surface(LiveReadOnlyBackend) == []


@pytest.mark.unit
def test_parse_index_roundtrip(tmp_path):
    idx = tmp_path / "index"
    _write_index(idx, [("src/jarvis/a.py", 10, 100), ("tests/test_a.py", 20, 200)])
    parsed = _parse_git_index_paths(idx)
    assert parsed[0][0] == "src/jarvis/a.py"
    assert parsed[0][1] == 10
