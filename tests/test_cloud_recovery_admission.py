"""Recovery must not publish capacity or consume work from an unapproved process."""

import pytest

import tinyassets.platform_runtime_provenance as provenance
from tests.test_cloud_only_admission_regressions import (
    ADMITTED,
    UNADMITTED,
    _claimed_row,
    _ready_cloud_assignment,
    _register_cloud_worker,
)
from tinyassets.runtime.assigned_queue_consumer import AssignedQueueConsumer


def _bind(monkeypatch, verdict):
    observation = provenance.ProcessProvenanceObservation(resolver=lambda: verdict)
    observation.observe()
    monkeypatch.setattr(provenance, "_PROCESS_OBSERVATION", observation)


def test_unadmitted_recovery_keeps_pending_work_and_existing_registration_inert(
    tmp_path, monkeypatch
):
    _bind(monkeypatch, ADMITTED)
    _register_cloud_worker(tmp_path)
    _adapter, candidate, _lease = _ready_cloud_assignment(tmp_path)
    _bind(monkeypatch, UNADMITTED)
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    touched = []
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda base: touched.append("enumerate") or [],
    )
    consumer = AssignedQueueConsumer(tmp_path)
    try:
        with pytest.raises(PermissionError, match="platform_not_cloud"):
            consumer.poll_once()
        assert touched == []
        assert _claimed_row(tmp_path, candidate.branch_task_id) == ("pending", "")
        assert list(tmp_path.rglob(".worker_supervisor*.json")) == []
        assert consumer._active == {}
    finally:
        consumer.stop()


def test_unadmitted_consumer_cannot_start_even_before_credential_scavenge(tmp_path, monkeypatch):
    _bind(monkeypatch, UNADMITTED)
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    consumer = AssignedQueueConsumer(tmp_path)

    def forbidden_scavenge():
        raise AssertionError("unapproved consumer reached credential maintenance")

    monkeypatch.setattr(consumer, "_scavenge_orphaned_credentials", forbidden_scavenge)
    try:
        with pytest.raises(PermissionError, match="platform_not_cloud"):
            consumer.start()
        assert consumer._thread is None
    finally:
        consumer.stop()


def test_admitted_recovery_can_still_poll(tmp_path, monkeypatch):
    _bind(monkeypatch, ADMITTED)
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    touched = []
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda base: touched.append("enumerate") or [],
    )
    consumer = AssignedQueueConsumer(tmp_path)
    try:
        assert consumer.poll_once() == 0
        assert touched == ["enumerate"]
    finally:
        consumer.stop()
