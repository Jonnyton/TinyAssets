"""What a served agent gets by DEFAULT from the two biggest engine reads.

The generic ceiling (``engine_result_bounds``) is a backstop: it stops a turn
dying of context overflow, but a truncated catalogue is still a bad answer. These
projections are the good answer -- the same reads, shaped so the agent can act on
them without asking for a megabyte first.

Measured on the live turn that caused this (2026-09-26, free-model universe,
``read_graph target="model_options"``): 1,274,067 bytes of model catalogue and
32.6 KB of status, in a turn that only wanted to know which model was selected.

Both projections are ADDITIVE about detail, never about existence: a count is
always beside a page, so the agent can see there are 347 models even when it is
looking at 8 of them. Nothing here decides anything for the agent; it decides
what arrives unasked.

Scope: the ENGINE surface only. ``read_model_options`` and ``get_status``
themselves are unchanged, because the owner's own model picker in the app is
specified to receive the complete catalogue
(``openspec/specs/live-mcp-connector-surface/spec.md``, "Complete choices, not a
first-page sample"). Narrowing what the picker receives is a spec change and does
not belong in a bug fix.
"""

from __future__ import annotations

#: Models shown per source in the default (unfiltered, first-page) view. Enough
#: to choose from -- the top of the platform's own ordering is where a sane
#: choice already is -- without enumerating a whole provider's inventory.
TOP_PER_SOURCE = 8

#: Rows per page once the agent filters or pages explicitly. It asked, so it gets
#: more, still bounded.
PAGE_ROWS = 25

_MODEL_OPTIONS_MORE = (
    'read_graph target="model_options" query="<text>" filters by model id or '
    "provider; output_offset=<n> pages through the filtered rows "
    "(next_offset tells you where to continue)"
)

#: Status blocks that describe the HOST and the deployment, not this universe:
#: activity-log tails, byte counts of the host's disk, ship health, supervisor
#: and release state. The uptime probes read them; a universe agent asked to
#: build a UI does not, and they are most of the 32.6 KB. Present in full via
#: ``query="full"``.
#:
#: A DENY list on purpose: a status field added next month is universe state far
#: more often than host telemetry, so the default must be to pass it through.
#: Dropping something the agent needed is a silent wrong answer; carrying one
#: extra small field is not.
HOST_STATUS_BLOCKS = (
    "evidence",
    "evidence_caveats",
    "identity_evidence",
    "storage_utilization",
    "provider_admission",
    "supervisor_liveness",
    "auto_ship_health",
    "open_brain",
    "release_state",
    "daemon",
    "active_host",
    "tier_routing_policy",
    "missing_data_files",
)

_STATUS_FULL_HINT = 'read_graph target="status" query="full" returns every block'


def _reference(row: object) -> tuple[str, str]:
    reference = row.get("reference") if isinstance(row, dict) else None
    if not isinstance(reference, dict):
        return "", ""
    return (
        str(reference.get("provider_ref") or ""),
        str(reference.get("model_id") or ""),
    )


def _compact_row(row: dict) -> dict:
    """One model as the facts a choice actually turns on.

    Kept: who serves it, its id, where the platform's own order puts it, whether
    it can be selected at all, its context window, tool support, and whether it
    costs anything. Dropped: per-component pricing, modality lists, benchmark
    scores, freshness stamps and eligibility prose -- available in the full read.
    """
    provider_ref, model_id = _reference(row)
    pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
    compact = {
        "provider_ref": provider_ref,
        "model_id": model_id,
        "order_index": row.get("order_index"),
        "selectable": bool(row.get("in_candidate_catalog")),
        "context_tokens": row.get("context_tokens"),
        "tools": row.get("tools"),
        "unmetered": pricing.get("unmetered"),
    }
    labels = row.get("labels")
    if isinstance(labels, list) and labels:
        compact["labels"] = labels
    reasons = row.get("reasons")
    if isinstance(reasons, list) and reasons:
        # Only the reason word: a model the agent cannot pick must say why, but
        # the component/prose belongs to the full read.
        compact["reasons"] = sorted({
            str(item.get("reason")) for item in reasons if isinstance(item, dict)
        })
    return compact


def _ordered(rows: list[dict]) -> list[dict]:
    """The platform's existing ordering, with unordered models after it.

    ``order_index`` is the plan's own candidate order -- this adds no ranking of
    its own. A model outside that order is still a choice, so it follows rather
    than disappearing.
    """
    def key(row: dict) -> tuple:
        index = row.get("order_index")
        ordered = type(index) is int
        provider_ref, model_id = _reference(row)
        return (0 if ordered else 1, index if ordered else 0, provider_ref, model_id)

    return sorted(rows, key=key)


def _matches(row: dict, needle: str) -> bool:
    provider_ref, model_id = _reference(row)
    return needle in model_id.lower() or needle in provider_ref.lower()


def compact_model_options(document: object, *, query: str = "", offset: int = 0) -> object:
    """Project the full advisory catalogue into a default a small model can read.

    An error document, or anything that is not the catalogue, passes through
    untouched: a projection must never turn a refusal into data.

    Three shapes, one function:

    * no query and ``offset`` 0 -- per source: how many models it has, how many
      are selectable, the current choice, and the top ``TOP_PER_SOURCE`` of the
      platform's own order;
    * a ``query`` -- the matching rows, ``PAGE_ROWS`` at a time;
    * ``offset`` past 0 -- every row, ``PAGE_ROWS`` at a time, same order.

    Every shape carries totals and ``next_offset``, so "there are more" is never
    something the agent has to infer.
    """
    if not isinstance(document, dict) or "options" not in document or document.get("error"):
        return document
    rows = [row for row in document.get("options") or () if isinstance(row, dict)]
    needle = (query or "").strip().lower()
    # A CURSOR, not an index: the agent copies back the ``next_offset`` it was
    # handed. 0 means "no cursor yet", which is the default view -- so the flat
    # listing's first row is cursor 1 and no row is unreachable.
    cursor = offset if type(offset) is int and offset > 0 else 0
    start = max(0, cursor - 1)
    view: dict[str, object] = {
        "kind": document.get("kind"),
        "view": "compact",
        "generation": document.get("generation"),
        "policy_source": document.get("policy_source"),
        "mode": document.get("mode"),
        "binding_state": document.get("binding_state"),
        "binding": document.get("binding"),
        "choice_authority": document.get("choice_authority"),
        "selected": _selected(document),
        "total_models": len(rows),
        "selectable_models": sum(1 for row in rows if row.get("in_candidate_catalog")),
        "unavailable_count": len(document.get("unavailable") or ()),
        "source_failures": document.get("source_failures"),
        "how_to_see_more": _MODEL_OPTIONS_MORE,
    }
    if needle or cursor:
        matching = _ordered([row for row in rows if not needle or _matches(row, needle)])
        page = matching[start:start + PAGE_ROWS]
        after = start + len(page)
        view["query"] = needle
        view["models"] = [_compact_row(row) for row in page]
        view["page"] = {
            "offset": cursor or 1, "returned": len(page), "matching": len(matching),
            "next_offset": (after + 1) if after < len(matching) else None,
        }
        return view
    view["sources"] = _source_summaries(rows, document)
    shown = sum(len(source["top"]) for source in view["sources"])
    view["page"] = {
        "offset": 0, "returned": shown, "matching": len(rows),
        # The whole flat listing from row one, not "the rest after the tops":
        # each source's top rows are a sample, so resuming past them would skip
        # models that belong to no source's head.
        "next_offset": 1 if shown < len(rows) else None,
    }
    return view


def _selected(document: dict) -> object:
    """The current choice as the picker's own ``order`` reports it."""
    order = document.get("order")
    if isinstance(order, list) and order and isinstance(order[0], dict):
        return order[0]
    return None


def _source_summaries(rows: list[dict], document: dict) -> list[dict]:
    """Per-source counts plus the head of the order, in source document order."""
    by_source: dict[str, list[dict]] = {}
    for row in rows:
        by_source.setdefault(_reference(row)[0], []).append(row)
    listed = [
        str(source.get("provider_ref") or "")
        for source in document.get("sources") or ()
        if isinstance(source, dict)
    ]
    order = [ref for ref in listed if ref in by_source]
    order += [ref for ref in by_source if ref not in set(order)]
    summaries = []
    for ref in order:
        owned = _ordered(by_source[ref])
        summaries.append({
            "provider_ref": ref,
            "models": len(owned),
            "selectable": sum(1 for row in owned if row.get("in_candidate_catalog")),
            "top": [_compact_row(row) for row in owned[:TOP_PER_SOURCE]],
        })
    return summaries


def universe_status_view(document: object) -> object:
    """Drop the host/deployment telemetry from a served agent's status read.

    The dropped block NAMES are kept in ``host_blocks_omitted`` beside the hint
    that returns them, because an agent that cannot see a field was omitted will
    conclude the platform does not report it.
    """
    if not isinstance(document, dict) or document.get("error"):
        return document
    omitted = [key for key in HOST_STATUS_BLOCKS if key in document]
    if not omitted:
        return document
    view = {key: value for key, value in document.items() if key not in set(omitted)}
    view["host_blocks_omitted"] = omitted
    view["how_to_see_more"] = _STATUS_FULL_HINT
    return view
