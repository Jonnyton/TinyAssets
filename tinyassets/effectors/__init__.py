"""External-write effectors — channel-agnostic dispatch.

Effectors translate ``external_write_packet``-shaped outputs from a node's
``output_keys`` into real-world side effects. They are NOT a new substrate
primitive type; they are glue that reads a documented packet shape out of a
run's final state and invokes a generic, credential-blind external call (or an
internal wiki write-back). Per the canonical 6+5 vocabulary, ``effects`` is a
``NodeDefinition`` attribute, not a fifth primitive. These functions are called
from the run-completion path in ``tinyassets.runs``; errors are captured into
the run's metadata, never raised to the user.

**The platform is channel-agnostic and ships with NO per-channel effector.** A
universe reaches any external service through the single generic
``authenticated_external_call`` sink over a user-configured connection — the
credential is applied inside an isolated worker process, never in this process.
Channels (GitHub, Slack, X, or anything not yet imagined) are user-built graph
nodes over that one primitive, not platform code. There is not a single channel
in the platform until a user builds one.
"""

from __future__ import annotations

from tinyassets.effectors.authenticated_external_call import (
    EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
    bounded_evidence,
    packet_verb,
    run_authenticated_external_call_effector,
)
from tinyassets.effectors.wiki_write_back import (
    EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK,
    run_wiki_write_back_effector,
)


def _authenticated_call_adapter(
    *, node_id, output_keys, run_state, base_path, run_id, dry_run,
    allowed_state_keys=None, prior_effects=None,
):
    return run_authenticated_external_call_effector(
        node_id=node_id,
        output_keys=output_keys,
        run_state=run_state,
        base_path=base_path,
        run_id=run_id,
        dry_run=dry_run,
        allowed_state_keys=allowed_state_keys,
        prior_effects=prior_effects,
    )


def _wiki_write_back_adapter(
    *, node_id, output_keys, run_state, base_path, run_id, dry_run, **_unused
):
    del dry_run  # internal write-back has no dry-run gate
    return run_wiki_write_back_effector(
        node_id=node_id,
        output_keys=output_keys,
        run_state=run_state,
        base_path=base_path,
        run_id=run_id,
    )


# Every external-write sink the platform knows -> its effector adapter. Only
# channel-agnostic sinks exist: the generic authenticated call and the internal
# wiki write-back. No GitHub/Slack/X/desktop sink lives here by design.
_EFFECTORS = {
    EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL: _authenticated_call_adapter,
    EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK: _wiki_write_back_adapter,
}


def _schema_defaulted_keys(state_schema) -> set:
    """The keys the compiler treats as declared for every node (BUG-085):
    state_schema entries carrying a default. Same helper the compiler uses."""
    try:
        from tinyassets.graph_compiler import _state_schema_defaults

        return set(_state_schema_defaults(state_schema).keys())
    except Exception:  # noqa: BLE001 - fail CLOSED: no extra keys become readable
        return set()


def run_effects_for_branch(
    *,
    branch,
    run_state,
    base_path=None,
    run_id="",
    dry_run=None,
    cloud_effect_session=None,
):
    """Dispatch every node's external-write effects.

    Reads each node's ``effects`` (a list of sink names), runs the matching
    effector adapter, and collects per-node evidence keyed by sink. An unknown
    sink is recorded as a structured error; an effector crash is captured, never
    raised to the completion path.
    """
    del cloud_effect_session  # no per-channel cloud session; kept for call-site compat
    evidence_map: dict[str, dict] = {}
    # Full generic-call results, kept in memory for THIS dispatch only: later
    # nodes' packets may reference an earlier node's response.body/status
    # (`$ta.effect`). What is persisted is `bounded_evidence(...)`, so a
    # fetched file never re-enters a model through read_graph.
    chain: dict[str, dict] = {}
    # One (sink, verb) per effect that actually ran; decides what this run cost
    # the engine's run budget once the loop is done (tinyassets.engine_admissions).
    fired: list[tuple[str, str | None]] = []
    schema_defaulted = _schema_defaulted_keys(getattr(branch, "state_schema", None))
    # Effects fire in the order nodes are STORED in the branch (write_graph
    # appends in the order given). That is the "earlier node" contract for
    # `$ta.effect` — storage order, deliberately not graph execution order,
    # which effects (all fired after the run) do not observe.
    for node in getattr(branch, "node_defs", None) or []:
        effects = list(getattr(node, "effects", None) or [])
        if not effects:
            continue
        node_id = getattr(node, "node_id", "")
        output_keys = list(getattr(node, "output_keys", None) or [])
        # A packet may read ONLY the node's declared input_keys plus the
        # state_schema-defaulted keys - never the whole final state (Codex
        # round 1, P0). This is NARROWER than the compiler's render view
        # (which shows everything when isolation is off or no inputs are
        # declared) on purpose: an effect reads less, never more.
        allowed_state_keys = set(getattr(node, "input_keys", None) or []) | schema_defaulted
        prior_effects = dict(chain)
        per_node = evidence_map.setdefault(node_id, {})
        for sink in effects:
            adapter = _EFFECTORS.get(sink)
            if adapter is None:
                # Say what to do instead, not just what is wrong. A branch stored
                # before a per-channel sink was retired keeps naming it forever,
                # and the node then does NOTHING every run. Observed live
                # 2026-08-29: a stored "Docs Touch PR" branch still declared
                # `github_pull_request`, so the universe's PR-opening run reported
                # completed with no PR, no branch and no HTTP call — and the bare
                # "unknown effect sink" told it nothing it could act on.
                #
                # The remedy is always the same shape, because the platform ships
                # exactly two sinks on purpose (channels are user-built graph
                # nodes over the generic call, never hard-coded effectors): the
                # branch must be rebuilt against a supported sink.
                supported = ", ".join(sorted(_EFFECTORS))
                per_node[sink] = {
                    "error": (
                        f"unknown effect sink: {sink} - this branch names a sink "
                        f"that no longer exists, so this node does nothing. "
                        f"Rebuild the node against one of: {supported}. For "
                        f"outbound HTTP, that is "
                        f"'{EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL}' with an "
                        f"external_write_packet in its output_keys."
                    ),
                    "error_kind": "unknown_sink",
                    "supported_sinks": sorted(_EFFECTORS),
                }
                continue
            try:
                result = adapter(
                    node_id=node_id,
                    output_keys=output_keys,
                    run_state=run_state,
                    base_path=base_path,
                    run_id=run_id,
                    dry_run=bool(dry_run),
                    allowed_state_keys=allowed_state_keys,
                    prior_effects=prior_effects,
                )
            except Exception as exc:  # defensive: never raise from completion path
                result = {
                    "error": f"effector crashed: {exc}",
                    "error_kind": "effector_crashed",
                }
            if not dry_run:
                verb = result.get("verb") if isinstance(result, dict) else None
                if isinstance(result, dict) and result.get("error_kind") == "method_mismatch":
                    # verb and request.method disagreed: the result echoes the
                    # declared verb, which says nothing about intent (Codex).
                    verb = None
                elif not verb and sink == EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL:
                    # Refused before the wire (a gate, a bad packet): the verb the
                    # packet DECLARED still says whether it could have written.
                    verb = packet_verb(output_keys=output_keys, run_state=run_state)
                fired.append((sink, verb))
            if sink == EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL and isinstance(result, dict):
                chain[node_id] = result
                result = bounded_evidence(result)
            per_node[sink] = result
    _settle_engine_admission(run_id, fired)
    return evidence_map


def _settle_engine_admission(run_id, fired) -> None:
    """Downgrade the run's engine admission to a read when nothing it fired
    could have changed the far side (GET/HEAD authenticated calls, or nothing
    at all). A run that was not engine-triggered has no admission row: no-op.
    Never raises into the completion path; a failure to settle leaves the row
    a write, which is the strict side."""
    if not run_id:
        return
    try:
        from tinyassets.engine_admissions import fired_only_reads, reclassify_read

        if fired_only_reads(list(fired), read_sink=EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL):
            reclassify_read(str(run_id))
    except Exception:  # pragma: no cover - defensive: the completion path never raises
        import logging

        logging.getLogger(__name__).exception("engine admission settle failed")


__all__ = [
    "EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL",
    "EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK",
    "run_authenticated_external_call_effector",
    "run_wiki_write_back_effector",
    "run_effects_for_branch",
]
