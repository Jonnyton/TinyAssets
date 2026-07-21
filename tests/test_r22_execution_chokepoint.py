"""Round-22 #1/#2 — the execution fail-closed CHOKEPOINT (production-shaped).

Unlike the r21 router tests (which always inject an explicit UniverseContext), these
drive the REAL run path — ``execute_branch`` → ``_invoke_graph`` → a BARE provider_call
(exactly what ``run_branch`` / ``execute_branch_async`` pass into background execution,
with NO universe context threaded). The graph-execution chokepoint resolves the run's
active universe and FAILS CLOSED before any node/provider is reached, so a
retired-or-unreadable universe can never leak ambient host execution — asserting ZERO
provider calls.
"""
from __future__ import annotations

from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.credential_vault import (
    quarantine_legacy_subscription_records,
    write_credential_vault,
)
from tinyassets.runs import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    execute_branch,
)


def _min_branch() -> BranchDefinition:
    """A valid single-node branch whose only node calls the provider."""
    return BranchDefinition(
        branch_def_id="r22-chokepoint",
        name="R22 Chokepoint",
        entry_point="a",
        node_defs=[
            NodeDefinition(
                node_id="a", display_name="A",
                prompt_template="say hi", output_keys=["a_out"],
            ),
        ],
        graph_nodes=[GraphNodeRef(id="a", node_def_id="a")],
        edges=[EdgeDefinition(from_node="a", to_node="END")],
    )


def _counting_provider(counter: dict):
    def _call(prompt: str, system: str = "", *, role: str = "writer", **_kw) -> str:
        counter["n"] += 1
        return "LEAKED_AMBIENT_EXECUTION"
    return _call


def test_r22_1_retired_universe_never_executes_via_production_run_path(
    tmp_path, monkeypatch,
):
    """Round-22 #1: a MARKER-ONLY retired universe executed through the real run path
    (bare provider into bg exec, NO UniverseContext) must FAIL CLOSED at the
    graph-execution chokepoint — ZERO provider calls."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / "u-retired-run"
    udir.mkdir()
    write_credential_vault(udir, [{
        "credential_type": "llm_subscription", "service": "claude",
        "oauth_token": "legacy",
    }])
    quarantine_legacy_subscription_records(udir)  # → marker-only retired
    fresh = tmp_path / "u-fresh-global"
    fresh.mkdir()
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(fresh))

    calls = {"n": 0}
    outcome = execute_branch(
        tmp_path, branch=_min_branch(), inputs={"x": "hi"},
        provider_call=_counting_provider(calls),
        _enqueue_universe_id=udir.name,
    )
    assert outcome.status == RUN_STATUS_FAILED
    assert "retired" in (outcome.error or "").lower()
    assert calls["n"] == 0, "a retired universe must not reach ANY provider"


def test_r22_2_malformed_vault_fails_closed_via_production_run_path(
    tmp_path, monkeypatch,
):
    """Round-22 #2: an UNREADABLE credential vault must BLOCK execution (fail closed) —
    never be classified 'fresh' and run on ambient host creds. ZERO provider calls."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / "u-malformed"
    udir.mkdir()
    # A corrupt vault — is_retired_universe() would quietly read this as False; the
    # STRICT gate must fail closed.
    (udir / ".credential-vault.json").write_text(
        "{ not valid json <<< recoverable", encoding="utf-8",
    )
    fresh = tmp_path / "u-fresh-global"
    fresh.mkdir()
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(fresh))

    calls = {"n": 0}
    outcome = execute_branch(
        tmp_path, branch=_min_branch(), inputs={"x": "hi"},
        provider_call=_counting_provider(calls),
        _enqueue_universe_id=udir.name,
    )
    assert outcome.status == RUN_STATUS_FAILED
    assert calls["n"] == 0, "an unreadable vault must block ALL providers (fail closed)"


def test_r22_1_fresh_universe_executes_normally(tmp_path, monkeypatch):
    """Control: a FRESH universe (no vault, never retired) is NOT blocked — the
    chokepoint must not over-block legitimate execution."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    udir = tmp_path / "u-fresh"
    udir.mkdir()
    monkeypatch.setenv("TINYASSETS_UNIVERSE", str(udir))

    calls = {"n": 0}

    def _ok(prompt: str, system: str = "", *, role: str = "writer", **_kw) -> str:
        calls["n"] += 1
        return "ok"

    outcome = execute_branch(
        tmp_path, branch=_min_branch(), inputs={"x": "hi"}, provider_call=_ok,
        _enqueue_universe_id=udir.name,
    )
    assert outcome.status == RUN_STATUS_COMPLETED
    assert calls["n"] >= 1
