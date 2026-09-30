"""No path hands one user another user's private branch history.

patch_branch mints a version snapshot before and after every edit, private
branches included, so a branch's versions are its prompts over time -- including
text the owner later removed. Node edit history is the same record per node.
The readers of both checked nothing. The connector's deprecated ``extensions``
tool was hidden from tools/list but still dispatchable, so any signed-in user
could call them by name. Astra refute review of #4107, 2026-09-30.

Two layers, each tested on its own:

* the connector no longer dispatches ``extensions`` at all (the route the leak
  took); the first test fails on the tree that had the leak;
* every reader of versions or node history asks the branch's readability gate,
  so no future route to them can repeat it.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

import pytest

from tests.test_branch_read_authority import (  # noqa: F401 - fixture
    _publish,
    _seed_branch,
    branch_authority_env,
)

SECRET = "ALICE PRIVATE PROMPT"


def _alices_private_branch(base: Path) -> str:
    branch = _seed_branch(base, branch_def_id="alice-private", author="alice",
                          visibility="private", node_ids=("step",))
    branch["node_defs"][0]["prompt_template"] = SECRET
    from tinyassets.daemon_server import save_branch_definition

    save_branch_definition(base, branch_def=branch)
    return _publish(base, branch, "alice")


def _via_connector(tool: str, arguments: dict) -> str:
    """Call a tool the way a connected client does, and return what it saw."""
    from tinyassets import universe_server

    try:
        result = asyncio.run(universe_server.mcp.call_tool(tool, arguments))
    except Exception as exc:  # noqa: BLE001 - a refusal is an answer here
        return f"refused: {exc}"
    return json.dumps(getattr(result, "structured_content", None) or str(result), default=str)


def test_another_user_cannot_read_private_history_through_the_connector(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],  # noqa: F811
) -> None:
    """The leak as it happened: Bob, signed in, asks the public connector for
    Alice's private branch versions by id. Red on the tree that had the leak."""
    base, authenticate = branch_authority_env
    version_id = _alices_private_branch(base)
    authenticate("bob")
    for arguments in (
        {"action": "list_branch_versions", "branch_def_id": "alice-private"},
        {"action": "get_branch_version", "branch_version_id": version_id},
        {"action": "list_node_versions", "branch_def_id": "alice-private", "node_id": "step"},
    ):
        seen = _via_connector("extensions", arguments)
        assert SECRET not in seen, (arguments, seen)


def test_the_connector_neither_lists_nor_dispatches_extensions() -> None:
    from tinyassets import universe_server

    names = {tool.name for tool in asyncio.run(universe_server.mcp.list_tools())}
    assert "extensions" not in names
    assert "extensions" not in universe_server._DEPRECATED_TOOL_NAMES
    assert _via_connector("extensions", {"action": "list_branches"}).startswith("refused")


def _ext(action: str, **kwargs) -> dict:
    from tinyassets.api.extensions import _extensions_impl

    return json.loads(_extensions_impl(action=action, **kwargs))


@pytest.mark.parametrize("action,kwargs", [
    ("list_branch_versions", {"branch_def_id": "alice-private"}),
    ("list_node_versions", {"branch_def_id": "alice-private", "node_id": "step"}),
    ("suggest_node_edit", {"branch_def_id": "alice-private", "node_id": "step"}),
])
def test_every_history_reader_answers_a_stranger_as_if_absent(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],  # noqa: F811
    action: str, kwargs: dict,
) -> None:
    base, authenticate = branch_authority_env
    _alices_private_branch(base)
    authenticate("bob")
    seen = _ext(action, **kwargs)
    assert SECRET not in json.dumps(seen)
    assert seen == {"error": "Branch 'alice-private' not found."}
    absent = _ext(action, **{**kwargs, "branch_def_id": "no-such-branch"})
    assert absent == {"error": "Branch 'no-such-branch' not found."}

    authenticate("alice")
    assert "error" not in _ext(action, **kwargs), "the owner still reads it"


def test_a_single_version_answers_a_stranger_as_if_absent(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],  # noqa: F811
) -> None:
    base, authenticate = branch_authority_env
    version_id = _alices_private_branch(base)
    from tinyassets.branch_versions import publish_branch_version

    public = _seed_branch(base, branch_def_id="bob-public", author="bob", node_ids=("s",))
    public_version = publish_branch_version(
        base, public, publisher="bob", public=True).branch_version_id

    authenticate("bob")
    assert _ext("get_branch_version", branch_version_id=version_id) == {
        "error": f"Version '{version_id}' not found."}
    assert _ext("get_branch_version", branch_version_id="no-such@00000000") == {
        "error": "Version 'no-such@00000000' not found."}

    authenticate("alice")
    assert _ext("get_branch_version", branch_version_id=version_id)["branch_version_id"] == \
        version_id
    authenticate("carol")
    assert _ext("get_branch_version", branch_version_id=public_version)[
        "branch_version_id"] == public_version


def test_a_public_branchs_unpublished_history_stays_its_authors(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],  # noqa: F811
) -> None:
    """Founder 2026-09-30 (astra round 3 on #4107): a public branch exposes only
    the versions its owner published. Its edit history -- the snapshots
    patch_branch mints on every edit -- stays readable to the author alone."""
    from tinyassets.branch_versions import publish_branch_version

    base, authenticate = branch_authority_env
    branch = _seed_branch(base, branch_def_id="alice-open", author="alice", node_ids=("s",))
    branch["node_defs"][0]["prompt_template"] = SECRET
    history = publish_branch_version(base, branch, publisher="alice",
                                     notes="patch_branch pre-patch snapshot").branch_version_id
    branch["node_defs"][0]["prompt_template"] = "the clean prompt"
    published = publish_branch_version(base, branch, publisher="alice",
                                       public=True).branch_version_id

    authenticate("bob")
    assert _ext("get_branch_version", branch_version_id=history) == {
        "error": f"Version '{history}' not found."}
    listed = _ext("list_branch_versions", branch_def_id="alice-open")
    assert [v["branch_version_id"] for v in listed["versions"]] == [published]
    assert SECRET not in json.dumps(listed)
    seen = _ext("get_branch_version", branch_version_id=published)
    assert seen["branch_version_id"] == published

    authenticate("alice")
    mine = _ext("list_branch_versions", branch_def_id="alice-open")
    assert {v["branch_version_id"] for v in mine["versions"]} == {history, published}


def test_publishing_an_identical_snapshot_marks_the_existing_row(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],  # noqa: F811
) -> None:
    """A publish whose content matches an earlier edit snapshot gets that same
    row back; it must come back MARKED, or the publish silently exposes nothing."""
    from tinyassets.branch_versions import get_branch_version, publish_branch_version

    base, _authenticate = branch_authority_env
    branch = _seed_branch(base, branch_def_id="same", author="alice", node_ids=("s",))
    first = publish_branch_version(base, branch, publisher="alice",
                                   notes="patch_branch post-patch snapshot")
    again = publish_branch_version(base, branch, publisher="alice", public=True)
    assert again.branch_version_id == first.branch_version_id
    assert get_branch_version(base, first.branch_version_id).public is True


def test_existing_rows_are_marked_by_how_they_were_minted(tmp_path: Path) -> None:
    """The migration: an explicit publish is marked, patch_branch's own edit
    snapshots are not."""
    from tinyassets.branch_versions import (
        _connect,
        get_branch_version,
        initialize_branch_versions_db,
    )

    initialize_branch_versions_db(tmp_path)
    with _connect(tmp_path) as conn:
        conn.execute("ALTER TABLE branch_versions DROP COLUMN public")
        for vid, notes in (("b@1", ""), ("b@2", "patch_branch pre-patch snapshot"),
                           ("b@3", "v2 of the shape")):
            conn.execute(
                "INSERT INTO branch_versions (branch_version_id, branch_def_id, content_hash, "
                "snapshot_json, notes, publisher, published_at) VALUES (?, 'b', ?, '{}', ?, "
                "'alice', '2026-01-01')", (vid, vid, notes))
    initialize_branch_versions_db(tmp_path)
    assert [get_branch_version(tmp_path, v).public for v in ("b@1", "b@2", "b@3")] == [
        True, False, True]


@pytest.mark.parametrize("action", ["fork_tree", "describe_branch"])
def test_lineage_hides_unpublished_versions(
    branch_authority_env, action,  # noqa: F811 - imported fixture
):
    from tinyassets.branch_versions import publish_branch_version

    base, authenticate = branch_authority_env
    branch = _seed_branch(base, branch_def_id="root", author="alice", node_ids=("s",))
    private_version = publish_branch_version(base, branch, publisher="alice").branch_version_id
    _seed_branch(base, branch_def_id="child", author="alice", fork_from=private_version)
    authenticate("bob")
    seen = _ext(action, branch_def_id="root")
    assert "child" not in json.dumps(seen), seen
    authenticate("alice")
    assert "child" in json.dumps(_ext(action, branch_def_id="root"))


def test_public_node_history_does_not_expose_private_edit_audits(
    branch_authority_env,  # noqa: F811 - imported fixture
):
    from tinyassets.daemon_server import update_branch_definition
    from tinyassets.runs import record_node_edit_audit

    base, authenticate = branch_authority_env
    branch = _seed_branch(base, branch_def_id="node-history", author="alice", node_ids=("s",))
    current = branch["node_defs"][0]
    record_node_edit_audit(
        base, branch_def_id="node-history", version_before=1, version_after=2,
        nodes_changed=["s"], node_before={**current, "prompt_template": SECRET},
        node_after=current,
    )
    update_branch_definition(base, branch_def_id="node-history", updates={"version": 2})
    authenticate("bob")
    seen = _ext("list_node_versions", branch_def_id="node-history", node_id="s")
    assert SECRET not in json.dumps(seen), seen
    assert len(seen["versions"]) == 1
    authenticate("alice")
    assert SECRET in json.dumps(
        _ext("list_node_versions", branch_def_id="node-history", node_id="s"))


@pytest.mark.parametrize("reader", ["leaderboard", "canonical", "handoff"])
def test_indirect_readers_hide_unpublished_versions(
    branch_authority_env, reader,  # noqa: F811 - imported fixture
):
    from tinyassets.api.canonical_dispatch import _latest_published_version_id
    from tinyassets.api.quality_leaderboard import _latest_active_version_id
    from tinyassets.branch_versions import mark_versions_public, publish_branch_version
    from tinyassets.handoffs.models import HandoffValidationError
    from tinyassets.handoffs.service import list_declarations

    base, authenticate = branch_authority_env
    branch = _seed_branch(base, branch_def_id="indirect", author="alice", node_ids=("s",))
    vid = publish_branch_version(base, branch, publisher="alice").branch_version_id
    authenticate("bob")
    if reader == "handoff":
        with pytest.raises(HandoffValidationError, match="not found"):
            list_declarations(actor_id="bob", base_path=base, branch_version_id=vid)
        mark_versions_public(base, [vid])
        assert list_declarations(actor_id="bob", base_path=base,
                                 branch_version_id=vid)["branch_version_id"] == vid
    else:
        read = (_latest_active_version_id if reader == "leaderboard"
                else _latest_published_version_id)
        assert not read(base, branch_def_id="indirect")
        mark_versions_public(base, [vid])
        assert read(base, branch_def_id="indirect") == vid


@pytest.mark.parametrize("actor,provenance", [("bob", "own"), ("alice", "public-foreign")])
def test_nested_invoke_cannot_run_unpublished_history(
    branch_authority_env, monkeypatch, actor, provenance,  # noqa: F811 - imported fixture
):
    from types import SimpleNamespace

    from tinyassets.branch_versions import mark_versions_public, publish_branch_version
    from tinyassets.branches import NodeDefinition
    from tinyassets.graph_compiler import (
        BranchExecutionContext,
        CompilerError,
        _build_invoke_branch_version_node,
    )

    base, _authenticate = branch_authority_env
    branch = _seed_branch(base, branch_def_id="nested", author="alice", node_ids=("s",))
    vid = publish_branch_version(base, branch, publisher="alice").branch_version_id
    called = []

    def launch(*args, **kwargs):
        called.append(kwargs["branch_version_id"])
        return SimpleNamespace(run_id="child-run")

    monkeypatch.setattr("tinyassets.runs.execute_branch_version_async", launch)
    node = NodeDefinition(node_id="invoke", display_name="Invoke",
                          invoke_branch_version_spec={"branch_version_id": vid,
                                                      "wait_mode": "async"})
    invoke = _build_invoke_branch_version_node(
        node, base_path=base, event_sink=None,
        execution_context=BranchExecutionContext(actor=actor, universe_id="u",
                                                 caller_provenance=provenance),
    )
    with pytest.raises(CompilerError, match="not available"):
        invoke({})
    assert called == []
    mark_versions_public(base, [vid])
    invoke({})
    assert called == [vid]


def test_suggest_edit_filters_private_run_context(
    branch_authority_env, monkeypatch,  # noqa: F811 - imported fixture
):
    base, authenticate = branch_authority_env
    _seed_branch(base, branch_def_id="suggest", author="alice", node_ids=("s",))
    authenticate("bob")
    monkeypatch.setattr("tinyassets.runs.list_runs", lambda *a, **k: [{"run_id": "private"}])
    monkeypatch.setattr("tinyassets.runs.node_output_from_run",
                        lambda *a, **k: {"detail": {"output": SECRET}})
    monkeypatch.setattr("tinyassets.runs.list_judgments",
                        lambda *a, **k: [{"run_id": "private", "text": SECRET}])
    monkeypatch.setattr("tinyassets.runs.get_run", lambda *a, **k: {"run_id": "private"})
    monkeypatch.setattr("tinyassets.api.runs._run_read_allowed", lambda row: False)
    seen = _ext("suggest_node_edit", branch_def_id="suggest", node_id="s")
    assert SECRET not in json.dumps(seen), seen
