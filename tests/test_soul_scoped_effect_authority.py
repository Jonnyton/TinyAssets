"""Soul-scoped effect-authority (gap 1 of the souled-universe model).

Covers three layers:
  1. ``universe_soul`` round-trips the ``effect_authority`` field through
     soul.md render/parse.
  2. ``resolve_soul_effect_authority`` returns AUTHORIZED / DENIED / UNDECLARED.
  3. The github_pr effector's Gate 0 enforces soul-declared grants (fail
     closed on mismatch) and falls through to the legacy gates when a
     universe declares nothing (transitional).

Design note: docs/design-notes/2026-05-28-souled-universe-effect-authority.md
"""

from __future__ import annotations

import json

import pytest

from workflow.effectors.authority import (
    AUTHORIZED,
    DENIED,
    UNDECLARED,
    effect_authority_key,
    resolve_soul_effect_authority,
)
from workflow.effectors.github_pr import (
    _CAPABILITIES_ENV,
    EXTERNAL_WRITE_SINK_GITHUB_PR,
    run_github_pr_effector,
)
from workflow.storage.effector_consents import grant_consent
from workflow.universe_soul import (
    effect_authority_from_soul,
    read_universe_soul,
    render_soul_markdown,
    write_universe_soul,
)

_DESTINATION = "Jonnyton/Workflow"
_GRANT = f"{EXTERNAL_WRITE_SINK_GITHUB_PR}:{_DESTINATION}"


@pytest.fixture
def universe_dir(tmp_path):
    universe = tmp_path / "u-test"
    universe.mkdir()
    return universe


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv(_CAPABILITIES_ENV, raising=False)
    monkeypatch.delenv("WORKFLOW_EXTERNAL_WRITE_ENABLED", raising=False)
    monkeypatch.delenv("WORKFLOW_EXTERNAL_WRITE_DRY_RUN", raising=False)


def _set_capability(monkeypatch, destination: str, token: str) -> None:
    monkeypatch.setenv(_CAPABILITIES_ENV, json.dumps({destination: token}))


def _make_packet(*, destination: str = _DESTINATION) -> dict:
    return {
        "sink": EXTERNAL_WRITE_SINK_GITHUB_PR,
        "destination": destination,
        "idempotency_hint": "soul-auth-test-001",
        "payload": {
            "title": "Soul-auth test",
            "body": "test",
            "base_branch": "main",
            "head_branch": "auto/soul-auth-test",
            "draft": True,
        },
        "expected_evidence_keys": ["pr_number", "pr_url"],
    }


# ---------------------------------------------------------------------------
# Layer 1 — soul.md round-trip
# ---------------------------------------------------------------------------


def test_soul_round_trips_effect_authority(universe_dir):
    write_universe_soul(
        universe_dir,
        purpose="maintain the platform",
        effect_authority=(_GRANT, "tweet:@workflow"),
    )
    soul = read_universe_soul(universe_dir)
    assert soul is not None
    assert soul.effect_authority == (_GRANT, "tweet:@workflow")
    assert effect_authority_from_soul(universe_dir) == (_GRANT, "tweet:@workflow")


def test_render_contains_effect_authority_section(universe_dir):
    soul = write_universe_soul(universe_dir, effect_authority=(_GRANT,))
    rendered = render_soul_markdown(soul)
    assert "## Effect Authority" in rendered
    assert f"- {_GRANT}" in rendered


def test_soul_without_effect_authority_reads_empty(universe_dir):
    write_universe_soul(universe_dir, purpose="no hands declared")
    assert effect_authority_from_soul(universe_dir) == ()


def test_effect_authority_blank_entries_are_dropped(universe_dir):
    write_universe_soul(universe_dir, effect_authority=(_GRANT, "  ", ""))
    assert read_universe_soul(universe_dir).effect_authority == (_GRANT,)


def test_effect_authority_merge_preserves_existing(universe_dir):
    write_universe_soul(universe_dir, effect_authority=(_GRANT,))
    # A later write that does not pass effect_authority keeps the prior grants.
    write_universe_soul(universe_dir, purpose="updated purpose only")
    assert effect_authority_from_soul(universe_dir) == (_GRANT,)


# ---------------------------------------------------------------------------
# Layer 2 — resolver
# ---------------------------------------------------------------------------


def test_resolver_undeclared_when_universe_dir_none():
    assert (
        resolve_soul_effect_authority(None, EXTERNAL_WRITE_SINK_GITHUB_PR, _DESTINATION)
        == UNDECLARED
    )


def test_resolver_undeclared_when_no_soul(universe_dir):
    assert (
        resolve_soul_effect_authority(universe_dir, EXTERNAL_WRITE_SINK_GITHUB_PR, _DESTINATION)
        == UNDECLARED
    )


def test_resolver_authorized_on_match(universe_dir):
    write_universe_soul(universe_dir, effect_authority=(_GRANT,))
    assert (
        resolve_soul_effect_authority(universe_dir, EXTERNAL_WRITE_SINK_GITHUB_PR, _DESTINATION)
        == AUTHORIZED
    )


def test_resolver_denied_on_declared_mismatch(universe_dir):
    write_universe_soul(
        universe_dir,
        effect_authority=(f"{EXTERNAL_WRITE_SINK_GITHUB_PR}:other/repo",),
    )
    assert (
        resolve_soul_effect_authority(universe_dir, EXTERNAL_WRITE_SINK_GITHUB_PR, _DESTINATION)
        == DENIED
    )


def test_effect_authority_key_strips():
    assert (
        effect_authority_key(" github_pull_request ", " owner/repo ")
        == "github_pull_request:owner/repo"
    )


# ---------------------------------------------------------------------------
# Layer 3 — effector Gate 0 integration
# ---------------------------------------------------------------------------


def test_gate0_blocks_when_soul_declares_mismatch_even_with_capability_and_consent(
    universe_dir, monkeypatch
):
    """Soul-authority is checked BEFORE capability/consent — a declared soul
    that omits this destination fails closed regardless of env/consent."""
    write_universe_soul(
        universe_dir,
        effect_authority=(f"{EXTERNAL_WRITE_SINK_GITHUB_PR}:other/repo",),
    )
    _set_capability(monkeypatch, _DESTINATION, "tok")
    grant_consent(
        universe_dir,
        sink=EXTERNAL_WRITE_SINK_GITHUB_PR,
        destination=_DESTINATION,
        granted_by="host",
    )

    result = run_github_pr_effector(
        node_id="n",
        output_keys=["pr_packet"],
        run_state={"pr_packet": _make_packet()},
        base_path=universe_dir,
    )
    assert result["dry_run"] is True
    assert result["reason"] == "soul_not_authorized"
    assert result["destination"] == _DESTINATION


def test_gate0_passes_to_capability_gate_when_soul_authorizes(universe_dir, monkeypatch):
    """A matching soul grant clears Gate 0; with no capability the effector
    then reports missing_capability — proving Gate 0 passed and Gate 1 ran."""
    write_universe_soul(universe_dir, effect_authority=(_GRANT,))
    result = run_github_pr_effector(
        node_id="n",
        output_keys=["pr_packet"],
        run_state={"pr_packet": _make_packet()},
        base_path=universe_dir,
    )
    assert result["dry_run"] is True
    assert result["reason"] == "missing_capability"


def test_undeclared_soul_falls_through_to_legacy_gates(universe_dir):
    """Transitional: a universe with no soul effect_authority is NOT blocked by
    Gate 0 — it falls through to the legacy capability gate (missing_capability)."""
    result = run_github_pr_effector(
        node_id="n",
        output_keys=["pr_packet"],
        run_state={"pr_packet": _make_packet()},
        base_path=universe_dir,
    )
    assert result["dry_run"] is True
    assert result["reason"] == "missing_capability"


def test_gate0_passes_then_consent_gate_when_soul_and_capability_present(
    universe_dir, monkeypatch
):
    """Soul authorizes + capability present + no consent -> missing_consent,
    proving Gate 0 and Gate 1 both passed and Gate 2 ran."""
    write_universe_soul(universe_dir, effect_authority=(_GRANT,))
    _set_capability(monkeypatch, _DESTINATION, "tok")
    result = run_github_pr_effector(
        node_id="n",
        output_keys=["pr_packet"],
        run_state={"pr_packet": _make_packet()},
        base_path=universe_dir,
    )
    assert result["dry_run"] is True
    assert result["reason"] == "missing_consent"
