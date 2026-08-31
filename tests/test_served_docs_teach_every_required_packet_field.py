"""Whatever the runtime demands of a workspace packet, the docs must teach.

Two gates, hours apart, were the same defect in different fields:

* `"sink": "workspace"` — required by `_parse_packet`, absent from all four
  documented examples. Fixed in #2748.
* `"grant_id"` — required by the checkout path
  (`effectors/workspace.py`: ``packet.grant_id is required``), absent from the
  documented checkout example. Found when the founder's universe followed the
  docs exactly and was refused `invalid_packet`.

The per-example test added with the first fix could not catch the second: it
asserted the examples PARSE, and parsing only needs the sink. So this file
asserts the stronger property — every field the effector refuses a packet for
lacking is a field the served docs mention.

Derived from the source rather than listed here, so a NEW requirement added to
the effector fails this the day it is written rather than the day a user hits
it. That is the whole point: nobody catches these by reading, because the
channel node's docs were right both times and only the workspace section was
wrong.
"""
from __future__ import annotations

import inspect
import re

import pytest

#: ``packet.<field> is required`` — the effector's own refusal wording.
_REQUIRED = re.compile(r"packet\.([a-z_]+) is required")


def _effector_source() -> str:
    import tinyassets.effectors.workspace as ws

    return inspect.getsource(ws)


def _served_workspace_docs() -> str:
    """The WORKSPACES section of `write_graph`'s docstring, flattened.

    Scoped to that section on purpose: the channel node's docs mention
    `grant_id` correctly, and searching the whole docstring would have passed
    while the workspace section was wrong — which is exactly how this shipped.
    """
    import tinyassets.engine_mcp_server as server

    doc = server.write_graph.__doc__ or ""
    assert doc, "write_graph lost its docstring; the served surface IS the docs"
    start = doc.index("WORKSPACES.")
    return " ".join(doc[start:].split())


def _required_fields() -> set[str]:
    return set(_REQUIRED.findall(_effector_source()))


def test_the_extraction_finds_something() -> None:
    """Guard the guard: a regex that silently matched nothing would make every
    assertion below pass vacuously."""
    found = _required_fields()
    assert found, "no 'packet.<field> is required' refusals found in the effector"
    assert "grant_id" in found, f"expected the known requirement; got {sorted(found)}"


@pytest.mark.parametrize("field", sorted(_required_fields()))
def test_every_required_packet_field_is_documented(field: str) -> None:
    docs = _served_workspace_docs()
    assert field in docs, (
        f"the workspace effector refuses a packet without {field!r}, and the "
        "served WORKSPACES docs never mention it — an agent following the "
        "documentation exactly is refused invalid_packet"
    )


def test_the_checkout_example_carries_both_connection_ids() -> None:
    """The specific shape the founder's universe was refused for.

    A checkout needs `connection_id` AND `grant_id`; the example carried only
    the first, so the documented packet could not work.
    """
    docs = _served_workspace_docs()
    start = docs.index('"op": "checkout"')
    example = docs[start - 60 : start + 320]
    for field in ("connection_id", "grant_id", "repo", "ref"):
        assert field in example, f"checkout example omits {field!r}: {example}"


def test_the_sink_is_still_in_every_example() -> None:
    """The first gate, kept pinned: parsing needs it and nothing else teaches
    it, so a docs rewrite must not quietly drop it again."""
    docs = _served_workspace_docs()
    ops = docs.count('"op": "')
    sinks = docs.count('"sink": "workspace"')
    assert ops >= 4, f"expected the create/checkout/push/discard examples, saw {ops}"
    assert sinks >= ops, (
        f"{ops} documented packets but only {sinks} carry the sink the runtime "
        "matches on"
    )
