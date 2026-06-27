"""Phase 7.3 H3 — single-entity branch cluster cutover to SqliteCachedBackend.

Exercises the 5 non-composite branch write handlers against a real git
repo in ``tmp_path``:

- create_branch
- add_node
- connect_nodes
- set_entry_point
- add_state_field

Verifies:

- One MCP write action = one commit. Commit message follows the
  ``branches.{action}: …`` template.
- Dirty local edits on the branch YAML raise the structured
  ``local_edit_conflict`` response (caught once in
  ``_dispatch_branch_action``); SQLite stays untouched on refusal.
- ``force=True`` overrides the dirty refusal.
- ``TINYASSETS_STORAGE_BACKEND=sqlite_only`` and "no git repo" both keep
  the legacy behavior — handlers still work, no YAML, no commits.

Mirrors the H2 fixture shape in ``test_phase7_h2_goals_cutover.py``.
"""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None,
    reason="git binary not available",
)


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, check=True,
    )


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "--initial-branch=main"], path)
    _run(["git", "config", "user.email", "ci@example.invalid"], path)
    _run(["git", "config", "user.name", "CI Bot"], path)
    _run(["git", "config", "commit.gpgsign", "false"], path)
    (path / "README.md").write_text("seed\n", encoding="utf-8")
    _run(["git", "add", "README.md"], path)
    _run(["git", "commit", "-m", "seed", "--no-gpg-sign"], path)


@pytest.fixture
def repo_env(tmp_path, monkeypatch):
    """Real git repo with output/ inside; backend auto-probes to Cached."""
    _init_repo(tmp_path)
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.delenv("TINYASSETS_STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("TINYASSETS_GIT_AUTHOR", raising=False)
    # Re-anchor the cached backend at the tmp repo by changing cwd.
    monkeypatch.chdir(tmp_path)

    from tinyassets.catalog import invalidate_backend_cache
    invalidate_backend_cache()
    from tinyassets import universe_server as us
    importlib.reload(us)

    yield us, tmp_path, base

    invalidate_backend_cache()
    importlib.reload(us)


@pytest.fixture
def no_git_env(tmp_path, monkeypatch):
    """No git repo at parent — backend auto-probes to SqliteOnly."""
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    monkeypatch.delenv("TINYASSETS_STORAGE_BACKEND", raising=False)
    monkeypatch.chdir(tmp_path)

    from tinyassets.catalog import invalidate_backend_cache
    invalidate_backend_cache()
    from tinyassets import universe_server as us
    importlib.reload(us)

    yield us, tmp_path, base

    invalidate_backend_cache()
    importlib.reload(us)


@pytest.fixture
def sqlite_only_env(tmp_path, monkeypatch):
    """Explicit sqlite_only — YAML/git pathway disabled regardless of repo."""
    _init_repo(tmp_path)
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    monkeypatch.setenv("TINYASSETS_STORAGE_BACKEND", "sqlite_only")
    monkeypatch.chdir(tmp_path)

    from tinyassets.catalog import invalidate_backend_cache
    invalidate_backend_cache()
    from tinyassets import universe_server as us
    importlib.reload(us)

    yield us, tmp_path, base

    invalidate_backend_cache()
    importlib.reload(us)


def _call(us, **kwargs):
    return json.loads(us.extensions(**kwargs))


def _commit_count(repo: Path) -> int:
    return int(
        _run(["git", "rev-list", "--count", "HEAD"], repo).stdout.strip()
    )


def _last_commit_subject(repo: Path) -> str:
    return _run(
        ["git", "log", "-1", "--format=%s"], repo,
    ).stdout.strip()


def _last_commit_files(repo: Path) -> list[str]:
    return [
        line.strip()
        for line in _run(
            ["git", "show", "--name-only", "--pretty=format:", "HEAD"], repo,
        ).stdout.splitlines()
        if line.strip()
    ]


# ─── create_branch ──────────────────────────────────────────────────────


def test_create_branch_yields_one_commit(repo_env):
    us, repo, _base = repo_env
    before = _commit_count(repo)
    result = _call(
        us, action="create_branch", name="Recipe tracker",
        description="Capture recipes",
    )
    assert result["status"] == "created"
    assert _commit_count(repo) - before == 1
    assert _last_commit_subject(repo) == "branches.create_branch: Recipe tracker"
    assert any(
        "branches/recipe-tracker.yaml" in f for f in _last_commit_files(repo)
    )


# ─── add_node ───────────────────────────────────────────────────────────


def test_add_node_commits_branch_and_node_yamls(repo_env):
    us, repo, _base = repo_env
    created = _call(us, action="create_branch", name="TinyAssets A")
    bid = created["branch_def_id"]

    before = _commit_count(repo)
    result = _call(
        us, action="add_node",
        branch_def_id=bid,
        node_id="gap_finder",
        display_name="Gap Finder",
        phase="orient",
        prompt_template="Find gaps in {{draft_text}}.",
    )
    assert result["status"] == "added"
    assert _commit_count(repo) - before == 1
    subject = _last_commit_subject(repo)
    assert subject.startswith("branches.add_node:")
    assert "gap_finder" in subject

    files = _last_commit_files(repo)
    assert any("branches/workflow-a.yaml" in f for f in files)
    assert any(
        "nodes/workflow-a/gap_finder.yaml" in f for f in files
    )


# ─── connect_nodes ──────────────────────────────────────────────────────


def test_connect_nodes_commits_branch_only(repo_env):
    us, repo, _base = repo_env
    created = _call(us, action="create_branch", name="Connect probe")
    bid = created["branch_def_id"]
    _call(
        us, action="add_node",
        branch_def_id=bid, node_id="src", display_name="Src",
        phase="orient", prompt_template="go",
    )
    _call(
        us, action="add_node",
        branch_def_id=bid, node_id="dst", display_name="Dst",
        phase="commit", prompt_template="stop",
    )

    before = _commit_count(repo)
    result = _call(
        us, action="connect_nodes",
        branch_def_id=bid, from_node="src", to_node="dst",
    )
    assert result["status"] == "connected"
    assert _commit_count(repo) - before == 1
    subject = _last_commit_subject(repo)
    assert subject.startswith("branches.connect_nodes:")
    assert "src->dst" in subject


# ─── set_entry_point ────────────────────────────────────────────────────


def test_set_entry_point_commits_branch_only(repo_env):
    us, repo, _base = repo_env
    created = _call(us, action="create_branch", name="Entry probe")
    bid = created["branch_def_id"]
    _call(
        us, action="add_node",
        branch_def_id=bid, node_id="start", display_name="Start",
        phase="orient", prompt_template="go",
    )

    before = _commit_count(repo)
    result = _call(
        us, action="set_entry_point",
        branch_def_id=bid, node_id="start",
    )
    assert result["status"] == "set"
    assert _commit_count(repo) - before == 1
    subject = _last_commit_subject(repo)
    assert subject.startswith("branches.set_entry_point:")
    assert "start" in subject


# ─── add_state_field ────────────────────────────────────────────────────


def test_add_state_field_commits_branch_only(repo_env):
    us, repo, _base = repo_env
    created = _call(us, action="create_branch", name="State probe")
    bid = created["branch_def_id"]

    before = _commit_count(repo)
    result = _call(
        us, action="add_state_field",
        branch_def_id=bid, field_name="citations", field_type="list",
    )
    assert result["status"] == "added"
    assert _commit_count(repo) - before == 1
    subject = _last_commit_subject(repo)
    assert subject.startswith("branches.add_state_field:")
    assert "citations" in subject


# ─── dirty-file refusal ─────────────────────────────────────────────────


def test_add_node_dirty_returns_local_edit_conflict(repo_env):
    us, repo, _base = repo_env
    created = _call(us, action="create_branch", name="Dirty probe")
    bid = created["branch_def_id"]

    # User hand-edits the branch YAML without committing.
    branch_path = repo / "branches" / "dirty-probe.yaml"
    branch_path.write_text(
        branch_path.read_text(encoding="utf-8") + "# user edit\n",
        encoding="utf-8",
    )

    before_commits = _commit_count(repo)
    result = _call(
        us, action="add_node",
        branch_def_id=bid, node_id="newbie", display_name="Newbie",
        phase="commit", prompt_template="x",
    )
    assert result["status"] == "local_edit_conflict"
    norm_path = result["conflicting_path"].replace("\\", "/")
    assert norm_path.endswith("branches/dirty-probe.yaml")
    assert _commit_count(repo) == before_commits


def test_add_node_force_overrides_dirty(repo_env):
    us, repo, _base = repo_env
    created = _call(us, action="create_branch", name="Force probe")
    bid = created["branch_def_id"]

    branch_path = repo / "branches" / "force-probe.yaml"
    branch_path.write_text("# user edit\n", encoding="utf-8")

    result = _call(
        us, action="add_node",
        branch_def_id=bid, node_id="winner", display_name="Winner",
        phase="commit", prompt_template="x",
        force=True,
    )
    assert result["status"] == "added"


# ─── sqlite_only + no-git bypass ────────────────────────────────────────


def test_sqlite_only_no_yaml_no_commits(sqlite_only_env):
    us, repo, _base = sqlite_only_env
    before = _commit_count(repo)
    result = _call(us, action="create_branch", name="Cache skip")
    assert result["status"] == "created"
    # No git commit
    assert _commit_count(repo) == before
    # No YAML on disk
    assert not (repo / "branches" / "cache-skip.yaml").exists()


def test_no_git_repo_no_yaml_no_commits(no_git_env):
    # no git repo — backend auto-probes to SqliteOnly; there's no repo
    # to even count commits against. Contract: handler still succeeds.
    us, repo, _base = no_git_env
    result = _call(us, action="create_branch", name="Nogit branch")
    assert result["status"] == "created"
    assert not (repo / "branches" / "nogit-branch.yaml").exists()
