"""PR-173 twitter_post external-write effector tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from workflow.branches import NodeDefinition
from workflow.effectors import (
    EXTERNAL_WRITE_SINK_TWITTER_POST,
    run_effects_for_branch,
    run_twitter_post_effector,
)
from workflow.storage.effector_consents import grant_consent
from workflow.storage.external_write_receipts import (
    STATUS_SUCCEEDED,
    lookup_receipt,
)


def _packet(**overrides):
    packet = {
        "sink": EXTERNAL_WRITE_SINK_TWITTER_POST,
        "destination": "x:self",
        "payload": {
            "text": "Workflow substrate can now post through twitter_post.",
            "reply_to_tweet_id": "",
            "quote_tweet_id": "",
        },
        "idempotency_hint": "twitter-post-run-1",
        "expected_evidence_keys": ["post_id", "post_url"],
    }
    for key, value in overrides.items():
        if key == "payload":
            packet["payload"].update(value)
        else:
            packet[key] = value
    return packet


def _set_credentials(monkeypatch):
    monkeypatch.setenv("TWITTER_API_KEY", "api-key")
    monkeypatch.setenv("TWITTER_API_SECRET", "api-secret")
    monkeypatch.setenv("TWITTER_ACCESS_TOKEN", "access-token")
    monkeypatch.setenv("TWITTER_ACCESS_TOKEN_SECRET", "access-secret")


def test_package_exports_twitter_post_effector():
    assert EXTERNAL_WRITE_SINK_TWITTER_POST == "twitter_post"
    assert callable(run_twitter_post_effector)


def test_twitter_post_dry_run_env_returns_would_post_before_network(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("WORKFLOW_EXTERNAL_WRITE_DRY_RUN", "1")
    post = Mock()
    monkeypatch.setattr("workflow.effectors.twitter_post._post_tweet", post)

    result = run_twitter_post_effector(
        node_id="emit",
        output_keys=["packet"],
        run_state={"packet": _packet()},
        base_path=tmp_path,
        run_id="run-dry",
    )

    post.assert_not_called()
    assert result["dry_run"] is True
    assert result["reason"] == "operator_kill_switch_active"
    assert result["would_post"]["text"].startswith("Workflow substrate")
    assert result["sink_handle"] == "@kwisatzh4derach"


def test_twitter_post_authority_denied_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKFLOW_EXTERNAL_WRITE_DRY_RUN", raising=False)
    monkeypatch.setattr(
        "workflow.effectors.twitter_post.resolve_soul_effect_authority",
        lambda *_args, **_kwargs: "denied",
    )
    post = Mock()
    monkeypatch.setattr("workflow.effectors.twitter_post._post_tweet", post)

    result = run_twitter_post_effector(
        node_id="emit",
        output_keys=["packet"],
        run_state={"packet": _packet()},
        base_path=tmp_path,
        run_id="run-authority-denied",
    )

    post.assert_not_called()
    assert result["dry_run"] is True
    assert result["reason"] == "soul_not_authorized"
    assert lookup_receipt(
        tmp_path,
        idempotency_hint="twitter-post-run-1",
        sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
    ) is None


def test_twitter_post_missing_consent_dry_runs_before_credentials(
    tmp_path, monkeypatch,
):
    monkeypatch.delenv("WORKFLOW_EXTERNAL_WRITE_DRY_RUN", raising=False)
    post = Mock()
    monkeypatch.setattr("workflow.effectors.twitter_post._post_tweet", post)

    result = run_twitter_post_effector(
        node_id="emit",
        output_keys=["packet"],
        run_state={"packet": _packet()},
        base_path=tmp_path,
        run_id="run-no-consent",
    )

    post.assert_not_called()
    assert result["dry_run"] is True
    assert result["reason"] == "missing_consent"
    assert result["destination"] == "x:self"


def test_twitter_post_success_records_post_evidence(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKFLOW_EXTERNAL_WRITE_DRY_RUN", raising=False)
    _set_credentials(monkeypatch)
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
        destination="x:self",
        granted_by="tester",
    )

    def fake_post(*, text, reply_to_tweet_id, quote_tweet_id, credentials):
        assert text.startswith("Workflow substrate")
        assert reply_to_tweet_id == ""
        assert quote_tweet_id == ""
        assert credentials.api_key == "api-key"
        return {"data": {"id": "1234567890"}}

    monkeypatch.setattr("workflow.effectors.twitter_post._post_tweet", fake_post)

    result = run_twitter_post_effector(
        node_id="emit",
        output_keys=["packet"],
        run_state={"packet": json.dumps(_packet())},
        base_path=tmp_path,
        run_id="run-ok",
    )

    assert result["phase"] == "phase_2"
    assert result["post_id"] == "1234567890"
    assert result["post_url"] == "https://x.com/kwisatzh4derach/status/1234567890"
    assert result["credential_source"] == "default"

    receipt = lookup_receipt(
        tmp_path,
        idempotency_hint="twitter-post-run-1",
        sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
    )
    assert receipt is not None
    assert receipt["status"] == STATUS_SUCCEEDED
    assert receipt["evidence"]["post_id"] == "1234567890"


def test_twitter_post_idempotency_dedup_uses_recorded_evidence(
    tmp_path, monkeypatch,
):
    monkeypatch.delenv("WORKFLOW_EXTERNAL_WRITE_DRY_RUN", raising=False)
    _set_credentials(monkeypatch)
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
        destination="x:self",
        granted_by="tester",
    )
    post = Mock(return_value={"data": {"id": "first"}})
    monkeypatch.setattr("workflow.effectors.twitter_post._post_tweet", post)

    first = run_twitter_post_effector(
        node_id="emit",
        output_keys=["packet"],
        run_state={"packet": _packet()},
        base_path=tmp_path,
        run_id="run-first",
    )
    second = run_twitter_post_effector(
        node_id="emit",
        output_keys=["packet"],
        run_state={"packet": _packet()},
        base_path=tmp_path,
        run_id="run-second",
    )

    assert first["post_id"] == "first"
    assert second["idempotency_dedup_hit"] is True
    assert second["evidence"]["post_id"] == "first"
    assert post.call_count == 1


def test_twitter_post_derives_idempotency_hint_when_omitted(
    tmp_path, monkeypatch,
):
    monkeypatch.delenv("WORKFLOW_EXTERNAL_WRITE_DRY_RUN", raising=False)
    _set_credentials(monkeypatch)
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
        destination="x:self",
        granted_by="tester",
    )
    monkeypatch.setattr(
        "workflow.effectors.twitter_post._post_tweet",
        lambda **_kwargs: {"data": {"id": "derived"}},
    )
    packet = _packet(idempotency_hint="")

    result = run_twitter_post_effector(
        node_id="emit",
        output_keys=["packet"],
        run_state={"packet": packet},
        base_path=tmp_path,
        run_id="source-run-42",
    )

    assert len(result["idempotency_hint"]) == 64
    assert result["post_id"] == "derived"


def test_twitter_post_rejects_payload_handle_mismatch_with_destination(
    tmp_path, monkeypatch,
):
    """A packet consented for destination 'x:self' must not be able to post
    from a different account by supplying payload.handle='@other'.

    Even with full authority + active consent for the authorized destination
    AND daemon-env credentials present for the @other account, the divergent
    payload handle must be REJECTED and no post attempted. This is the
    PR-1374 authorization-bypass regression guard.
    """
    monkeypatch.delenv("WORKFLOW_EXTERNAL_WRITE_DRY_RUN", raising=False)
    # Active consent + authority for the authorized destination only.
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
        destination="x:self",
        granted_by="tester",
    )
    monkeypatch.setattr(
        "workflow.effectors.twitter_post.resolve_soul_effect_authority",
        lambda *_args, **_kwargs: "undeclared",
    )
    # Daemon env carries valid per-handle credentials for the @other account
    # — the exact precondition that made the bypass postable before the fix.
    monkeypatch.setenv("TWITTER_OTHER_API_KEY", "other-api-key")
    monkeypatch.setenv("TWITTER_OTHER_API_SECRET", "other-api-secret")
    monkeypatch.setenv("TWITTER_OTHER_ACCESS_TOKEN", "other-access-token")
    monkeypatch.setenv("TWITTER_OTHER_ACCESS_TOKEN_SECRET", "other-access-secret")

    post = Mock()
    monkeypatch.setattr("workflow.effectors.twitter_post._post_tweet", post)

    packet = _packet(payload={"handle": "@other"})
    result = run_twitter_post_effector(
        node_id="emit",
        output_keys=["packet"],
        run_state={"packet": packet},
        base_path=tmp_path,
        run_id="run-handle-mismatch",
    )

    # No post attempted, structured rejection naming both accounts.
    post.assert_not_called()
    assert result.get("error_kind") == "handle_authority_mismatch"
    assert result["authorized_handle"] == "@kwisatzh4derach"
    assert result["requested_handle"] == "@other"
    assert result["destination"] == "x:self"
    # No success receipt was minted for the mismatched attempt.
    assert lookup_receipt(
        tmp_path,
        idempotency_hint="twitter-post-run-1",
        sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
    ) is None


def test_twitter_post_payload_handle_matching_destination_is_allowed(
    tmp_path, monkeypatch,
):
    """A payload handle that resolves to the SAME account as the authorized
    destination is fine — the binding check only blocks divergence, not a
    redundant restatement of the authorized account."""
    monkeypatch.delenv("WORKFLOW_EXTERNAL_WRITE_DRY_RUN", raising=False)
    _set_credentials(monkeypatch)
    grant_consent(
        tmp_path,
        sink=EXTERNAL_WRITE_SINK_TWITTER_POST,
        destination="x:self",
        granted_by="tester",
    )
    monkeypatch.setattr(
        "workflow.effectors.twitter_post._post_tweet",
        lambda **_kwargs: {"data": {"id": "match-ok"}},
    )

    # 'x:self' normalizes to the default handle; restate it explicitly.
    packet = _packet(payload={"handle": "@kwisatzh4derach"})
    result = run_twitter_post_effector(
        node_id="emit",
        output_keys=["packet"],
        run_state={"packet": packet},
        base_path=tmp_path,
        run_id="run-handle-match",
    )

    assert result.get("error_kind") != "handle_authority_mismatch"
    assert result["post_id"] == "match-ok"
    assert result["sink_handle"] == "@kwisatzh4derach"


def test_branch_dispatch_routes_twitter_post_sink(tmp_path):
    branch = SimpleNamespace(
        node_defs=[
            NodeDefinition(
                node_id="emit",
                display_name="Emit",
                output_keys=["packet"],
                effects=[EXTERNAL_WRITE_SINK_TWITTER_POST],
            ),
        ],
    )

    ev_map = run_effects_for_branch(
        branch=branch,
        run_state={"packet": _packet()},
        base_path=tmp_path,
        run_id="run-dispatch",
    )

    ev = ev_map["emit"][EXTERNAL_WRITE_SINK_TWITTER_POST]
    assert ev["reason"] == "missing_consent"
