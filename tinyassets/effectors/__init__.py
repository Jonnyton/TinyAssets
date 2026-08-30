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

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from tinyassets.effectors.authenticated_external_call import (
    EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL,
    bounded_evidence,
    packet_accept_statuses,
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


class EffectFailedError(Exception):
    """A node's declared effect could not do what its packet said (design D1,
    change `sandboxed-code-node`): the packet was refused before the wire, the
    adapter crashed, the sink does not exist, or a WRITE was answered >= 400 by
    the far side. The node fails and the run ends ``failed`` with exactly the
    message shape the run surfaces already classify
    (``external write failed - <node>/<sink>: <error> [<kind>]``), so
    ``external_write_failed`` / ``external_write_refused`` keep their
    actionability. Later nodes do not run: no ``open_pr`` 422 after a refused
    ``write_readme``, no dangling branches (live 2026-08-30, runs
    6cb4d9f48a9949be / 7a7a91c14b0d4b8b). A READ answered >= 400 is data, not a
    failure - probe-then-branch stays possible."""

    def __init__(self, node_id: str, sink: str, error: str, error_kind: str = "") -> None:
        self.node_id = node_id
        self.sink = sink
        self.error = error
        self.error_kind = error_kind or "effect_failed"
        super().__init__(
            f"external write failed - {node_id}/{sink}: {error} [{self.error_kind}]"
        )


_READ_VERBS = frozenset({"GET", "HEAD"})


@dataclass
class EffectChain:
    """Run-scoped effect state. Effects fire at node time (design D1); this is
    what they leave behind for the rest of the run and for persistence:

    - ``results``: node_id -> the FULL authenticated-call result, in memory
      only, so a later packet's ``$ta.effect`` and a code node's ``effects``
      see whole bodies, never the 4 KiB preview.
    - ``evidence``: node_id -> {sink: bounded evidence} - what is persisted on
      every terminal status, failure included.
    - ``fired``: one (sink, verb) per effect that ran - what the engine budget
      settles on (``tinyassets.engine_admissions``).

    The chain is created by the runner before ``compile_branch``, registered
    under its run id so ``update_run_status`` can settle from ``fired`` on any
    terminal path, and forgotten at terminal status.
    """

    run_id: str = ""
    base_path: Any = None
    dry_run: bool | None = None
    cloud_effect_session: Any = None
    results: dict[str, dict] = field(default_factory=dict)
    evidence: dict[str, dict] = field(default_factory=dict)
    fired: list[tuple[str, str | None]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    settled: bool = False

    def prior_effects(self, ancestors: set[str] | None = None) -> dict[str, dict]:
        """Full results of the nodes a reference may legally name (for
        ``$ta.effect``): the node's graph ANCESTORS (Codex round 1, P1) - a
        graph-defined relation, not "whatever happened to complete first",
        so the same branch never resolves on one run and refuses on the next.
        ``None`` = no ancestry known (legacy post-run dispatch): every
        completed node."""
        with self.lock:
            items = dict(self.results)
        if ancestors is None:
            return items
        return {k: v for k, v in items.items() if k in ancestors}

    def effects_view(self, ancestors: set[str] | None = None) -> dict[str, dict]:
        """What a code node receives as ``effects``: node_id -> {status, body}
        for its graph ancestors, a JSON body parsed when it parses. NEVER the
        response headers: ``$ta.effect`` denies them and persisted evidence
        strips their values because a ``Set-Cookie`` there is a credential
        (Codex round 1, P0) - code gets exactly what a packet could reference,
        no more."""
        out: dict[str, dict] = {}
        for node_id, result in self.prior_effects(ancestors).items():
            response = result.get("response") if isinstance(result.get("response"), dict) else None
            if not isinstance(response, dict):
                continue
            body = response.get("body")
            if isinstance(body, str) and body.lstrip()[:1] in ("{", "["):
                try:
                    body = json.loads(body)
                except ValueError:
                    pass
            out[node_id] = {"status": response.get("status"), "body": body}
        return out

    def delivered_nodes(self) -> list[str]:
        """Nodes whose effect reached the far side - what a failed run must
        still report (design D1: 'failed after writes' is a real state)."""
        with self.lock:
            evidence = dict(self.evidence)
        out = []
        for node_id, per_sink in evidence.items():
            for result in (per_sink or {}).values():
                if isinstance(result, dict) and result.get("delivered") is True:
                    out.append(node_id)
                    break
        return out

    def settle(self) -> None:
        """Settle the run's engine admission from what actually fired. Idempotent;
        a write that fired before a failure still settles as a write."""
        with self.lock:
            if self.settled:
                return
            self.settled = True
            fired = list(self.fired)
        settle_engine_admission(self.run_id, fired)


_ACTIVE_CHAINS: dict[str, EffectChain] = {}
_ACTIVE_CHAINS_LOCK = threading.Lock()


def register_effect_chain(chain: EffectChain) -> None:
    if not chain.run_id:
        return
    with _ACTIVE_CHAINS_LOCK:
        _ACTIVE_CHAINS[chain.run_id] = chain


def active_effect_chain(run_id: str) -> EffectChain | None:
    with _ACTIVE_CHAINS_LOCK:
        return _ACTIVE_CHAINS.get(run_id)


def forget_effect_chain(run_id: str) -> EffectChain | None:
    with _ACTIVE_CHAINS_LOCK:
        return _ACTIVE_CHAINS.pop(run_id, None)


def dispatch_node_effects(
    chain: EffectChain,
    node,
    run_state: dict,
    *,
    state_schema=None,
    ancestors: set[str] | None = None,
) -> dict[str, dict]:
    """Fire ``node.effects`` NOW, against ``run_state`` = the state the node saw
    merged with the delta it returned (the packet lives in that delta). Records
    full results, bounded evidence and fired verbs on ``chain``; raises
    ``EffectFailedError`` per design D1 so the node - and the run - fail.

    A node's effects fire AT MOST ONCE per run (Codex round 1, P0): a cycle
    that revisits an effect node fails on the second visit instead of firing
    the same PUT up to the recursion ceiling under one admission."""
    effects = list(getattr(node, "effects", None) or [])
    if not effects:
        return {}
    node_id = getattr(node, "node_id", "")
    with chain.lock:
        already = node_id in chain.evidence
    if already:
        raise EffectFailedError(
            node_id, effects[0],
            "this node's effects already fired in this run - a cycle revisited it; "
            "each node's effects fire at most once per run, so route the loop "
            "around the effect node or split the branch",
            "effect_already_fired",
        )
    per_node = _fire_node_effects(
        node, run_state, chain=chain,
        schema_defaulted=_schema_defaulted_keys(state_schema),
        ancestors=ancestors,
    )
    with chain.lock:
        chain.evidence[node_id] = per_node
    accept = packet_accept_statuses(
        output_keys=list(getattr(node, "output_keys", None) or []), run_state=run_state,
    )
    failure = first_effect_failure(per_node, accept_statuses=accept)
    if failure is not None:
        sink, error, kind = failure
        raise EffectFailedError(node_id, sink, error, kind)
    return per_node


def first_effect_failure(
    per_node: dict, *, accept_statuses: set[int] | None = None,
) -> tuple[str, str, str] | None:
    """The D1 rule over one node's evidence: (sink, error, kind) for the first
    effect that failed the node, or None. A refusal before the wire, a crash
    and a dead sink always fail. A delivered call answered >= 400 fails
    whatever its verb - the HTTP method is not intent (a GraphQL query is a
    POST; a required GET that 404s must not feed an error body downstream,
    Codex round 1) - UNLESS the packet declared that status in
    ``accept_statuses`` (probe-then-branch: ``"accept_statuses": [404]``).
    Accounting (read vs write for the budget) stays verb-based and separate."""
    accept = set(accept_statuses or ())
    for sink, result in (per_node or {}).items():
        if not isinstance(result, dict):
            continue
        if result.get("delivered") is True:
            response = result.get("response") if isinstance(result.get("response"), dict) else {}
            status = response.get("status")
            if isinstance(status, int) and status >= 400 and status not in accept:
                body = response.get("body")
                preview = (body if isinstance(body, str) else str(body or ""))[:200]
                error = f"far side answered HTTP {status}: {preview}".rstrip(": ")
                return (sink, error, "far_side_error")
            continue
        kind = str(result.get("error_kind") or "")
        error = str(result.get("error") or "")
        if error or kind:
            return (sink, error or f"refused before the wire: {kind}", kind or "effect_failed")
    return None


def _fire_node_effects(
    node, run_state, *, chain: EffectChain, schema_defaulted: set,
    ancestors: set[str] | None = None,
) -> dict:
    """Run every sink one node declares and return its bounded evidence
    ({sink: result}); full authenticated-call results and fired verbs land on
    ``chain``. Never raises: every failure is a structured row (the D1 rule is
    applied by the caller)."""
    node_id = getattr(node, "node_id", "")
    output_keys = list(getattr(node, "output_keys", None) or [])
    # A packet may read ONLY the node's declared input_keys plus the
    # state_schema-defaulted keys - never the whole final state (Codex
    # round 1, P0). This is NARROWER than the compiler's render view
    # (which shows everything when isolation is off or no inputs are
    # declared) on purpose: an effect reads less, never more.
    allowed_state_keys = set(getattr(node, "input_keys", None) or []) | schema_defaulted
    prior_effects = chain.prior_effects(ancestors)
    per_node: dict[str, dict] = {}
    for sink in list(getattr(node, "effects", None) or []):
        adapter = _EFFECTORS.get(sink)
        if adapter is None:
            # Say what to do instead, not just what is wrong. A branch stored
            # before a per-channel sink was retired keeps naming it forever,
            # and the node then does NOTHING every run. Observed live
            # 2026-08-29: a stored "Docs Touch PR" branch still declared
            # `github_pull_request`. The platform ships exactly two sinks on
            # purpose (channels are user-built graph nodes over the generic
            # call, never hard-coded effectors): the branch must be rebuilt
            # against a supported sink.
            supported = ", ".join(sorted(_EFFECTORS))
            # A sink we do not know is not a read (Codex round 2): what it
            # would have done is unknown, so the run stays a write.
            with chain.lock:
                chain.fired.append((sink, None))
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
                base_path=chain.base_path,
                run_id=chain.run_id,
                dry_run=bool(chain.dry_run),
                allowed_state_keys=allowed_state_keys,
                prior_effects=prior_effects,
            )
        except Exception as exc:  # defensive: never raise from an adapter
            result = {
                "error": f"effector crashed: {exc}",
                "error_kind": "effector_crashed",
            }
        if not chain.dry_run:
            verb = result.get("verb") if isinstance(result, dict) else None
            if isinstance(result, dict) and result.get("error_kind") == "method_mismatch":
                # verb and request.method disagreed: the result echoes the
                # declared verb, which says nothing about intent (Codex).
                verb = None
            elif not verb and sink == EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL:
                # Refused before the wire (a gate, a bad packet): the verb the
                # packet DECLARED still says whether it could have written.
                verb = packet_verb(output_keys=output_keys, run_state=run_state)
            with chain.lock:
                chain.fired.append((sink, verb))
        if sink == EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL and isinstance(result, dict):
            with chain.lock:
                chain.results[node_id] = result
            _log_effect_not_ok(chain.run_id, node_id, result)
            result = bounded_evidence(result, node_id=node_id)
        per_node[sink] = result
    return per_node


def run_effects_for_branch(
    *,
    branch,
    run_state,
    base_path=None,
    run_id="",
    dry_run=None,
    cloud_effect_session=None,
):
    """Post-run dispatch of every node's effects, in branch STORAGE order.

    This is the legacy path for a branch compiled WITHOUT an effect chain
    (tests, callers outside the runner). Production runs fire effects at node
    time through ``dispatch_node_effects`` and never come here - the runner
    reads the chain's evidence instead, so nothing is dispatched twice.
    Failures are structured rows, never raised.
    """
    chain = EffectChain(
        run_id=run_id, base_path=base_path, dry_run=dry_run,
        cloud_effect_session=cloud_effect_session,
    )
    schema_defaulted = _schema_defaulted_keys(getattr(branch, "state_schema", None))
    for node in getattr(branch, "node_defs", None) or []:
        if not list(getattr(node, "effects", None) or []):
            continue
        chain.evidence[getattr(node, "node_id", "")] = _fire_node_effects(
            node, run_state, chain=chain, schema_defaulted=schema_defaulted,
        )
    chain.settle()
    return chain.evidence

def _log_effect_not_ok(run_id, node_id, result) -> None:
    """One log line per outbound call that did not succeed: the far side
    answered >= 400, or the packet was refused before the wire. Concern
    2026-08-28: GitHub said 403 and the daemon log said nothing for 25 minutes
    while the reason sat in the evidence map. Status line and the first bytes
    of the response only - never the request, which carries the credential
    path. Never raises into the completion path."""
    try:
        response = result.get("response")
        status = response.get("status") if isinstance(response, dict) else None
        if isinstance(status, int) and status >= 400:
            body = response.get("body")
            preview = (body if isinstance(body, str) else str(body or ""))[:200]
            logging.getLogger(__name__).warning(
                "external effect refused by the far side: run=%s node=%s status=%s body=%s",
                run_id,
                node_id,
                status,
                preview.replace(chr(10), " "),
            )
        elif result.get("error") or result.get("error_kind"):
            logging.getLogger(__name__).warning(
                "external effect did not fire: run=%s node=%s kind=%s error=%s",
                run_id,
                node_id,
                result.get("error_kind"),
                str(result.get("error") or "")[:200].replace(chr(10), " "),
            )
    except Exception:  # pragma: no cover - defensive: the completion path never raises
        pass


def settle_engine_admission(run_id, fired) -> None:
    """Downgrade the run's engine admission to a read when nothing it fired
    could have changed the far side (GET/HEAD authenticated calls, or nothing
    at all - a run that failed or was cancelled fired nothing, because effects
    fire only after success). A run that was not engine-triggered has no
    admission row: no-op. Never raises into the completion path; a failure to
    settle leaves the row a write, which is the strict side."""
    if not run_id:
        return
    try:
        from tinyassets.engine_admissions import fired_only_reads, reclassify_read, settle_write

        if fired_only_reads(list(fired), read_sink=EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL):
            reclassify_read(str(run_id))
        else:
            # Final: a status rewritten to FAILED after these effects fired
            # must not turn this write into a read (Codex round 3).
            settle_write(str(run_id))
    except Exception:  # pragma: no cover - defensive: the completion path never raises
        logging.getLogger(__name__).exception("engine admission settle failed")


__all__ = [
    "EffectChain",
    "EffectFailedError",
    "dispatch_node_effects",
    "first_effect_failure",
    "register_effect_chain",
    "active_effect_chain",
    "forget_effect_chain",
    "EXTERNAL_WRITE_SINK_AUTHENTICATED_CALL",
    "EXTERNAL_WRITE_SINK_WIKI_WRITE_BACK",
    "run_authenticated_external_call_effector",
    "run_wiki_write_back_effector",
    "run_effects_for_branch",
]
