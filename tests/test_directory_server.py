from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity
from tinyassets.daemon_server import grant_universe_access
from tinyassets.directory_server import (
    _redact_directory_status,
    directory_mcp,
    read_graph,
    read_page,
    write_graph,
    write_page,
)

# Coarse effect grants — resolve-always mode matches an action's effect
# (read/write/costly/admin) across every tool (universe, wiki, extensions, …).
_FOUNDER_SCOPES = ["read", "write", "costly", "admin"]


class _StaticAuthProvider(AuthProvider):
    """Resolve-always provider (like WorkOS) resolving bearer ``"ok"``."""

    def __init__(self, identity: Identity | None) -> None:
        self.identity = identity

    def resolve_token(self, token: str) -> Identity | None:
        return self.identity if token == "ok" else None

    def is_auth_required(self) -> bool:
        return False

    def resolve_always_writes(self) -> bool:
        return True

    def register_client(self, metadata: dict) -> dict:
        return {"client_id": "t", **metadata}

    def create_authorization(self, *a, **k) -> str:  # noqa: ANN002, ANN003
        return "c"

    def exchange_code(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
        return None


@pytest.fixture(autouse=True)
def _reset_auth_provider():
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


def _auth_grant(base, universe_ids, sub: str = "directory-test") -> None:
    """Authenticate a founder + grant admin (env-var write authority was removed)."""
    set_provider(_StaticAuthProvider(
        Identity(user_id=sub, username=sub, capabilities=list(_FOUNDER_SCOPES)),
    ))
    auth_middleware("ok")
    for uid in universe_ids:
        grant_universe_access(
            base, universe_id=uid, actor_id=sub, permission="admin", granted_by=sub,
        )

EXPECTED_TOOLS = {
    "read_graph": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "write_graph": {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
    "run_graph": {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
    "read_page": {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
    "write_page": {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
}

LEGACY_DIRECTORY_TOOL_NAMES = {
    "get_workflow_status",
    "list_workflow_universes",
    "inspect_workflow_universe",
    "list_workflow_goals",
    "search_workflow_goals",
    "get_workflow_goal",
    "search_workflow_wiki",
    "read_workflow_wiki_page",
    "list_workflow_runs",
    "propose_workflow_goal",
    "submit_workflow_request",
    "universe",
    "extensions",
    "goals",
    "wiki",
}


def _list_tools():
    return asyncio.run(directory_mcp.list_tools(run_middleware=False))


def test_directory_surface_exposes_review_scoped_tool_set() -> None:
    tools = {tool.name: tool for tool in _list_tools()}

    assert set(tools) == set(EXPECTED_TOOLS)
    assert LEGACY_DIRECTORY_TOOL_NAMES.isdisjoint(tools)


def test_directory_tools_have_explicit_submission_annotations() -> None:
    tools = {tool.name: tool for tool in _list_tools()}

    for tool_name, expected in EXPECTED_TOOLS.items():
        tool = tools[tool_name]
        assert tool.title, f"{tool_name} missing tool title"
        annotations = tool.annotations
        assert annotations is not None, f"{tool_name} missing annotations"
        assert annotations.title, f"{tool_name} missing annotation title"
        for hint_name, expected_value in expected.items():
            assert getattr(annotations, hint_name) is expected_value, (
                f"{tool_name}.{hint_name} must be {expected_value}"
            )


def test_chatgpt_submission_packet_matches_directory_surface() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    packet = json.loads(
        (repo_root / "chatgpt-app-submission.json").read_text(encoding="utf-8")
    )
    tools = {tool.name: tool for tool in _list_tools()}

    assert set(packet["tools"]) == set(tools)
    for tool_name, tool in tools.items():
        annotations = tool.annotations
        assert annotations is not None
        assert packet["tools"][tool_name]["annotations"] == {
            "readOnlyHint": annotations.readOnlyHint,
            "openWorldHint": annotations.openWorldHint,
            "destructiveHint": annotations.destructiveHint,
        }


def test_directory_tools_do_not_use_catch_all_action_inputs() -> None:
    for tool in _list_tools():
        properties = tool.parameters.get("properties", {})
        assert "action" not in properties, (
            f"{tool.name} must expose a narrow tool, not an action router"
        )


def test_directory_tool_inputs_avoid_sensitive_credentials() -> None:
    sensitive_terms = {
        "password",
        "secret",
        "token",
        "api_key",
        "mfa",
        "ssn",
        "credit_card",
    }

    for tool in _list_tools():
        properties = tool.parameters.get("properties", {})
        names = {name.lower() for name in properties}
        assert names.isdisjoint(sensitive_terms), (
            f"{tool.name} requests a sensitive credential-like field"
        )


def test_directory_read_page_schema_advertises_changed_since() -> None:
    """PR-088: directory wiki reads must expose the since-feed timestamp."""

    tool = next(tool for tool in _list_tools() if tool.name == "read_page")
    properties = tool.parameters["properties"]

    assert properties["changed_since"]["type"] == "string"
    assert properties["changed_since"]["default"] == ""
    assert "changed after this" in properties["changed_since"]["description"]
    assert "changed_since" not in tool.parameters.get("required", [])


def test_directory_status_redacts_operator_diagnostics() -> None:
    redacted = _redact_directory_status({
        "active_host": {
            "host_id": "alice@example.com",
            "served_llm_type": "any",
        },
        "evidence": {
            "activity_log_tail": ["[2026-05-02] raw internal log"],
            "last_n_calls": [{"ts": "2026-05-02", "raw": "internal"}],
            "policy_hash": "abc123",
            "activity_log_line_count": 1,
        },
        "evidence_caveats": {
            "last_completed_request_llm_used": ["No recent provider tag."],
            "last_n_calls": ["Internal recent-call diagnostic caveat."],
        },
        "session_boundary": {"account_user": "alice@example.com"},
        "storage_utilization": {
            "pressure_level": "ok",
            "per_subsystem": {
                "wiki": {
                    "bytes": 10,
                    "path": "C:/Users/Jonathan/AppData/Roaming/TinyAssets/wiki",
                },
            },
        },
        "actionable_next_steps": [
            "Inspect the full activity_log_tail.",
            "Inspect last_n_calls for legacy entries.",
            "Check daemon status again.",
        ],
    })

    assert "host_id" not in redacted["active_host"]
    assert "session_boundary" not in redacted
    assert "activity_log_tail" not in redacted["evidence"]
    assert "last_n_calls" not in redacted["evidence"]
    assert "policy_hash" not in redacted["evidence"]
    assert "activity_log_tail_count" not in redacted["evidence"]
    assert "last_n_calls_count" not in redacted["evidence"]
    assert "last_n_calls" not in redacted["evidence_caveats"]
    assert "last_completed_request_llm_used" in redacted["evidence_caveats"]
    assert "path" not in redacted["storage_utilization"]["per_subsystem"]["wiki"]
    assert redacted["actionable_next_steps"] == ["Check daemon status again."]
    assert "directory_privacy_note" in redacted


def test_directory_goal_write_and_search_round_trip(monkeypatch, tmp_path) -> None:
    """Guard the reviewed directory goal path beyond tool-schema listing."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "directory-test")

    from tinyassets.catalog import invalidate_backend_cache

    invalidate_backend_cache()
    try:
        proposed = json.loads(
            write_graph(
                target="goal",
                name="Directory smoke goal",
                tags="directory,smoke",
                visibility="public",
            )
        )
        assert proposed["status"] == "proposed"

        searched = json.loads(read_graph(target="goals", query="Directory smoke"))
        assert searched["count"] >= 1
        assert any(
            goal["goal_id"] == proposed["goal"]["goal_id"]
            for goal in searched["goals"]
        )
    finally:
        invalidate_backend_cache()


def test_directory_submit_request_queues_temp_universe_request(monkeypatch, tmp_path) -> None:
    """Guard the reviewed directory request write path without touching prod."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    from tinyassets.catalog import invalidate_backend_cache

    invalidate_backend_cache()
    universe_dir = tmp_path / "directory-universe"
    universe_dir.mkdir()
    # Queuing work needs a soul with a declared Loop branch (souled universes
    # no longer silently attach the fantasy loop).
    from tinyassets.universe_bundle import seed_okf_bundle

    seed_okf_bundle(
        universe_dir, purpose="directory test", loop_branch_def_id="loop-dir-test",
    )
    _auth_grant(tmp_path, ["directory-universe"])

    try:
        result = json.loads(
            write_graph(
                target="request",
                graph_id="directory-universe",
                text="Summarize submission readiness blockers.",
                request_type="general",
            )
        )

        assert result["universe_id"] == "directory-universe"
        assert result["status"] == "pending"
        assert result["request_id"].startswith("req_")
        assert result["queue_position"] == 1
        assert result["ahead_of_yours"] == 0
        assert "what_happens_next" in result

        requests = json.loads((universe_dir / "requests.json").read_text(encoding="utf-8"))
        assert requests[0]["id"] == result["request_id"]
        assert requests[0]["text"] == "Summarize submission readiness blockers."
        assert requests[0]["type"] == "general"
    finally:
        invalidate_backend_cache()


def test_directory_write_page_drafts_temp_wiki_page(monkeypatch, tmp_path) -> None:
    """Guard the five-handle page write adapter against parameter drift."""
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))

    drafted = json.loads(
        write_page(
            category="notes",
            filename="directory-page-smoke",
            content="# Directory page smoke\n",
            log_entry="directory page smoke",
        )
    )

    assert drafted["status"] == "drafted"
    assert drafted["path"] == "drafts/notes/directory-page-smoke.md"
    assert (
        wiki_root / "drafts" / "notes" / "directory-page-smoke.md"
    ).read_text(encoding="utf-8") == "# Directory page smoke\n"


def test_directory_write_page_honors_target_universe(monkeypatch, tmp_path) -> None:
    """A writer scoped to a universe writes to that universe's page substrate."""
    shared_wiki = tmp_path / "shared-wiki"
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(shared_wiki))
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    _auth_grant(tmp_path, ["splitroot"])

    drafted = json.loads(
        write_page(
            universe_id="splitroot",
            category="plans",
            filename="archon-telemetry-contract",
            content="# Archon telemetry contract\n",
            log_entry="splitroot writer target",
        )
    )

    assert drafted["status"] == "drafted"
    assert drafted["universe_id"] == "splitroot"
    assert drafted["path"] == "drafts/plans/archon-telemetry-contract.md"
    target = (
        tmp_path
        / "splitroot"
        / "wiki"
        / "drafts"
        / "plans"
        / "archon-telemetry-contract.md"
    )
    assert target.read_text(encoding="utf-8") == "# Archon telemetry contract\n"
    assert not (
        shared_wiki / "drafts" / "plans" / "archon-telemetry-contract.md"
    ).exists()


def test_directory_write_page_rejects_dot_universe(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))

    result = json.loads(
        write_page(
            universe_id=".",
            category="plans",
            filename="bad-target",
            content="# Bad target\n",
        )
    )

    assert "Invalid universe_id" in result["error"]
    assert not (tmp_path / "wiki" / "drafts" / "plans" / "bad-target.md").exists()


def test_directory_read_page_changed_since_routes_to_since_feed(
    monkeypatch, tmp_path,
) -> None:
    """Empty read_page + changed_since is the directory-safe since action."""
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))

    from tinyassets.api.wiki import _ensure_wiki_scaffold

    _ensure_wiki_scaffold(wiki_root)
    fresh = wiki_root / "pages" / "notes" / "fresh-directory-feed.md"
    fresh.write_text(
        "---\ntitle: Fresh directory feed\ntype: note\n---\n# Fresh\n",
        encoding="utf-8",
    )

    result = json.loads(
        read_page(changed_since="2026-05-01T00:00:00Z", max_results=5)
    )

    assert result["changed_since"] == "2026-05-01T00:00:00Z"
    assert any(
        item["path"] == "pages/notes/fresh-directory-feed.md"
        for item in result["results"]
    )
