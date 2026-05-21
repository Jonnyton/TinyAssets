"""DESIGN-008 — selector-branch dispatch unit tests.

Covers ``workflow.api.selector_dispatch`` directly:

  * ``resolve_selector_branch_version_id`` — goal_binding vs.
    platform_default fallback.
  * ``ensure_default_selector_published`` — idempotency,
    deterministic branch_def_id, active version returned.
  * ``dispatch_selector`` output parsing under several malformed
    shapes (missing key, wrong type, non-coercible score, etc.).
  * Empty candidate set short-circuits without dispatching.

The selector dispatch tests that need an actual LLM run live in
``test_quality_leaderboard.py`` where they monkeypatch
``dispatch_selector`` itself.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def base_path(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    from workflow.daemon_server import initialize_author_server
    from workflow.runs import initialize_runs_db
    initialize_author_server(tmp_path)
    initialize_runs_db(tmp_path)
    return tmp_path


def _make_goal(
    base_path: Path,
    goal_id: str,
    *,
    selector_branch_version_id: str | None = None,
) -> dict:
    from workflow.daemon_server import save_goal, update_goal
    save_goal(
        base_path,
        goal=dict(
            goal_id=goal_id,
            name=goal_id,
            description="",
            author="host",
            tags=[],
            visibility="public",
        ),
    )
    if selector_branch_version_id is not None:
        update_goal(
            base_path,
            goal_id=goal_id,
            updates={
                "selector_branch_version_id": selector_branch_version_id,
            },
        )
    from workflow.daemon_server import get_goal
    return get_goal(base_path, goal_id=goal_id)


# ---------------------------------------------------------------------------
# ensure_default_selector_published — idempotency + active version
# ---------------------------------------------------------------------------


def test_default_selector_publishes_on_first_call(base_path):
    from workflow.api.selector_dispatch import (
        DEFAULT_SELECTOR_BRANCH_DEF_ID,
        ensure_default_selector_published,
    )
    bvid = ensure_default_selector_published(base_path)
    assert bvid.startswith(DEFAULT_SELECTOR_BRANCH_DEF_ID + "@")


def test_default_selector_is_idempotent(base_path):
    from workflow.api.selector_dispatch import ensure_default_selector_published
    a = ensure_default_selector_published(base_path)
    b = ensure_default_selector_published(base_path)
    assert a == b


def test_default_selector_branch_def_exists_after_publish(base_path):
    from workflow.api.selector_dispatch import (
        DEFAULT_SELECTOR_BRANCH_DEF_ID,
        ensure_default_selector_published,
    )
    ensure_default_selector_published(base_path)
    from workflow.daemon_server import get_branch_definition
    branch = get_branch_definition(
        base_path, branch_def_id=DEFAULT_SELECTOR_BRANCH_DEF_ID,
    )
    assert branch["name"] == "Platform Default Selector v1"
    assert branch["author"] == "platform"
    node_ids = [n["node_id"] for n in branch.get("node_defs", [])]
    assert "rank" in node_ids


# ---------------------------------------------------------------------------
# resolve_selector_branch_version_id — binding vs default
# ---------------------------------------------------------------------------


def test_resolve_returns_goal_binding_when_set(base_path):
    # Bind the goal to a deliberately-fake bvid so we don't accidentally
    # publish a default; we just want to confirm the resolver prefers
    # the explicit binding.
    _make_goal(
        base_path, "g1",
        selector_branch_version_id="some_branch@deadbeef",
    )
    from workflow.api.selector_dispatch import resolve_selector_branch_version_id
    result = resolve_selector_branch_version_id(base_path, goal_id="g1")
    assert result["ok"] is True
    assert result["branch_version_id"] == "some_branch@deadbeef"
    assert result["source"] == "goal_binding"


def test_resolve_falls_back_to_platform_default(base_path):
    _make_goal(base_path, "g1", selector_branch_version_id=None)
    from workflow.api.selector_dispatch import (
        DEFAULT_SELECTOR_BRANCH_DEF_ID,
        resolve_selector_branch_version_id,
    )
    result = resolve_selector_branch_version_id(base_path, goal_id="g1")
    assert result["ok"] is True
    assert result["source"] == "platform_default"
    assert result["branch_version_id"].startswith(
        DEFAULT_SELECTOR_BRANCH_DEF_ID + "@",
    )


def test_resolve_returns_goal_not_found_for_missing_goal(base_path):
    from workflow.api.selector_dispatch import resolve_selector_branch_version_id
    result = resolve_selector_branch_version_id(base_path, goal_id="never")
    assert result["ok"] is False
    assert result["error_kind"] == "goal_not_found"


# ---------------------------------------------------------------------------
# dispatch_selector — empty candidate set
# ---------------------------------------------------------------------------


def test_dispatch_short_circuits_on_empty_candidates(base_path):
    _make_goal(base_path, "g1")
    from workflow.api.selector_dispatch import dispatch_selector
    result = dispatch_selector(
        base_path, goal_id="g1", candidate_branches=[],
    )
    assert result["ok"] is True
    assert result["ranked_entries"] == []
    assert result["source"] == "empty_candidate_set"
    # No selector publish should have happened — we short-circuited
    # before resolving.
    from workflow.api.selector_dispatch import (
        DEFAULT_SELECTOR_BRANCH_DEF_ID,
    )
    from workflow.daemon_server import get_branch_definition
    with pytest.raises(KeyError):
        get_branch_definition(
            base_path, branch_def_id=DEFAULT_SELECTOR_BRANCH_DEF_ID,
        )


# ---------------------------------------------------------------------------
# _parse_ranked_entries — output shape validation
# ---------------------------------------------------------------------------


def _parse(output):
    from workflow.api.selector_dispatch import _parse_ranked_entries
    return _parse_ranked_entries(output)


def test_parse_accepts_list_directly():
    result = _parse({
        "ranked_entries": [
            {"branch_def_id": "b1", "score": 9.0, "rationale": "top"},
            {"branch_def_id": "b2", "score": 5.0, "rationale": "mid"},
        ],
    })
    assert result["ok"] is True
    assert [e["branch_def_id"] for e in result["ranked_entries"]] == ["b1", "b2"]
    assert result["ranked_entries"][0]["score"] == 9.0
    assert result["ranked_entries"][0]["rationale"] == "top"


def test_parse_accepts_json_string():
    result = _parse({
        "ranked_entries": '[{"branch_def_id":"b1","score":7.5}]',
    })
    assert result["ok"] is True
    assert result["ranked_entries"][0]["branch_def_id"] == "b1"
    assert result["ranked_entries"][0]["score"] == 7.5


def test_parse_strips_markdown_fence_from_json_string():
    """A common LLM failure mode is wrapping JSON in ```json … ```.
    The parser must tolerate the fence so an otherwise-correct
    selector doesn't fail the contract on a cosmetic wrapper."""
    result = _parse({
        "ranked_entries": (
            "```json\n"
            '[{"branch_def_id":"b1","score":6.0}]\n'
            "```"
        ),
    })
    assert result["ok"] is True
    assert result["ranked_entries"][0]["branch_def_id"] == "b1"


def test_parse_unwraps_full_object_stuffed_into_field():
    """Some prompts emit the full ``{"ranked_entries": [...]}`` object
    in the field itself. Substrate unwraps."""
    result = _parse({
        "ranked_entries": (
            '{"ranked_entries":[{"branch_def_id":"b1","score":4.0}]}'
        ),
    })
    assert result["ok"] is True
    assert result["ranked_entries"][0]["branch_def_id"] == "b1"


def test_parse_rejects_missing_key():
    result = _parse({"something_else": []})
    assert result["ok"] is False
    assert result["error_kind"] == "selector_invalid_output"
    assert "ranked_entries" in result["error"]


def test_parse_rejects_non_list():
    result = _parse({"ranked_entries": {"not": "a list"}})
    assert result["ok"] is False
    assert result["error_kind"] == "selector_invalid_output"


def test_parse_rejects_non_decodable_string():
    result = _parse({"ranked_entries": "not valid json{{"})
    assert result["ok"] is False
    assert result["error_kind"] == "selector_invalid_output"


def test_parse_rejects_entry_without_branch_def_id():
    result = _parse({
        "ranked_entries": [
            {"score": 7.0, "rationale": "no id"},
        ],
    })
    assert result["ok"] is False
    assert result["error_kind"] == "selector_invalid_output"
    assert "branch_def_id" in result["error"]


def test_parse_rejects_entry_without_score():
    result = _parse({
        "ranked_entries": [
            {"branch_def_id": "b1", "rationale": "no score"},
        ],
    })
    assert result["ok"] is False
    assert result["error_kind"] == "selector_invalid_output"
    assert "score" in result["error"]


def test_parse_rejects_non_coercible_score():
    result = _parse({
        "ranked_entries": [
            {"branch_def_id": "b1", "score": "not a number"},
        ],
    })
    assert result["ok"] is False
    assert result["error_kind"] == "selector_invalid_output"
    assert "score" in result["error"]


def test_parse_rejects_empty_branch_def_id():
    result = _parse({
        "ranked_entries": [
            {"branch_def_id": "  ", "score": 7.0},
        ],
    })
    assert result["ok"] is False
    assert result["error_kind"] == "selector_invalid_output"


def test_parse_accepts_optional_fields_missing():
    """rationale + branch_version_id are optional; their absence is
    not a contract violation."""
    result = _parse({
        "ranked_entries": [
            {"branch_def_id": "b1", "score": 5},
        ],
    })
    assert result["ok"] is True
    assert result["ranked_entries"][0]["rationale"] == ""
    assert result["ranked_entries"][0]["branch_version_id"] == ""


def test_parse_normalizes_score_to_float():
    """LLMs emit ints sometimes. Substrate coerces to float so
    downstream typing is stable."""
    result = _parse({
        "ranked_entries": [
            {"branch_def_id": "b1", "score": 5},
        ],
    })
    assert isinstance(result["ranked_entries"][0]["score"], float)


# ---------------------------------------------------------------------------
# Configurable selector timeout
# ---------------------------------------------------------------------------


def test_resolve_timeout_reads_env(monkeypatch):
    from workflow.api.selector_dispatch import (
        SELECTOR_TIMEOUT_ENV,
        SELECTOR_TIMEOUT_S_DEFAULT,
        _resolve_timeout,
    )
    monkeypatch.delenv(SELECTOR_TIMEOUT_ENV, raising=False)
    assert _resolve_timeout(None) == SELECTOR_TIMEOUT_S_DEFAULT
    monkeypatch.setenv(SELECTOR_TIMEOUT_ENV, "30")
    assert _resolve_timeout(None) == 30.0
    # Explicit arg wins over env.
    assert _resolve_timeout(45.0) == 45.0


def test_resolve_timeout_clamps_to_min_one_second(monkeypatch):
    from workflow.api.selector_dispatch import _resolve_timeout
    assert _resolve_timeout(0.0) == 1.0
    assert _resolve_timeout(-5) == 1.0


# ---------------------------------------------------------------------------
# End-to-end integration — round 2 P1.1 regression guard
#
# Build + publish a real selector branch, bind it on a real Goal, call
# recommend_parent_for_fork without mocking dispatch_selector. Asserts:
# selector ran via _execute_branch_core, leaderboard non-empty,
# selector source = "goal_binding", rationale is selector-emitted.
# ---------------------------------------------------------------------------


def _selector_stub_provider(*, candidate_ids: list[str]):
    """Build a stub provider_call that emits a valid selector JSON
    payload covering the given candidate ids.

    Used by the e2e regression tests: no real LLM, but the substrate
    runs the published selector branch through ``_execute_branch_core``
    and the parser unwraps the JSON string the stub emits — proving
    snapshot reconstruction + graph compile + node dispatch + output
    parsing all wire correctly.
    """
    import json as _json

    def _call(prompt, system="", *, role=""):
        ranked = [
            {
                "branch_def_id": cid,
                "branch_version_id": "",
                "score": 5.0 - i,
                "rationale": f"stub ranked {cid} at position {i + 1}",
            }
            for i, cid in enumerate(candidate_ids)
        ]
        return _json.dumps({"ranked_entries": ranked})

    return _call


def test_end_to_end_selector_dispatch_with_real_published_branch(base_path):
    """Round-2 P1.1 regression guard.

    Round-1 monkeypatched ``dispatch_selector`` everywhere, so the
    snapshot reconstruction bug (immutable snapshot strips ``name``
    → ``validate()`` rejects with "Branch name is required") was
    never caught. This test exercises the full path: real selector
    branch + real Goal + a deterministic provider stub →
    ``recommend_parent_for_fork`` returns a non-empty leaderboard
    backed by a real ``_execute_branch_core`` selector run.

    ``dispatch_selector`` is NOT mocked. Only ``provider_call`` is
    threaded as a stub (the substrate's own injection point — same
    as ``_action_run_branch_version`` accepts). This is the seam
    real production code uses to bind providers.
    """
    from workflow.api.quality_leaderboard import recommend_parent_for_fork
    from workflow.api.selector_dispatch import (
        ensure_default_selector_published,
    )
    from workflow.daemon_server import (
        save_branch_definition,
        save_goal,
        update_goal,
    )

    save_goal(
        base_path,
        goal=dict(
            goal_id="g-e2e",
            name="E2E Goal",
            description="",
            author="host",
            tags=[],
            visibility="public",
        ),
    )
    save_branch_definition(
        base_path,
        branch_def=dict(
            branch_def_id="b-e2e",
            name="b-e2e",
            description="end-to-end candidate",
            author="alice",
            tags=[],
            graph_nodes=[],
            edges=[],
            state_schema=[],
            entry_point="",
            published=True,
            goal_id="g-e2e",
        ),
    )

    # Bind the platform default selector explicitly so we exercise
    # the goal_binding resolution path (not just the lazy
    # platform_default fallback).
    default_bvid = ensure_default_selector_published(base_path)
    update_goal(
        base_path,
        goal_id="g-e2e",
        updates={"selector_branch_version_id": default_bvid},
    )

    # Provider stub returns valid selector JSON for the candidate
    # set. The substrate threads it all the way through compile +
    # node dispatch + output parsing.
    stub = _selector_stub_provider(candidate_ids=["b-e2e"])
    result = recommend_parent_for_fork(
        base_path, goal_id="g-e2e", viewer="", provider_call=stub,
    )

    assert result.get("ok") is True, result
    assert result.get("error_kind") is None
    assert result["leaderboard_size"] == 1
    parent = result["recommended_parent"]
    assert parent is not None
    assert parent["branch_def_id"] == "b-e2e"
    assert result["selector"]["source"] == "goal_binding"
    assert result["selector"]["branch_version_id"] == default_bvid
    # Real run_id (non-empty string) — proves _execute_branch_core
    # actually ran the selector graph.
    assert result["selector"]["run_id"]
    # Selector emitted the stub rationale verbatim.
    assert "stub ranked b-e2e" in result["rationale"]


def test_end_to_end_platform_default_fallback(base_path):
    """Same end-to-end shape but with NO explicit selector binding.

    The leaderboard caller resolves to the platform default selector
    on the fly and the substrate publishes it lazily. Asserts the
    no-binding fallback path also runs end-to-end without snapshot
    reconstruction errors.
    """
    from workflow.api.quality_leaderboard import recommend_parent_for_fork
    from workflow.daemon_server import save_branch_definition, save_goal

    save_goal(
        base_path,
        goal=dict(
            goal_id="g-fallback",
            name="Fallback Goal",
            description="",
            author="host",
            tags=[],
            visibility="public",
        ),
    )
    save_branch_definition(
        base_path,
        branch_def=dict(
            branch_def_id="b-fallback",
            name="b-fallback",
            description="",
            author="alice",
            tags=[],
            graph_nodes=[],
            edges=[],
            state_schema=[],
            entry_point="",
            published=True,
            goal_id="g-fallback",
        ),
    )

    stub = _selector_stub_provider(candidate_ids=["b-fallback"])
    result = recommend_parent_for_fork(
        base_path, goal_id="g-fallback", viewer="",
        provider_call=stub,
    )

    assert result.get("ok") is True, result
    assert result["recommended_parent"]["branch_def_id"] == "b-fallback"
    # Source is platform_default because no explicit binding existed.
    assert result["selector"]["source"] == "platform_default"
    # Stub rationale flowed through.
    assert "stub ranked b-fallback" in result["rationale"]
