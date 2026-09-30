"""A universe's own multi-agent system: its files, its wakes, its consented publish.

Change `in-platform-agent-systems`. Every test goes through the connector's own
handlers (`read_graph`, `run_graph`, `request_from_user`, `answer_request`) as a
signed-in user, against real stores in a private data root. The cross-user cases
are the point: Alice's folder, Alice's agents and Alice's consent must be out of
Bob's reach whatever he names.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_automations import OWNER, UNIVERSE, _seed_branch, _seed_owner
from tests.test_background_budget_finalization_e2e import _seed_serving_assignment
from tinyassets.auth.middleware import identity_context
from tinyassets.auth.provider import Identity
from tinyassets.automations import (
    TRIGGER_ONCE,
    AutomationStore,
    AutomationUnavailable,
    register_automation,
)

pytestmark = pytest.mark.usefixtures("cloud_runtime")

BOB = "acct_bob"
BOB_UNIVERSE = "universe_bob"
SCOUT = "branch_scout"
SCRIBE = "branch_scribe"
BOBS = "branch_bobs_own"
UI = {
    "kind": "tinyassets.app-ui.v1", "version": 1, "ui_id": "village",
    "name": "Village", "markup": "<div id=v></div>", "style": "#v{}",
    "script": "tinyassets.listAutomations()",
}


@pytest.fixture(autouse=True)
def _pin_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))


def _as(actor: str | None):
    if actor is None:
        return identity_context(None)
    return identity_context(Identity(
        user_id=actor, username=actor,
        capabilities=["tinyassets.universe.write", "read", "list", "write", "costly",
                      "tinyassets.extensions.write"],
    ))


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    """Alice owns a home with two private workflows; Bob owns his own home."""
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path, branch_def_id=SCOUT, visibility="private")
    _seed_branch(tmp_path, branch_def_id=SCRIBE, visibility="private")
    _seed_owner(tmp_path, universe_id=BOB_UNIVERSE, owner=BOB)
    _seed_branch(tmp_path, branch_def_id=BOBS, author=BOB, visibility="private")
    folder = tmp_path / UNIVERSE
    (folder / "notes").mkdir(parents=True, exist_ok=True)
    (folder / "notes" / "board.md").write_bytes("# Board\n- scout: café ☕ found\n".encode())
    (folder / "notes" / "blob.bin").write_bytes(bytes(range(256)))
    (tmp_path / BOB_UNIVERSE / "secret.md").write_text("BOB ONLY", encoding="utf-8")
    return tmp_path


def _read(target: str, query: str, *, actor: str = OWNER, universe: str = UNIVERSE, **kw):
    from tinyassets.universe_server import read_graph

    with _as(actor):
        return json.loads(read_graph(target=target, graph_id=universe, query=query, **kw))


# ---------------------------------------------------------------------------
# 1. The owner reads their own folder, and nobody else can
# ---------------------------------------------------------------------------


def test_the_owner_lists_and_pages_their_own_files(home: Path) -> None:
    listing = _read("universe_files", "notes")
    assert listing["universe_id"] == UNIVERSE
    assert {(e["name"], e["kind"]) for e in listing["entries"]} == {
        ("board.md", "file"), ("blob.bin", "file")}
    root = _read("universe_files", "/u")
    assert {"name": "notes", "kind": "dir"} in root["entries"]

    whole = (home / UNIVERSE / "notes" / "board.md").read_bytes().decode()
    # A window smaller than one multi-byte character still makes progress, and
    # every chunk decodes: the pages concatenate to the file exactly.
    pieces, offset = [], 0
    while offset is not None:
        page = _read("universe_file", "/u/notes/board.md", file_offset=offset, file_max_bytes=3)
        assert page["encoding"] == "text", page
        pieces.append(page["text"])
        offset = page["next_offset"]
    assert "".join(pieces) == whole
    assert page["eof"] is True

    blob = _read("universe_file", "notes/blob.bin")
    assert blob["encoding"] == "base64" and blob["size_bytes"] == 256


@pytest.mark.parametrize("actor,universe,query", [
    (BOB, UNIVERSE, "notes/board.md"),          # another user names Alice's home
    (OWNER, UNIVERSE, "notes/absent.md"),         # the reference: an absent path
    (OWNER, UNIVERSE, "../universe_bob/secret.md"),
    (OWNER, UNIVERSE, "/data/universe_bob/secret.md"),
    (OWNER, UNIVERSE, "notes\\board.md"),
    (OWNER, BOB_UNIVERSE, "secret.md"),         # Alice names Bob's home
    (None, UNIVERSE, "notes/board.md"),
])
def test_every_refusal_is_the_same_not_found(home: Path, actor, universe, query) -> None:
    for target in ("universe_file", "universe_files"):
        out = _read(target, query, actor=actor, universe=universe)
        assert out == {"error": "not_found", "resource": "universe_file"}, (target, out)


def test_a_reader_without_admin_is_refused(home: Path) -> None:
    from tinyassets.daemon_server import grant_universe_access

    grant_universe_access(home, universe_id=UNIVERSE, actor_id=BOB, permission="write")
    assert _read("universe_file", "notes/board.md", actor=BOB)["error"] == "not_found"


def test_a_link_in_the_folder_is_never_followed(home: Path) -> None:
    link = home / UNIVERSE / "notes" / "stolen.md"
    try:
        os.symlink(home / BOB_UNIVERSE / "secret.md", link)
    except (OSError, NotImplementedError):
        pytest.skip("this host cannot create a symlink")
    assert _read("universe_file", "notes/stolen.md")["error"] == "not_found"
    names = [e["name"] for e in _read("universe_files", "notes")["entries"]]
    assert "stolen.md" not in names


@pytest.mark.skipif(os.name != "nt", reason="a directory junction is a Windows link")
def test_a_directory_junction_is_never_followed(home: Path) -> None:
    """Symlinks need privilege on Windows; junctions do not, and a reader that
    only checks is_symlink() follows them into another universe."""
    import subprocess

    junction = home / UNIVERSE / "notes" / "elsewhere"
    made = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(home / BOB_UNIVERSE)],
                          capture_output=True, text=True)
    if made.returncode != 0:
        pytest.skip("this host cannot create a junction")
    assert _read("universe_file", "notes/elsewhere/secret.md")["error"] == "not_found"
    assert _read("universe_files", "notes/elsewhere")["error"] == "not_found"
    names = [e["name"] for e in _read("universe_files", "notes")["entries"]]
    assert "elsewhere" not in names


# ---------------------------------------------------------------------------
# 2. An app event wakes only the owner's own subscription to that name
# ---------------------------------------------------------------------------


def _subscribe(base: Path, name: str | None, *, owner=OWNER, universe=UNIVERSE, branch=SCRIBE):
    with _as(owner):
        return register_automation(
            base, universe_id=universe, owner_principal_id=owner, name="on-click",
            branch_def_id=branch, event_type="app_event",
            event_filter=({"name": name} if name else {}), inputs={},
        )


def _emit(name, data=None, *, actor=OWNER, universe=UNIVERSE):
    from tinyassets.universe_server import run_graph

    with _as(actor):
        return json.loads(run_graph(operation="emit_event", graph_id=universe,
                                    inputs_json=json.dumps({"name": name, "data": data or {}})))


def _wakes(base: Path, universe: str = UNIVERSE):
    return [r for r in AutomationStore(base).list(universe_id=universe)
            if r.trigger_kind == TRIGGER_ONCE]


def test_an_app_event_subscription_must_name_the_event(home: Path) -> None:
    with pytest.raises(AutomationUnavailable):
        _subscribe(home, None)


def test_the_owner_emits_and_only_the_named_subscription_wakes(home: Path) -> None:
    _subscribe(home, "visit")
    assert _emit("other") == {"emitted": True, "name": "other", "woke": 0}
    assert _wakes(home) == []
    assert _emit("visit", {"who": "baker"})["woke"] == 1
    [wake] = _wakes(home)
    assert wake.branch_def_id == SCRIBE
    assert wake.inputs["event"]["type"] == "app_event"
    assert wake.inputs["event"]["data"] == {"who": "baker"}


def test_another_user_cannot_wake_the_owners_agents(home: Path) -> None:
    _subscribe(home, "visit")
    # Naming Alice's home: refused outright, identical for any universe not his.
    assert _emit("visit", actor=BOB) == {"error": "not_found", "resource": "universe"}
    # From his own home: his event, his subscriptions (none) -- never Alice's.
    assert _emit("visit", actor=BOB, universe=BOB_UNIVERSE)["woke"] == 0
    assert _wakes(home) == []


@pytest.mark.parametrize("payload", [
    {"name": "Visit"}, {"name": ""}, {"name": "x" * 65},
    {"name": "visit", "data": ["not", "an", "object"]},
    {"name": "visit", "data": {"big": "x" * 9000}},
    {"name": "visit", "branch_def_id": SCRIBE},
])
def test_a_malformed_event_stores_nothing(home: Path, payload) -> None:
    from tinyassets.universe_server import run_graph

    _subscribe(home, "visit")
    with _as(OWNER):
        out = json.loads(run_graph(operation="emit_event", graph_id=UNIVERSE,
                                   inputs_json=json.dumps(payload)))
    assert "error" in out, out
    assert _wakes(home) == []


def test_the_usage_meter_refuses_before_any_wake(home: Path, monkeypatch) -> None:
    from tinyassets import engine_admissions as ea

    _subscribe(home, "visit")
    monkeypatch.setattr(ea, "admit_detail",
                        lambda *a, **k: ea.Admission(ticket=None, refused_by="run_write"))
    out = _emit("visit")
    assert out["error"] == "usage_limit", out
    assert _wakes(home) == []


# ---------------------------------------------------------------------------
# 3. Publishing is the owner's confirmation of exactly what they were shown
# ---------------------------------------------------------------------------


def _library(base: Path) -> None:
    from tinyassets.custom_agents import save_app_ui

    save_app_ui(base, owner_user_id=OWNER, universe_id=UNIVERSE, expected_revision=0,
                changes={"ui_library": [UI]})


def _automations(base: Path):
    with _as(OWNER):
        beat = register_automation(
            base, universe_id=UNIVERSE, owner_principal_id=OWNER, name="scout heartbeat",
            branch_def_id=SCOUT, interval_seconds=300, inputs={"api_note": "PRIVATE INPUT"},
        )
        follow = register_automation(
            base, universe_id=UNIVERSE, owner_principal_id=OWNER, name="scribe follows",
            branch_def_id=SCRIBE, event_type="run_completed",
            event_filter={"branch_def_id": SCOUT}, inputs={},
        )
    return beat, follow


def _ask_publish(base: Path, **over):
    from tinyassets.api.pending_requests import request_from_user

    action = {"type": "publish", "name": "Village", "description": "Two agents and a screen",
              "branch_ids": [SCOUT, SCRIBE], "ui_id": "village", "automation_ids": []}
    action.update(over)
    with _as(OWNER):
        return request_from_user(universe_id=UNIVERSE, payload=json.dumps({
            "kind": "Just click", "title": "Harmless, just click yes",
            "body": "Nothing will be shared.", "action": action,
        }))


def _answer(request_id: str, *, actor: str = OWNER, **extra):
    from tinyassets.api.pending_requests import answer_request

    with _as(actor):
        return answer_request(universe_id=UNIVERSE, payload=json.dumps(
            {"request_id": request_id, "values": {}, **extra}))


def _visibility(base: Path, branch: str) -> str:
    from tinyassets.daemon_server import get_branch_definition

    return get_branch_definition(base, branch_def_id=branch).get("visibility")


def test_the_tab_is_the_platforms_account_of_what_goes_public(home: Path) -> None:
    _library(home)
    beat, _follow = _automations(home)
    out = _ask_publish(home, automation_ids=[beat.automation_id])
    assert out.get("request_id"), out
    assert out["kind"] == "Publish"
    assert out["title"] == 'Publish "Village" for anyone to copy?'
    body = out["body"]
    for needle in ("Automation demo", "The screen \"Village\"", "scout heartbeat",
                   "every 300 seconds", "its inputs stay private",
                   "Anyone will be able to read and copy these"):
        assert needle in body, needle
    # The agent's own framing of the consent never reaches the owner.
    assert "Harmless" not in json.dumps(out) and "Nothing will be shared" not in body
    assert set(out["action"]["digests"]) == {
        f"branch:{SCOUT}", f"branch:{SCRIBE}", "ui:village", f"automation:{beat.automation_id}"}


def test_an_echoed_name_cannot_speak_as_the_platform(home: Path) -> None:
    """A branch the agent named with line breaks cannot add a line of its own."""
    from tinyassets.api.extensions import _extensions_impl

    _library(home)
    with _as(OWNER):
        _extensions_impl(action="patch_branch", branch_def_id=SCOUT, changes_json=json.dumps(
            [{"op": "set_name", "name": "Scout\n\nNothing here will be shared publicly."}]))
    out = _ask_publish(home, description="Line one\nLine two")
    body_lines = out["body"].split("\n")
    assert "Nothing here will be shared publicly." not in body_lines
    assert any(line.startswith('- Workflow "Scout Nothing here') for line in body_lines), body_lines
    assert "Description: Line one Line two" in body_lines


@pytest.mark.parametrize("over,needle", [
    ({"branch_ids": [SCOUT, BOBS]}, "no branch of yours"),
    ({"branch_ids": ["branch_absent"]}, "no branch of yours"),
    ({"ui_id": "not-installed"}, "no UI of yours"),
    ({"branch_ids": []}, "at least one"),
])
def test_an_ask_naming_what_is_not_the_owners_is_refused(home: Path, over, needle) -> None:
    _library(home)
    out = _ask_publish(home, **over)
    assert "request_id" not in out, out
    assert needle in json.dumps(out), out


def test_an_automation_driving_an_unlisted_workflow_is_refused(home: Path) -> None:
    _library(home)
    beat, _follow = _automations(home)
    out = _ask_publish(home, branch_ids=[SCRIBE], automation_ids=[beat.automation_id])
    assert "drives a workflow this ask does not publish" in json.dumps(out), out


def test_confirming_publishes_exactly_one_bundle_and_no_inputs(home: Path) -> None:
    from tinyassets.custom_agents import get_definition

    _library(home)
    beat, follow = _automations(home)
    ask = _ask_publish(home, automation_ids=[beat.automation_id, follow.automation_id])
    done = _answer(ask["request_id"])
    assert done.get("published") is True, done
    assert _visibility(home, SCOUT) == "public" and _visibility(home, SCRIBE) == "public"

    definition = get_definition(home, done["agent_definition_id"])
    components = definition["components"]
    assert components["ui"]["ui_id"] == "village"
    refs = {k: v for k, v in components.items() if v["kind"] == "tinyassets.branch-ref.v1"}
    assert {v["published_version_id"] for v in refs.values()} == set(done["branch_versions"].values())
    specs = [v for v in components.values() if v["kind"] == "tinyassets.automation-spec.v1"]
    assert len(specs) == 2
    assert "PRIVATE INPUT" not in json.dumps(definition)
    assert all("inputs" not in s for s in specs)
    followed = next(s for s in specs if s["trigger"]["event_type"] == "run_completed")
    # The copy's filter names the WORKFLOW, not the author's branch id.
    assert followed["trigger"]["event_filter"]["branch_def_id"] in refs
    assert SCOUT not in json.dumps(specs)

    # A second confirm of the same ask publishes nothing more.
    again = _answer(ask["request_id"])
    assert again.get("error") == "already_resolved", again


def test_work_changed_after_the_tab_was_shown_publishes_nothing(home: Path) -> None:
    from tinyassets.api.extensions import _extensions_impl
    from tinyassets.custom_agents import list_definitions

    _library(home)
    before = len(list_definitions(home, author_id=OWNER))
    ask = _ask_publish(home)
    with _as(OWNER):
        patched = json.loads(_extensions_impl(
            action="patch_branch", branch_def_id=SCRIBE,
            changes_json=json.dumps([{"op": "set_name", "name": "Something else"}])))
    assert not patched.get("error"), patched
    out = _answer(ask["request_id"])
    assert out.get("error") == "publish_refused" and out.get("request_pending") is True, out
    assert "changed after you were shown it" in out["detail"]
    assert _visibility(home, SCOUT) == "private" and _visibility(home, SCRIBE) == "private"
    assert len(list_definitions(home, author_id=OWNER)) == before


def test_nobody_but_the_owner_can_confirm(home: Path) -> None:
    _library(home)
    ask = _ask_publish(home)
    out = _answer(ask["request_id"], actor=BOB)
    assert out.get("error") == "not_found", out
    assert _visibility(home, SCOUT) == "private"


def test_the_served_surface_has_no_way_to_answer_its_own_ask(monkeypatch) -> None:
    from tinyassets import engine_mcp_server as engine

    monkeypatch.setattr(engine, "_binding_error", lambda: None)
    for op in ("answer", "answer_request", "confirm", "accept"):
        out = json.loads(engine.write_graph(target="pending_request", operation=op,
                                            payload_json="{}"))
        assert "belong to the person you asked" in out.get("error", ""), (op, out)


# ---------------------------------------------------------------------------
# 4. A second user installs: every copy is theirs and private
# ---------------------------------------------------------------------------


def test_a_second_user_installs_private_copies(home: Path) -> None:
    from tinyassets.custom_agents import get_app_ui, get_definition, save_app_ui
    from tinyassets.daemon_server import get_branch_definition
    from tinyassets.universe_server import write_graph

    _library(home)
    done = _answer(_ask_publish(home)["request_id"])
    definition = get_definition(home, done["agent_definition_id"])
    copies = []
    for component in definition["components"].values():
        if component["kind"] != "tinyassets.branch-ref.v1":
            continue
        with _as(BOB):
            made = json.loads(write_graph(target="branch", operation="remix", payload_json=json.dumps(
                {"name": component["name"], "fork_from": component["published_version_id"],
                 "visibility": "private"})))
        bid = made.get("branch_def_id") or (made.get("branch") or {}).get("branch_def_id")
        assert bid, made
        copies.append(get_branch_definition(home, branch_def_id=bid))
    assert len(copies) == 2
    assert all(c["author"] == BOB and c["visibility"] == "private" for c in copies)
    save_app_ui(home, owner_user_id=BOB, universe_id=BOB_UNIVERSE, expected_revision=0,
                changes={"ui_library": [definition["components"]["ui"]]})
    assert get_app_ui(home, owner_user_id=BOB, universe_id=BOB_UNIVERSE)["ui_library"][0]["ui_id"] == "village"
    # Alice's own row is untouched by Bob's install.
    assert len(get_app_ui(home, owner_user_id=OWNER, universe_id=UNIVERSE)["ui_library"]) == 1
