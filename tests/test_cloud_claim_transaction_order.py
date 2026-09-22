"""Executable ordering proof for process admission and the actual claim CAS."""

import tinyassets.platform_runtime_provenance as provenance
from tests.test_cloud_only_admission_regressions import ADMITTED, _ready_cloud_assignment


def test_claim_resolves_before_store_and_checks_cached_evidence_inside_transaction(
    tmp_path, monkeypatch
):
    events = []
    adapter, candidate, lease = _ready_cloud_assignment(tmp_path)
    real_claim = adapter._store.claim_v2_task

    def resolve():
        assert events == [], "admission resolution ran after entering the claim store"
        events.append("resolve")
        return ADMITTED

    monkeypatch.setattr(
        provenance,
        "_PROCESS_OBSERVATION",
        provenance.ProcessProvenanceObservation(resolver=resolve),
    )

    def enter_store(*args, **kwargs):
        assert events == ["resolve"]
        events.append("store")
        predicate = kwargs["claim_check"]

        def check(conn, task, transaction_at):
            assert conn.in_transaction
            assert provenance.peek_platform_runtime_provenance() is ADMITTED
            events.append("cas")
            return predicate(conn, task, transaction_at)

        kwargs["claim_check"] = check
        return real_claim(*args, **kwargs)

    monkeypatch.setattr(adapter._store, "claim_v2_task", enter_store)
    assert adapter.claim_assigned(candidate, consumer_lease=lease) is not None
    assert events == ["resolve", "store", "cas"]
