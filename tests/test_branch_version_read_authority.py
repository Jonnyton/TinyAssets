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


@pytest.mark.parametrize("tool,arguments", [
    ("extensions", {"action": "list_branches"}),
    ("universe", {"action": "inspect"}),
    ("goals", {"action": "list"}),
    ("gates", {"action": "list_claims"}),
    ("wiki", {"action": "list"}),
])
def test_the_connector_dispatches_no_legacy_fat_tool(tool: str, arguments: dict) -> None:
    """Hidden-but-dispatchable was the route: astra found private runs, versions
    and bindings reachable through gates and goals as well as extensions. The
    registry itself -- what a client can call, listed or not -- is the check."""
    from tinyassets import universe_server

    registered = {t.name for t in asyncio.run(universe_server.mcp.list_tools(run_middleware=False))}
    assert tool not in registered
    assert _via_connector(tool, arguments).startswith("refused")


def test_a_canonical_cannot_name_or_run_a_private_version(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],  # noqa: F811
) -> None:
    """Astra refute, P1: Bob set a personal canonical to Alice's private
    version and ran the goal; the preflight returned the private snapshot's
    input names. The version is now checked where it is set AND where it runs."""
    from tinyassets.api.market import _action_goal_set_canonical
    from tinyassets.api.runs import _action_run_branch_version
    from tinyassets.daemon_server import get_goal, save_goal

    base, authenticate = branch_authority_env
    version_id = _alices_private_branch(base)
    goal = save_goal(base, goal={"goal_id": "open-goal", "name": "Open goal",
                                 "description": "", "author": "carol", "visibility": "public"})
    authenticate("bob")
    refused = json.loads(_action_goal_set_canonical(
        {"goal_id": goal["goal_id"], "scope": "bob", "branch_version_id": version_id}))
    assert refused == {"status": "rejected", "error": f"Branch version '{version_id}' not found."}
    assert version_id not in json.dumps(get_goal(base, goal_id=goal["goal_id"]))

    run = json.loads(_action_run_branch_version({"branch_version_id": version_id}))
    assert SECRET not in json.dumps(run)
    assert run == {"error": f"branch_version_id {version_id!r} not found in branch_versions"}


def test_a_run_view_does_not_render_an_unreadable_branch(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],  # noqa: F811
) -> None:
    """Astra refute, P1: a run a stranger can read re-loaded the CURRENT
    private branch and drew its name, nodes and edges into the diagram."""
    from tinyassets.api.runs import _compose_run_snapshot

    base, authenticate = branch_authority_env
    _alices_private_branch(base)
    record = {"run_id": "r1", "branch_def_id": "alice-private", "status": "completed",
              "actor": "alice", "last_node_id": "", "started_at": None, "finished_at": None,
              "error": "", "output": {}}
    authenticate("bob")
    seen = json.dumps(_compose_run_snapshot(record, []), default=str)
    assert "Step" not in seen and "alice-private\"]" not in seen, seen
    assert "branch not found" in seen

    authenticate("alice")
    assert "Step" in json.dumps(_compose_run_snapshot(record, []), default=str)


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
    public = _seed_branch(base, branch_def_id="bob-public", author="bob", node_ids=("s",))
    public_version = _publish(base, public, "bob")

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
