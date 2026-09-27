"""The connector's two catalogue readers, and the ceiling around them.

The engine surface was bounded first (PR #4037). This is the other half: the
connector handed `structured_content` the whole payload while bounding only its
text block, so the 1,274,067-byte catalogue that ended a free model's turn on
2026-09-26 still reached a browser chatbot -- `structuredContent` is the half the
Apps SDK path exists to serve and the half a chatbot client parses.

Every test drives `mcp.call_tool`, not the module function: the ceiling lives in
the MCP adapter, so a test calling `universe_server.read_graph` directly would
pass while the served surface stayed unbounded.
"""
from __future__ import annotations

import asyncio
import base64
import json

import pytest

import tinyassets.universe_server as us


def _call(tool: str, arguments: dict):
    return asyncio.run(us.mcp.call_tool(tool, arguments))


def _model(provider: str, index: int, *, order: int | None = None) -> dict:
    """A row with every field the real `model_options_document` emits."""
    return {
        "reference": {"provider_ref": provider, "model_id": f"vendor/model-{index}"},
        "source_kind": "http", "availability_basis": "discovered",
        "freshness": "fresh", "provider_default": False, "tools": True,
        "context_tokens": 128_000,
        "input_modalities": ["text"], "output_modalities": ["text"],
        "pricing": {"freshness": "fresh", "unmetered": True,
                    "charges": [{"component": "input", "amount_micros": 0,
                                 "confirmed": True}],
                    "unknown_components": []},
        "scores": {"source": "bench", "freshness": "fresh", "agentic": 1, "general": 2},
        "in_candidate_catalog": True, "order_index": order,
        "basis": "eligible", "labels": [], "reasons": [],
    }


def _catalogue(count: int = 400) -> dict:
    rows = [_model("openrouter", i, order=i) for i in range(count)]
    return {
        "version": 1, "universe_id": "u-1", "advisory": True,
        "kind": "advisory_model_options", "generation": 3,
        "policy_source": "saved", "mode": "explicit", "binding_state": "bound",
        "binding": {"id": "b-1", "revision": 2},
        "choice_authority": "accepted_manifest", "legacy_source": None,
        "preferences": {}, "accepted_model_access": {},
        "sources": [{"provider_ref": "openrouter", "access_method": "api_key",
                     "bind_key": "k", "reasons": []}],
        "options": rows, "unavailable": [], "source_failures": [],
        "order": [row["reference"] for row in rows],
    }


@pytest.fixture
def catalogue(monkeypatch):
    """Serve a real-sized catalogue from the collector, unchanged."""
    document = _catalogue()
    import tinyassets.api.model_options as api

    monkeypatch.setattr(api, "read_model_options", lambda **kw: document)
    return document


# ── the picker's read is untouched ──────────────────────────────────────────

def test_the_pickers_complete_catalogue_survives_the_ceiling(catalogue):
    """`model_options` is exempt, and that exemption is what keeps the app working.

    `tinyassets/onboarding/app.html:1423` reads this target, and the spec requires
    every protocol-bounded choice to survive in structured content. If the ceiling
    ever stops exempting it, the owner can no longer pick a model they own.
    """
    result = _call("read_graph", {"target": "model_options"})
    structured = result.structured_content

    assert "truncated" not in structured
    assert len(structured["options"]) == 400
    assert len(json.dumps(structured).encode()) > 100_000, (
        "the complete document is genuinely over the ceiling — that is the point"
    )


# ── the model's read is bounded ─────────────────────────────────────────────

def test_the_summary_is_bounded_and_reports_the_totals(catalogue):
    from tinyassets.engine_result_bounds import DEFAULT_CEILING_BYTES

    structured = _call("read_graph", {"target": "model_options_summary"}).structured_content

    assert "truncated" not in structured, "the projection fits; nothing to truncate"
    assert len(json.dumps(structured).encode()) < DEFAULT_CEILING_BYTES
    assert structured["view"] == "compact"
    assert structured["total_models"] == 400
    assert structured["selectable_models"] == 400
    assert structured["sources"][0]["models"] == 400
    assert structured["selected"] == {"provider_ref": "openrouter",
                                      "model_id": "vendor/model-0"}


def test_paging_the_summary_covers_every_row_exactly_once(catalogue):
    seen, cursor, pages = [], 1, 0
    while cursor is not None:
        structured = _call(
            "read_graph", {"target": "model_options_summary", "output_offset": cursor},
        ).structured_content
        seen.extend(row["model_id"] for row in structured["models"])
        cursor = structured["page"]["next_offset"]
        pages += 1
        assert pages < 40, "paging did not terminate"

    assert seen == [f"vendor/model-{i}" for i in range(400)]
    assert len(seen) == len(set(seen)) == 400


def test_a_filter_reports_a_true_total(catalogue):
    structured = _call(
        "read_graph", {"target": "model_options_summary", "query": "model-39"},
    ).structured_content

    assert {row["model_id"] for row in structured["models"]} == {
        "vendor/model-39", "vendor/model-390", "vendor/model-391",
        "vendor/model-392", "vendor/model-393", "vendor/model-394",
        "vendor/model-395", "vendor/model-396", "vendor/model-397",
        "vendor/model-398", "vendor/model-399",
    }
    assert structured["page"]["matching"] == 11
    # A filter narrows the rows, never the catalogue's reported size.
    assert structured["total_models"] == 400

    empty = _call(
        "read_graph", {"target": "model_options_summary", "query": "nothing-matches"},
    ).structured_content
    assert empty["models"] == [] and empty["page"]["matching"] == 0
    assert empty["total_models"] == 400


def test_a_refusal_is_not_reshaped_into_catalogue_data(monkeypatch):
    import tinyassets.api.model_options as api

    refusal = {"error": "not_found", "resource": "model_options"}
    monkeypatch.setattr(api, "read_model_options", lambda **kw: refusal)

    for target in ("model_options", "model_options_summary"):
        structured = _call("read_graph", {"target": target}).structured_content
        assert structured["error"] == "not_found", target
        assert "options" not in structured and "sources" not in structured, target


# ── the ceiling itself, on the connector ────────────────────────────────────

def test_an_oversized_read_is_marked_in_structured_content(monkeypatch):
    """The gap this closes: the text block was bounded, the structured half was not."""
    from tinyassets.engine_result_bounds import DEFAULT_CEILING_BYTES

    huge = {"branches": [{"id": f"b-{i}", "name": "x" * 200} for i in range(400)]}
    monkeypatch.setattr(us, "_extensions_impl", lambda **kw: json.dumps(huge))
    assert len(json.dumps(huge).encode()) > DEFAULT_CEILING_BYTES

    structured = _call("read_graph", {"target": "branches"}).structured_content

    assert structured["truncated"] is True
    assert structured["original_bytes"] == len(
        json.dumps(huge, separators=(",", ":")).encode()
    )
    assert structured["ceiling_bytes"] == DEFAULT_CEILING_BYTES
    assert "query=" in structured["hint"]
    assert len(json.dumps(structured).encode()) <= DEFAULT_CEILING_BYTES


def test_a_read_within_the_ceiling_is_unchanged(monkeypatch):
    payload = {"branches": [{"id": "b-1", "name": "small"}]}
    monkeypatch.setattr(us, "_extensions_impl", lambda **kw: json.dumps(payload))

    structured = _call("read_graph", {"target": "branches"}).structured_content
    assert structured == payload


def test_exact_bytes_are_never_bounded_on_the_connector_either(monkeypatch):
    """`run_file`'s contract is exact bytes; truncating loses the paging cursor."""
    payload = {
        "file_id": "f-1",
        "bytes_base64": base64.b64encode(b"\x00\xff" * 131_072).decode(),
        "next_offset": 262_144, "eof": False,
    }
    import tinyassets.api.run_files as run_files

    monkeypatch.setattr(run_files, "read_file", lambda **kw: json.dumps(payload))
    assert len(json.dumps(payload).encode()) > 300_000

    structured = _call(
        "read_graph", {"target": "run_file", "run_id": "r-1", "file_id": "f-1"},
    ).structured_content

    assert "truncated" not in structured
    assert structured["next_offset"] == 262_144
    assert structured["bytes_base64"] == payload["bytes_base64"]


# ── scope: the handles a ceiling would destroy rather than bound ────────────

def test_the_ceiling_governs_exactly_one_handle():
    """An allowlist, and the reason each other handle is out of it.

    `converse` carries the universe's own reply to its founder — that reply is the
    product. `read_page`/`write_page` carry content the user authored (Hard Rule
    9). `get_status` is read by the app itself, so bounding it breaks the status
    dot. Widening this set means proving a partial reply is still a true one.
    """
    assert us._CEILING_TOOLS == {"read_graph"}
    for spared in ("converse", "read_page", "write_page", "get_status"):
        assert spared not in us._CEILING_TOOLS, spared


def test_the_exempt_set_is_two_entries_for_two_reasons():
    from tinyassets.engine_result_bounds import EXACT_BYTE_READS

    exempt = us._connector_ceiling_exempt()
    assert exempt == EXACT_BYTE_READS | {("read_graph", "model_options")}
    assert ("read_graph", "run_file") in exempt
    assert ("read_graph", "model_options") in exempt
    # The bounded sibling is NOT exempt — if it were, the split bought nothing.
    assert ("read_graph", "model_options_summary") not in exempt
    assert len(exempt) == 2, (
        "a third entry is evidence someone widened the hole instead of splitting "
        "the read — amend the spec requirement instead"
    )


def test_a_positional_target_is_still_recognised():
    """A positional call must not read as an unidentified one.

    An unidentified call is not exempt, so misreading `read_graph("run_file")`
    would truncate exact bytes.
    """
    bound = us._bound_arguments(us.read_graph, ("run_file",), {})
    assert bound["target"] == "run_file"
    assert us._bound_arguments(us.read_graph, (), {"target": "run_file"})["target"] == (
        "run_file"
    )
