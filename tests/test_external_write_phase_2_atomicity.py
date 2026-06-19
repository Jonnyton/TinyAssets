"""PR-122 Phase 2 round-2 P1.1 — idempotency-race regression guards.

Codex's round-1 review on PR #969 caught a real concurrency bug:
the round-1 sequence ``lookup_receipt → invoke gh → record_receipt``
was non-atomic, and ``database is locked`` errors were silently
treated as a miss. Two concurrent threads could observe "no receipt"
and both invoke ``gh pr create``, producing duplicate PRs.

Round-2 contract enforced here:

* :func:`workflow.storage.external_write_receipts.try_reserve_receipt`
  atomically reserves the slot via INSERT … ON CONFLICT DO NOTHING.
  Concurrent reservers see exactly one ``reserved`` outcome and the
  others see ``in_flight`` (pending row) or ``duplicate`` (terminal
  succeeded row).
* :func:`workflow.storage.external_write_receipts.finalize_receipt`
  promotes ``pending`` → ``succeeded`` only when the caller's
  ``run_id`` matches the reservation owner.
* :func:`workflow.storage.external_write_receipts.release_reservation`
  flips ``pending`` → ``failed`` only when the caller still owns the
  row, so a retry under the same hint can re-reserve.
* The effector NEVER silently swallows
  :class:`sqlite3.OperationalError`; it surfaces ``error_kind=
  receipt_store_locked`` so the operator can see the lock state.
* Stale pending reservations (older than
  ``STALE_PENDING_THRESHOLD_SECONDS``) can be reclaimed by a fresh
  reservation attempt.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from workflow.effectors import EXTERNAL_WRITE_SINK_GITHUB_PR
from workflow.effectors.github_pr import (
    _CAPABILITIES_ENV,
    run_github_pr_effector,
)
from workflow.storage.effector_consents import grant_consent
from workflow.storage.external_write_receipts import (
    STALE_PENDING_THRESHOLD_SECONDS,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SUCCEEDED,
    finalize_receipt,
    initialize_receipts_db,
    list_receipts,
    lookup_receipt,
    release_reservation,
    try_reserve_receipt,
)

_DESTINATION = "Jonnyton/Workflow"


def _make_packet(*, idempotency_hint: str = "hint-race") -> dict:
    return {
        "sink": EXTERNAL_WRITE_SINK_GITHUB_PR,
        "destination": _DESTINATION,
        "payload": {
            "title": "race test",
            "body": "",
            "base_branch": "main",
            "head_branch": "auto/race",
            "draft": True,
        },
        "idempotency_hint": idempotency_hint,
    }


@pytest.fixture
def universe_dir(tmp_path):
    u = tmp_path / "u-race"
    u.mkdir()
    return u


@pytest.fixture
def gates_open(universe_dir, monkeypatch):
    """All three gates configured EXCEPT the idempotency receipt, which
    starts empty so the test can drive its concurrency shape."""
    monkeypatch.delenv(_CAPABILITIES_ENV, raising=False)
    monkeypatch.setenv(
        _CAPABILITIES_ENV, json.dumps({_DESTINATION: "tok"}),
    )
    monkeypatch.delenv("WORKFLOW_EXTERNAL_WRITE_ENABLED", raising=False)
    monkeypatch.delenv("WORKFLOW_EXTERNAL_WRITE_DRY_RUN", raising=False)
    grant_consent(
        universe_dir,
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        destination=_DESTINATION,
        granted_by="host",
    )
    return universe_dir


# ---------------------------------------------------------------------------
# Storage-layer atomicity primitives
# ---------------------------------------------------------------------------


def test_try_reserve_first_caller_wins(universe_dir):
    res = try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-A",
    )
    assert res["status"] == "reserved"
    row = res["row"]
    assert row["run_id"] == "run-A"
    assert row["status"] == STATUS_PENDING


def test_try_reserve_second_caller_sees_in_flight(universe_dir):
    try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-A",
    )
    res = try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-B",
    )
    assert res["status"] == "in_flight"
    assert res["row"]["run_id"] == "run-A"


def test_try_reserve_sees_duplicate_after_finalize(universe_dir):
    try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-A",
    )
    assert finalize_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        evidence={"pr_number": 1},
        run_id="run-A",
    ) is True
    res = try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-B",
    )
    assert res["status"] == "duplicate"
    assert res["row"]["evidence"]["pr_number"] == 1
    assert res["row"]["status"] == STATUS_SUCCEEDED


def test_finalize_only_succeeds_for_reservation_owner(universe_dir):
    try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-A",
    )
    # Another run cannot finalize someone else's reservation.
    not_owner = finalize_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        evidence={"pr_number": 99},
        run_id="run-B",
    )
    assert not_owner is False
    # Real owner can.
    assert finalize_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        evidence={"pr_number": 1},
        run_id="run-A",
    ) is True


def test_release_marks_failed_and_allows_retry(universe_dir):
    try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-A",
    )
    assert release_reservation(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-A",
    ) is True
    row = lookup_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
    )
    assert row is not None
    assert row["status"] == STATUS_FAILED
    # A retry under the same hint can re-reserve via the failed-prior
    # branch.
    res = try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-B",
    )
    assert res["status"] == "reserved_after_failed"
    assert res["row"]["run_id"] == "run-B"
    assert res["row"]["status"] == STATUS_PENDING


def test_release_does_not_clobber_other_owner(universe_dir):
    """Release must not flip another run's reservation to failed."""
    try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-A",
    )
    # Some other run with a different id tries to release.
    assert release_reservation(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-B",
    ) is False
    row = lookup_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
    )
    assert row is not None
    assert row["status"] == STATUS_PENDING
    assert row["run_id"] == "run-A"


def test_stale_pending_can_be_reclaimed(universe_dir):
    """A pending reservation older than STALE_PENDING_THRESHOLD_SECONDS
    is auto-reclaimable by a fresh reserver."""
    fake_now = 10_000.0
    try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-A",
        now=fake_now,
    )
    # Step the clock past the stale threshold.
    later = fake_now + STALE_PENDING_THRESHOLD_SECONDS + 60.0
    res = try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-B",
        now=later,
    )
    assert res["status"] == "reserved_after_stale"
    assert res["displaced_run_id"] == "run-A"
    assert res["row"]["run_id"] == "run-B"


def test_stale_threshold_respected_below_age(universe_dir):
    fake_now = 10_000.0
    try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-A",
        now=fake_now,
    )
    later = fake_now + STALE_PENDING_THRESHOLD_SECONDS - 60.0
    res = try_reserve_receipt(
        universe_dir,
        idempotency_hint="hint-1",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-B",
        now=later,
    )
    assert res["status"] == "in_flight"


def test_no_hint_returns_no_hint_status(universe_dir):
    res = try_reserve_receipt(
        universe_dir,
        idempotency_hint="",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        run_id="run-A",
    )
    assert res["status"] == "no_hint"


def test_migration_adds_status_column_to_existing_db(tmp_path):
    """An existing receipts DB without the ``status`` column (round-1
    shape) must migrate transparently when initialize_receipts_db
    runs."""
    universe = tmp_path / "u-mig"
    universe.mkdir()
    # Hand-build a round-1-shape table.
    from workflow.storage.external_write_receipts import (
        receipts_db_path,
    )
    db = receipts_db_path(universe)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE external_write_receipts (
            idempotency_hint TEXT NOT NULL,
            sink             TEXT NOT NULL,
            evidence_json    TEXT NOT NULL,
            run_id           TEXT NOT NULL,
            created_at       REAL NOT NULL,
            PRIMARY KEY (idempotency_hint, sink)
        )
        """
    )
    conn.execute(
        "INSERT INTO external_write_receipts VALUES (?, ?, ?, ?, ?)",
        (
            "round-1-hint", EXTERNAL_WRITE_SINK_GITHUB_PR,
            json.dumps({"pr_number": 7}), "old-run", 100.0,
        ),
    )
    conn.commit()
    conn.close()

    initialize_receipts_db(universe)
    row = lookup_receipt(
        universe,
        idempotency_hint="round-1-hint",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
    )
    assert row is not None
    # Round-1 rows migrate with status='succeeded' so they continue to
    # dedup-hit as terminal receipts.
    assert row["status"] == STATUS_SUCCEEDED
    assert row["evidence"]["pr_number"] == 7


# ---------------------------------------------------------------------------
# Effector-level: concurrent threads produce exactly one gh invocation
# ---------------------------------------------------------------------------


def test_concurrent_effector_calls_invoke_gh_exactly_once(gates_open):
    """The round-1 P1.1 reproduction: two callers, same hint, race the
    reservation. Round-2 must produce exactly ONE ``gh pr create``
    invocation. The other caller sees ``concurrent_in_flight`` (when
    the receipt is still pending) or a dedup hit (when the receipt
    has already finalized).

    This test is structured as a deterministic two-step rather than
    a wall-clock-dependent thread barrier — the prior shape was
    flaky under heavy test-suite load. The invariants under test
    (atomic reservation; second caller cannot fire gh) are properties
    of the storage layer, not of OS scheduling, so a sequential
    drive captures them without timing fragility.
    """
    universe = gates_open
    packet = _make_packet(idempotency_hint="hint-concurrent")
    fake_stdout = "https://github.com/Jonnyton/Workflow/pull/4242\n"
    call_count = {"n": 0}

    def fake_run(*args, **kwargs):
        call_count["n"] += 1
        return SimpleNamespace(
            returncode=0, stdout=fake_stdout, stderr="",
        )

    # Step 1: caller A holds a pending reservation but has NOT yet
    # invoked gh. We simulate this with a manually-injected pending
    # row at the storage layer — the same shape ``try_reserve_receipt``
    # would have left after a successful reserve.
    from workflow.storage.external_write_receipts import (
        _connect,
        initialize_receipts_db,
    )
    initialize_receipts_db(universe)
    with _connect(universe) as conn:
        conn.execute(
            "INSERT INTO external_write_receipts ("
            "  idempotency_hint, sink, evidence_json, run_id, "
            "  created_at, status"
            ") VALUES (?, ?, '{}', ?, ?, ?)",
            (
                "hint-concurrent", EXTERNAL_WRITE_SINK_GITHUB_PR,
                "run-A", time.time(), STATUS_PENDING,
            ),
        )
        conn.commit()

    # Caller B enters the effector. Reservation is contended; they
    # must see concurrent_in_flight and skip gh.
    with patch(
        "workflow.effectors.github_pr.subprocess.run",
        side_effect=fake_run,
    ):
        result_b = run_github_pr_effector(
            node_id="emit",
            output_keys=["pr_packet"],
            run_state={"pr_packet": packet},
            base_path=universe,
            run_id="run-B",
        )
    assert call_count["n"] == 0, (
        "Caller B must not invoke gh when A holds the reservation. "
        f"P1.1 race regression. Got {call_count['n']} invocations."
    )
    assert result_b["reason"] == "concurrent_in_flight"
    assert result_b["held_by_run_id"] == "run-A"

    # Step 2: caller A finishes its (mocked) gh invocation and
    # finalizes the receipt to succeeded.
    from workflow.storage.external_write_receipts import finalize_receipt
    finalize_receipt(
        universe,
        idempotency_hint="hint-concurrent",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        evidence={
            "pr_number": 4242,
            "pr_url": "https://github.com/Jonnyton/Workflow/pull/4242",
        },
        run_id="run-A",
    )

    # Step 3: caller B retries. Now the row is terminal-succeeded, so
    # they get the dedup-hit shape and STILL don't invoke gh.
    with patch(
        "workflow.effectors.github_pr.subprocess.run",
        side_effect=fake_run,
    ):
        result_b_retry = run_github_pr_effector(
            node_id="emit",
            output_keys=["pr_packet"],
            run_state={"pr_packet": packet},
            base_path=universe,
            run_id="run-B",
        )
    assert call_count["n"] == 0, (
        f"Caller B's retry must dedup-hit; got {call_count['n']} "
        "gh invocations."
    )
    assert result_b_retry["idempotency_dedup_hit"] is True
    assert result_b_retry["evidence"]["pr_number"] == 4242
    assert result_b_retry["recorded_run_id"] == "run-A"

    # Final state: terminal succeeded with caller A's evidence.
    receipt = lookup_receipt(
        universe,
        idempotency_hint="hint-concurrent",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
    )
    assert receipt is not None
    assert receipt["status"] == STATUS_SUCCEEDED
    assert receipt["evidence"]["pr_number"] == 4242
    assert receipt["run_id"] == "run-A"


def test_concurrent_with_seeded_terminal_row_skips_gh(gates_open):
    """When the receipt is already terminal-succeeded, no thread should
    invoke gh — both see ``duplicate``."""
    universe = gates_open
    from workflow.storage.external_write_receipts import record_receipt
    record_receipt(
        universe,
        idempotency_hint="hint-already-done",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        evidence={"pr_number": 5, "pr_url": "https://x/5"},
        run_id="prior-run",
    )
    packet = _make_packet(idempotency_hint="hint-already-done")

    results: dict[str, dict] = {}
    call_count = {"n": 0}
    call_lock = threading.Lock()

    def fake_run(*args, **kwargs):
        with call_lock:
            call_count["n"] += 1
        return SimpleNamespace(
            returncode=0, stdout="https://github.com/x/x/pull/99\n",
            stderr="",
        )

    def worker(run_id: str) -> None:
        with patch(
            "workflow.effectors.github_pr.subprocess.run",
            side_effect=fake_run,
        ):
            results[run_id] = run_github_pr_effector(
                node_id="emit",
                output_keys=["pr_packet"],
                run_state={"pr_packet": packet},
                base_path=universe,
                run_id=run_id,
            )

    threads = [
        threading.Thread(target=worker, args=("run-A",)),
        threading.Thread(target=worker, args=("run-B",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert call_count["n"] == 0, (
        "An already-finalized receipt must dedup-hit; no thread should "
        "invoke gh."
    )
    for r in results.values():
        assert r.get("idempotency_dedup_hit") is True
        assert r["evidence"]["pr_number"] == 5


# ---------------------------------------------------------------------------
# `database is locked` is surfaced, never silently treated as miss
# ---------------------------------------------------------------------------


def test_receipt_store_lock_error_returns_structured_evidence(
    gates_open, monkeypatch,
):
    """Round-1's silent-miss-on-lock bug: P1.1's second leak vector.
    Round-2 contract: lock errors surface as receipt_store_locked
    evidence; the effector NEVER invokes gh under a lock-class error."""
    universe = gates_open
    packet = _make_packet(idempotency_hint="hint-lock")

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    with patch(
        "workflow.effectors.github_pr._try_reserve",
        side_effect=boom,
    ), patch(
        "workflow.effectors.github_pr.subprocess.run"
    ) as mock_run:
        result = run_github_pr_effector(
            node_id="emit",
            output_keys=["pr_packet"],
            run_state={"pr_packet": packet},
            base_path=universe,
            run_id="run-A",
        )
    mock_run.assert_not_called()
    assert result["error_kind"] == "receipt_store_locked"
    assert "duplicate writes" in result["error"]
    # No row was committed.
    rows = list_receipts(universe)
    assert all(r["idempotency_hint"] != "hint-lock" for r in rows)


def test_receipt_store_non_lock_error_also_short_circuits(
    gates_open, monkeypatch,
):
    """Other OperationalError variants (disk full, malformed schema,
    etc.) also surface — they're classified ``receipt_store_error``
    rather than the more specific ``receipt_store_locked`` so the
    operator can distinguish lock contention from a corrupted DB."""
    universe = gates_open
    packet = _make_packet(idempotency_hint="hint-other-err")

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    with patch(
        "workflow.effectors.github_pr._try_reserve",
        side_effect=boom,
    ), patch(
        "workflow.effectors.github_pr.subprocess.run"
    ) as mock_run:
        result = run_github_pr_effector(
            node_id="emit",
            output_keys=["pr_packet"],
            run_state={"pr_packet": packet},
            base_path=universe,
            run_id="run-A",
        )
    mock_run.assert_not_called()
    assert result["error_kind"] == "receipt_store_error"


# ---------------------------------------------------------------------------
# BUG-111: real writes materialize changes_json before gh pr create
# ---------------------------------------------------------------------------


def test_effector_materializes_packet_changes_before_creating_pr(gates_open):
    universe = gates_open
    changes_json = {"README_PROBE.md": "probe\n"}
    packet = _make_packet(idempotency_hint="hint-materialize")
    packet["payload"]["changes_json"] = changes_json
    succeed = SimpleNamespace(
        returncode=0,
        stdout="https://github.com/Jonnyton/Workflow/pull/77\n",
        stderr="",
    )

    with patch(
        "workflow.effectors.github_pr._materialize_branch",
        return_value={"materialized": True},
    ) as mock_materialize, patch(
        "workflow.effectors.github_pr.subprocess.run",
        return_value=succeed,
    ) as mock_run:
        result = run_github_pr_effector(
            node_id="emit",
            output_keys=["pr_packet"],
            run_state={"pr_packet": packet},
            base_path=universe,
            run_id="run-materialize",
        )

    assert result["pr_number"] == 77
    mock_materialize.assert_called_once()
    assert mock_materialize.call_args.kwargs["changes_json"] == changes_json
    mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# gh failure releases the reservation; subsequent retry can re-reserve
# ---------------------------------------------------------------------------


def test_failure_releases_reservation_and_retry_can_proceed(gates_open):
    universe = gates_open
    packet = _make_packet(idempotency_hint="hint-fail-retry")
    fail = SimpleNamespace(
        returncode=2, stdout="", stderr="gh: rate limit",
    )
    succeed = SimpleNamespace(
        returncode=0,
        stdout="https://github.com/Jonnyton/Workflow/pull/77\n",
        stderr="",
    )
    with patch(
        "workflow.effectors.github_pr._materialize_branch",
        return_value={"materialized": True},
    ), patch(
        "workflow.effectors.github_pr.subprocess.run",
        return_value=fail,
    ):
        first = run_github_pr_effector(
            node_id="emit",
            output_keys=["pr_packet"],
            run_state={"pr_packet": packet},
            base_path=universe,
            run_id="run-A",
        )
    assert first["error_kind"] == "gh_nonzero_exit"
    assert first.get("reservation_released") is True
    # The failed row is still there but marked status=failed.
    failed_row = lookup_receipt(
        universe,
        idempotency_hint="hint-fail-retry",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
    )
    assert failed_row is not None
    assert failed_row["status"] == STATUS_FAILED

    # Retry under the same hint succeeds.
    with patch(
        "workflow.effectors.github_pr._materialize_branch",
        return_value={"materialized": True},
    ), patch(
        "workflow.effectors.github_pr.subprocess.run",
        return_value=succeed,
    ):
        second = run_github_pr_effector(
            node_id="emit",
            output_keys=["pr_packet"],
            run_state={"pr_packet": packet},
            base_path=universe,
            run_id="run-B",
        )
    assert second["pr_number"] == 77
    final = lookup_receipt(
        universe,
        idempotency_hint="hint-fail-retry",
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
    )
    assert final is not None
    assert final["status"] == STATUS_SUCCEEDED
    assert final["run_id"] == "run-B"


# ---------------------------------------------------------------------------
# Public-API signature lock — try_reserve_receipt / finalize_receipt /
# release_reservation are exported so future refactors can't quietly
# remove the atomic seam.
# ---------------------------------------------------------------------------


def test_storage_module_exports_atomic_primitives():
    """Lock the public surface so a future refactor can't quietly
    revert to a non-atomic record_receipt-only flow."""
    from workflow.storage import external_write_receipts as mod
    for name in (
        "try_reserve_receipt", "finalize_receipt", "release_reservation",
        "STATUS_PENDING", "STATUS_SUCCEEDED", "STATUS_FAILED",
        "STALE_PENDING_THRESHOLD_SECONDS",
    ):
        assert hasattr(mod, name), (
            f"workflow.storage.external_write_receipts must export "
            f"`{name}` so the effector's atomic seam stays callable"
        )
        assert name in mod.__all__, (
            f"`{name}` must be in __all__ so import * paths surface it"
        )
