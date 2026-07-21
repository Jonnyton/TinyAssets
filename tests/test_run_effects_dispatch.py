"""Codex r11 #3: the PUBLIC aggregate dispatcher (run_effects_for_branch) must
thread the AUTHORITATIVE branch_def_id to the merge effector.

Before the fix, `_branch_without_github_merge` stripped `branch_def_id`, so the
merge effector resolved the merge preference from MODEL-emitted packet identity
instead of the owner binding — the trust-from-packet hole. This exercises the
real dispatcher path (the bundle test bypasses it).
"""

from __future__ import annotations

from types import SimpleNamespace

from tinyassets.effectors import (
    EXTERNAL_WRITE_SINK_GITHUB_MERGE,
    run_effects_for_branch,
)
from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_HEAD = "a" * 40


def _branch(branch_def_id):
    node = SimpleNamespace(
        node_id="merge",
        output_keys=["merge_packet"],
        effects=[EXTERNAL_WRITE_SINK_GITHUB_MERGE],
    )
    return SimpleNamespace(branch_def_id=branch_def_id, node_defs=[node])


def _run_state(packet_branch_def_id=""):
    payload = {"pr_number": 7, "expected_head_sha": _HEAD, "base_ref": "main"}
    if packet_branch_def_id:
        payload["branch_def_id"] = packet_branch_def_id  # spoof attempt
    return {
        "merge_packet": {
            "sink": EXTERNAL_WRITE_SINK_GITHUB_MERGE,
            "destination": _DEST,
            "payload": payload,
        }
    }


def test_dispatcher_resolves_preference_from_authoritative_branch(tmp_path):
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id="patch_loop_reference",
        merge_preference="manual", bound_by="owner",
    )
    evidence = run_effects_for_branch(
        branch=_branch("patch_loop_reference"),
        run_state=_run_state(),
        base_path=str(tmp_path),
    )
    merge = evidence["merge"][EXTERNAL_WRITE_SINK_GITHUB_MERGE]
    assert merge["branch_def_id"] == "patch_loop_reference"  # from run context
    assert merge["merge_preference"] == "manual"
    assert merge["action"] == "await_owner_merge"


def test_dispatcher_ignores_packet_spoofed_branch_def_id(tmp_path):
    """A packet claiming another branch's `auto` binding must be ignored — the
    AUTHORITATIVE branch (from the run context) governs the resolution."""
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id="bd_auto", merge_preference="auto", bound_by="owner",
    )
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id="bd_manual", merge_preference="manual", bound_by="owner",
    )
    evidence = run_effects_for_branch(
        branch=_branch("bd_manual"),           # the real branch
        run_state=_run_state("bd_auto"),        # the packet lies
        base_path=str(tmp_path),
    )
    merge = evidence["merge"][EXTERNAL_WRITE_SINK_GITHUB_MERGE]
    assert merge["branch_def_id"] == "bd_manual"
    assert merge["merge_preference"] == "manual"  # NOT the packet's auto
    assert merge["action"] == "await_owner_merge"
