"""A branch's versions are exactly as readable as the branch.

patch_branch mints a version snapshot before and after every edit, private
branches included, so a branch's version history is its prompts over time,
including whatever the owner later removed. The version readers did no check at
all. Any signed-in caller could reach them through the connector's deprecated
``extensions`` handle (hidden from tools/list, still dispatchable) and read
another user's private branch history. Astra refute review, 2026-09-30.

Driven through that connector handle, because that is the route the leak took.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from tests.test_branch_read_authority import (  # noqa: F401 - fixture
    _publish,
    _seed_branch,
    branch_authority_env,
)

SECRET = "ALICE PRIVATE PROMPT"


def _ext(action: str, **kwargs) -> dict:
    from tinyassets.universe_server import extensions

    return json.loads(extensions(action=action, **kwargs))


def _alices_private_branch(base: Path) -> str:
    branch = _seed_branch(base, branch_def_id="alice-private", author="alice",
                          visibility="private", node_ids=("step",))
    branch["node_defs"][0]["prompt_template"] = SECRET
    return _publish(base, branch, "alice")


def test_another_user_cannot_read_a_private_branchs_versions(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],  # noqa: F811
) -> None:
    base, authenticate = branch_authority_env
    version_id = _alices_private_branch(base)

    authenticate("bob")
    listed = _ext("list_branch_versions", branch_def_id="alice-private")
    one = _ext("get_branch_version", branch_version_id=version_id)
    assert SECRET not in json.dumps(listed) and SECRET not in json.dumps(one)
    # Unreadable reads exactly like absent: the refusal confirms nothing.
    assert listed == {"error": "Branch 'alice-private' not found."}
    assert _ext("list_branch_versions", branch_def_id="no-such-branch") == {
        "error": "Branch 'no-such-branch' not found."}
    assert one == {"error": f"Version '{version_id}' not found."}
    assert _ext("get_branch_version", branch_version_id="no-such@00000000") == {
        "error": "Version 'no-such@00000000' not found."}


def test_the_owner_and_everyone_on_a_public_branch_still_read_versions(
    branch_authority_env: tuple[Path, Callable[[str | None], None]],  # noqa: F811
) -> None:
    base, authenticate = branch_authority_env
    version_id = _alices_private_branch(base)
    public = _seed_branch(base, branch_def_id="bob-public", author="bob", node_ids=("s",))
    public_version = _publish(base, public, "bob")

    authenticate("alice")
    own = _ext("get_branch_version", branch_version_id=version_id)
    assert own["branch_version_id"] == version_id
    assert _ext("list_branch_versions", branch_def_id="alice-private")["count"] == 1

    authenticate("carol")
    assert _ext("get_branch_version",
                branch_version_id=public_version)["branch_version_id"] == public_version
    assert _ext("list_branch_versions", branch_def_id="bob-public")["count"] == 1
