"""Handoff receipts — exactly-once effects, uncertain replies, dry-run purity,
and the lifecycle mapping from receipt status to handoff state.

Requirement source: ``openspec/changes/complete-independent-full-platform-targets/
specs/real-world-handoffs-and-outcomes/spec.md`` (tasks 5.1, 5.4).

Covered requirements:
  - Dry runs never create external handoffs or authoritative outcomes
  - Exactly-once handoff effects are bound to canonical receipts
  - Handoff lifecycle separates submission, acceptance, and later real-world
    outcome
"""

from __future__ import annotations

import pytest

from tinyassets.handoffs import adapters as handoff_adapters
from tinyassets.handoffs import service
from tinyassets.handoffs.adapters import HandoffResult
from tinyassets.handoffs.models import (
    HandoffValidationError,
    derive_handoff_effect_key,
)

DECLARATION = {
    "output_field": "submission",
    "adapter": "arxiv",
    "adapter_action": "submit",
    "destination": "arxiv.org/cs",
    "effect_class": "reversible",
    "outcome_kind": "preprint_submission",
    "evidence_contract": {"id_field": "arxiv_id"},
}


def _branch(declaration=None, branch_def_id="b1"):
    return {
        "branch_def_id": branch_def_id,
        "name": f"Branch {branch_def_id}",
        "entry_point": "n1",
        "graph_nodes": [{"id": "n1", "node_def_id": "n1", "position": 0}],
        "node_defs": [{
            "node_id": "n1",
            "display_name": "Writer",
            "source_code": "def run(state):\n    return {}",
            "output_keys": ["submission"],
            "handoffs": [dict(declaration or DECLARATION)],
        }],
    }


class Env:
    def __init__(self, base, universe_dir, version, run_id):
        self.base = base
        self.universe_dir = universe_dir
        self.version = version
        self.run_id = run_id
        self.owner = "account-alice"
        self.calls: list = []

    @property
    def version_id(self):
        return self.version.branch_version_id

    def execute(self, **kwargs):
        return service.execute(
            actor_id=kwargs.pop("actor_id", self.owner),
            base_path=self.base,
            universe_dir=self.universe_dir,
            run_id=kwargs.pop("run_id", self.run_id),
            branch_version_id=kwargs.pop("branch_version_id", self.version_id),
            output_field="submission",
            **kwargs,
        )


def _make_env(tmp_path, monkeypatch, declaration=None):
    base = tmp_path / "data"
    base.mkdir(exist_ok=True)
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))

    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.runs import create_run, update_run_status
    from tinyassets.storage.effector_consents import grant_consent

    version = publish_branch_version(
        base, _branch(declaration), publisher="account-alice"
    )
    run_id = create_run(
        base,
        branch_def_id="b1",
        thread_id="t1",
        inputs={},
        actor="account-alice",
        owner_user_id="account-alice",
    )
    update_run_status(
        base, run_id, status="completed", output={"submission": {"title": "Paper"}}
    )
    universe_dir = base / "u1"
    universe_dir.mkdir(exist_ok=True)
    grant_consent(
        universe_dir,
        sink="arxiv",
        destination="arxiv.org/cs",
        granted_by="account-alice",
    )
    return Env(base, universe_dir, version, run_id)


@pytest.fixture
def env(tmp_path, monkeypatch):
    return _make_env(tmp_path, monkeypatch)


@pytest.fixture
def bind_adapter(env):
    """Bind an adapter for one test and always release the global registry."""
    bound: list[str] = []

    def _bind(fn):
        handoff_adapters.register_adapter("arxiv", fn)
        bound.append("arxiv")
        return fn

    yield _bind
    for name in bound:
        handoff_adapters.unregister_adapter(name)


def _accepting(env, external_id="arXiv:2601.00001"):
    def _adapter(request):
        env.calls.append(request)
        return HandoffResult(
            state="accepted",
            external_id=external_id,
            evidence={"queued": True},
        )

    return _adapter


def _submitting(env):
    def _adapter(request):
        env.calls.append(request)
        return HandoffResult(state="submitted", evidence={"queue_position": 4})

    return _adapter


def _receipt(env, effect_key):
    from tinyassets.storage.external_write_receipts import lookup_receipt

    return lookup_receipt(env.universe_dir, idempotency_hint=effect_key, sink="arxiv")


def _effect_key(env):
    from tinyassets.handoffs.models import output_digest

    return derive_handoff_effect_key(
        branch_version_id=env.version_id,
        content_hash=env.version.content_hash,
        run_id=env.run_id,
        output_field="submission",
        output_sha256=output_digest({"title": "Paper"}),
        adapter_action="submit",
        destination="arxiv.org/cs",
    )


# ── System-derived identity ───────────────────────────────────────────────────

class TestEffectIdentity:
    def test_identity_is_deterministic_for_the_same_source(self, env):
        assert _effect_key(env) == _effect_key(env)

    def test_identity_uses_the_landed_effect_key_space(self, env):
        assert _effect_key(env).startswith("effect:v1:")

    def test_identity_changes_with_the_destination(self, env):
        from tinyassets.handoffs.models import output_digest

        other = derive_handoff_effect_key(
            branch_version_id=env.version_id,
            content_hash=env.version.content_hash,
            run_id=env.run_id,
            output_field="submission",
            output_sha256=output_digest({"title": "Paper"}),
            adapter_action="submit",
            destination="arxiv.org/math",
        )
        assert other != _effect_key(env)

    def test_identity_changes_with_the_source_version(self, env):
        from tinyassets.handoffs.models import output_digest

        other = derive_handoff_effect_key(
            branch_version_id=env.version_id,
            content_hash="f" * 64,
            run_id=env.run_id,
            output_field="submission",
            output_sha256=output_digest({"title": "Paper"}),
            adapter_action="submit",
            destination="arxiv.org/cs",
        )
        assert other != _effect_key(env)

    def test_empty_identity_component_is_refused(self, env):
        with pytest.raises(HandoffValidationError):
            derive_handoff_effect_key(
                branch_version_id=env.version_id,
                content_hash=env.version.content_hash,
                run_id="",
                output_field="submission",
                output_sha256="a" * 64,
                adapter_action="submit",
                destination="arxiv.org/cs",
            )

    def test_execution_uses_the_derived_identity_not_a_caller_hint(
        self, env, bind_adapter
    ):
        bind_adapter(_accepting(env))
        result = env.execute()
        assert result["effect_key"] == _effect_key(env)


# ── Dry-run purity ────────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_reserves_no_receipt(self, env, bind_adapter):
        bind_adapter(_accepting(env))
        service.dry_run(
            actor_id=env.owner,
            base_path=env.base,
            run_id=env.run_id,
            branch_version_id=env.version_id,
            output_field="submission",
        )
        assert env.calls == []
        assert _receipt(env, _effect_key(env)) is None

    def test_dry_run_creates_no_handoff_row_and_no_outcome(self, env, bind_adapter):
        bind_adapter(_accepting(env))
        service.dry_run(
            actor_id=env.owner,
            base_path=env.base,
            run_id=env.run_id,
            branch_version_id=env.version_id,
            output_field="submission",
        )
        listed = service.listing(actor_id=env.owner, base_path=env.base)
        evidence = service.outcome_evidence(actor_id=env.owner, base_path=env.base)
        assert listed["count"] == 0
        assert evidence["summary"]["total_claims"] == 0

    def test_dry_run_reports_simulated_and_redacts_the_payload(self, env):
        report = service.dry_run(
            actor_id=env.owner,
            base_path=env.base,
            run_id=env.run_id,
            branch_version_id=env.version_id,
            output_field="submission",
        )
        assert report["evidence_level"] == "simulated"
        assert report["would_handoff"]["destination"] == "arxiv.org/cs"
        assert "payload" not in report["would_handoff"]
        assert report["would_handoff"]["payload_type"] == "dict"

    def test_dry_run_names_the_authority_still_required(self, env):
        report = service.dry_run(
            actor_id=env.owner,
            base_path=env.base,
            run_id=env.run_id,
            branch_version_id=env.version_id,
            output_field="submission",
        )
        assert any("consent" in item for item in report["authority_still_required"])


# ── Exactly-once ──────────────────────────────────────────────────────────────

class TestExactlyOnce:
    def test_second_execution_replays_without_a_second_push(self, env, bind_adapter):
        bind_adapter(_accepting(env))
        first = env.execute()
        second = env.execute()
        assert first["executed"] is True
        assert second["replay"] is True
        assert second["executed"] is False
        assert len(env.calls) == 1

    def test_replay_returns_the_same_external_id(self, env, bind_adapter):
        bind_adapter(_accepting(env))
        first = env.execute()
        second = env.execute()
        assert second["handoff"]["external_id"] == first["handoff"]["external_id"]

    def test_the_receipt_row_is_the_canonical_journal(self, env, bind_adapter):
        bind_adapter(_accepting(env))
        env.execute()
        receipt = _receipt(env, _effect_key(env))
        assert receipt is not None
        assert receipt["status"] == "succeeded"

    def test_only_one_handoff_row_exists_per_identity(self, env, bind_adapter):
        bind_adapter(_accepting(env))
        env.execute()
        env.execute()
        assert service.listing(actor_id=env.owner, base_path=env.base)["count"] == 1

    def test_only_one_outcome_is_created_across_replays(self, env, bind_adapter):
        bind_adapter(_accepting(env))
        env.execute()
        env.execute()
        evidence = service.outcome_evidence(actor_id=env.owner, base_path=env.base)
        assert evidence["summary"]["total_claims"] == 1


# ── Uncertain and rejected replies ────────────────────────────────────────────

class TestUncertainAndRejected:
    def test_ambiguous_reply_becomes_uncertain_not_retried(self, env, bind_adapter):
        from tinyassets.effectors.outbound_boundary import AmbiguousEffectOutcome

        def _ambiguous(request):
            env.calls.append(request)
            raise AmbiguousEffectOutcome("timed out after sending")

        bind_adapter(_ambiguous)
        result = env.execute()
        assert result["status"] == "uncertain"
        assert result["handoff"]["state"] == "uncertain"

    def test_uncertain_effect_is_not_reissued_under_a_fresh_key(
        self, env, bind_adapter
    ):
        from tinyassets.effectors.outbound_boundary import AmbiguousEffectOutcome

        def _ambiguous(request):
            env.calls.append(request)
            raise AmbiguousEffectOutcome("timed out after sending")

        bind_adapter(_ambiguous)
        env.execute()
        env.execute()
        assert len(env.calls) == 1
        assert _receipt(env, _effect_key(env))["status"] == "held"

    def test_uncertain_handoff_creates_no_outcome_claim(self, env, bind_adapter):
        from tinyassets.effectors.outbound_boundary import AmbiguousEffectOutcome

        def _ambiguous(request):
            raise AmbiguousEffectOutcome("timed out after sending")

        bind_adapter(_ambiguous)
        env.execute()
        evidence = service.outcome_evidence(actor_id=env.owner, base_path=env.base)
        assert evidence["summary"]["total_claims"] == 0

    def test_definitive_rejection_becomes_rejected_with_no_outcome(
        self, env, bind_adapter
    ):
        def _rejecting(request):
            env.calls.append(request)
            raise ValueError("provider refused the submission")

        bind_adapter(_rejecting)
        result = env.execute()
        assert result["status"] == "rejected"
        evidence = service.outcome_evidence(actor_id=env.owner, base_path=env.base)
        assert evidence["summary"]["total_claims"] == 0


# ── Lifecycle separation ──────────────────────────────────────────────────────

class TestLifecycleSeparation:
    def test_transport_success_proves_submission_only(self, env, bind_adapter):
        bind_adapter(_submitting(env))
        result = env.execute()
        assert result["status"] == "submitted"
        assert result["handoff"]["external_id"] == ""

    def test_submitted_handoff_marks_no_verified_outcome(self, env, bind_adapter):
        bind_adapter(_submitting(env))
        env.execute()
        evidence = service.outcome_evidence(actor_id=env.owner, base_path=env.base)
        assert evidence["summary"]["by_evidence_level"] == {}

    def test_accepted_reply_creates_an_externally_verified_outcome(
        self, env, bind_adapter
    ):
        bind_adapter(_accepting(env))
        result = env.execute()
        assert result["status"] == "accepted"
        assert result["outcome"]["evidence_level"] == "externally_verified"
        assert result["outcome"]["external_id"] == "arXiv:2601.00001"

    def test_the_outcome_links_the_exact_source_and_receipt(self, env, bind_adapter):
        bind_adapter(_accepting(env))
        result = env.execute()
        outcome = result["outcome"]
        assert outcome["run_id"] == env.run_id
        assert outcome["branch_version_id"] == env.version_id
        assert outcome["content_hash"] == env.version.content_hash
        assert outcome["output_field"] == "submission"
        assert outcome["effect_key"] == _effect_key(env)

    def test_lifecycle_transitions_are_append_only_and_contiguous(
        self, env, bind_adapter
    ):
        bind_adapter(_accepting(env))
        result = env.execute()
        detail = service.get(
            actor_id=env.owner,
            base_path=env.base,
            handoff_id=result["handoff"]["handoff_id"],
        )
        seqs = [item["seq"] for item in detail["transitions"]]
        assert seqs == list(range(1, len(seqs) + 1))
        assert detail["transitions"][0]["to_state"] == "reserved"
        assert detail["transitions"][-1]["to_state"] == "accepted"

    def test_owner_cannot_declare_its_own_handoff_accepted(self, env, bind_adapter):
        bind_adapter(_submitting(env))
        result = env.execute()
        with pytest.raises(HandoffValidationError, match="not an owner-settable state"):
            service.record_evidence(
                actor_id=env.owner,
                base_path=env.base,
                handoff_id=result["handoff"]["handoff_id"],
                to_state="accepted",
            )

    def test_owner_may_downgrade_a_submitted_handoff_to_orphaned(
        self, env, bind_adapter
    ):
        bind_adapter(_submitting(env))
        result = env.execute()
        downgraded = service.record_evidence(
            actor_id=env.owner,
            base_path=env.base,
            handoff_id=result["handoff"]["handoff_id"],
            to_state="orphaned",
            evidence={"reason": "record withdrawn upstream"},
        )
        assert downgraded["status"] == "orphaned"

    def test_a_downgrade_preserves_the_prior_acceptance_evidence(
        self, env, bind_adapter
    ):
        bind_adapter(_accepting(env))
        result = env.execute()
        handoff_id = result["handoff"]["handoff_id"]
        service.record_evidence(
            actor_id=env.owner,
            base_path=env.base,
            handoff_id=handoff_id,
            to_state="orphaned",
        )
        detail = service.get(
            actor_id=env.owner, base_path=env.base, handoff_id=handoff_id
        )
        states = [item["to_state"] for item in detail["transitions"]]
        assert "accepted" in states
        assert states[-1] == "orphaned"

    def test_a_terminal_handoff_cannot_transition_again(self, env, bind_adapter):
        bind_adapter(_submitting(env))
        result = env.execute()
        handoff_id = result["handoff"]["handoff_id"]
        service.record_evidence(
            actor_id=env.owner,
            base_path=env.base,
            handoff_id=handoff_id,
            to_state="orphaned",
        )
        with pytest.raises(HandoffValidationError, match="not a legal handoff transition"):
            service.record_evidence(
                actor_id=env.owner,
                base_path=env.base,
                handoff_id=handoff_id,
                to_state="cancelled",
            )


# ── Owner scoping ─────────────────────────────────────────────────────────────

class TestOwnerScoping:
    def test_another_account_cannot_read_the_handoff(self, env, bind_adapter):
        from tinyassets.handoffs.models import HandoffAccessError

        bind_adapter(_accepting(env))
        result = env.execute()
        with pytest.raises(HandoffAccessError):
            service.get(
                actor_id="account-mallory",
                base_path=env.base,
                handoff_id=result["handoff"]["handoff_id"],
            )

    def test_another_account_sees_an_empty_list(self, env, bind_adapter):
        bind_adapter(_accepting(env))
        env.execute()
        assert (
            service.listing(actor_id="account-mallory", base_path=env.base)["count"] == 0
        )
