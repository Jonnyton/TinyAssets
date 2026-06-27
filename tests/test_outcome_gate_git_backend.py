"""Outcome gates git-commit path and YAML emitters.

Covers docs/specs/outcome_gates_phase6.md rollout details:
- `save_gate_claim_and_commit` + `retract_gate_claim_and_commit`
  composites on `SqliteOnlyBackend` and `SqliteCachedBackend`.
- YAML round-trip for `gate_ladder` (goals) and gate claims
  (gates/<goal_slug>/<branch_slug>__<rung>.yaml).
- Force + local_edit_conflict pattern on `define_ladder`, `claim`,
  `retract`. Dirty files surface the `_format_dirty_file_conflict`
  envelope via the gates dispatch wrapper.
- Commit message templates: `goals.define_ladder:` / `gates.claim:` /
  `gates.retract:`.

SqliteOnlyBackend tests skip the dirty-check / git-commit assertions
(no git seam). SqliteCachedBackend tests use a real temp git repo via
`git_bridge`-friendly tmp dirs.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

import pytest
import yaml

# ───────────────────────────────────────────────────────────────────────
# Fixtures
# ───────────────────────────────────────────────────────────────────────


def _init_git_repo(repo: Path) -> None:
    """Initialize a bare git repo at ``repo`` with one empty commit
    so `git_bridge` treats it as enabled.
    """
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=repo, check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo, check=True, capture_output=True,
    )
    (repo / "README.md").write_text("seed\n")
    subprocess.run(
        ["git", "add", "README.md"], cwd=repo, check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=repo, check=True,
        capture_output=True,
    )


@pytest.fixture
def cached_gates_env(tmp_path, monkeypatch):
    """A temp git repo with GATES_ENABLED + sqlite_cached backend."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    base = repo / "output"
    base.mkdir()
    monkeypatch.chdir(repo)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "alice")
    monkeypatch.setenv("GATES_ENABLED", "1")
    monkeypatch.setenv("TINYASSETS_STORAGE_BACKEND", "sqlite_cached")
    from tinyassets.catalog import backend as backend_mod
    backend_mod.invalidate_backend_cache()
    from tinyassets import universe_server as us
    importlib.reload(us)
    yield us, base, repo, monkeypatch
    backend_mod.invalidate_backend_cache()
    importlib.reload(us)


def _call(us, tool, action, **kwargs):
    return json.loads(getattr(us, tool)(action=action, **kwargs))


_LADDER = [
    {"rung_key": "draft_complete", "name": "Draft complete",
     "description": "Full draft emitted."},
    {"rung_key": "peer_reviewed", "name": "Peer reviewed",
     "description": "At least 2 reviewers."},
]


def _seed(us):
    g = _call(us, "goals", "propose", name="Research paper", description="x")
    gid = g["goal"]["goal_id"]
    b = _call(us, "extensions", "create_branch", name="LoRA v3")
    bid = b["branch_def_id"]
    _call(us, "goals", "bind", goal_id=gid, branch_def_id=bid)
    return gid, bid


def _last_commit_message(repo: Path) -> str:
    out = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo, check=True,
        capture_output=True, text=True,
    )
    return out.stdout.strip()


# ───────────────────────────────────────────────────────────────────────
# YAML emitters (serializer round-trip)
# ───────────────────────────────────────────────────────────────────────


def test_goal_yaml_roundtrip_with_ladder():
    from tinyassets.catalog.serializer import (
        goal_from_yaml_payload,
        goal_to_yaml_payload,
    )

    original = {
        "goal_id": "g1",
        "name": "Research paper",
        "description": "x",
        "author": "alice",
        "tags": ["ai"],
        "visibility": "public",
        "created_at": 1.0,
        "updated_at": 2.0,
        "gate_ladder": _LADDER,
    }
    payload = goal_to_yaml_payload(original)
    assert payload["gate_ladder"] == _LADDER
    restored = goal_from_yaml_payload(payload)
    assert restored["gate_ladder"] == _LADDER


def test_goal_yaml_omits_empty_ladder():
    from tinyassets.catalog.serializer import goal_to_yaml_payload

    payload = goal_to_yaml_payload({
        "goal_id": "g1", "name": "G", "gate_ladder": [],
    })
    assert "gate_ladder" not in payload


def test_gate_claim_yaml_roundtrip():
    from tinyassets.catalog.serializer import (
        gate_claim_from_yaml_payload,
        gate_claim_to_yaml_payload,
    )

    original = {
        "claim_id": "abc123",
        "branch_def_id": "b1",
        "goal_id": "g1",
        "rung_key": "draft_complete",
        "evidence_url": "https://example.com/x",
        "evidence_note": "first",
        "claimed_by": "alice",
        "claimed_at": "2026-05-01T14:22:03Z",
        "retracted_at": None,
        "retracted_reason": "",
    }
    payload = gate_claim_to_yaml_payload(original)
    restored = gate_claim_from_yaml_payload(payload)
    assert restored == original


def test_gate_claim_yaml_roundtrip_retracted():
    from tinyassets.catalog.serializer import (
        gate_claim_from_yaml_payload,
        gate_claim_to_yaml_payload,
    )

    original = {
        "claim_id": "abc123", "branch_def_id": "b1", "goal_id": "g1",
        "rung_key": "draft_complete",
        "evidence_url": "https://example.com/x", "evidence_note": "",
        "claimed_by": "alice",
        "claimed_at": "2026-05-01T14:22:03Z",
        "retracted_at": "2026-05-02T09:00:00Z",
        "retracted_reason": "evidence 404",
    }
    payload = gate_claim_to_yaml_payload(original)
    assert payload["retracted_at"] == "2026-05-02T09:00:00Z"
    restored = gate_claim_from_yaml_payload(payload)
    assert restored["retracted_at"] == "2026-05-02T09:00:00Z"


# ───────────────────────────────────────────────────────────────────────
# Layout paths
# ───────────────────────────────────────────────────────────────────────


def test_gate_claim_path_shape(tmp_path):
    from tinyassets.catalog.layout import YamlRepoLayout

    layout = YamlRepoLayout(tmp_path)
    path = layout.gate_claim_path("fantasy-novel", "loral-v3", "draft_complete")
    assert path == (
        tmp_path.resolve() / "gates" / "fantasy-novel"
        / "loral-v3__draft_complete.yaml"
    )


# ───────────────────────────────────────────────────────────────────────
# SqliteOnly backend (no git seam)
# ───────────────────────────────────────────────────────────────────────


def test_sqlite_only_save_gate_claim_returns_none_commit(tmp_path):
    """SqliteOnlyBackend.save_gate_claim_and_commit delegates to
    daemon_server.claim_gate and returns ``(saved, None)``.
    """
    from tinyassets.branches import BranchDefinition
    from tinyassets.catalog.backend import SqliteOnlyBackend
    from tinyassets.daemon_server import (
        initialize_author_server,
        save_branch_definition,
        save_goal,
        update_branch_definition,
    )

    base = tmp_path / "out"
    base.mkdir()
    initialize_author_server(base)
    goal = save_goal(base, goal={"name": "G", "author": "alice"})
    branch = save_branch_definition(
        base, branch_def=BranchDefinition(name="B", author="alice").to_dict(),
    )
    update_branch_definition(
        base, branch_def_id=branch["branch_def_id"],
        updates={"goal_id": goal["goal_id"]},
    )
    from tinyassets.daemon_server import set_goal_ladder
    set_goal_ladder(base, goal_id=goal["goal_id"], ladder=_LADDER)

    backend = SqliteOnlyBackend(base)
    saved, commit = backend.save_gate_claim_and_commit(
        branch_def_id=branch["branch_def_id"],
        goal_id=goal["goal_id"],
        rung_key="draft_complete",
        evidence_url="https://example.com/x",
        evidence_note="",
        claimed_by="alice",
        goal_slug="g", branch_slug="b",
        author="alice <a@x>", message="gates.claim: g/b@draft_complete",
    )
    assert commit is None
    assert saved["rung_key"] == "draft_complete"
    assert saved["branch_def_id"] == branch["branch_def_id"]


# ───────────────────────────────────────────────────────────────────────
# SqliteCached backend: commits + YAML + force
# ───────────────────────────────────────────────────────────────────────


def test_define_ladder_commits_and_writes_goal_yaml(cached_gates_env):
    us, _base, repo, _ = cached_gates_env
    gid, _bid = _seed(us)
    result = _call(us, "gates", "define_ladder",
                   goal_id=gid, ladder=json.dumps(_LADDER))
    assert result["status"] == "defined"
    # YAML written under goals/<slug>.yaml with gate_ladder key.
    yaml_files = list((repo / "goals").glob("*.yaml"))
    assert len(yaml_files) == 1
    content = yaml.safe_load(yaml_files[0].read_text(encoding="utf-8"))
    assert "gate_ladder" in content
    assert [r["rung_key"] for r in content["gate_ladder"]] == [
        "draft_complete", "peer_reviewed",
    ]
    # Commit namespace per spec: goals.define_ladder.
    assert _last_commit_message(repo).startswith("goals.define_ladder: ")


def test_claim_commits_and_writes_gate_yaml(cached_gates_env):
    us, _base, repo, _ = cached_gates_env
    gid, bid = _seed(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    result = _call(us, "gates", "claim",
                   branch_def_id=bid, rung_key="draft_complete",
                   evidence_url="https://example.com/x")
    assert result["status"] == "claimed"
    gate_files = list((repo / "gates").rglob("*.yaml"))
    assert len(gate_files) == 1
    content = yaml.safe_load(gate_files[0].read_text(encoding="utf-8"))
    assert content["rung_key"] == "draft_complete"
    assert content["evidence_url"] == "https://example.com/x"
    assert content["retracted_at"] is None
    assert _last_commit_message(repo).startswith("gates.claim: ")


def test_retract_rewrites_same_yaml_with_retracted_at(cached_gates_env):
    us, _base, repo, _ = cached_gates_env
    gid, bid = _seed(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/x")
    path_before = next((repo / "gates").rglob("*.yaml"))
    result = _call(us, "gates", "retract",
                   branch_def_id=bid, rung_key="draft_complete",
                   reason="evidence 404")
    assert result["status"] == "retracted"
    gate_files = list((repo / "gates").rglob("*.yaml"))
    assert len(gate_files) == 1  # same file, not deleted
    assert gate_files[0] == path_before
    content = yaml.safe_load(gate_files[0].read_text(encoding="utf-8"))
    assert content["retracted_at"] is not None
    assert content["retracted_reason"] == "evidence 404"
    assert _last_commit_message(repo).startswith("gates.retract: ")


def test_claim_dirty_file_returns_local_edit_conflict(cached_gates_env):
    us, _base, repo, _ = cached_gates_env
    gid, bid = _seed(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    # First claim writes the file.
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/first")
    # Simulate a local edit — append a comment, don't commit.
    gate_file = next((repo / "gates").rglob("*.yaml"))
    gate_file.write_text(
        gate_file.read_text(encoding="utf-8") + "# local edit\n",
        encoding="utf-8",
    )
    # Second claim should surface local_edit_conflict.
    result = _call(us, "gates", "claim",
                   branch_def_id=bid, rung_key="draft_complete",
                   evidence_url="https://example.com/second")
    assert result["status"] == "local_edit_conflict"
    assert "gates" in result["conflicting_path"]
    assert result["all_conflicts"] == [result["conflicting_path"]]
    assert any("force=True" in o for o in result["options"])


def test_claim_force_overrides_dirty_file(cached_gates_env):
    us, _base, repo, _ = cached_gates_env
    gid, bid = _seed(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/first")
    gate_file = next((repo / "gates").rglob("*.yaml"))
    gate_file.write_text(
        gate_file.read_text(encoding="utf-8") + "# local edit\n",
        encoding="utf-8",
    )
    result = _call(us, "gates", "claim",
                   branch_def_id=bid, rung_key="draft_complete",
                   evidence_url="https://example.com/second",
                   force=True)
    assert result["status"] == "claimed"
    # File was overwritten.
    content = yaml.safe_load(gate_file.read_text(encoding="utf-8"))
    assert content["evidence_url"] == "https://example.com/second"


def test_retract_dirty_file_returns_local_edit_conflict(cached_gates_env):
    us, _base, repo, _ = cached_gates_env
    gid, bid = _seed(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/x")
    gate_file = next((repo / "gates").rglob("*.yaml"))
    gate_file.write_text(
        gate_file.read_text(encoding="utf-8") + "# local edit\n",
        encoding="utf-8",
    )
    result = _call(us, "gates", "retract",
                   branch_def_id=bid, rung_key="draft_complete",
                   reason="nope")
    assert result["status"] == "local_edit_conflict"


def test_define_ladder_dirty_file_returns_local_edit_conflict(cached_gates_env):
    us, _base, repo, _ = cached_gates_env
    gid, _bid = _seed(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    goal_file = next((repo / "goals").glob("*.yaml"))
    goal_file.write_text(
        goal_file.read_text(encoding="utf-8") + "# local edit\n",
        encoding="utf-8",
    )
    result = _call(us, "gates", "define_ladder",
                   goal_id=gid, ladder=json.dumps(_LADDER))
    assert result["status"] == "local_edit_conflict"
    assert "goals" in result["conflicting_path"]


def test_claim_commit_message_format(cached_gates_env):
    us, _base, repo, _ = cached_gates_env
    gid, bid = _seed(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/x")
    msg = _last_commit_message(repo)
    # Pattern: "gates.claim: <goal_slug>/<branch_slug>@<rung_key>"
    assert msg.startswith("gates.claim: ")
    assert "@draft_complete" in msg
    assert "/" in msg  # goal_slug/branch_slug separator


def test_retract_commit_message_format(cached_gates_env):
    us, _base, repo, _ = cached_gates_env
    gid, bid = _seed(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/x")
    _call(us, "gates", "retract",
          branch_def_id=bid, rung_key="draft_complete",
          reason="bogus")
    msg = _last_commit_message(repo)
    assert msg.startswith("gates.retract: ")
    assert "@draft_complete" in msg


def test_get_ladder_no_commit(cached_gates_env):
    """Read-only action MUST NOT emit a commit."""
    us, _base, repo, _ = cached_gates_env
    gid, _bid = _seed(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    msg_before = _last_commit_message(repo)
    _call(us, "gates", "get_ladder", goal_id=gid)
    msg_after = _last_commit_message(repo)
    assert msg_before == msg_after


def test_list_claims_no_commit(cached_gates_env):
    us, _base, repo, _ = cached_gates_env
    gid, bid = _seed(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/x")
    msg_before = _last_commit_message(repo)
    _call(us, "gates", "list_claims", branch_def_id=bid)
    assert _last_commit_message(repo) == msg_before


def test_leaderboard_no_commit(cached_gates_env):
    us, _base, repo, _ = cached_gates_env
    gid, bid = _seed(us)
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/x")
    msg_before = _last_commit_message(repo)
    _call(us, "gates", "leaderboard", goal_id=gid)
    assert _last_commit_message(repo) == msg_before


# ───────────────────────────────────────────────────────────────────────
# Integration: define_ladder → claim → retract → re-claim flow
# ───────────────────────────────────────────────────────────────────────


def test_full_round_trip_commits_four_times(cached_gates_env):
    """define_ladder + claim + retract + re-claim = 4 new commits
    (plus whatever `goals propose` / `bind` / `create_branch` emit).
    """
    us, _base, repo, _ = cached_gates_env

    def _count_commits() -> int:
        out = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=repo,
            check=True, capture_output=True, text=True,
        )
        return int(out.stdout.strip())

    gid, bid = _seed(us)
    pre = _count_commits()
    _call(us, "gates", "define_ladder",
          goal_id=gid, ladder=json.dumps(_LADDER))
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/a")
    _call(us, "gates", "retract",
          branch_def_id=bid, rung_key="draft_complete",
          reason="typo")
    _call(us, "gates", "claim",
          branch_def_id=bid, rung_key="draft_complete",
          evidence_url="https://example.com/b")
    post = _count_commits()
    assert post - pre == 4
