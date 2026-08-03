from __future__ import annotations

import hashlib
import json

import pytest

from tinyassets.effectors import github_pr
from tinyassets.storage import external_write_receipts
from tinyassets.storage.outbound_connections import (
    ProxyRequestError,
    ScopedConnectionProxy,
)

_SHA = "a" * 40


def _identity(**overrides):
    values = {
        "universe_id": "universe-42",
        "automation_id": "automation-7",
        "claim_id": "claim-3",
        "repository": "Owner/Repo",
        "intended_head_sha": _SHA,
    }
    values.update(overrides)
    return github_pr.GitHubPullRequestEffectIdentity(**values)


def _pull(identity, *, number=17, body=None, head_sha=None, repository=None):
    return {
        "number": number,
        "html_url": f"https://github.com/owner/repo/pull/{number}",
        "state": "open",
        "body": body if body is not None else github_pr.github_pr_effect_marker(identity),
        "head": {"sha": head_sha if head_sha is not None else identity.intended_head_sha},
        "base": {"repo": {"full_name": repository or identity.repository}},
    }


class _Channel:
    def __init__(self, response, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def request(self, verb, request):
        self.calls.append({"verb": verb, "request": request})
        if self.error is not None:
            raise self.error
        return self.response


def _proxy(response, error=None, *, destination="owner/repo"):
    channel = _Channel(response, error)
    proxy = ScopedConnectionProxy(
        grant_id="grant-secret-free",
        provider="github",
        destination=destination,
        scopes=("pull_requests:read_for_commit",),
        _channel=channel,
    )
    return proxy, channel


def test_effect_identity_is_closed_canonical_and_secret_free():
    identity = _identity()
    assert identity.repository == "owner/repo"
    assert identity.intended_head_sha == _SHA
    assert identity.effect_kind == "github_pull_request"

    marker = github_pr.github_pr_effect_marker(identity)
    assert marker.startswith("<!-- tinyassets-github-pr-effect:v1:")
    assert marker.endswith(" -->")
    assert len(marker) < 120
    for private_value in ("universe-42", "automation-7", "claim-3"):
        assert private_value not in marker
    assert marker == github_pr.github_pr_effect_marker(_identity())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("universe_id", ""),
        ("automation_id", " automation-7"),
        ("claim_id", "x\nclaim"),
        ("repository", "not-a-repository"),
        ("repository", "../repo"),
        ("repository", "owner/.."),
        ("repository", "./repo"),
        ("repository", "owner/."),
        ("intended_head_sha", "abc"),
        ("effect_kind", "github_issue"),
    ],
)
def test_effect_identity_rejects_invalid_or_open_fields(field, value):
    with pytest.raises(ValueError):
        _identity(**{field: value})


def test_body_marker_append_is_idempotent_and_rejects_conflicting_marker():
    identity = _identity()
    marked = github_pr.with_github_pr_effect_marker("Review me.", identity)
    assert marked == f"Review me.\n\n{github_pr.github_pr_effect_marker(identity)}"
    assert github_pr.with_github_pr_effect_marker(marked, identity) == marked

    other = _identity(claim_id="claim-other")
    with pytest.raises(ValueError, match="different TinyAssets effect marker"):
        github_pr.with_github_pr_effect_marker(marked, other)


def test_body_marker_append_rejects_expected_plus_malformed_reserved_marker():
    identity = _identity()
    body = (
        f"{github_pr.github_pr_effect_marker(identity)}\n"
        "<!-- tinyassets-github-pr-effect:v1:not-a-digest -->"
    )
    with pytest.raises(ValueError, match="malformed TinyAssets effect marker"):
        github_pr.with_github_pr_effect_marker(body, identity)


def test_exact_commit_marker_and_repository_match_reconciles_success():
    identity = _identity()
    proxy, channel = _proxy([_pull(identity)])

    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )

    assert result == {
        "status": "succeeded",
        "evidence": {
            "repository": "owner/repo",
            "intended_head_sha": _SHA,
            "effect_digest": identity.digest,
            "pr_number": 17,
            "pr_url": "https://github.com/owner/repo/pull/17",
            "pr_state": "open",
        },
    }
    assert channel.calls == [
        {
            "verb": "pull_requests:read_for_commit",
            "request": {
                "repository": "owner/repo",
                "intended_head_sha": _SHA,
                "per_page": 100,
            },
        }
    ]
    assert "grant-secret-free" not in repr(result)


def test_connection_destination_url_normalizes_to_exact_repository():
    identity = _identity()
    proxy, channel = _proxy(
        [_pull(identity)],
        destination="github.com/Owner/Repo",
    )

    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )

    assert result["status"] == "succeeded"
    assert channel.calls[0]["request"]["repository"] == "owner/repo"


def test_scoped_cloud_effect_reserves_exact_identity_before_visible_publish(tmp_path):
    intended_sha = "b" * 40

    class _EffectChannel:
        def __init__(self):
            self.calls = []

        def request(self, verb, request):
            self.calls.append({"verb": verb, "request": request})
            if verb == "pull_requests:read_for_commit":
                return []
            if request["operation"] == "prepare_commit":
                return {"commit_sha": intended_sha, "tree_sha": "c" * 40}
            assert request["operation"] == "publish_pull_request"
            return {
                "pr_url": "https://github.com/owner/repo/pull/17",
                "pr_number": 17,
                "commit_sha": intended_sha,
            }

    channel = _EffectChannel()
    proxy = ScopedConnectionProxy(
        grant_id="grant-cloud",
        provider="github",
        destination="github.com/owner/repo",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        _channel=channel,
    )
    packet = {
        "sink": "github_pull_request",
        "destination": "owner/repo",
        "payload": {
            "title": "Ship the slice",
            "body": "Reviewed change.",
            "base_branch": "main",
            "changes_json": {"README.md": "updated\n"},
            "draft": True,
        },
        "idempotency_hint": "branch-authored-key-must-not-own-cloud-effect",
    }

    evidence = github_pr._execute_scoped_cloud_github_pr_effect(
        universe_dir=tmp_path,
        universe_id="universe-42",
        automation_id="automation-7",
        claim_id="claim-3",
        repository="owner/repo",
        packet=packet,
        proxy=proxy,
        run_id="run-1",
    )

    assert evidence["status"] == "succeeded"
    assert evidence["result"]["pr_number"] == 17
    assert len(channel.calls) == 2
    prepare = channel.calls[0]
    publish = channel.calls[1]
    assert prepare["request"]["operation"] == "prepare_commit"
    assert publish["request"]["operation"] == "publish_pull_request"
    assert publish["request"]["intended_head_sha"] == intended_sha
    assert publish["request"]["head_branch"].startswith("tinyassets/cloud-")
    assert "branch-authored-key" not in str(publish)
    identity = github_pr.GitHubPullRequestEffectIdentity(
        universe_id="universe-42",
        automation_id="automation-7",
        claim_id="claim-3",
        repository="owner/repo",
        intended_head_sha=intended_sha,
    )
    assert github_pr.github_pr_effect_marker(identity) in publish["request"]["body"]


def test_scoped_cloud_effect_reconciles_ambiguous_publish_without_second_write(tmp_path):
    intended_sha = "b" * 40
    identity = github_pr.GitHubPullRequestEffectIdentity(
        universe_id="universe-42",
        automation_id="automation-7",
        claim_id="claim-3",
        repository="owner/repo",
        intended_head_sha=intended_sha,
    )

    class _AmbiguousChannel:
        def __init__(self):
            self.publish_count = 0

        def request(self, verb, request):
            if verb == "pull_requests:read_for_commit":
                return [_pull(identity)]
            if request["operation"] == "prepare_commit":
                return {"commit_sha": intended_sha, "tree_sha": "c" * 40}
            self.publish_count += 1
            raise github_pr.AmbiguousProxyOutcome("connection dropped after send")

    channel = _AmbiguousChannel()
    proxy = ScopedConnectionProxy(
        grant_id="grant-cloud",
        provider="github",
        destination="github.com/owner/repo",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        _channel=channel,
    )
    packet = {
        "sink": "github_pull_request",
        "destination": "owner/repo",
        "payload": {
            "title": "Ship",
            "body": "Reviewed",
            "base_branch": "main",
            "changes_json": {"README.md": "updated\n"},
        },
    }

    evidence = github_pr._execute_scoped_cloud_github_pr_effect(
        universe_dir=tmp_path,
        universe_id=identity.universe_id,
        automation_id=identity.automation_id,
        claim_id=identity.claim_id,
        repository=identity.repository,
        packet=packet,
        proxy=proxy,
        run_id="run-ambiguous",
    )

    assert evidence["status"] == "succeeded"
    assert evidence["reconciled"] is True
    assert evidence["pr_number"] == 17
    assert channel.publish_count == 1


def test_scoped_cloud_effect_replay_reuses_journaled_prepared_commit(tmp_path):
    prepared_shas = iter(("b" * 40, "d" * 40))

    class _ReplayChannel:
        def __init__(self):
            self.prepare_count = 0
            self.publish_count = 0

        def request(self, verb, request):
            assert verb != "pull_requests:read_for_commit"
            if request["operation"] == "prepare_commit":
                self.prepare_count += 1
                return {"commit_sha": next(prepared_shas), "tree_sha": "c" * 40}
            self.publish_count += 1
            return {
                "pr_url": "https://github.com/owner/repo/pull/17",
                "pr_number": 17,
                "commit_sha": request["intended_head_sha"],
            }

    channel = _ReplayChannel()
    proxy = ScopedConnectionProxy(
        grant_id="grant-cloud",
        provider="github",
        destination="github.com/owner/repo",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        _channel=channel,
    )
    packet = {
        "sink": "github_pull_request",
        "destination": "owner/repo",
        "payload": {
            "title": "Ship",
            "body": "Reviewed",
            "base_branch": "main",
            "changes_json": {"README.md": "updated\n"},
        },
    }
    kwargs = {
        "universe_dir": tmp_path,
        "universe_id": "universe-42",
        "automation_id": "automation-7",
        "claim_id": "claim-3",
        "repository": "owner/repo",
        "packet": packet,
        "proxy": proxy,
    }

    first = github_pr._execute_scoped_cloud_github_pr_effect(
        **kwargs,
        run_id="run-first",
    )
    replay = github_pr._execute_scoped_cloud_github_pr_effect(
        **kwargs,
        run_id="run-replay",
    )

    assert first["status"] == "succeeded"
    assert replay["status"] == "succeeded"
    assert replay["replay"] is True
    assert channel.prepare_count == 1
    assert channel.publish_count == 1


def test_scoped_cloud_effect_claim_freezes_first_effect_intent(tmp_path):
    class _FrozenChannel:
        def __init__(self):
            self.prepare_count = 0
            self.publish_count = 0

        def request(self, verb, request):
            assert verb != "pull_requests:read_for_commit"
            if request["operation"] == "prepare_commit":
                self.prepare_count += 1
                return {"commit_sha": "b" * 40, "tree_sha": "c" * 40}
            self.publish_count += 1
            return {
                "pr_url": "https://github.com/owner/repo/pull/17",
                "pr_number": 17,
                "commit_sha": request["intended_head_sha"],
            }

    channel = _FrozenChannel()
    proxy = ScopedConnectionProxy(
        grant_id="grant-cloud",
        provider="github",
        destination="github.com/owner/repo",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        _channel=channel,
    )
    base_packet = {
        "sink": "github_pull_request",
        "destination": "owner/repo",
        "payload": {
            "title": "Ship",
            "body": "Reviewed",
            "base_branch": "main",
            "changes_json": {"README.md": "first\n"},
        },
    }
    kwargs = {
        "universe_dir": tmp_path,
        "universe_id": "universe-42",
        "automation_id": "automation-7",
        "claim_id": "claim-3",
        "repository": "owner/repo",
        "proxy": proxy,
    }
    github_pr._execute_scoped_cloud_github_pr_effect(
        **kwargs,
        packet=base_packet,
        run_id="run-first",
    )
    changed_packet = json.loads(json.dumps(base_packet))
    changed_packet["payload"]["changes_json"]["README.md"] = "second\n"

    with pytest.raises(PermissionError, match="intent changed"):
        github_pr._execute_scoped_cloud_github_pr_effect(
            **kwargs,
            packet=changed_packet,
            run_id="run-changed",
        )

    assert channel.prepare_count == 1
    assert channel.publish_count == 1


def test_scoped_cloud_effect_freezes_pull_request_metadata_before_retry(tmp_path):
    class _RejectedThenAvailableChannel:
        def __init__(self):
            self.prepare_count = 0
            self.publish_count = 0

        def request(self, verb, request):
            assert verb != "pull_requests:read_for_commit"
            if request["operation"] == "prepare_commit":
                self.prepare_count += 1
                return {"commit_sha": "b" * 40, "tree_sha": "c" * 40}
            self.publish_count += 1
            if self.publish_count == 1:
                raise RuntimeError("definitive rejection")
            return {
                "pr_url": "https://github.com/owner/repo/pull/17",
                "pr_number": 17,
                "commit_sha": request["intended_head_sha"],
            }

    channel = _RejectedThenAvailableChannel()
    proxy = ScopedConnectionProxy(
        grant_id="grant-cloud",
        provider="github",
        destination="github.com/owner/repo",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        _channel=channel,
    )
    packet = {
        "sink": "github_pull_request",
        "destination": "owner/repo",
        "payload": {
            "title": "Ship",
            "body": "First reviewed body",
            "base_branch": "main",
            "changes_json": {"README.md": "first\n"},
            "labels": ["automation"],
            "draft": True,
        },
    }
    kwargs = {
        "universe_dir": tmp_path,
        "universe_id": "universe-42",
        "automation_id": "automation-7",
        "claim_id": "claim-3",
        "repository": "owner/repo",
        "proxy": proxy,
    }

    first = github_pr._execute_scoped_cloud_github_pr_effect(
        **kwargs,
        packet=packet,
        run_id="run-first",
    )
    assert first["status"] == "failed"

    changed_packet = json.loads(json.dumps(packet))
    changed_packet["payload"]["body"] = "Changed body must not publish"
    with pytest.raises(PermissionError, match="intent changed"):
        github_pr._execute_scoped_cloud_github_pr_effect(
            **kwargs,
            packet=changed_packet,
            run_id="run-changed",
        )

    assert channel.prepare_count == 1
    assert channel.publish_count == 1


def test_scoped_cloud_effect_allows_only_one_failed_publish_retry(tmp_path):
    class _AlwaysRejectedChannel:
        def __init__(self):
            self.prepare_count = 0
            self.publish_count = 0

        def request(self, verb, request):
            assert verb != "pull_requests:read_for_commit"
            if request["operation"] == "prepare_commit":
                self.prepare_count += 1
                return {"commit_sha": "b" * 40, "tree_sha": "c" * 40}
            self.publish_count += 1
            raise RuntimeError("definitive rejection")

    channel = _AlwaysRejectedChannel()
    proxy = ScopedConnectionProxy(
        grant_id="grant-cloud",
        provider="github",
        destination="github.com/owner/repo",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        _channel=channel,
    )
    kwargs = {
        "universe_dir": tmp_path,
        "universe_id": "universe-42",
        "automation_id": "automation-7",
        "claim_id": "claim-3",
        "repository": "owner/repo",
        "packet": {
            "sink": "github_pull_request",
            "destination": "owner/repo",
            "payload": {
                "title": "Ship",
                "body": "Reviewed",
                "base_branch": "main",
                "changes_json": {"README.md": "first\n"},
            },
        },
        "proxy": proxy,
    }

    first = github_pr._execute_scoped_cloud_github_pr_effect(
        **kwargs,
        run_id="run-first",
    )
    retry = github_pr._execute_scoped_cloud_github_pr_effect(
        **kwargs,
        run_id="run-retry",
    )
    exhausted = github_pr._execute_scoped_cloud_github_pr_effect(
        **kwargs,
        run_id="run-exhausted",
    )

    assert first["status"] == "failed"
    assert retry["status"] == "failed"
    assert exhausted["status"] == "failed"
    assert exhausted["reason"] == "retry_limit_exhausted"
    assert exhausted["failed_attempts"] == 2
    assert channel.prepare_count == 1
    assert channel.publish_count == 2


def test_scoped_cloud_effect_freezes_intent_before_failed_preparation(tmp_path):
    class _FailedPreparationChannel:
        def __init__(self):
            self.prepare_count = 0

        def request(self, verb, request):
            assert verb == "pull_requests:write"
            assert request["operation"] == "prepare_commit"
            self.prepare_count += 1
            if self.prepare_count == 1:
                raise RuntimeError("preparation rejected")
            return {"commit_sha": "b" * 40, "tree_sha": "c" * 40}

    channel = _FailedPreparationChannel()
    proxy = ScopedConnectionProxy(
        grant_id="grant-cloud",
        provider="github",
        destination="github.com/owner/repo",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        _channel=channel,
    )
    packet = {
        "sink": "github_pull_request",
        "destination": "owner/repo",
        "payload": {
            "title": "Ship",
            "body": "Original body",
            "base_branch": "main",
            "changes_json": {"README.md": "first\n"},
        },
    }
    kwargs = {
        "universe_dir": tmp_path,
        "universe_id": "universe-42",
        "automation_id": "automation-7",
        "claim_id": "claim-3",
        "repository": "owner/repo",
        "proxy": proxy,
    }

    with pytest.raises(ProxyRequestError, match="preparation did not complete"):
        github_pr._execute_scoped_cloud_github_pr_effect(
            **kwargs,
            packet=packet,
            run_id="run-first",
        )

    changed_packet = json.loads(json.dumps(packet))
    changed_packet["payload"]["changes_json"]["README.md"] = "changed\n"
    with pytest.raises(PermissionError, match="intent changed"):
        github_pr._execute_scoped_cloud_github_pr_effect(
            **kwargs,
            packet=changed_packet,
            run_id="run-changed",
        )

    assert channel.prepare_count == 1


def test_scoped_cloud_effect_recovers_crash_after_atomic_intent_reservation(tmp_path):
    packet = {
        "sink": "github_pull_request",
        "destination": "owner/repo",
        "payload": {
            "title": "Ship",
            "body": "Original body",
            "base_branch": "main",
            "changes_json": {"README.md": "first\n"},
            "labels": ["automation"],
            "draft": True,
        },
    }
    prepare_request = {
        "operation": "prepare_commit",
        "repository": "owner/repo",
        "base_branch": "main",
        "changes_json": {"README.md": "first\n"},
        "edits_json": None,
        "commit_message": "Ship",
    }
    effect_intent_digest = hashlib.sha256(
        json.dumps(
            {
                "prepare": prepare_request,
                "pull_request": {
                    "base_branch": "main",
                    "body": "Original body",
                    "draft": True,
                    "labels": ["automation"],
                    "title": "Ship",
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    preparation_identity_digest = hashlib.sha256(
        json.dumps(
            {
                "automation_id": "automation-7",
                "claim_id": "claim-3",
                "effect_kind": github_pr._GITHUB_PR_EFFECT_KIND,
                "repository": "owner/repo",
                "universe_id": "universe-42",
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    intent_key = f"github-pr-intent:{preparation_identity_digest}"
    reservation = external_write_receipts.try_reserve_receipt(
        tmp_path,
        idempotency_hint=intent_key,
        sink="github_pull_request.intent",
        run_id="run-crashed",
        reservation_evidence={
            "result": {"effect_intent_digest": effect_intent_digest},
        },
    )
    assert reservation["row"]["evidence"] == {
        "result": {"effect_intent_digest": effect_intent_digest},
    }
    with external_write_receipts._connect(tmp_path) as conn:
        conn.execute(
            "UPDATE external_write_receipts SET created_at = 0 "
            "WHERE idempotency_hint = ? AND sink = ?",
            (intent_key, "github_pull_request.intent"),
        )
        conn.commit()

    class _RecoveredChannel:
        def __init__(self):
            self.calls = []

        def request(self, verb, request):
            self.calls.append((verb, request["operation"]))
            if request["operation"] == "prepare_commit":
                return {"commit_sha": "b" * 40, "tree_sha": "c" * 40}
            return {
                "pr_url": "https://github.com/owner/repo/pull/17",
                "pr_number": 17,
                "commit_sha": request["intended_head_sha"],
            }

    channel = _RecoveredChannel()
    proxy = ScopedConnectionProxy(
        grant_id="grant-cloud",
        provider="github",
        destination="github.com/owner/repo",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        _channel=channel,
    )
    evidence = github_pr._execute_scoped_cloud_github_pr_effect(
        universe_dir=tmp_path,
        universe_id="universe-42",
        automation_id="automation-7",
        claim_id="claim-3",
        repository="owner/repo",
        packet=packet,
        proxy=proxy,
        run_id="run-recovered",
    )

    assert evidence["status"] == "succeeded"
    assert channel.calls == [
        ("pull_requests:write", "prepare_commit"),
        ("pull_requests:write", "publish_pull_request"),
    ]


def test_scoped_cloud_effect_stale_retry_keeps_failure_count(tmp_path):
    class _SimulatedWorkerCrash(BaseException):
        pass

    class _CrashOnRetryChannel:
        def __init__(self):
            self.publish_count = 0

        def request(self, verb, request):
            if verb == "pull_requests:read_for_commit":
                return []
            if request["operation"] == "prepare_commit":
                return {"commit_sha": "b" * 40, "tree_sha": "c" * 40}
            self.publish_count += 1
            if self.publish_count == 1:
                raise RuntimeError("first attempt rejected")
            raise _SimulatedWorkerCrash("worker died after retry started")

    channel = _CrashOnRetryChannel()
    proxy = ScopedConnectionProxy(
        grant_id="grant-cloud",
        provider="github",
        destination="github.com/owner/repo",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        _channel=channel,
    )
    kwargs = {
        "universe_dir": tmp_path,
        "universe_id": "universe-42",
        "automation_id": "automation-7",
        "claim_id": "claim-3",
        "repository": "owner/repo",
        "packet": {
            "sink": "github_pull_request",
            "destination": "owner/repo",
            "payload": {
                "title": "Ship",
                "body": "Reviewed",
                "base_branch": "main",
                "changes_json": {"README.md": "first\n"},
            },
        },
        "proxy": proxy,
    }

    first = github_pr._execute_scoped_cloud_github_pr_effect(
        **kwargs,
        run_id="run-first",
    )
    assert first["failed_attempts"] == 1
    with pytest.raises(_SimulatedWorkerCrash, match="worker died"):
        github_pr._execute_scoped_cloud_github_pr_effect(
            **kwargs,
            run_id="run-retry-crash",
        )

    with external_write_receipts._connect(tmp_path) as conn:
        conn.execute(
            "UPDATE external_write_receipts SET created_at = 0 "
            "WHERE sink = ? AND status = ?",
            ("github_pull_request", "pending"),
        )
        conn.commit()

    reconciled = github_pr._execute_scoped_cloud_github_pr_effect(
        **kwargs,
        run_id="run-reconcile",
    )
    exhausted = github_pr._execute_scoped_cloud_github_pr_effect(
        **kwargs,
        run_id="run-exhausted",
    )

    assert reconciled["status"] == "failed"
    assert reconciled["failed_attempts"] == 2
    assert exhausted["reason"] == "retry_limit_exhausted"
    assert exhausted["failed_attempts"] == 2
    assert channel.publish_count == 2


def test_authoritative_empty_commit_association_is_terminal_absence():
    identity = _identity()
    proxy, _channel = _proxy([])
    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )
    assert result["status"] == "failed"
    assert result["reason"] == "destination_absent"
    assert result["evidence"]["exact_matches"] == 0


def test_full_page_is_indeterminate_without_pagination_proof():
    identity = _identity()
    proxy, _channel = _proxy(
        [_pull(identity, number=index + 1) for index in range(100)]
    )
    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )
    assert result["status"] == "unknown"
    assert result["reason"] == "destination_result_truncated"


@pytest.mark.parametrize(
    "pulls",
    [
        lambda identity: [
            _pull(identity, head_sha="b" * 40),
        ],
        lambda identity: [
            _pull(identity, body="marker missing"),
        ],
        lambda identity: [
            _pull(identity, repository="other/repo"),
        ],
        lambda identity: [
            _pull(
                identity,
                body=(
                    f"{github_pr.github_pr_effect_marker(identity)}\n"
                    f"{github_pr.github_pr_effect_marker(_identity(claim_id='other'))}"
                ),
            ),
        ],
        lambda identity: [
            _pull(
                identity,
                body=(
                    f"{github_pr.github_pr_effect_marker(identity)}\n"
                    f"{github_pr.github_pr_effect_marker(identity)}"
                ),
            ),
        ],
        lambda identity: [
            _pull(
                identity,
                body=(
                    f"{github_pr.github_pr_effect_marker(identity)}\n"
                    "<!-- tinyassets-github-pr-effect:v1:not-a-digest -->"
                ),
            ),
        ],
        lambda identity: [
            _pull(identity, number=1),
            _pull(identity, number=2),
        ],
    ],
)
def test_partial_or_multiple_matches_are_indeterminate(pulls):
    identity = _identity()
    proxy, _channel = _proxy(pulls(identity))
    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )
    assert result["status"] == "unknown"
    assert result["reason"] in {
        "destination_partial_match",
        "destination_multiple_matches",
    }


@pytest.mark.parametrize(
    ("response", "error", "reason"),
    [
        (
            None,
            ProxyRequestError("token should not echo"),
            "destination_unavailable",
        ),
        ({"unexpected": "shape"}, None, "destination_malformed"),
        ([{"number": 1}], None, "destination_malformed"),
    ],
)
def test_destination_failures_and_malformed_results_hold_without_leaking_details(
    response,
    error,
    reason,
):
    identity = _identity()
    proxy, _channel = _proxy(response, error)
    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )
    assert result["status"] == "unknown"
    assert result["reason"] == reason
    assert "grant-secret-free" not in repr(result)
    assert "token should not echo" not in repr(result)


def test_proxy_destination_must_match_the_server_authored_repository():
    identity = _identity()
    proxy, channel = _proxy([], destination="other/repo")
    result = github_pr.reconcile_github_pull_request_effect(
        identity,
        proxy=proxy,
    )
    assert result["status"] == "unknown"
    assert result["reason"] == "destination_authority_mismatch"
    assert channel.calls == []


def test_reconciler_rejects_branch_authored_mapping_instead_of_minting_identity():
    proxy, _channel = _proxy([])
    with pytest.raises(TypeError, match="server-authored"):
        github_pr.reconcile_github_pull_request_effect(
            {
                "universe_id": "caller",
                "automation_id": "caller",
                "claim_id": "caller",
                "repository": "owner/repo",
                "intended_head_sha": _SHA,
            },
            proxy=proxy,
        )
