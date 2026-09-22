"""Negative regressions for cloud-only runtime admission (change task 9).

Test-matrix rows 1, 2 and the bounded 4/5 pair from
`openspec/changes/cloud-only-runtime-admission/design.md`. These are written
against the **unfixed** tree on purpose: the negatives assert the refusal that
tasks 6-7 are supposed to add, so they fail here at the missing-refusal
assertion and pass once admission is actually wired. The positives assert
preserved behaviour and pass at baseline, which is what proves the negatives
are refusals rather than broken setup.

Nothing here is enforcement, and nothing here is production authority. Every
case runs on a temp data root with a fixture DB and an injected resolver
(`design.md` § Local isolated tests vs production authority): a green run
establishes no custody, no cloud fact and no live claim. The resolver is
injected through the existing `ProcessProvenanceObservation` seam — no
environment bypass, no tests-only production helper, and no production edit.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import tinyassets.platform_runtime_provenance as provenance
from tests.test_branch_tasks_v2 import _activation_subject, _commit, _MutableClock
from tinyassets.branch_tasks_v2 import AssignedConsumerLease, Epoch2BranchTaskAdapter
from tinyassets.daemon_registry import create_daemon, ensure_daemon_runtime
from tinyassets.daemon_server import initialize_author_server, list_runtime_instances
from tinyassets.platform_runtime_provenance import (
    CLOUD,
    NOT_CLOUD,
    ProcessProvenanceObservation,
    RuntimeProvenance,
)
from tinyassets.storage import db_path
from tinyassets.storage.automation_activations import (
    AutomationActivationExecutor,
    AutomationActivationStore,
)

NOW = "2026-07-24T08:01:00+00:00"

UNADMITTED = RuntimeProvenance(
    verdict=NOT_CLOUD,
    reason="metadata_unreachable",
    metadata_reachable=False,
    expected_identity_prepared=False,
)
ADMITTED = RuntimeProvenance(
    verdict=CLOUD,
    reason="instance_match",
    metadata_reachable=True,
    expected_identity_prepared=True,
)


@pytest.fixture
def bind_provenance(monkeypatch):
    """Install one process observation carrying an injected verdict.

    This drives the real seam a runtime guard has to read: the module-level
    `_PROCESS_OBSERVATION` that both `observe_platform_runtime_provenance()`
    and the non-mutating `peek_platform_runtime_provenance()` resolve through.
    The cache is warmed once here so a guard reading either accessor sees the
    same immutable verdict, exactly as a real process does after startup
    resolution. No metadata socket is opened: the resolver is a callable.
    """

    def _bind(verdict: RuntimeProvenance) -> ProcessProvenanceObservation:
        observation = ProcessProvenanceObservation(resolver=lambda: verdict)
        observation.observe()
        monkeypatch.setattr(provenance, "_PROCESS_OBSERVATION", observation)
        return observation

    return _bind


def _ready_cloud_assignment(tmp_path: Path):
    """A valid, ready, pending `cloud` epoch-2 task plus a valid consumer lease.

    Same shape as the baseline single-winner claim test in
    `tests/test_branch_tasks_v2.py`, so the setup itself is known-claimable.
    """
    initialize_author_server(tmp_path)
    activations = AutomationActivationStore(tmp_path)
    active = activations.activate(
        expected=activations.create_stopped(
            universe_id="universe-a", automation_id="automation-a"
        ),
        executor_class=AutomationActivationExecutor.CLOUD,
        subject=_activation_subject("branch-version-a"),
        lease_id="activation-lease-a",
    )
    assert active is not None
    committed = _commit(tmp_path, automation_activation=active)
    adapter = Epoch2BranchTaskAdapter(tmp_path, clock=_MutableClock(NOW))
    candidate = adapter.get(committed["branch_task_id"])
    assert candidate is not None
    assert candidate.automation_executor_class == "cloud"
    lease = AssignedConsumerLease(
        consumer_id="assigned-consumer:boot-a",
        lease_id="lease-a",
        expires_at="2026-07-24T08:02:00+00:00",
    )
    return adapter, candidate, lease


def _claimed_row(tmp_path: Path, branch_task_id: str) -> tuple[str, str]:
    """Read the persisted claim state, not the return value."""
    with sqlite3.connect(db_path(tmp_path)) as conn:
        row = conn.execute(
            "SELECT status, COALESCE(claimed_by, ?) FROM branch_tasks_v2 "
            "WHERE branch_task_id = ?",
            ("", branch_task_id),
        ).fetchone()
    assert row is not None
    return str(row[0]), str(row[1])


def _cloud_worker_rows(tmp_path: Path) -> list[dict]:
    return [
        row
        for row in list_runtime_instances(tmp_path)
        if (row.get("metadata") or {}).get("runtime_registration") == "cloud_worker"
    ]


def _cloud_registration_args(tmp_path: Path, *, worker_id: str = "worker-cloud-1"):
    initialize_author_server(tmp_path)
    daemon = create_daemon(
        tmp_path,
        display_name="Admission regression daemon",
        created_by="acct_alice",
        soul_mode="soul",
        soul_text="Own one bounded cloud registration.",
    )
    return dict(
        daemon_id=str(daemon["daemon_id"]),
        universe_id="universe-a",
        provider_name="codex",
        model_name="gpt-5",
        created_by="cloud-worker",
        worker_id=worker_id,
        metadata={"automation_executor_class": "cloud"},
    )


def _register_cloud_worker(tmp_path: Path, *, worker_id: str = "worker-cloud-1"):
    return ensure_daemon_runtime(
        tmp_path, **_cloud_registration_args(tmp_path, worker_id=worker_id)
    )


# --- matrix 1: negative direct claim --------------------------------------


def test_unadmitted_direct_claim_assigned_claims_nothing(
    tmp_path: Path, bind_provenance
) -> None:
    """Matrix 1. No `authority_claim` callback is passed — that is the point.

    `transaction_check` returns the non-optional predicate's result unchanged
    when `authority_claim is None` (`branch_tasks_v2.py:489`), so a gate that
    lives only in the optional callback is opt-out by construction and a test
    that supplies one proves nothing. The setup is a valid ready assignment
    with a valid unexpired consumer lease; the only thing wrong with this
    process is that it is not admitted.
    """
    bind_provenance(UNADMITTED)
    adapter, candidate, lease = _ready_cloud_assignment(tmp_path)

    claimed = adapter.claim_assigned(candidate, consumer_lease=lease)

    status, claimed_by = _claimed_row(tmp_path, candidate.branch_task_id)
    assert claimed is None, "unadmitted process claimed an assigned cloud task"
    assert claimed_by == "", f"unadmitted process is recorded as claimer: {claimed_by}"
    assert status == "pending", (
        f"task left {status!r}, not pending, by an unadmitted claim"
    )


def test_admitted_direct_claim_assigned_still_succeeds(
    tmp_path: Path, bind_provenance
) -> None:
    """Preserved behaviour, and the control for the negative above.

    Identical fixture, identical call, only the injected verdict differs. If
    this fails, the negative's red is setup breakage rather than a refusal.
    """
    bind_provenance(ADMITTED)
    adapter, candidate, lease = _ready_cloud_assignment(tmp_path)

    claimed = adapter.claim_assigned(candidate, consumer_lease=lease)

    assert claimed is not None
    assert claimed.claimed_by == lease.consumer_id
    status, claimed_by = _claimed_row(tmp_path, candidate.branch_task_id)
    assert claimed_by == lease.consumer_id
    assert status != "pending"


# --- matrix 2: negative registration --------------------------------------


def test_unadmitted_ensure_daemon_runtime_writes_no_cloud_worker_row(
    tmp_path: Path, bind_provenance
) -> None:
    """Matrix 2. Asserted on the persisted row, never on source text.

    A permission refusal or a refusing return is acceptable. An arbitrary
    programming/setup error must fail the test, not count as admission safety.
    After an unadmitted call there must be no cloud-worker registration row.
    """
    bind_provenance(UNADMITTED)
    registration_args = _cloud_registration_args(tmp_path)

    try:
        ensure_daemon_runtime(tmp_path, **registration_args)
    except PermissionError:
        pass

    rows = _cloud_worker_rows(tmp_path)
    assert rows == [], (
        f"unadmitted process registered {len(rows)} cloud_worker runtime row(s)"
    )


def test_admitted_ensure_daemon_runtime_registers_cloud_worker(
    tmp_path: Path, bind_provenance
) -> None:
    """Preserved behaviour: the admitted path still registers."""
    bind_provenance(ADMITTED)

    runtime = _register_cloud_worker(tmp_path)

    assert runtime["metadata"]["runtime_registration"] == "cloud_worker"
    rows = _cloud_worker_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["instance_id"] == runtime["runtime_instance_id"]


# --- matrix 4/5 (bounded): a row and a cloud-looking host are not authority --


def test_existing_registration_and_cloud_labels_do_not_authorize_claim(
    tmp_path: Path, bind_provenance, monkeypatch
) -> None:
    """Matrix 4 + 5, bounded to what a local fixture can honestly show.

    The registration row is written while admitted, then the same data root is
    read by an unadmitted process wearing the cheap cloud-looking labels a copy
    of this repo can wear: the serving env flag, a `mcp.tinyassets.io` hostname
    and a container-ish env set. None of those is evidence, and an existing row
    is not permission — authority is re-resolved on read (`design.md`
    § Enforcement sites (B)). No real production path is set and no live state
    is touched: the data root is the pytest temp dir throughout.
    """
    bind_provenance(ADMITTED)
    registered = _register_cloud_worker(tmp_path)
    assert registered["metadata"]["runtime_registration"] == "cloud_worker"
    adapter, candidate, lease = _ready_cloud_assignment(tmp_path)

    # Now the same checkout, off cloud, dressed up.
    bind_provenance(UNADMITTED)
    monkeypatch.setenv("TINYASSETS_ALLOW_CLAUDE_SERVING", "1")
    monkeypatch.setenv("HOSTNAME", "mcp.tinyassets.io")
    monkeypatch.setenv("TINYASSETS_CONTAINER", "tinyassets-daemon")
    monkeypatch.setattr("socket.gethostname", lambda: "mcp.tinyassets.io")

    claimed = adapter.claim_assigned(candidate, consumer_lease=lease)

    status, claimed_by = _claimed_row(tmp_path, candidate.branch_task_id)
    assert claimed is None, (
        "an existing registration plus cloud-looking labels authorized an "
        "unadmitted claim"
    )
    assert claimed_by == ""
    assert status == "pending"
    assert _cloud_worker_rows(tmp_path), "fixture lost the pre-existing registration"
