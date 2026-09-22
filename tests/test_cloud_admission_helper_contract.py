"""Focused contract tests for the tasks 6-7 admission helpers.

Three properties the claim/registration regressions cannot see from outside:
the cached read never resolves anything, the claim path resolves **before** it
opens the write transaction, and the refusal reaches the read-only diagnostic
as the same stable token rather than as a second vocabulary.

Isolated like the regressions: a temp data root, an injected resolver through
the existing `ProcessProvenanceObservation` seam, no socket, no production
credential and no cloud fact established by a green run.
"""

from __future__ import annotations

from pathlib import Path

import tinyassets.platform_runtime_provenance as provenance
from tests.test_cloud_only_admission_regressions import (
    ADMITTED,
    UNADMITTED,
    _ready_cloud_assignment,
)
from tests.test_cloud_only_admission_regressions import (
    bind_provenance as _bind_provenance_fixture,
)
from tinyassets.platform_runtime_provenance import (
    PLATFORM_NOT_CLOUD_REASON,
    ProcessProvenanceObservation,
    cached_process_is_cloud_admitted,
)

bind_provenance = _bind_provenance_fixture


def test_cached_admission_read_never_resolves(monkeypatch) -> None:
    """The in-transaction read is peek-only, so it can never open a socket.

    An unobserved process reads `None` and is refused. If this read resolved,
    the CAS would perform a bounded network probe under the SQLite write lock —
    the exact ordering failure `design.md` § Enforcement sites (A) forbids.
    """
    calls: list[str] = []

    def resolver():
        calls.append("resolve")
        return ADMITTED

    observation = ProcessProvenanceObservation(resolver=resolver)
    monkeypatch.setattr(provenance, "_PROCESS_OBSERVATION", observation)

    assert cached_process_is_cloud_admitted() is False
    assert calls == [], "the cached admission read resolved a verdict"


def test_claim_resolves_once_before_the_transaction(
    tmp_path: Path, monkeypatch
) -> None:
    """Resolution happens outside the write transaction, and exactly once.

    The observation starts **unobserved**, so a claim that succeeds proves
    `claim_assigned` itself resolved: a peek-only CAS on an unobserved process
    refuses. With the test above pinning the CAS read as peek-only, the resolve
    cannot be inside the transaction — which is the ordering property. The
    counting resolver additionally shows it happened exactly once.
    """
    calls: list[str] = []

    def resolver():
        calls.append("resolve")
        return ADMITTED

    monkeypatch.setattr(
        provenance, "_PROCESS_OBSERVATION", ProcessProvenanceObservation(resolver=resolver)
    )
    adapter, candidate, lease = _ready_cloud_assignment(tmp_path)

    claimed = adapter.claim_assigned(candidate, consumer_lease=lease)

    assert claimed is not None
    assert calls == ["resolve"], f"resolver ran {len(calls)} time(s), expected once"


def test_unadmitted_refusal_is_explained_with_the_stable_token(
    tmp_path: Path, bind_provenance
) -> None:
    """The diagnostic reports the same token the CAS refused on.

    `explain_assigned_refusal` reads the shared non-optional predicate, so a
    refusal has one definition and one name. The token is sanitized by
    construction: no instance id, no expected id, no address, no hostname.
    """
    bind_provenance(ADMITTED)
    adapter, candidate, lease = _ready_cloud_assignment(tmp_path)

    bind_provenance(UNADMITTED)
    assert adapter.claim_assigned(candidate, consumer_lease=lease) is None
    reason = adapter.explain_assigned_refusal(candidate, consumer_lease=lease)

    assert reason == PLATFORM_NOT_CLOUD_REASON
    assert reason is not None and not any(char.isdigit() for char in reason)


def test_unadmitted_registration_refusal_leaks_no_identity(
    tmp_path: Path, bind_provenance
) -> None:
    """The registration refusal message carries tokens, never identifiers."""
    from tests.test_cloud_only_admission_regressions import _cloud_registration_args
    from tinyassets.daemon_registry import ensure_daemon_runtime

    bind_provenance(ADMITTED)
    args = _cloud_registration_args(tmp_path)

    bind_provenance(UNADMITTED)
    try:
        ensure_daemon_runtime(tmp_path, **args)
    except PermissionError as exc:
        message = str(exc)
    else:  # pragma: no cover - a non-refusal fails the regression suite too
        raise AssertionError("unadmitted registration did not refuse")

    assert PLATFORM_NOT_CLOUD_REASON in message
    assert not any(char.isdigit() for char in message)
    assert args["daemon_id"] not in message
