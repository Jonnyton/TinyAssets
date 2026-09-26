"""What arrives unasked from the two engine reads that blew a turn's context.

``read_graph target="model_options"`` returned 1,274,067 bytes and
``target="status"`` 32.6 KB to the same live turn on 2026-09-26. The generic
ceiling stops that killing a turn; these tests are about the answer being USEFUL
rather than merely small -- counts beside every page, and an explicit way to
reach the rest.
"""
from __future__ import annotations

import json

from tests.engine_authority_helpers import mock_engine_admission


def _model(provider: str, index: int, *, order: int | None = None) -> dict:
    """A row the real ``model_options_document`` would emit, fields and all."""
    return {
        "reference": {"provider_ref": provider, "model_id": f"vendor/model-{index}"},
        "source_kind": "http",
        "availability_basis": "discovered",
        "freshness": "fresh",
        "provider_default": False,
        "tools": True,
        "context_tokens": 128_000,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "pricing": {
            "freshness": "fresh", "unmetered": True,
            "charges": [{"component": "input", "amount_micros": 0, "confirmed": True}],
            "unknown_components": [],
        },
        "scores": {"source": "bench", "freshness": "fresh", "agentic": 1, "general": 2},
        "in_candidate_catalog": True,
        "order_index": order,
        "basis": "eligible",
        "labels": [],
        "reasons": [],
    }


def _catalogue(counts: dict[str, int]) -> dict:
    rows, position = [], 0
    for provider, count in counts.items():
        for index in range(count):
            rows.append(_model(provider, index, order=position))
            position += 1
    return {
        "version": 1, "universe_id": "u-pinned", "advisory": True,
        "kind": "advisory_model_options", "generation": 3,
        "policy_source": "saved", "mode": "explicit",
        "binding_state": "bound", "binding": {"id": "b-1", "revision": 2},
        "choice_authority": "accepted_manifest", "legacy_source": None,
        "preferences": {"anything": "here"},
        "accepted_model_access": {"openrouter": {"scope": "all"}},
        "sources": [{"provider_ref": provider, "access_method": "api_key",
                     "bind_key": "k", "reasons": []} for provider in counts],
        "options": rows, "unavailable": [], "source_failures": [],
        "order": [row["reference"] for row in rows],
    }


# ── model_options: compact by default, complete in its counts ───────────────

def test_the_default_view_is_compact_and_still_reports_the_totals():
    from tinyassets.engine_read_views import TOP_PER_SOURCE, compact_model_options

    document = _catalogue({"openrouter": 340, "anthropic": 11})
    full_bytes = len(json.dumps(document).encode())
    view = compact_model_options(document)
    assert full_bytes > 200_000, "the fixture has to be the size that caused this"

    assert len(json.dumps(view).encode()) < full_bytes // 20
    assert view["view"] == "compact"
    assert view["total_models"] == 351
    assert view["selectable_models"] == 351
    assert [source["provider_ref"] for source in view["sources"]] == [
        "openrouter", "anthropic",
    ]
    assert [source["models"] for source in view["sources"]] == [340, 11]
    assert all(len(source["top"]) <= TOP_PER_SOURCE for source in view["sources"])
    # The current choice survives the projection: it is the one fact the turn
    # that died was actually after.
    assert view["selected"] == {"provider_ref": "openrouter", "model_id": "vendor/model-0"}
    assert view["page"]["matching"] == 351
    assert view["page"]["next_offset"] == 1
    assert "query=" in view["how_to_see_more"]


def test_paging_walks_every_row_without_skipping_or_repeating_one():
    from tinyassets.engine_read_views import PAGE_ROWS, compact_model_options

    document = _catalogue({"openrouter": 57})
    seen, cursor, pages = [], compact_model_options(document)["page"]["next_offset"], 0
    while cursor is not None:
        view = compact_model_options(document, offset=cursor)
        assert len(view["models"]) <= PAGE_ROWS
        seen.extend(row["model_id"] for row in view["models"])
        cursor = view["page"]["next_offset"]
        pages += 1
        assert pages < 20, "paging did not terminate"

    assert seen == [f"vendor/model-{i}" for i in range(57)]
    assert len(seen) == len(set(seen)) == 57, "no row skipped, none returned twice"


def test_a_query_filters_by_model_id_or_provider():
    from tinyassets.engine_read_views import compact_model_options

    document = _catalogue({"openrouter": 30, "anthropic": 4})
    view = compact_model_options(document, query="model-1")
    ids = [row["model_id"] for row in view["models"]]
    assert ids, "a matching query must return rows"
    assert all("model-1" in model_id for model_id in ids)
    assert view["page"]["matching"] == len(
        [row for row in document["options"] if "model-1" in row["reference"]["model_id"]]
    )

    by_source = compact_model_options(document, query="anthropic")
    assert len(by_source["models"]) == 4
    assert all(row["provider_ref"] == "anthropic" for row in by_source["models"])

    empty = compact_model_options(document, query="no-such-model")
    assert empty["models"] == []
    assert empty["page"]["matching"] == 0
    assert empty["page"]["next_offset"] is None
    # Absent matches never hide the catalogue's real size.
    assert empty["total_models"] == 34


def test_a_compact_row_keeps_what_a_choice_turns_on():
    from tinyassets.engine_read_views import compact_model_options

    document = _catalogue({"openrouter": 3})
    document["options"][1]["in_candidate_catalog"] = False
    document["options"][1]["labels"] = ["recent_sign_in_failure"]
    document["options"][1]["reasons"] = [
        {"reason": "source_not_accepted", "component": "policy"},
    ]
    row = compact_model_options(document, query="model-1")["models"][0]

    assert row["model_id"] == "vendor/model-1"
    assert row["selectable"] is False
    assert row["context_tokens"] == 128_000
    assert row["tools"] is True
    assert row["unmetered"] is True
    assert row["labels"] == ["recent_sign_in_failure"]
    assert row["reasons"] == ["source_not_accepted"]
    # The bulk is what went: per-component pricing, modality lists, benchmarks.
    assert "pricing" not in row and "scores" not in row and "input_modalities" not in row


def test_a_refusal_is_never_projected_into_data():
    from tinyassets.engine_read_views import compact_model_options, universe_status_view

    for refusal in (
        {"error": "not_found", "resource": "model_options"},
        {"error": "model_options_unavailable"},
    ):
        assert compact_model_options(refusal) == refusal
        assert universe_status_view(refusal) == refusal
    assert compact_model_options("not json at all") == "not json at all"
    assert compact_model_options({"no": "options key"}) == {"no": "options key"}


# ── status: this universe, not the host ─────────────────────────────────────

def _status() -> dict:
    return {
        "persona": {"name": "tiny"},
        "schema_version": 9,
        "universe_id": "u-pinned",
        "universe_exists": True,
        "caveats": ["one"],
        "actionable_next_steps": ["two"],
        "request_identity": {"user_id": "sub-1"},
        "session_boundary": {"prior_session_at": None},
        "sandbox_status": {"ok": True},
        "per_provider_cooldown_remaining": {"openrouter": 0},
        "active_turn": None,
        "evidence": {"activity_log_tail": ["line"] * 400},
        "evidence_caveats": [],
        "identity_evidence": {"blob": "x" * 500},
        "storage_utilization": {"per_subsystem": {"logs": {"bytes": 1, "path": "/data"}}},
        "provider_admission": {"samples": []},
        "supervisor_liveness": {"alive": True},
        "auto_ship_health": {"state": "green"},
        "open_brain": {"entries": 0},
        "release_state": {"git_sha": "abc"},
        "daemon": {"has_work": False},
        "active_host": None,
        "tier_routing_policy": {"tiers": []},
        "missing_data_files": [],
    }


def test_status_drops_host_telemetry_and_names_what_it_dropped():
    from tinyassets.engine_read_views import HOST_STATUS_BLOCKS, universe_status_view

    document = _status()
    view = universe_status_view(document)

    assert len(json.dumps(view).encode()) < len(json.dumps(document).encode()) // 2
    for block in HOST_STATUS_BLOCKS:
        assert block not in view, block
    # Named, not silently gone: an agent that cannot see a block was omitted
    # concludes the platform does not report it.
    assert set(view["host_blocks_omitted"]) == set(HOST_STATUS_BLOCKS)
    assert 'query="full"' in view["how_to_see_more"]


def test_status_keeps_every_universe_fact():
    from tinyassets.engine_read_views import universe_status_view

    view = universe_status_view(_status())
    for kept in (
        "persona", "universe_id", "universe_exists", "caveats",
        "actionable_next_steps", "request_identity", "session_boundary",
        "sandbox_status", "per_provider_cooldown_remaining", "active_turn",
        "schema_version",
    ):
        assert kept in view, kept
    assert view["persona"] == {"name": "tiny"}
    # A cooldown explains a refusal to the agent itself, so it is universe state.
    assert view["per_provider_cooldown_remaining"] == {"openrouter": 0}


def test_a_status_with_no_host_blocks_is_passed_through_unchanged():
    from tinyassets.engine_read_views import universe_status_view

    lean = {"universe_id": "u-pinned", "persona": {"name": "tiny"}}
    assert universe_status_view(lean) == lean
    assert "host_blocks_omitted" not in universe_status_view(lean)


# ── the engine surface actually applies them ────────────────────────────────

def _bind(monkeypatch, payload: dict):
    import tinyassets.universe_server as us
    from tinyassets import engine_mcp_server as s

    monkeypatch.setattr(s, "_ACTOR_ID", "sub-1")
    monkeypatch.setattr(s, "_GRAPH_ID", "u-pinned")
    mock_engine_admission(monkeypatch, {s._GRAPH_ID})
    monkeypatch.setattr(us, "read_graph", lambda **kw: json.dumps(payload))
    return s


def test_the_engine_read_returns_the_compact_catalogue(monkeypatch):
    from tinyassets.engine_read_views import TOP_PER_SOURCE

    document = _catalogue({"openrouter": 340})
    s = _bind(monkeypatch, document)

    envelope = json.loads(s.read_graph(target="model_options"))
    view = envelope["content"]
    assert envelope["untrusted"] is True, "a provider's model names stay data"
    assert view["view"] == "compact"
    assert view["total_models"] == 340
    assert len(view["sources"][0]["top"]) == TOP_PER_SOURCE
    # The whole point: the payload the live turn choked on now fits a ceiling.
    assert len(json.dumps(view).encode()) < 24_576


def test_the_engine_read_pages_and_filters_the_catalogue(monkeypatch):
    document = _catalogue({"openrouter": 40})
    s = _bind(monkeypatch, document)

    paged = json.loads(s.read_graph(target="model_options", output_offset=1))["content"]
    assert [row["model_id"] for row in paged["models"]][0] == "vendor/model-0"
    assert paged["page"]["next_offset"] == 26

    second = json.loads(
        s.read_graph(target="model_options", output_offset=26)
    )["content"]
    assert [row["model_id"] for row in second["models"]][0] == "vendor/model-25"
    assert second["page"]["next_offset"] is None

    filtered = json.loads(
        s.read_graph(target="model_options", query="model-7")
    )["content"]
    assert {row["model_id"] for row in filtered["models"]} == {"vendor/model-7"}


def test_the_engine_status_read_trims_by_default_and_not_on_request(monkeypatch):
    s = _bind(monkeypatch, _status())

    trimmed = json.loads(s.read_graph(target="status"))
    assert "storage_utilization" not in trimmed
    assert trimmed["host_blocks_omitted"]

    full = json.loads(s.read_graph(target="status", query="full"))
    assert full == _status(), "query=full is the unabridged read, byte for byte"


def test_the_engine_get_status_tool_trims_the_same_way(monkeypatch):
    """The other status door on this surface, which has no parameters of its own."""
    import tinyassets.universe_server as us

    s = _bind(monkeypatch, _status())
    monkeypatch.setattr(us, "get_status", lambda **kw: json.dumps(_status()))

    trimmed = json.loads(s.get_status())
    assert "storage_utilization" not in trimmed and "release_state" not in trimmed
    assert trimmed["host_blocks_omitted"]
    assert trimmed["universe_id"] == "u-pinned"
