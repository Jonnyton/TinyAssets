"""Patch-loop S3 (Codex adapt round 2) — authoring persists the sandbox
classification, and VALIDATE matches the runtime fail-closed gate.

FINDING 1 (behavior): a spec carrying ``requires_sandbox`` / ``node_kind`` must
persist through EVERY authoring surface — build_branch, node-ref copy, and
update/edit — not silently drop to False/"" (which would let a coding node be
stored unclassified and never get the hardened sandbox posture).

FINDING 2 (behavior): validate_branch must use the SAME effective gate as
runtime (``enforce_os_sandbox`` → whole-process OS-isolation attestation). A
coding branch on an unattested host must report ``runnable=False`` +
``sandbox_blocked=True`` at VALIDATE time, so a user learns before run time — not
via a fail-closed error mid-run. With attestation set, it is runnable + clean.

Behavior tests (not implementation tests) so they survive the S3→main rebase
regardless of whether S2's generic passthrough or direct threading wins.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def ext_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "tester")
    # Default: NOT attested (the current-droplet posture). Individual tests opt
    # into attestation via monkeypatch.setenv.
    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)
    from tinyassets import universe_server as us

    importlib.reload(us)
    yield us, base
    importlib.reload(us)


def _call(us, tool: str, action: str, **kwargs):
    return json.loads(getattr(us, tool)(action=action, **kwargs))


def _load(base: Path, bid: str) -> dict:
    from tinyassets.daemon_server import get_branch_definition

    return get_branch_definition(base, branch_def_id=bid)


def _node(branch: dict, nid: str) -> dict:
    for n in branch["node_defs"]:
        if n["node_id"] == nid:
            return n
    raise AssertionError(f"node '{nid}' not on branch")


def _build(us, *, node: dict, entry: str, name: str = "b") -> str:
    spec = {
        "name": name,
        "entry_point": entry,
        "node_defs": [node],
        "edges": [
            {"from": "START", "to": entry},
            {"from": entry, "to": "END"},
        ],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    res = _call(us, "extensions", "build_branch", spec_json=json.dumps(spec))
    assert res["status"] == "built", res
    return res["branch_def_id"]


def _coding_node(nid: str = "draft_patch") -> dict:
    return {
        "node_id": nid,
        "display_name": "Draft the patch",
        "prompt_template": "implement the fix: {x}",
        "requires_sandbox": True,
        "node_kind": "coding",
    }


# --------------------------------------------------------------------------- #
# FINDING 1 — classification persists through every authoring surface
# --------------------------------------------------------------------------- #


def test_build_branch_persists_sandbox_classification(ext_env):
    us, base = ext_env
    bid = _build(us, node=_coding_node(), entry="draft_patch")
    persisted = _node(_load(base, bid), "draft_patch")
    assert persisted["requires_sandbox"] is True
    assert persisted["node_kind"] == "coding"


def test_node_ref_copy_preserves_sandbox_classification(ext_env):
    us, base = ext_env
    src_bid = _build(us, node=_coding_node(), entry="draft_patch", name="src")
    # A design-only target branch we copy the coding node INTO.
    tgt_bid = _build(
        us,
        node={
            "node_id": "seed",
            "display_name": "Seed",
            "prompt_template": "seed: {x}",
        },
        entry="seed",
        name="tgt",
    )
    res = _call(
        us, "extensions", "add_node",
        branch_def_id=tgt_bid,
        node_id="draft_patch",
        node_ref_json=json.dumps({"source": src_bid, "node_id": "draft_patch"}),
    )
    assert "error" not in res, res
    copied = _node(_load(base, tgt_bid), "draft_patch")
    assert copied["requires_sandbox"] is True
    assert copied["node_kind"] == "coding"


def test_update_node_sets_sandbox_classification(ext_env):
    us, base = ext_env
    # Start from a plain (unclassified) node, then classify it via update.
    bid = _build(
        us,
        node={
            "node_id": "worker",
            "display_name": "Worker",
            "prompt_template": "work: {x}",
        },
        entry="worker",
    )
    before = _node(_load(base, bid), "worker")
    assert before.get("requires_sandbox") in (False, None)
    assert before.get("node_kind", "") == ""

    res = _call(
        us, "extensions", "patch_branch",
        branch_def_id=bid,
        changes_json=json.dumps([
            {
                "op": "update_node",
                "node_id": "worker",
                "requires_sandbox": True,
                "node_kind": "coding",
            }
        ]),
    )
    assert res.get("status") != "rejected", res
    after = _node(_load(base, bid), "worker")
    assert after["requires_sandbox"] is True
    assert after["node_kind"] == "coding"


def test_patch_nodes_can_set_requires_sandbox(ext_env):
    us, base = ext_env
    bid = _build(
        us,
        node={
            "node_id": "worker",
            "display_name": "Worker",
            "prompt_template": "work: {x}",
        },
        entry="worker",
    )
    res = _call(
        us, "extensions", "patch_nodes",
        branch_def_id=bid,
        field="requires_sandbox",
        value="true",
    )
    assert res.get("status") != "rejected", res
    after = _node(_load(base, bid), "worker")
    assert after["requires_sandbox"] is True


# --------------------------------------------------------------------------- #
# FINDING 2 — validate matches the runtime attestation gate
# --------------------------------------------------------------------------- #


def test_validate_blocks_coding_branch_no_runner(ext_env, monkeypatch):
    # REFRAME (Codex S3 REJECT R4): a coding/repo branch is NOT runnable — there
    # is no per-job sandbox runner in this deploy — surfaced at VALIDATE with the
    # honest runner reason (never "ready because a CLI is on PATH").
    us, _base = ext_env
    monkeypatch.delenv("TINYASSETS_OS_SANDBOX_ATTESTED", raising=False)
    bid = _build(us, node=_coding_node(), entry="draft_patch")

    res = _call(us, "extensions", "validate_branch", branch_def_id=bid)
    assert res["valid"] is True  # structurally valid...
    assert res["runnable"] is False  # ...but NOT runnable (no runner)
    assert res["sandbox_blocked"] is True
    assert any("runner" in w for w in res["sandbox_warnings"])


def test_validate_blocks_coding_branch_even_under_attestation(ext_env, monkeypatch):
    # Attestation alone is NOT the runner (attestation ≠ prepared checkout /
    # isolation). A coding branch is blocked EVEN attested until the runner lands.
    us, _base = ext_env
    monkeypatch.setenv("TINYASSETS_OS_SANDBOX_ATTESTED", "1")
    bid = _build(us, node=_coding_node(), entry="draft_patch")

    res = _call(us, "extensions", "validate_branch", branch_def_id=bid)
    assert res["runnable"] is False
    assert res["sandbox_blocked"] is True


def test_validate_repo_exec_and_repo_read_nodes_also_block(ext_env):
    # R5: verify (repo-exec) + investigate (repo-read) are repo-touching too.
    us, _base = ext_env
    for nid, tmpl in (("verify", "run {x}"), ("investigate", "inspect {x}")):
        bid = _build(
            us,
            node={"node_id": nid, "display_name": nid, "prompt_template": tmpl},
            entry=nid,
            name=nid,
        )
        res = _call(us, "extensions", "validate_branch", branch_def_id=bid)
        assert res["sandbox_blocked"] is True, nid
        assert res["runnable"] is False, nid


def test_validate_design_only_branch_runnable(ext_env):
    # A pure text branch is unaffected by the runner gate.
    us, _base = ext_env
    bid = _build(
        us,
        node={
            "node_id": "summarize",
            "display_name": "Summarize",
            "prompt_template": "summarize: {x}",
        },
        entry="summarize",
    )
    res = _call(us, "extensions", "validate_branch", branch_def_id=bid)
    assert res["runnable"] is True
    assert res["sandbox_blocked"] is False
    assert res["sandbox_warnings"] == []


def test_validate_fails_closed_on_sandbox_check_exception(ext_env, monkeypatch):
    # R4/5b: an exception in the readiness check must NOT swallow into
    # runnable=true — it fails CLOSED with the error surfaced.
    import tinyassets.sandbox_policy as sp_mod

    us, _base = ext_env

    def _boom():
        raise RuntimeError("readiness blew up")

    monkeypatch.setattr(sp_mod, "coding_nodes_runnable", _boom)
    bid = _build(us, node=_coding_node(), entry="draft_patch")

    res = _call(us, "extensions", "validate_branch", branch_def_id=bid)
    assert res["sandbox_blocked"] is True
    assert res["runnable"] is False
    assert any("fail closed" in w.lower() for w in res["sandbox_warnings"])


# --------------------------------------------------------------------------- #
# Codex r10 #1 — run_branch REFUSES a sandbox-blocked branch at QUEUE TIME
# (synchronous structured refusal, no run_id) instead of queue-then-fail.
# --------------------------------------------------------------------------- #


def test_run_branch_refuses_coding_branch_at_queue_time(ext_env):
    # The queue-time refusal reads the SAME readiness check validate uses
    # (branch_sandbox_status). A coding branch is structurally valid but must be
    # refused synchronously — no run_id, so nothing is ever enqueued.
    from tinyassets.api.runs import _action_run_branch

    _us, _base = ext_env
    bid = _build(_us, node=_coding_node(), entry="draft_patch")

    res = json.loads(_action_run_branch({"branch_def_id": bid}))
    assert res.get("sandbox_blocked") is True, res
    assert "run_id" not in res, res  # nothing queued
    assert "draft_patch" in res.get("repo_touching_nodes", []), res
    assert any("runner" in w for w in res.get("sandbox_warnings", [])), res


def test_run_branch_repo_exec_and_repo_read_also_refused(ext_env):
    # repo_exec (verify) + repo_read (investigate) are repo-touching too — the
    # enqueue refusal covers the whole repo-touching set, not just coding.
    from tinyassets.api.runs import _action_run_branch

    _us, _base = ext_env
    for nid, tmpl in (("verify", "run {x}"), ("investigate", "inspect {x}")):
        bid = _build(
            _us,
            node={"node_id": nid, "display_name": nid, "prompt_template": tmpl},
            entry=nid,
            name=nid,
        )
        res = json.loads(_action_run_branch({"branch_def_id": bid}))
        assert res.get("sandbox_blocked") is True, (nid, res)
        assert "run_id" not in res, (nid, res)


# --------------------------------------------------------------------------- #
# C1a — authoring rejects non-finite / non-positive timeout_seconds (nothing
# persisted), so a bad value can never reach config construction.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", "0", "-3.5", "inf", "nan"])
def test_build_branch_rejects_bad_timeout_seconds(ext_env, bad):
    us, base = ext_env
    spec = {
        "name": "b",
        "entry_point": "n",
        "node_defs": [{
            "node_id": "n",
            "display_name": "N",
            "prompt_template": "do it: {x}",
            "timeout_seconds": bad,
        }],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    res = _call(us, "extensions", "build_branch", spec_json=json.dumps(spec))
    # Rejected at authoring — nothing built/persisted.
    assert res.get("status") != "built", res


def test_update_node_rejects_bad_timeout_seconds(ext_env):
    us, base = ext_env
    bid = _build(
        us,
        node={"node_id": "n", "display_name": "N", "prompt_template": "do it: {x}"},
        entry="n",
    )
    for bad in ("NaN", "Infinity", "-2", "0"):
        res = _call(
            us, "extensions", "patch_branch",
            branch_def_id=bid,
            changes_json=json.dumps([
                {"op": "update_node", "node_id": "n", "timeout_seconds": bad},
            ]),
        )
        assert res.get("status") == "rejected", (bad, res)
    # A good finite positive value still works.
    ok = _call(
        us, "extensions", "patch_branch",
        branch_def_id=bid,
        changes_json=json.dumps([
            {"op": "update_node", "node_id": "n", "timeout_seconds": 45},
        ]),
    )
    assert ok.get("status") != "rejected", ok


def test_patch_nodes_rejects_bad_timeout_seconds(ext_env):
    # C1a (Fable non-blocking r9 #5): the third authoring surface (patch_nodes
    # bulk-set) must also reject non-finite / non-positive timeout_seconds.
    us, _base = ext_env
    bid = _build(
        us,
        node={"node_id": "n", "display_name": "N", "prompt_template": "do it: {x}"},
        entry="n",
    )
    for bad in ("NaN", "Infinity", "-1", "0", "-3.5"):
        res = _call(
            us, "extensions", "patch_nodes",
            branch_def_id=bid, field="timeout_seconds", value=bad,
        )
        assert res.get("status") == "rejected", (bad, res)
    ok = _call(
        us, "extensions", "patch_nodes",
        branch_def_id=bid, field="timeout_seconds", value="45",
    )
    assert ok.get("status") != "rejected", ok


# --------------------------------------------------------------------------- #
# Codex S3 r11 — mutable capability metadata must not bypass the sandbox gate.
#   #2 reject unknown node_kind; #3 forbid a downgrade of the sandbox class;
#   #4 a security-metadata change invalidates a source_code node's approval.
# --------------------------------------------------------------------------- #


def test_build_branch_rejects_unknown_node_kind(ext_env):
    # #2: an unrecognized node_kind must be REJECTED at authoring, never silently
    # downgraded to the least-restricted "text" class.
    us, _base = ext_env
    spec = {
        "name": "b", "entry_point": "n",
        "node_defs": [{
            "node_id": "n", "display_name": "N",
            "prompt_template": "do: {x}", "node_kind": "totally_bogus_kind",
        }],
        "edges": [{"from": "START", "to": "n"}, {"from": "n", "to": "END"}],
        "state_schema": [{"name": "x", "type": "str"}],
    }
    res = _call(us, "extensions", "build_branch", spec_json=json.dumps(spec))
    assert res.get("status") != "built", res


def test_update_node_rejects_unknown_node_kind(ext_env):
    us, _base = ext_env
    bid = _build(
        us,
        node={"node_id": "n", "display_name": "N", "prompt_template": "do: {x}"},
        entry="n",
    )
    res = _call(
        us, "extensions", "patch_branch", branch_def_id=bid,
        changes_json=json.dumps([
            {"op": "update_node", "node_id": "n", "node_kind": "bogus_kind"},
        ]),
    )
    assert res.get("status") == "rejected", res


def test_patch_nodes_rejects_unknown_node_kind(ext_env):
    us, _base = ext_env
    bid = _build(
        us,
        node={"node_id": "n", "display_name": "N", "prompt_template": "do: {x}"},
        entry="n",
    )
    res = _call(
        us, "extensions", "patch_nodes",
        branch_def_id=bid, field="node_kind", value="bogus_kind",
    )
    assert res.get("status") == "rejected", res


def test_update_node_forbids_sandbox_downgrade(ext_env):
    # #3: a coding (repo-touching) node may NOT be downgraded to text.
    us, _base = ext_env
    bid = _build(
        us,
        node={"node_id": "c", "display_name": "C", "prompt_template": "do: {x}",
              "node_kind": "coding"},
        entry="c",
    )
    res = _call(
        us, "extensions", "patch_branch", branch_def_id=bid,
        changes_json=json.dumps([
            {"op": "update_node", "node_id": "c", "node_kind": "text"},
        ]),
    )
    assert res.get("status") == "rejected", res
    # Escalation the other way (text → coding) stays allowed.
    bid2 = _build(
        us,
        node={"node_id": "t", "display_name": "T", "prompt_template": "do: {x}"},
        entry="t", name="b2",
    )
    ok = _call(
        us, "extensions", "patch_branch", branch_def_id=bid2,
        changes_json=json.dumps([
            {"op": "update_node", "node_id": "t", "requires_sandbox": True},
        ]),
    )
    assert ok.get("status") != "rejected", ok


def test_patch_nodes_forbids_sandbox_downgrade(ext_env):
    us, _base = ext_env
    bid = _build(
        us,
        node={"node_id": "c", "display_name": "C", "prompt_template": "do: {x}",
              "requires_sandbox": True},
        entry="c",
    )
    res = _call(
        us, "extensions", "patch_nodes",
        branch_def_id=bid, field="requires_sandbox", value="false",
    )
    assert res.get("status") == "rejected", res


def test_update_node_clears_source_approval_on_metadata_change(ext_env):
    # #4: a source_code node's approval is bound to its security metadata; a change
    # to node_kind / requires_sandbox invalidates the approval (re-review needed).
    us, base = ext_env
    src = "def run(state):\n    return {}\n"
    bid = _build(
        us,
        node={"node_id": "sc", "display_name": "Custom", "source_code": src},
        entry="sc",
    )
    # Genuinely approve the source_code node via the host approval action.
    appr = _call(
        us, "extensions", "approve_source_code",
        branch_def_id=bid, node_id="sc", reason="reviewed",
    )
    assert appr.get("status") == "approved", appr
    before = _node(_load(base, bid), "sc")
    assert before["approved"] is True and before["approved_source_hash"], before
    # Escalate node_kind (allowed direction) — the metadata change must still
    # invalidate the approval, since it covered the old source+kind+sandbox tuple.
    res = _call(
        us, "extensions", "patch_branch", branch_def_id=bid,
        changes_json=json.dumps([
            {"op": "update_node", "node_id": "sc", "node_kind": "coding"},
        ]),
    )
    assert res.get("status") != "rejected", res
    after = _node(_load(base, bid), "sc")
    assert after["approved"] is False, after
    assert not after.get("approved_source_hash"), after


def test_run_branch_version_fails_closed_on_malformed_snapshot(ext_env, monkeypatch):
    # #5: a version-run must FAIL CLOSED on an unclassifiable snapshot, not
    # continue into execution.
    from tinyassets.api import runs as runs_mod

    us, _base = ext_env

    class _BV:
        # A non-dict snapshot makes BranchDefinition.from_dict raise → the queue
        # gate must classify this as unrunnable and refuse (never execute).
        snapshot = "this-is-not-a-branch-dict"

    monkeypatch.setattr(
        "tinyassets.branch_versions.get_branch_version", lambda *a, **k: _BV(),
    )
    res = json.loads(
        runs_mod._action_run_branch_version({"branch_version_id": "bv-x"})
    )
    assert res.get("sandbox_blocked") is True, res
    assert "run_id" not in res, res
