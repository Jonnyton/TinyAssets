"""Patch-loop S4 (GitHub-native): the merge effector maps the owner-bound merge
PREFERENCE to the right native GitHub action and RECORDS the exact call.

Phase 1 records/schedules only — no live merge. Autonomous preferences
(auto / not_before) FAIL CLOSED unless a verified review gate is proven via the
injected GitHub client. GitHub is authoritative for the merge itself.
"""

from __future__ import annotations

from tests.fake_github import InMemoryGitHubApi, code_owner_review_ruleset
from tinyassets.effectors import github_merge
from tinyassets.storage import review_queue as rq

_DEST = "Owner/Repo"
_HEAD = "a" * 40
_PR = 7
_BDID = "patch_loop_reference"


def _packet():
    return {
        "merge_packet": {
            "sink": github_merge.EXTERNAL_WRITE_SINK_GITHUB_MERGE,
            "destination": _DEST,
            "payload": {
                "pr_number": _PR,
                "expected_head_sha": _HEAD,
                "base_ref": "main",
                "merge_method": "squash",
            },
        }
    }


def _run(tmp_path, **kw):
    # Default the gate inputs the hardened autonomous path needs; individual
    # tests override (e.g. drop the api to assert fail-closed).
    kw.setdefault("app_actor_id", 4242)
    kw.setdefault("expected_owner", "owner")
    return github_merge.run_github_merge_effector(
        node_id="merge", output_keys=["merge_packet"], run_state=_packet(),
        base_path=str(tmp_path), run_id="run-1",
        authoritative_branch_def_id=_BDID, **kw,
    )


def _bind(tmp_path, preference, **kw):
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id=_BDID, merge_preference=preference, bound_by="owner", **kw
    )


# ── manual: owner-triggered; records the merge_pr call ────────────────────────


def test_manual_records_merge_call_no_api_needed(tmp_path):
    _bind(tmp_path, "manual")
    out = _run(tmp_path)  # no github_api needed for manual
    assert out["action"] == "await_owner_merge"
    assert out["github_call"]["kind"] == "merge_pr"
    assert out["github_call"]["params"]["sha"] == _HEAD
    assert out["merge_preference"] == "manual"


# ── auto: requires a verified gate ────────────────────────────────────────────


def test_auto_without_api_fails_closed(tmp_path):
    _bind(tmp_path, "auto")
    out = _run(tmp_path)  # no api wired
    assert out["error_kind"] == "review_gate_unverifiable"
    assert "manual" in out["error"]


def test_auto_with_verified_gate_records_enable_auto_merge(tmp_path):
    _bind(tmp_path, "auto")
    api = InMemoryGitHubApi()  # default: code-owner ruleset + CODEOWNERS present
    out = _run(tmp_path, github_api=api)
    assert out["action"] == "enable_auto_merge"
    assert out["github_call"]["kind"] == "enable_auto_merge"
    assert out["setup"]["gated"] is True


def test_auto_refuses_when_gate_not_configured(tmp_path):
    _bind(tmp_path, "auto")
    api = InMemoryGitHubApi(rulesets=[], codeowners=None)  # nothing configured
    out = _run(tmp_path, github_api=api)
    assert out["error_kind"] == "review_gate_not_configured"
    assert "required_code_owner_review_rule" in out["setup"]["missing"]
    assert "codeowners_catchall_owner" in out["setup"]["missing"]


def test_auto_refuses_when_app_is_bypass_actor(tmp_path):
    _bind(tmp_path, "auto")
    rs = code_owner_review_ruleset(
        bypass_actors=[{"actor_id": 4242, "actor_type": "Integration", "bypass_mode": "always"}]
    )
    api = InMemoryGitHubApi(rulesets=[rs])
    out = _run(tmp_path, github_api=api, app_actor_id=4242)
    assert out["error_kind"] == "review_gate_not_configured"
    assert "app_not_bypass_actor" in out["setup"]["missing"]


# ── not_before: verified gate, then a single durable timer ───────────────────


def test_not_before_schedules_timer_and_records_on_fire_call(tmp_path):
    _bind(tmp_path, "not_before", not_before_delay_s=3600)
    api = InMemoryGitHubApi()
    out = _run(tmp_path, github_api=api, now=1000.0)
    assert out["action"] == "scheduled_not_before"
    assert out["not_before"] == 1000.0 + 3600
    assert out["github_call_on_fire"]["kind"] == "enable_auto_merge"
    # A durable timer is scheduled.
    due = rq.due_not_before_timers(tmp_path, now=1000.0 + 3600 + 1)
    assert len(due) == 1 and due[0]["pr_number"] == _PR


# ── packet validation ─────────────────────────────────────────────────────────


def test_missing_head_sha_fails_closed(tmp_path):
    _bind(tmp_path, "manual")
    packet = _packet()
    packet["merge_packet"]["payload"].pop("expected_head_sha")
    out = github_merge.run_github_merge_effector(
        node_id="merge", output_keys=["merge_packet"], run_state=packet,
        base_path=str(tmp_path), authoritative_branch_def_id=_BDID,
    )
    assert out["error_kind"] == "missing_expected_head_sha"


def test_no_matching_packet(tmp_path):
    out = github_merge.run_github_merge_effector(
        node_id="merge", output_keys=["merge_packet"], run_state={},
        base_path=str(tmp_path), authoritative_branch_def_id=_BDID,
    )
    assert out["error_kind"] == "no_matching_packet"
