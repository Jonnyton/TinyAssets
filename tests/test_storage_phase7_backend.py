"""Phase 7.1 — StorageBackend smoke tests.

``SqliteOnlyBackend`` is the pre-Phase-7 behavior (zero change).
``SqliteCachedBackend`` adds a YAML mirror under a repo root; the
git stage call is a stubbed no-op for 7.1.

These tests cover the dual-write property: after a cached write, both
the SQLite row and the YAML file exist and agree. Spec AC #1.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
import yaml

from tinyassets.branches import BranchDefinition, NodeDefinition
from tinyassets.catalog import (
    SqliteCachedBackend,
    SqliteOnlyBackend,
    YamlRepoLayout,
    get_backend,
    invalidate_backend_cache,
)


@pytest.fixture
def base_path(tmp_path, monkeypatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    # Ensure the daemon DB is live before the backend touches it.
    from tinyassets.daemon_server import initialize_author_server

    initialize_author_server(base)
    # Also reload universe_server so any @mcp decoration lands fresh
    # (not strictly needed here, but matches other test fixtures).
    from tinyassets import universe_server as us
    importlib.reload(us)
    yield base


def _make_branch() -> BranchDefinition:
    b = BranchDefinition(
        name="Bulk-patch probe",
        description="Three-node capture/tag/archive.",
        author="tester",
        entry_point="capture",
    )
    b.node_defs = [
        NodeDefinition(
            node_id="capture", display_name="Capture",
            prompt_template="Echo: {raw}",
            output_keys=["capture_output"],
        ),
    ]
    b.state_schema = [
        {"name": "raw", "type": "str", "default": ""},
        {"name": "capture_output", "type": "str", "default": ""},
    ]
    return b


def test_unknown_backend_choice_fails_closed_to_sqlite_only(
    base_path, tmp_path, monkeypatch,
):
    monkeypatch.setenv("TINYASSETS_STORAGE_BACKEND", "sqlite")
    monkeypatch.setattr(
        "tinyassets.catalog.backend.git_bridge.is_enabled", lambda _repo: True,
    )
    invalidate_backend_cache()

    backend = get_backend(base_path, repo_root=tmp_path / "repo")

    assert isinstance(backend, SqliteOnlyBackend)


# ─────────────────────────────────────────────────────────────────────
# SqliteOnlyBackend — zero behavior change
# ─────────────────────────────────────────────────────────────────────


def test_sqlite_only_backend_persists_branch_via_daemon_server(base_path):
    backend = SqliteOnlyBackend(base_path)
    saved = backend.save_branch(_make_branch())

    assert saved["name"] == "Bulk-patch probe"
    # Round-trip via daemon_server directly — no YAML side-effect.
    from tinyassets.daemon_server import get_branch_definition

    row = get_branch_definition(
        base_path, branch_def_id=saved["branch_def_id"],
    )
    assert row["name"] == saved["name"]


def test_sqlite_only_backend_persists_goal_via_daemon_server(base_path):
    backend = SqliteOnlyBackend(base_path)
    saved = backend.save_goal({
        "name": "Produce academic paper",
        "description": "Lit review → submittable draft.",
        "author": "tester",
        "tags": ["research"],
    })
    assert saved["name"] == "Produce academic paper"

    from tinyassets.daemon_server import get_goal

    row = get_goal(base_path, goal_id=saved["goal_id"])
    assert row["name"] == saved["name"]


def test_sqlite_only_backend_does_not_write_yaml(base_path, tmp_path):
    """Repo root is irrelevant to the sqlite-only backend — it must
    not touch any filesystem location outside base_path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    backend = SqliteOnlyBackend(base_path)
    backend.save_branch(_make_branch())
    assert list(repo.iterdir()) == [], (
        "sqlite_only must leave the repo root untouched"
    )


# ─────────────────────────────────────────────────────────────────────
# SqliteCachedBackend — dual-write
# ─────────────────────────────────────────────────────────────────────


def test_cached_backend_writes_branch_yaml_and_sqlite(base_path, tmp_path):
    repo = tmp_path / "repo"
    stage_calls: list[Path] = []
    backend = SqliteCachedBackend(
        base_path, repo_root=repo,
        stage_hook=stage_calls.append,
    )
    saved = backend.save_branch(_make_branch())

    # SQLite side intact.
    from tinyassets.daemon_server import get_branch_definition
    row = get_branch_definition(
        base_path, branch_def_id=saved["branch_def_id"],
    )
    assert row["name"] == saved["name"]

    # YAML side present at the spec path.
    layout = YamlRepoLayout(repo)
    branch_path = layout.branch_path("bulk-patch-probe")
    assert branch_path.exists()
    payload = yaml.safe_load(branch_path.read_text(encoding="utf-8"))
    assert payload["name"] == "Bulk-patch probe"
    assert payload["id"] == saved["branch_def_id"]

    # Per-node file also written at nodes/<branch_slug>/<node_id>.yaml.
    node_path = layout.node_path("bulk-patch-probe", "capture")
    assert node_path.exists()
    node_payload = yaml.safe_load(node_path.read_text(encoding="utf-8"))
    assert node_payload["id"] == "capture"
    assert node_payload["prompt_template"] == "Echo: {raw}"

    # stage_hook invoked for each written file; 7.2 will route these
    # to git_bridge.stage.
    assert branch_path in stage_calls
    assert node_path in stage_calls


def test_cached_backend_writes_goal_yaml_and_sqlite(base_path, tmp_path):
    repo = tmp_path / "repo"
    stage_calls: list[Path] = []
    backend = SqliteCachedBackend(
        base_path, repo_root=repo,
        stage_hook=stage_calls.append,
    )
    saved = backend.save_goal({
        "name": "Produce academic paper",
        "author": "tester",
        "tags": ["research"],
    })

    from tinyassets.daemon_server import get_goal
    assert get_goal(base_path, goal_id=saved["goal_id"])["name"] == (
        "Produce academic paper"
    )

    layout = YamlRepoLayout(repo)
    goal_path = layout.goal_path("produce-academic-paper")
    assert goal_path.exists()
    payload = yaml.safe_load(goal_path.read_text(encoding="utf-8"))
    assert payload["name"] == "Produce academic paper"
    assert payload["id"] == saved["goal_id"]
    assert goal_path in stage_calls


def test_cached_backend_default_stage_hook_is_safe(base_path, tmp_path):
    """Without an explicit hook, the backend must still work (Phase
    7.1 ships with the no-op default; Phase 7.2 replaces)."""
    repo = tmp_path / "repo"
    backend = SqliteCachedBackend(base_path, repo_root=repo)
    saved = backend.save_branch(_make_branch())
    assert saved["branch_def_id"]
    assert YamlRepoLayout(repo).branch_path(
        "bulk-patch-probe",
    ).exists()


def test_cached_backend_sqlite_write_short_circuits_on_failure(
    base_path, tmp_path, monkeypatch,
):
    """If the SQLite write raises, the YAML file must not exist —
    we don't want a half-commit to land in the repo ahead of the
    durable mirror."""
    repo = tmp_path / "repo"
    backend = SqliteCachedBackend(base_path, repo_root=repo)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("sqlite write refused")

    monkeypatch.setattr(
        "tinyassets.daemon_server.save_branch_definition", _boom,
    )
    with pytest.raises(RuntimeError):
        backend.save_branch(_make_branch())

    layout = YamlRepoLayout(repo)
    assert not layout.branch_path("bulk-patch-probe").exists()


def test_cached_backend_overwrites_yaml_on_second_save(
    base_path, tmp_path,
):
    repo = tmp_path / "repo"
    backend = SqliteCachedBackend(base_path, repo_root=repo)

    b = _make_branch()
    backend.save_branch(b)

    # Edit the branch and re-save.
    b.description = "updated description"
    backend.save_branch(b)

    layout = YamlRepoLayout(repo)
    payload = yaml.safe_load(
        layout.branch_path("bulk-patch-probe").read_text(encoding="utf-8"),
    )
    assert payload["description"] == "updated description"
