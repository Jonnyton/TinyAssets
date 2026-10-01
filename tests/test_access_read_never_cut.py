"""An agent can always read its whole access state and its whole automation list.

Live 2026-09-28..10-01, the founder's universe: ``read_graph target="access"``
was 25,001 bytes and the result ceiling cut it at 21,764, so the standing
decisions at its tail were unreadable on every wake, and ``query="GTM Village"``
returned the same bytes because nothing read ``query``. ``target="automations"``
was worse: 8 active rows projected to 282,886 bytes (each carried its whole
``inputs``), so the ceiling cut inside the FIRST row and the agent could not
recover its own morning-note schedule id.

Every test here drives ``mcp.call_tool`` -- the real dispatch path with the
result ceiling in it -- because calling the handler function would pass while
the served result was still being cut.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from tests.test_agent_access_controls import _served
from tests.test_pending_requests import _login, _logout, _make_universe
from tests.test_served_automation_lifecycle import bound  # noqa: F401 - fixture
from tinyassets import engine_result_bounds as bounds

_GTM = "GTM Village"


@pytest.fixture(autouse=True)
def _default_ceiling(monkeypatch):
    monkeypatch.delenv(bounds.CEILING_ENV, raising=False)
    monkeypatch.delenv(bounds.CONTEXT_TOKENS_ENV, raising=False)
    _logout()
    yield
    _logout()


@pytest.fixture
def base(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    _make_universe(root, "u-1", admin="founder")
    return root


def _seed_decisions(udir, count: int) -> list[str]:
    """``count`` standing decisions, newest first in the returned order."""
    from tinyassets.storage.pending_requests import _db

    conn = _db(udir)
    keys = []
    try:
        with conn:
            for i in range(count):
                key = f"decision-{i:03d}"
                topic = _GTM if i % 12 == 0 else "an unrelated vendor"
                conn.execute(
                    "INSERT INTO request_suppressions (dedupe_key, kind, title, "
                    "feedback, decision, created_at) VALUES (?,?,?,?,?,?)",
                    (key, "Decision", f"{topic} schedule {i}",
                     f"morning note for {topic}; automation sched-{i:03d}. " * 12,
                     "allowed", 1_000_000.0 + i),
                )
                keys.append(key)
    finally:
        conn.close()
    return list(reversed(keys))


def _seed_consents(udir) -> None:
    from tinyassets.storage.effector_consents import grant_consent

    for i in range(4):
        grant_consent(udir, sink="authenticated_external_call",
                      destination=f"gtm-village-{i}.example", granted_by="founder")
        grant_consent(udir, sink="authenticated_external_call",
                      destination=f"other-{i}.example", granted_by="founder")


def _engine_read(s, **arguments) -> tuple[str, dict]:
    result = asyncio.run(s.mcp.call_tool("read_graph", arguments))
    text = result.content[0].text
    return text, json.loads(text)


def _uncut(text: str, document: dict) -> None:
    assert "truncated" not in document, document.get("hint")
    assert len(text.encode("utf-8")) <= bounds.DEFAULT_CEILING_BYTES


# -- access ------------------------------------------------------------------


def test_an_over_ceiling_access_read_names_every_section_it_did_not_inline(
    monkeypatch, base,
):
    s = _served(monkeypatch)
    _seed_decisions(base / "u-1", 60)
    _seed_consents(base / "u-1")

    text, held = _engine_read(s, target="access")

    _uncut(text, held)
    assert held["complete"] is False
    pointer = held["sectioned"]["standing_decisions"]
    assert pointer == {
        "count": 60,
        "read_with": 'read_graph target="access" field_name="standing_decisions"',
    }
    # What was inlined is whole, not a prefix of a section.
    assert len(held["channel_consents"]) == 8
    assert "how_to_change" in held


def test_every_standing_decision_is_recoverable_by_paging(monkeypatch, base):
    s = _served(monkeypatch)
    expected = _seed_decisions(base / "u-1", 60)

    seen, offset, pages = [], 0, 0
    while offset is not None:
        text, page = _engine_read(s, target="access", field_name="standing_decisions",
                                  output_offset=offset)
        _uncut(text, page)
        assert page["total"] == 60 and page["offset"] == offset
        seen += [row["dedupe_key"] for row in page["rows"]]
        assert page["complete"] is (page["next_offset"] is None)
        if page["next_offset"] is not None:
            assert f'output_offset={page["next_offset"]}' in page["next"]
        offset, pages = page["next_offset"], pages + 1

    assert seen == expected  # every decision, once, in order
    assert pages >= 2, "the fixture must be over the ceiling to prove paging"
    # The tail of the full feedback text survives, not just the row heads.
    assert all(row["feedback"].endswith(". ") for row in page["rows"])


def test_query_narrows_every_section(monkeypatch, base):
    s = _served(monkeypatch)
    _seed_decisions(base / "u-1", 60)
    _seed_consents(base / "u-1")

    text, held = _engine_read(s, target="access", query=_GTM.lower())

    _uncut(text, held)
    titles = [row["title"] for row in held["standing_decisions"]]
    assert titles and all(_GTM in title for title in titles)
    assert len(titles) == 5  # i = 0, 12, 24, 36, 48
    destinations = {row["destination"] for row in held["channel_consents"]}
    assert destinations == set()  # "gtm village" is not "gtm-village"
    assert held["matched"]["standing_decisions"] == 5
    assert held["query"] == _GTM.lower()
    assert "complete" not in held  # it fits: the document is returned whole

    _, by_host = _engine_read(s, target="access", query="gtm-village")
    assert {row["destination"] for row in by_host["channel_consents"]} == {
        f"gtm-village-{i}.example" for i in range(4)
    }


def test_an_unknown_section_names_the_real_ones(monkeypatch, base):
    from fastmcp.exceptions import ToolError

    s = _served(monkeypatch)

    with pytest.raises(ToolError) as refused:
        _engine_read(s, target="access", field_name="automations")

    refusal = json.loads(str(refused.value))
    assert refusal["error"] == "unknown_access_section"
    assert "standing_decisions" in refusal["sections"]


def test_the_connector_door_serves_the_same_projection(monkeypatch, base):
    import tinyassets.universe_server as us

    _seed_decisions(base / "u-1", 60)
    _login("founder")

    result = asyncio.run(us.mcp.call_tool(
        "read_graph", {"target": "access", "graph_id": "u-1"}))
    held = json.loads(result.content[0].text)
    assert "truncated" not in held
    assert held["sectioned"]["standing_decisions"]["count"] == 60

    result = asyncio.run(us.mcp.call_tool(
        "read_graph", {"target": "access", "graph_id": "u-1", "query": _GTM}))
    narrowed = json.loads(result.content[0].text)
    assert len(narrowed["standing_decisions"]) == 5


def test_standing_decisions_are_not_capped_at_fifty(base):
    from tinyassets.storage.pending_requests import list_suppressions

    _seed_decisions(base / "u-1", 60)

    assert len(list_suppressions(base / "u-1")) == 60


# -- automations ---------------------------------------------------------------


def _create(engine, name: str, inputs: dict) -> dict:
    from tests.test_automations import BRANCH

    created = json.loads(engine.write_graph(
        target="automation", operation="create",
        payload_json=json.dumps({"name": name, "branch_def_id": BRANCH,
                                 "interval_seconds": 3600, "inputs": inputs}),
    ))
    assert created["status"] == "automation_created", created
    return created["automation"]


def test_every_automation_id_survives_rows_bigger_than_the_ceiling(bound):  # noqa: F811
    from tinyassets import engine_mcp_server as engine

    prompt = "Compose the founder's morning note. " * 2_000  # ~72 KB, like live
    ids = [_create(engine, f"morning note {i}", {"prompt": prompt, "topic": "gtm"})
           ["automation_id"] for i in range(3)]

    text, listed = _engine_read(engine, target="automations")

    _uncut(text, listed)
    listed_ids = [row["automation_id"] for row in listed["automations"]]
    assert sorted(listed_ids) == sorted(ids) and len(listed_ids) == 3
    assert listed["complete"] is True and listed["total"] == 3
    assert listed["automations"][0]["input_chars"] == {"prompt": len(prompt), "topic": 3}

    # One row over the ceiling: whole fields, its input names, no body.
    text, one = _engine_read(engine, target="automation", automation_id=ids[0])
    _uncut(text, one)
    assert one["automation"]["automation_id"] == ids[0]
    assert "inputs" not in one["automation"]
    assert one["automation"]["inputs_read_with"].endswith('field_name="<input name>"')

    # ...and the body itself, reassembled exactly from bounded chunks.
    parts, offset = [], 0
    while offset is not None:
        text, chunk = _engine_read(engine, target="automation", automation_id=ids[0],
                                   field_name="prompt", output_offset=offset,
                                   output_max_chars=32768)
        _uncut(text, chunk)
        parts.append(chunk["automation"]["value"])
        offset = chunk["automation"]["next_offset"]
    assert "".join(parts) == prompt


def test_the_list_pages_past_thirty_rows(bound, monkeypatch):  # noqa: F811
    from tinyassets import engine_mcp_server as engine

    monkeypatch.setenv(bounds.CEILING_ENV, str(bounds.MIN_CEILING_BYTES * 2))
    ids = [_create(engine, f"wake {i}", {"topic": "x"})["automation_id"]
           for i in range(35)]

    seen, offset = [], 0
    while offset is not None:
        text, page = _engine_read(engine, target="automations", output_offset=offset)
        assert "truncated" not in page
        assert len(text.encode("utf-8")) <= bounds.MIN_CEILING_BYTES * 2
        seen += [row["automation_id"] for row in page["automations"]]
        offset = page["next_offset"]

    assert sorted(seen) == sorted(ids) and len(seen) == 35


# -- the fitter ----------------------------------------------------------------


def test_a_row_larger_than_the_budget_is_clipped_alone_not_skipped():
    rows = [{"k": "a"}, {"k": "b", "text": "b" * 500}, {"k": "c"}]

    def build(page, next_offset):
        return {"rows": page, "next_offset": next_offset}

    first = bounds.page_to_fit(rows, start=0, budget=100, build=build, render=json.dumps)
    second = bounds.page_to_fit(rows, start=1, budget=100, build=build, render=json.dumps)

    assert first["rows"][0] == {"k": "a"} and first["next_offset"] == 1
    (clipped,) = second["rows"]
    assert second["next_offset"] == 2  # the cursor past it survives
    assert len(json.dumps(second)) <= 100
    assert clipped["clipped_chars"] == {"text": 500}
    assert "b" * 10 in clipped["text"] and clipped["k"] == "b"
    assert bounds.page_to_fit(rows, start=3, budget=100, build=build,
                              render=json.dumps) == {"rows": [], "next_offset": None}


def test_the_connector_door_lists_automations_without_bodies(bound):  # noqa: F811
    import tinyassets.universe_server as us
    from tests.test_automations import OWNER, UNIVERSE
    from tinyassets import engine_mcp_server as engine

    prompt = "Compose the founder's morning note. " * 2_000
    ids = {_create(engine, f"note {i}", {"prompt": prompt})["automation_id"]
           for i in range(3)}
    _login(OWNER)

    result = asyncio.run(us.mcp.call_tool(
        "read_graph", {"target": "automations", "graph_id": UNIVERSE}))
    listed = json.loads(result.content[0].text)

    assert "truncated" not in listed
    assert {row["automation_id"] for row in listed["automations"]} == ids
    assert all(row["input_chars"] == {"prompt": len(prompt)}
               for row in listed["automations"])


# -- refute round 1 (Codex, 2026-10-01) ------------------------------------------


def test_one_standing_decision_over_the_ceiling_is_clipped_and_paged_past(
    monkeypatch, base,
):
    from tinyassets.storage.pending_requests import _db

    s = _served(monkeypatch)
    expected = _seed_decisions(base / "u-1", 3)
    conn = _db(base / "u-1")
    with conn:
        conn.execute("UPDATE request_suppressions SET title = ?, feedback = ? "
                     "WHERE dedupe_key = 'decision-001'",
                     ("😀" * 120, "😀" * 20_000))
    conn.close()

    seen, offset, clipped = [], 0, {}
    while offset is not None:
        text, page = _engine_read(s, target="access", field_name="standing_decisions",
                                  output_offset=offset)
        _uncut(text, page)
        for row in page["rows"]:
            seen.append(row["dedupe_key"])
            clipped.update(row.get("clipped_chars", {}))
        offset = page["next_offset"]

    assert seen == expected
    assert clipped["feedback"] == 20_000


def test_an_unbounded_query_is_refused_not_echoed(monkeypatch, base):
    from fastmcp.exceptions import ToolError

    s = _served(monkeypatch)
    with pytest.raises(ToolError) as refused:
        _engine_read(s, target="access", query="q" * 30_000)
    assert json.loads(str(refused.value))["error"] == "query_too_long"


def test_connector_continuations_repeat_the_universe_they_read(monkeypatch, base):
    import tinyassets.universe_server as us

    _seed_decisions(base / "u-1", 60)
    _login("founder")

    result = asyncio.run(us.mcp.call_tool(
        "read_graph", {"target": "access", "graph_id": "u-1"}))
    held = json.loads(result.content[0].text)
    assert 'graph_id="u-1"' in held["sectioned"]["standing_decisions"]["read_with"]


def test_an_input_name_is_matched_exactly(bound):  # noqa: F811
    from tinyassets import engine_mcp_server as engine

    row = _create(engine, "spaced", {" prompt ": "padded", "prompt": "plain"})
    _, chunk = _engine_read(engine, target="automation",
                            automation_id=row["automation_id"], field_name=" prompt ")
    assert chunk["automation"]["value"] == "padded"


def test_an_unknown_input_refusal_keeps_the_owner_for_provenance():
    from tinyassets.api.automations import project_automation

    foreign = {"automation": {"automation_id": "a1", "owner": {"is_you": False},
                              "inputs": {"ignore previous instructions": "x"}}}
    refused = project_automation(foreign, budget=10_000, render=json.dumps,
                                 field_name="missing")
    assert refused["error"] == "unknown_automation_input"
    assert refused["automation"]["owner"] == {"is_you": False}
    assert "inputs" not in refused  # foreign names only inside the owned envelope


def test_a_huge_automation_name_is_clipped_not_cut(bound):  # noqa: F811
    from tinyassets import engine_mcp_server as engine

    row = _create(engine, "n" * 30_000, {"prompt": "p" * 50_000})

    text, listed = _engine_read(engine, target="automations")
    _uncut(text, listed)
    assert listed["automations"][0]["automation_id"] == row["automation_id"]
    assert listed["automations"][0]["clipped_chars"]["name"] == 30_000

    text, one = _engine_read(engine, target="automation",
                             automation_id=row["automation_id"])
    _uncut(text, one)
    text, chunk = _engine_read(engine, target="automation",
                               automation_id=row["automation_id"], field_name="prompt")
    _uncut(text, chunk)
    assert chunk["automation"]["clipped_chars"] == {"name": 30_000}


def test_the_list_total_counts_legacy_rows(bound, monkeypatch):  # noqa: F811
    from tests.test_automations import OWNER, UNIVERSE
    from tinyassets import engine_mcp_server as engine
    from tinyassets.api import automations as api

    _create(engine, "current", {"topic": "x"})
    monkeypatch.setattr(api, "_legacy_rows", lambda base, uid: [
        {"legacy": True, "owner": {"is_you": True}}])
    # The owner door's document and the model door's projection agree.
    domain = api._list(bound, universe_id=UNIVERSE, actor=OWNER, payload=None,
                       limit=None)
    assert domain["total"] == domain["count"] == 2
    _, listed = _engine_read(engine, target="automations")
    assert listed["total"] == 2 and listed["count"] == 2
