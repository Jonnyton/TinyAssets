"""The outcome registry extension — one registry, explicit evidence levels,
multi-source attribution without double-counting, and gate-event separation.

Requirement source: ``openspec/changes/complete-independent-full-platform-targets/
specs/real-world-handoffs-and-outcomes/spec.md`` (tasks 5.1, 5.2).

Covered requirements:
  - Handoffs extend the existing outcome registry with exact provenance
  - Existing outcome recording becomes the user-attestation entry point
  - Outcome consumers preserve evidence level and avoid fixed engagement
    optimization
"""

from __future__ import annotations

import sqlite3

import pytest

from tinyassets.handoffs import service
from tinyassets.handoffs.models import (
    HandoffAccessError,
    HandoffAuthorityError,
    HandoffValidationError,
    normalize_external_ref,
)
from tinyassets.handoffs.store import HandoffStore


@pytest.fixture
def base(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    return root


@pytest.fixture
def store(base):
    store = HandoffStore(base)
    store.initialize()
    return store


@pytest.fixture
def version(base):
    """A real published version, so gate-event cites resolve like in production."""
    from tinyassets.branch_versions import publish_branch_version

    return publish_branch_version(
        base,
        {
            "branch_def_id": "b1",
            "name": "Branch b1",
            "entry_point": "n1",
            "graph_nodes": [{"id": "n1", "node_def_id": "n1", "position": 0}],
            "node_defs": [{
                "node_id": "n1",
                "display_name": "Writer",
                "source_code": "def run(state):\n    return {}",
                "output_keys": ["submission"],
            }],
        },
        publisher="account-alice",
    )


@pytest.fixture
def run_id(base):
    from tinyassets.runs import create_run, update_run_status

    run = create_run(
        base,
        branch_def_id="b1",
        thread_id="t1",
        inputs={},
        actor="account-alice",
        owner_user_id="account-alice",
    )
    update_run_status(base, run, status="completed", output={"submission": {"x": 1}})
    return run


def _rows(base, table: str) -> list[sqlite3.Row]:
    from tinyassets.runs import runs_db_path

    conn = sqlite3.connect(runs_db_path(base))
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(f"SELECT * FROM {table}").fetchall()
    finally:
        conn.close()


# ── One registry, not two ─────────────────────────────────────────────────────

class TestSingleRegistry:
    def test_a_handoff_outcome_lands_in_outcome_event(self, base, store, run_id):
        recorded = store.record_outcome_evidence(
            account_id="account-alice",
            outcome_kind="preprint_submission",
            evidence_source="provider",
            evidence_level="externally_verified",
            run_id=run_id,
            external_id="arXiv:2601.00001",
        )
        events = _rows(base, "outcome_event")
        assert len(events) == 1
        assert events[0]["outcome_id"] == recorded["outcome_id"]

    def test_the_existing_get_outcome_action_can_read_it(self, base, store, run_id):
        """The canonical ``get_outcome`` reader sees handoff-derived claims."""
        import json

        from tinyassets.api.market import _OUTCOME_ACTIONS

        recorded = store.record_outcome_evidence(
            account_id="account-alice",
            outcome_kind="preprint_submission",
            evidence_source="provider",
            evidence_level="externally_verified",
            run_id=run_id,
            external_id="arXiv:2601.00001",
        )
        payload = json.loads(
            _OUTCOME_ACTIONS["get_outcome"]({"outcome_id": recorded["outcome_id"]})
        )
        assert payload["outcome_id"] == recorded["outcome_id"]
        assert payload["run_id"] == run_id

    def test_an_unmapped_kind_stays_one_table_via_custom(self, base, store, run_id):
        """A richer outcome_kind must not need a DDL change to the base table."""
        store.record_outcome_evidence(
            account_id="account-alice",
            outcome_kind="regulatory_approval",
            evidence_source="user_attestation",
            evidence_level="user_attested",
            run_id=run_id,
        )
        events = _rows(base, "outcome_event")
        assert events[0]["outcome_type"] == "custom"
        evidence = _rows(base, "outcome_evidence")
        assert evidence[0]["outcome_kind"] == "regulatory_approval"

    def test_a_legacy_row_is_never_attributed_to_the_verifier(self, base, store):
        """``verified_by`` names a verifier, not the account that claimed it.

        Backfilling it as ``account_id`` would attribute someone else's claim to
        whoever checked it, and the row would be indelible once written. The
        migration therefore leaves the actor fields empty.
        """
        from tinyassets.api.market import _outcome_connect
        from tinyassets.outcomes.schema import migrate_outcome_schema

        conn = _outcome_connect(base)
        try:
            conn.execute(
                """
                INSERT INTO outcome_event (
                    outcome_id, run_id, outcome_type, verified_by, verified_at,
                    payload, recorded_at, note
                ) VALUES ('legacy-1','run-legacy','merged_pr','account-carol',
                          '2026-01-02T00:00:00Z','{}','2026-01-01T00:00:00Z','')
                """
            )
            conn.commit()
            migrate_outcome_schema(conn)
            conn.commit()
        finally:
            conn.close()

        rows = _rows(base, "outcome_evidence")
        assert len(rows) == 1
        assert rows[0]["account_id"] == ""
        assert rows[0]["attested_by"] == ""

    def test_a_legacy_row_is_not_presented_as_externally_verified(self, base, store):
        """A legacy ``verified_at`` is not evidence this extension can vouch for."""
        from tinyassets.api.market import _outcome_connect
        from tinyassets.outcomes.schema import migrate_outcome_schema

        conn = _outcome_connect(base)
        try:
            conn.execute(
                """
                INSERT INTO outcome_event (
                    outcome_id, run_id, outcome_type, verified_by, verified_at,
                    payload, recorded_at, note
                ) VALUES ('legacy-2','run-legacy','merged_pr','account-carol',
                          '2026-01-02T00:00:00Z','{}','2026-01-01T00:00:00Z','')
                """
            )
            conn.commit()
            migrate_outcome_schema(conn)
            conn.commit()
        finally:
            conn.close()

        assert _rows(base, "outcome_evidence")[0]["evidence_level"] == "user_attested"

    def test_a_legacy_row_does_not_appear_in_any_accounts_list(self, base, store):
        from tinyassets.api.market import _outcome_connect
        from tinyassets.outcomes.schema import migrate_outcome_schema

        conn = _outcome_connect(base)
        try:
            conn.execute(
                """
                INSERT INTO outcome_event (
                    outcome_id, run_id, outcome_type, payload, recorded_at, note
                ) VALUES ('legacy-3','run-legacy','merged_pr','{}',
                          '2026-01-01T00:00:00Z','')
                """
            )
            conn.commit()
            migrate_outcome_schema(conn)
            conn.commit()
        finally:
            conn.close()

        assert store.list_outcome_evidence(account_id="account-carol") == []
        assert store.list_outcome_evidence(account_id="account-alice") == []


# ── Evidence levels ───────────────────────────────────────────────────────────

class TestEvidenceLevels:
    def test_attestation_begins_user_attested(self, base, run_id):
        recorded = service.attest_outcome(
            actor_id="account-alice",
            base_path=base,
            run_id=run_id,
            outcome_kind="journal_acceptance",
            evidence_url="https://doi.org/10.1234/example",
            note="accepted at a journal",
        )
        assert recorded["evidence_level"] == "user_attested"

    def test_a_valid_evidence_url_does_not_promote_the_claim(self, base, run_id):
        recorded = service.attest_outcome(
            actor_id="account-alice",
            base_path=base,
            run_id=run_id,
            outcome_kind="journal_acceptance",
            evidence_url="https://doi.org/10.1234/example",
        )
        assert recorded["evidence_level"] != "externally_verified"

    def test_verification_preserves_the_original_attester(self, base, store, run_id):
        recorded = service.attest_outcome(
            actor_id="account-alice",
            base_path=base,
            run_id=run_id,
            outcome_kind="journal_acceptance",
        )
        verified = store.transition_outcome_evidence(
            recorded["outcome_id"],
            actor_id="account-verifier",
            expected_level="user_attested",
            to_level="externally_verified",
            evidence_source="verifier",
            external_id="10.1234/example",
        )
        assert verified["attested_by"] == "account-alice"
        assert verified["evidence_level"] == "externally_verified"
        assert verified["transitions"][-1]["actor_id"] == "account-verifier"

    def test_transitions_are_append_only_and_contiguous(self, base, store, run_id):
        recorded = service.attest_outcome(
            actor_id="account-alice",
            base_path=base,
            run_id=run_id,
            outcome_kind="journal_acceptance",
        )
        store.transition_outcome_evidence(
            recorded["outcome_id"],
            actor_id="account-verifier",
            expected_level="user_attested",
            to_level="externally_verified",
            evidence_source="verifier",
            external_id="10.1234/example",
        )
        final = store.transition_outcome_evidence(
            recorded["outcome_id"],
            actor_id="account-moderator",
            expected_level="externally_verified",
            to_level="disputed",
            evidence_source="moderation",
        )
        seqs = [item["seq"] for item in final["transitions"]]
        levels = [item["to_level"] for item in final["transitions"]]
        assert seqs == [1, 2, 3]
        assert levels == ["user_attested", "externally_verified", "disputed"]

    def test_an_illegal_evidence_transition_is_refused(self, base, store, run_id):
        recorded = service.attest_outcome(
            actor_id="account-alice",
            base_path=base,
            run_id=run_id,
            outcome_kind="journal_acceptance",
        )
        store.transition_outcome_evidence(
            recorded["outcome_id"],
            actor_id="account-moderator",
            expected_level="user_attested",
            to_level="retracted",
            evidence_source="moderation",
        )
        with pytest.raises(HandoffValidationError, match="not a legal evidence"):
            store.transition_outcome_evidence(
                recorded["outcome_id"],
                actor_id="account-alice",
                expected_level="retracted",
                to_level="externally_verified",
                evidence_source="verifier",
            )

    def test_an_unknown_evidence_level_is_refused(self, base, store, run_id):
        with pytest.raises(HandoffValidationError, match="evidence_level must be"):
            store.record_outcome_evidence(
                account_id="account-alice",
                outcome_kind="journal_acceptance",
                evidence_source="user_attestation",
                evidence_level="definitely_verified",
                run_id=run_id,
            )

    def test_the_python_guard_and_the_sql_check_agree(self):
        """The registry owns the vocabulary; the handoff models import it.

        Divergence here surfaced as a plausible-looking Python success followed
        by an opaque IntegrityError, so it is asserted rather than assumed.
        """
        from tinyassets.handoffs.models import PERSISTABLE_EVIDENCE_LEVELS
        from tinyassets.outcomes.schema import (
            OUTCOME_EVIDENCE_LEVELS,
            OUTCOME_EVIDENCE_SCHEMA,
        )

        assert PERSISTABLE_EVIDENCE_LEVELS == OUTCOME_EVIDENCE_LEVELS
        for level in OUTCOME_EVIDENCE_LEVELS:
            assert f"'{level}'" in OUTCOME_EVIDENCE_SCHEMA


# ── Multi-source attribution ──────────────────────────────────────────────────

class TestMultiSourceAttribution:
    def test_two_sources_on_one_artifact_do_not_double_count(self, base, store):
        for account in ("account-alice", "account-bob"):
            store.record_outcome_evidence(
                account_id=account,
                outcome_kind="published_paper",
                evidence_source="provider",
                evidence_level="externally_verified",
                external_id="https://doi.org/10.1234/shared",
            )
        summary = store.outcome_evidence_summary()
        assert summary["total_claims"] == 2
        assert summary["artifact_count"] == 1

    def test_both_attributions_remain_visible(self, base, store):
        first = store.record_outcome_evidence(
            account_id="account-alice",
            outcome_kind="published_paper",
            evidence_source="provider",
            evidence_level="externally_verified",
            external_id="https://doi.org/10.1234/shared",
        )
        store.record_outcome_evidence(
            account_id="account-bob",
            outcome_kind="published_paper",
            evidence_source="provider",
            evidence_level="externally_verified",
            external_id="doi.org/10.1234/shared/",
        )
        contributors = {
            item["contributed_by"]
            for item in store.get_outcome_evidence(first["outcome_id"])["artifact_sources"]
        }
        assert contributors == {"account-alice", "account-bob"}

    @pytest.mark.parametrize(
        "raw",
        [
            "https://doi.org/10.1234/shared",
            "http://www.doi.org/10.1234/shared",
            "doi.org/10.1234/shared/",
            "  DOI.org/10.1234/Shared  ",
        ],
    )
    def test_equivalent_identifiers_normalize_together(self, raw):
        assert (
            normalize_external_ref("published_paper", raw)
            == "published_paper:doi.org/10.1234/shared"
        )

    def test_different_kinds_are_different_artifacts(self):
        assert normalize_external_ref("published_paper", "x") != normalize_external_ref(
            "merged_pr", "x"
        )

    def test_a_claim_without_an_external_id_joins_no_artifact(self, base, store):
        store.record_outcome_evidence(
            account_id="account-alice",
            outcome_kind="published_paper",
            evidence_source="user_attestation",
            evidence_level="user_attested",
        )
        assert store.outcome_evidence_summary()["artifact_count"] == 0


# ── Consumer view ─────────────────────────────────────────────────────────────

class TestConsumerView:
    def test_counts_are_separated_by_evidence_level(self, base, store):
        store.record_outcome_evidence(
            account_id="account-alice",
            outcome_kind="published_paper",
            evidence_source="user_attestation",
            evidence_level="user_attested",
            external_id="doi.org/10.1/a",
        )
        store.record_outcome_evidence(
            account_id="account-alice",
            outcome_kind="published_paper",
            evidence_source="provider",
            evidence_level="externally_verified",
            external_id="doi.org/10.1/b",
        )
        summary = store.outcome_evidence_summary(account_id="account-alice")
        assert summary["by_evidence_level"] == {
            "user_attested": 1,
            "externally_verified": 1,
        }

    def test_no_flattened_success_count_is_offered(self, base, store):
        store.record_outcome_evidence(
            account_id="account-alice",
            outcome_kind="published_paper",
            evidence_source="user_attestation",
            evidence_level="user_attested",
        )
        summary = store.outcome_evidence_summary()
        assert "success_count" not in summary
        assert "verified_count" not in summary

    def test_a_disputed_claim_updates_the_aggregate_without_erasing_history(
        self, base, store, run_id
    ):
        recorded = service.attest_outcome(
            actor_id="account-alice",
            base_path=base,
            run_id=run_id,
            outcome_kind="published_paper",
        )
        store.transition_outcome_evidence(
            recorded["outcome_id"],
            actor_id="account-moderator",
            expected_level="user_attested",
            to_level="disputed",
            evidence_source="moderation",
        )
        summary = store.outcome_evidence_summary()
        detail = store.get_outcome_evidence(recorded["outcome_id"])
        assert summary["by_evidence_level"] == {"disputed": 1}
        assert detail["transitions"][0]["to_level"] == "user_attested"


# ── Attestation authority ─────────────────────────────────────────────────────

class TestAttestationAuthority:
    def test_attesting_against_a_foreign_run_is_refused(self, base, run_id):
        with pytest.raises(HandoffAuthorityError):
            service.attest_outcome(
                actor_id="account-mallory",
                base_path=base,
                run_id=run_id,
                outcome_kind="published_paper",
            )

    def test_attaching_to_a_foreign_handoff_is_refused(self, base, store, run_id):
        from tinyassets.handoffs.models import HandoffRecord

        store.create_handoff(
            HandoffRecord(
                handoff_id="ho-foreign",
                owner_id="account-bob",
                effect_key="effect:v1:foreign",
                sink="arxiv",
                adapter_action="submit",
                destination="arxiv.org/cs",
                branch_def_id="b1",
                branch_version_id="b1@v1",
                content_hash="a" * 64,
                run_id="run-bob",
                output_field="submission",
                output_sha256="b" * 64,
                effect_class="reversible",
                outcome_kind="preprint_submission",
                state="submitted",
                created_at="2026-07-25T00:00:00Z",
                updated_at="2026-07-25T00:00:00Z",
            ),
            evidence_source="test",
        )
        with pytest.raises(HandoffAccessError):
            service.attest_outcome(
                actor_id="account-alice",
                base_path=base,
                run_id=run_id,
                outcome_kind="published_paper",
                handoff_id="ho-foreign",
            )


# ── Gate events stay specialized and separate ─────────────────────────────────

class TestGateEventSeparation:
    def test_an_outcome_transition_does_not_touch_gate_events(
        self, base, store, run_id, version
    ):
        from tinyassets.gate_events.store import attest_gate_event, get_gate_event

        event = attest_gate_event(
            base,
            goal_id="goal-1",
            event_type="citation",
            event_date="2026-07-01",
            attested_by="account-alice",
            cites=[{"branch_version_id": version.branch_version_id, "run_id": run_id}],
        )
        recorded = service.attest_outcome(
            actor_id="account-alice",
            base_path=base,
            run_id=run_id,
            outcome_kind="published_paper",
        )
        store.transition_outcome_evidence(
            recorded["outcome_id"],
            actor_id="account-verifier",
            expected_level="user_attested",
            to_level="externally_verified",
            evidence_source="verifier",
            external_id="doi.org/10.1/x",
        )
        assert get_gate_event(base, event.event_id).verification_status == "attested"

    def test_a_gate_event_verification_does_not_promote_an_outcome(
        self, base, store, run_id, version
    ):
        from tinyassets.gate_events.store import attest_gate_event, verify_gate_event

        event = attest_gate_event(
            base,
            goal_id="goal-1",
            event_type="citation",
            event_date="2026-07-01",
            attested_by="account-alice",
            cites=[{"branch_version_id": version.branch_version_id, "run_id": run_id}],
        )
        recorded = service.attest_outcome(
            actor_id="account-alice",
            base_path=base,
            run_id=run_id,
            outcome_kind="published_paper",
        )
        verify_gate_event(base, event_id=event.event_id, verifier_id="account-verifier")
        after = store.get_outcome_evidence(recorded["outcome_id"])
        assert after["evidence_level"] == "user_attested"
        assert len(after["transitions"]) == 1
