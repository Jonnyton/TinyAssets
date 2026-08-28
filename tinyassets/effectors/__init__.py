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
    run_authenticated_external_call_effector,
)
from tinyassets.effectors.wiki_write_back import (
    EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK,
    run_wiki_write_back_effector,
)


def _authenticated_call_adapter(
    *, node_id, output_keys, run_state, base_path, run_id, dry_run
):
    return run_authenticated_external_call_effector(
        node_id=node_id,
        output_keys=output_keys,
        run_state=run_state,
        base_path=base_path,
        run_id=run_id,
        dry_run=dry_run,
    )


def _wiki_write_back_adapter(
    *, node_id, output_keys, run_state, base_path, run_id, dry_run
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
    for node in getattr(branch, "node_defs", None) or []:
        effects = list(getattr(node, "effects", None) or [])
        if not effects:
            continue
        node_id = getattr(node, "node_id", "")
        output_keys = list(getattr(node, "output_keys", None) or [])
        per_node = evidence_map.setdefault(node_id, {})
        for sink in effects:
            adapter = _EFFECTORS.get(sink)
            if adapter is None:
                # Name the way FORWARD, not just the fact of refusal. Per-channel
                # sinks (github_pull_request, slack_message, x_post, …) were deleted
                # in the channel-agnostic rebuild: every integration is now composed
                # from the one generic primitive. A caller reaching here is almost
                # always a graph author still using a retired name, and telling them
                # only "unknown" leaves them guessing at a sink that will never exist.
                per_node[sink] = {
                    "error": f"unknown effect sink: {sink}",
                    "error_kind": "unknown_sink",
                    "valid_sinks": sorted(_EFFECTORS),
                    "remediation": (
                        f"{sink!r} is not a sink. Per-channel effectors were removed: "
                        f"any external integration — GitHub, Slack, X, anything with "
                        f"an HTTP API — is composed from "
                        f"{EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL!r} pointed at that "
                        f"API, using a deposited connection and a granted destination. "
                        f"Use that sink and put the endpoint in the request packet."
                    ),
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
                )
            except Exception as exc:  # defensive: never raise from completion path
                result = {
                    "error": f"effector crashed: {exc}",
                    "error_kind": "effector_crashed",
                }
            per_node[sink] = result
    return evidence_map


__all__ = [
    "EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL",
    "EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK",
    "run_authenticated_external_call_effector",
    "run_wiki_write_back_effector",
    "run_effects_for_branch",
]
