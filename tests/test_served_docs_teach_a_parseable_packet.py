"""Every packet the served docs show must parse through the REAL matcher.

Fourth gate in the same family, found the same way as the first three -- by the
founder's universe trying to do the job and reporting the exact refusal:

    external write failed - mkws/workspace: node 'mkws' declared
    effects=[workspace] but no output_key held a parseable workspace packet
    [no_matching_packet]

`_parse_packet` accepts a value only when ``packet["sink"] == "workspace"``.
The WORKSPACES section of `write_graph`'s docstring showed four example packets
and **none of them carried that field**, so an agent that followed the
documentation exactly produced something the runtime discarded. The universe
built the documented shape twice, got the identical refusal both times, and
stopped -- correctly, since the shape it was told to write could not work.

The sibling effector had it right all along: the channel node's docs show
``{"sink": "authenticated_external_call", ...}``. Only the workspace docs
omitted it.

Why the suite was silent: `tests/test_workspace_effector.py:90` builds every
packet through a helper that hardcodes ``"sink": EXTERNAL_WRITE_SINK_WORKSPACE``.
So the matcher, the effector and the whole path were exercised with a field the
docs never mentioned. That is the same blind spot as the previous three gates --
tests that construct the object directly cannot see a surface that teaches the
wrong shape.

These tests close it by extracting the packets from the DOCSTRING itself and
feeding them to the runtime's own parser. A doc example that stops parsing
fails here, whichever side changed.
"""
from __future__ import annotations

import json
import re

import pytest

from tinyassets.effectors.workspace import (
    EXTERNAL_WRITE_SINK_WORKSPACE,
    _find_packet,
    _parse_packet,
)


def _served_doc() -> str:
    import tinyassets.engine_mcp_server as server

    doc = server.write_graph.__doc__
    assert doc, "write_graph lost its docstring; the served surface is the docs"
    return doc


def _documented_workspace_packets() -> list[str]:
    """Every ``{...}`` literal in the docstring that names a workspace ``op``.

    Extracted from the prose rather than listed here, so a NEW example added to
    the docs is covered the day it is written instead of the day someone
    remembers to update a fixture.
    """
    doc = _served_doc().replace("\n", " ")
    # Doc literals are wrapped in double backticks and may wrap across lines.
    found = []
    for match in re.finditer(r"\{[^{}]*\}", doc):
        blob = match.group(0)
        if '"op"' in blob and any(
            op in blob for op in ('"create"', '"checkout"', '"push"', '"discard"')
        ):
            found.append(" ".join(blob.split()))
    return found


def test_the_docs_actually_show_workspace_packets() -> None:
    """Guard the guard: if extraction silently found nothing, everything below
    would pass vacuously."""
    packets = _documented_workspace_packets()
    assert len(packets) >= 4, (
        f"expected the create/checkout/push/discard examples, found {packets}"
    )


@pytest.mark.parametrize("blob", _documented_workspace_packets())
def test_every_documented_packet_names_the_sink(blob: str) -> None:
    assert '"sink"' in blob, (
        "this documented packet omits the field the runtime matches on, so an "
        f"agent copying it is refused no_matching_packet: {blob}"
    )
    assert f'"{EXTERNAL_WRITE_SINK_WORKSPACE}"' in blob, blob


@pytest.mark.parametrize("blob", _documented_workspace_packets())
def test_every_documented_packet_parses_through_the_real_matcher(blob: str) -> None:
    """The point of the whole file: the docs and the runtime, not two opinions."""
    # Replace the ``<placeholder>`` prose with values of the right shape so the
    # literal is JSON; the FIELDS are what is under test, not the examples'
    # sample values.
    concrete = re.sub(r"<[^>]*>", "x", blob)
    try:
        value = json.loads(concrete)
    except ValueError as exc:  # pragma: no cover - the assertion carries it
        pytest.fail(f"documented packet is not valid JSON ({exc}): {concrete}")

    assert _parse_packet(value) is not None, (
        "the runtime's own matcher rejects a packet the docs teach; an agent "
        f"following this example gets no_matching_packet: {concrete}"
    )


def test_a_packet_without_the_sink_is_refused() -> None:
    """The behaviour the docs were failing to mention, pinned directly.

    If this ever stops being true -- if the matcher grows a fallback -- the
    docs above should be revisited, not this test deleted.
    """
    assert _parse_packet({"op": "create", "storage": "scratch"}) is None


def test_the_refusal_the_universe_actually_hit() -> None:
    """End to end through `_find_packet`, the way the effector calls it."""
    documented_but_missing_sink = {"op": "create", "storage": "scratch"}
    key, packet = _find_packet(
        output_keys=["workspace_packet"],
        run_state={"workspace_packet": documented_but_missing_sink},
    )
    assert (key, packet) == (None, None), "this is the no_matching_packet path"

    with_sink = dict(documented_but_missing_sink, sink=EXTERNAL_WRITE_SINK_WORKSPACE)
    key, packet = _find_packet(
        output_keys=["workspace_packet"], run_state={"workspace_packet": with_sink}
    )
    assert key == "workspace_packet" and packet == with_sink


def test_a_json_string_packet_parses_too() -> None:
    """Code nodes return JSON strings as readily as dicts, and the docs do not
    distinguish; the matcher accepts both, so keep it that way."""
    blob = json.dumps({"sink": EXTERNAL_WRITE_SINK_WORKSPACE, "op": "create"})
    assert _parse_packet(blob) is not None
