"""PR-175: github_merge effector is head-SHA-bound and fail-closed."""

from __future__ import annotations

import json
from types import SimpleNamespace

from workflow import effectors
from workflow.credential_vault import write_credential_vault
from workflow.effectors import github_merge

_DEST = "Jonnyton/Workflow"
_HEAD = "a" * 40
_OTHER_HEAD = "b" * 40


def _packet(**payload):
    data = {
        "sink": github_merge.EXTERNAL_WRITE_SINK_GITHUB_MERGE,
        "destination": _DEST,
        "payload": {
            "pr_number": 1325,
            "expected_head_sha": _HEAD,
            "authorization": {
                "mode": github_merge.AUTHORIZATION_MODE_GITHUB_BRANCH_PROTECTION,
            },
            **payload,
        },
    }
    return {"merge_packet": data}


def _run(run_state=None, base_path=None):
    return github_merge.run_github_merge_effector(
        node_id="merge",
        output_keys=["merge_packet"],
        run_state=_packet() if run_state is None else run_state,
        base_path=base_path,
    )


def _with_capability(monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PR_CAPABILITIES",
        json.dumps({_DEST: "capability-token"}),
    )


def _scripted_api(responses):
    def fake(*, method, path, capability_token, body=None):
        fake.calls.append((method, path, capability_token, body))
        for matcher, result in responses:
            if matcher(method, path):
                return result
        raise AssertionError(f"no scripted response for {method} {path}")

    fake.calls = []
    return fake


def _open_pr(head_sha=_HEAD):
    return {
        "state": "open",
        "draft": False,
        "head": {"sha": head_sha},
    }


def test_missing_authorization_fails_before_github(monkeypatch):
    _with_capability(monkeypatch)
    fake = _scripted_api([])
    monkeypatch.setattr(github_merge, "_github_api", fake)
    state = _packet(authorization={})
    result = _run(state)
    assert result["error_kind"] == "missing_merge_authorization"
    assert fake.calls == []


def test_head_sha_mismatch_refuses_stale_authorization(monkeypatch):
    _with_capability(monkeypatch)
    fake = _scripted_api([
        (lambda m, p: m == "GET" and p.endswith("/pulls/1325"), (_open_pr(_OTHER_HEAD), None)),
    ])
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run()
    assert result["error_kind"] == "head_sha_mismatch"
    assert result["expected_head_sha"] == _HEAD
    assert result["actual_head_sha"] == _OTHER_HEAD
    assert [call[0] for call in fake.calls] == ["GET"]


def test_github_branch_protection_block_is_fail_closed(monkeypatch):
    _with_capability(monkeypatch)
    fake = _scripted_api([
        (lambda m, p: m == "GET" and p.endswith("/pulls/1325"), (_open_pr(), None)),
        (
            lambda m, p: m == "PUT" and p.endswith("/pulls/1325/merge"),
            (None, {"http_status": 405, "detail": "Required reviews are missing"}),
        ),
    ])
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run()
    assert result["error_kind"] == "github_merge_blocked"
    assert result["http_status"] == 405
    assert fake.calls[1][3]["sha"] == _HEAD


def test_successful_merge_is_bound_to_expected_head_sha(monkeypatch):
    _with_capability(monkeypatch)
    fake = _scripted_api([
        (lambda m, p: m == "GET" and p.endswith("/pulls/1325"), (_open_pr(), None)),
        (
            lambda m, p: m == "PUT" and p.endswith("/pulls/1325/merge"),
            ({"merged": True, "sha": "mergecommit", "message": "merged"}, None),
        ),
    ])
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run()
    assert result["merged"] is True
    assert result["head_sha"] == _HEAD
    assert result["merge_commit_sha"] == "mergecommit"
    assert fake.calls[1][3] == {"sha": _HEAD, "merge_method": "squash"}


def test_missing_capability_returns_dry_run(monkeypatch):
    monkeypatch.delenv("WORKFLOW_GITHUB_PR_CAPABILITIES", raising=False)
    fake = _scripted_api([])
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run()
    assert result["dry_run"] is True
    assert result["reason"] == "missing_capability"
    assert fake.calls == []


def test_vault_capability_overrides_env_when_base_path_is_bound(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "WORKFLOW_GITHUB_PR_CAPABILITIES",
        json.dumps({_DEST: "env-token"}),
    )
    write_credential_vault(
        tmp_path,
        [
            {
                "credential_type": "vcs",
                "service": "github",
                "destination": _DEST,
                "purpose": "write",
                "token": "vault-token",
            }
        ],
    )
    fake = _scripted_api([
        (lambda m, p: m == "GET" and p.endswith("/pulls/1325"), (_open_pr(), None)),
        (
            lambda m, p: m == "PUT" and p.endswith("/pulls/1325/merge"),
            ({"merged": True, "sha": "mergecommit"}, None),
        ),
    ])
    monkeypatch.setattr(github_merge, "_github_api", fake)

    result = _run(base_path=tmp_path)

    assert result["merged"] is True
    assert fake.calls[0][2] == "vault-token"
    assert fake.calls[1][2] == "vault-token"


def test_operator_kill_switch_returns_dry_run(monkeypatch):
    monkeypatch.setenv("WORKFLOW_EXTERNAL_WRITE_DRY_RUN", "1")
    fake = _scripted_api([])
    monkeypatch.setattr(github_merge, "_github_api", fake)
    result = _run()
    assert result["dry_run"] is True
    assert result["reason"] == "operator_kill_switch_active"
    assert fake.calls == []


def test_package_run_effects_dispatches_github_merge(monkeypatch):
    def fake_merge(**kwargs):
        return {"merged": True, "node_id": kwargs["node_id"]}

    monkeypatch.setattr(effectors, "run_github_merge_effector", fake_merge)
    branch = SimpleNamespace(
        node_defs=[
            SimpleNamespace(
                node_id="merge-node",
                output_keys=["merge_packet"],
                effects=[github_merge.EXTERNAL_WRITE_SINK_GITHUB_MERGE],
            )
        ]
    )
    result = effectors.run_effects_for_branch(branch=branch, run_state=_packet())
    assert result == {
        "merge-node": {
            github_merge.EXTERNAL_WRITE_SINK_GITHUB_MERGE: {
                "merged": True,
                "node_id": "merge-node",
            }
        }
    }
