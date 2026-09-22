"""Negative regressions for the two provider lanes that never claim (task 9).

Test-matrix row 3 (`openspec/changes/cloud-only-runtime-admission/design.md`
§ Test matrix) for enforcement site **(C)** — the last provider-authority
boundary. `design.md` § Enforcement sites says this site "carries the whole
foreground/served surface, because those paths never call `claim_assigned` and
stamp the class as a literal (`foreground_run_provider.py:484,595`,
`background_served_provider.py:1336,1547`)". Neither lane traverses
`claim_assigned`, so the row-1/row-2 regressions in
`tests/test_cloud_only_admission_regressions.py` cannot cover them.

Red-before, on purpose: against the unfixed tree both negatives reach the
provider-dispatch fake and fail on the "never invoked" assertion, and both
positives pass. The positives are the discriminator — they run the *same*
fixture, the *same* per-universe authority and the *same* inputs, changing only
the injected verdict, so a negative that goes red is a missing refusal rather
than broken setup.

Nothing here is enforcement and nothing establishes a cloud fact. The verdict
is injected through the existing `ProcessProvenanceObservation` seam
(`platform_runtime_provenance.py` module docstring: "Tests inject a
reader/resolver"), so no metadata socket is opened. Every provider dispatch is
a local callable: the foreground lane runs on the `_CountingProvider` router
and the monkeypatched `call_provider` that `_run_branch` installs, the served
lane on the `raw_provider` callable `_BackgroundAssignedProviderSession` is
constructed with. No listener, no server, no subprocess, no network, no
production credential, and no production edit.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import tinyassets.background_served_provider as background_provider
from tests.test_background_served_provider import _authority_fixture, _lease
from tests.test_cloud_only_admission_regressions import (
    ADMITTED,
    UNADMITTED,
)
from tests.test_cloud_only_admission_regressions import (
    bind_provenance as _bind_provenance_fixture,
)
from tests.test_run_provider_session import _branch, _run_branch
from tinyassets.exceptions import ProviderAuthorityHeldError
from tinyassets.storage.provider_work_authority import db_path as authority_db_path

#: The only outcomes that count as a refusal. Anything else — a KeyError, an
#: AttributeError, an ImportError, a TypeError from a half-wired fixture —
#: propagates and fails the test. An arbitrary programming error is not
#: admission safety (same rule as the claim/registration regressions).
REFUSALS = (ProviderAuthorityHeldError, PermissionError)

#: Re-register the row-1/row-2 observation seam under its own name rather than
#: duplicating it. pytest discovers fixtures by module attribute, so the rebind
#: is enough; importing the name directly collides with the test parameters
#: that request it.
bind_provenance = _bind_provenance_fixture


def _receipt_rows(base_path: Path) -> list[tuple[str, str]]:
    """Persisted foreground run receipts, read from storage rather than a return.

    `executor_class` is not a column — it lives inside the serialized receipt
    record (`storage/provider_work_authority.py`, `record_json`), so the class
    a run was actually stamped with is read out of the stored record.
    """
    with sqlite3.connect(authority_db_path(base_path)) as conn:
        return [
            (str(kind), str(json.loads(record).get("executor_class")))
            for kind, record in conn.execute(
                "SELECT work_item_kind, record_json FROM provider_work_receipts"
            )
        ]


# --- small local helpers (no production helper is introduced) --------------

_SERVED_OPERATION = background_provider.BACKGROUND_BRANCH_RUN_OPERATION


def background_provider_session(base_path: Path, task, raw_provider):
    return background_provider._BackgroundAssignedProviderSession(
        base_path, task, _lease(), raw_provider
    )


def _reservations(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute("SELECT COUNT(*) FROM provider_invocation_reservations").fetchone()[0]
    )


# --- lane 1: foreground run (foreground_run_provider.py:484,595) ----------


def test_unadmitted_foreground_run_never_reaches_the_provider(
    tmp_path: Path, monkeypatch, authenticate_request, bind_provenance
) -> None:
    """Matrix 3, foreground half.

    `_run_branch` is the existing vetted foreground harness: a real branch
    definition, a real founder home, real serving-assignment seeding and real
    run execution, with only the executor replaced by `_CountingProvider`.
    The authority here is valid and per-universe — `acct_alice` owns
    `universe_alice`, the branch is authored by `acct_alice`, and the serving
    assignment is seeded through the same path the passing baseline tests use.
    The single thing wrong with this process is that it is not admitted, and
    `_ForegroundRunProviderSession._admit()` stamps `executor_class="cloud"` as
    a literal without consulting any provenance.
    """
    bind_provenance(UNADMITTED)

    response, provider, _captured = _run_branch(
        tmp_path, monkeypatch, authenticate_request, _branch(node_count=1)
    )

    assert provider.calls == [], (
        f"unadmitted foreground run dispatched {len(provider.calls)} provider "
        "call(s) before any admission check"
    )
    assert response["terminal_status"] != "completed", (
        "unadmitted foreground run completed a cloud-class turn"
    )
    assert _receipt_rows(tmp_path) == [], (
        "unadmitted foreground run minted a cloud-class provider work receipt"
    )


def test_admitted_foreground_run_still_launches_and_settles(
    tmp_path: Path, monkeypatch, authenticate_request, bind_provenance
) -> None:
    """Preserved behaviour, and the control for the negative above.

    Identical branch, identical harness, identical authority — only the
    injected verdict differs. If this fails, the negative's red is setup
    breakage rather than a refusal.
    """
    bind_provenance(ADMITTED)

    response, provider, _captured = _run_branch(
        tmp_path, monkeypatch, authenticate_request, _branch(node_count=1)
    )

    assert response["terminal_status"] == "completed", response["terminal_error"]
    assert len(provider.calls) == 1
    assert _receipt_rows(tmp_path) == [("run", "cloud")]


# --- lane 2: background served turn (background_served_provider.py:1336,1547)


def test_unadmitted_background_served_turn_never_reaches_the_provider(
    tmp_path: Path, monkeypatch, bind_provenance
) -> None:
    """Matrix 3, served half.

    Driven through `_BackgroundAssignedProviderSession.__call__` — the actual
    authority path, not a source-string assertion. `_authority_fixture` gives
    it a valid, active, unexpired per-universe background binding owned by
    `acct_owner_a` for `universe_a`, a claimed attempt whose lease has not
    expired, a live queue-owner row and a matching consumer lease; the same
    fixture state the launch positives in
    `tests/test_background_served_provider.py` succeed on.

    A refusal is allowed to arrive as either a raised `REFUSALS` member or a
    refusing return. What is not allowed is the provider fake running: this
    lane stamps `executor_class="cloud"` as a literal at
    `background_served_provider.py:1336,1547`, so on the unfixed tree the call
    lands and this goes red.
    """
    bind_provenance(UNADMITTED)
    task, conn, _assignment, _current, _events = _authority_fixture(tmp_path, monkeypatch)
    raw_calls: list[str] = []

    session = background_provider_session(
        tmp_path, task, lambda *_a, **_k: raw_calls.append("raw") or "unexpected"
    )
    try:
        session("prompt")
    except REFUSALS:
        pass

    assert raw_calls == [], (
        "unadmitted served turn invoked the provider before any admission check"
    )
    assert _reservations(conn) == 0, (
        "unadmitted served turn reserved cloud-class provider budget"
    )


def test_admitted_background_served_turn_still_launches(
    tmp_path: Path, monkeypatch, bind_provenance
) -> None:
    """Preserved behaviour and the control: same fixture, admitted verdict."""
    bind_provenance(ADMITTED)
    task, conn, _assignment, _current, _events = _authority_fixture(tmp_path, monkeypatch)
    raw_calls: list[str] = []

    def raw_provider(*_args, **kwargs):
        carrier = kwargs["universe_context"].provider_invocation
        assert carrier.validate_for_call(role="writer", operation=_SERVED_OPERATION) == "codex"
        raw_calls.append("raw")
        return "ok"

    session = background_provider_session(tmp_path, task, raw_provider)

    assert session("prompt") == "ok"
    assert raw_calls == ["raw"]
    assert _reservations(conn) == 1
