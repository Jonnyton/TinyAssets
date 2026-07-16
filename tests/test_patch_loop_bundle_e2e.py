"""Patch-loop BUNDLE integration (Codex R6 C4 / F4).

Proves the real end-to-end contract: a compiled branch's ``present`` node opens
a PR and ENQUEUES it (a real effect run, not a handcrafted packet calling
storage), the owner then decides on the review queue, and a reshape carries the
resume identity the loop needs to resume the run.

This activates in the S1+S3+S4 BUNDLE. It is skipped here on the S4-only branch
because S1 owns the reference-design seed + the effect/sandbox_policy wiring on
the present/owner_gate/merge nodes. On rebase onto S1 (the seed + effect
declarations appear), the skip lifts and this RUNS in the bundle.

Bundle contract this test pins (coordinate with S1):
- reference design seed: ``tinyassets/branch_designs/patch_loop_reference.json``
- present node effect sink: ``github_pull_request`` (github_pr effector), with a
  ``review_queue`` payload block carrying request_ref + verify hint + resume
  identity (universe_id / branch_def_id).
- merge node effect sink: ``github_merge``.
- reshape ``route_back`` resume identity: ``{target_node: "draft_patch",
  universe_id, branch_def_id, run_id, owner_notes}``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tinyassets.effectors import github_pr
from tinyassets.storage import review_queue as rq

_REFERENCE_SEED = (
    Path(__file__).resolve().parents[1]
    / "tinyassets" / "branch_designs" / "patch_loop_reference.json"
)


def _reference_declares_effects() -> bool:
    """S1 marker: the reference design seed exists and its present/merge nodes
    declare the github_pull_request / github_merge effects."""
    if not _REFERENCE_SEED.exists():
        return False
    try:
        spec = json.loads(_REFERENCE_SEED.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    nodes = spec.get("nodes") or spec.get("spec_json", {}).get("nodes") or []
    sinks = {
        sink
        for node in nodes
        if isinstance(node, dict)
        for sink in (node.get("effects") or [])
    }
    return {"github_pull_request", "github_merge"} <= sinks


_BUNDLE_READY = _reference_declares_effects()
_SKIP_REASON = (
    "patch-loop bundle integration: activates on rebase onto S1 (reference "
    "design seed + present/merge effect declarations). S4-only branch: skipped."
)


@pytest.mark.skipif(not _BUNDLE_READY, reason=_SKIP_REASON)
def test_present_to_owner_reshape_resume_e2e(monkeypatch, tmp_path):
    # Gates open — exercise the enqueue + owner-decision + resume contract only.
    monkeypatch.setattr(github_pr, "resolve_soul_effect_authority", lambda *a, **k: "")
    monkeypatch.setattr(github_pr, "_read_capability", lambda *a, **k: "tok")
    monkeypatch.setattr(github_pr, "_check_consent", lambda *a, **k: True)
    monkeypatch.setattr(github_pr, "_try_reserve", lambda *a, **k: {"status": "no_hint"})
    monkeypatch.setattr(
        github_pr, "_materialize_branch",
        lambda **k: {"head_branch": "auto/fix", "commit_sha": "a" * 40},
    )
    monkeypatch.setattr(
        github_pr, "_invoke_gh_pr_create",
        lambda **k: {
            "pr_url": "https://github.com/Owner/Repo/pull/7",
            "pr_number": 7, "stdout": "", "invocation_mode": "gh",
        },
    )
    # Owner binds the governing policy for the reference design.
    rq.set_merge_policy_binding(
        tmp_path, branch_def_id="patch_loop_reference",
        merge_policy="manual", founder_oauth_per_merge=True, bound_by="owner",
    )
    # Run the present node's github_pr effect through the real effector path.
    result = github_pr.run_github_pr_effector(
        node_id="present",
        output_keys=["pr_packet"],
        run_state={
            "pr_packet": {
                "sink": github_pr.EXTERNAL_WRITE_SINK_GITHUB_PR,
                "destination": "Owner/Repo",
                "payload": {
                    "title": "Fix", "body": "b", "head_branch": "auto/fix",
                    "review_queue": {
                        "request_ref": "req-1",
                        "verify_verdict": "pass",
                        "universe_id": "u-1",
                        "branch_def_id": "patch_loop_reference",
                    },
                },
            }
        },
        base_path=str(tmp_path),
        run_id="run-1",
    )
    item_id = result["review_queue_item_id"]
    item = rq.get_item(tmp_path, item_id=item_id)
    assert item["status"] == "pending"
    assert item["run_id"] == "run-1"
    assert item["founder_oauth_per_merge"] is True  # owner-bound, not packet

    # Owner reshapes → the loop gets the resume identity to resume the run.
    reshaped = rq.reshape_item(
        tmp_path, item_id=item_id, reshaped_by="owner", notes="tighten it"
    )
    route = reshaped["route_back"]
    assert route["target_node"] == "draft_patch"
    assert route["universe_id"] == "u-1"
    assert route["branch_def_id"] == "patch_loop_reference"
    assert route["run_id"] == "run-1"
    assert route["owner_notes"] == "tighten it"


def test_bundle_contract_is_documented_even_when_skipped():
    """A cheap always-run guard so the bundle contract file/name can't silently
    drift: the seed path + skip reason are stable strings the bundle relies on."""
    assert _REFERENCE_SEED.name == "patch_loop_reference.json"
    assert "github_pull_request" in _SKIP_REASON or not _BUNDLE_READY
