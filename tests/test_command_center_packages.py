"""A whole command center as one package: Alice publishes, Bob installs and runs it.

Change `command-center-packages`. Every round trip goes through the real
handlers (`request_from_user`, `answer_request`, `list_requests`) as signed-in
users against real stores in a private data root. The cross-user cases are the
point: nothing private of Alice's reaches the package or Bob's command center,
and nothing of the package exists in Bob's until Bob confirms.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from pathlib import Path

import pytest

from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_automations import (
    OWNER,
    UNIVERSE,
    _real_providers,
    _seed_branch,
    _seed_owner,
)
from tests.test_background_budget_finalization_e2e import _seed_serving_assignment
from tests.test_in_platform_agent_systems import (
    BOB,
    BOB_UNIVERSE,
    SCOUT,
    SCRIBE,
    UI,
    _as,
)
from tinyassets import command_center_packages as ccp
from tinyassets.automations import STATE_PAUSED, AutomationStore, register_automation

pytestmark = pytest.mark.usefixtures("cloud_runtime")

SECRET_KEY = "sk-live-" + "Zq8rT2vX9mK4pL7nB3wE6yH1jD5"
ALICE_EMAIL = "alice.private@example.com"


@pytest.fixture(autouse=True)
def _pin_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))


def _write(folder: Path, rel: str, data: str | bytes) -> None:
    path = folder / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)


#: Alice's whole command center: what travels, and what must never.
TRAVELS = {
    "AGENTS.md": "# Village lead\n## Responsibility\nRun the GTM village.\n",
    "identity.md": "---\ntype: identity\n---\nI am the village lead.\n",
    "settings.yaml": "model: openrouter/free\n",
    "skills/scout/SKILL.md": "# Scout\nFind leads and write them to notes/board.md.\n",
    "agents/scribe/AGENTS.md": "# Scribe\nSummarise the board every hour.\n",
    "notes/board.md": "# Board\n- scout: three bakeries found\n",
    "wiki/pages/village.md": "# Village\nHow the village works.\n",
}
PRIVATE = {
    "founder.md": "Alice lives on Elm Street and hates mornings.\n",
    "soul.md": "---\nloop_branch_def_id: x\n---\nsoul\n",
    "log.md": "private brain history\n",
    "activity.log": "runtime\n",
    ".credentials.json": '{"token": "' + SECRET_KEY + '"}',
    ".runtime/agent-sessions/native/s.jsonl": "session transcript\n",
    "notes/keys.md": "my key: " + SECRET_KEY + "\n",
    "notes/leads.md": "write to " + ALICE_EMAIL + " tomorrow\n",
    "notes/photo.png": bytes(range(256)),
    "wiki/drafts/plan.md": "unfinished private plan\n",
    "agents/scribe/MEMORY.md": "- [m_s1] Alice's scribe memory\n",
    "workspaces/repo/README.md": "a managed checkout\n",
    "ledger.db": b"SQLite format 3\x00rest",
    f"notes/{ALICE_EMAIL}.md": "harmless body\n",
}
MEMORY = "# Memory\n- [m_pub] Prefers short summaries\n- [m_priv] Alice's bank is Acme\n"


def _seed_bob_serving(base: Path) -> None:
    """Bob's OWN connected model: his installed copies run on it, never Alice's."""
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.custom_agents import create_binding, publish_definition
    from tinyassets.provider_serving_binding import bind_serving_provider, set_serving

    folder = base / BOB_UNIVERSE
    folder.mkdir(exist_ok=True)
    write_credential_vault(
        folder, [{"credential_type": "llm_subscription", "service": "codex",
                  "auth_json_b64": "e30="}],
        owner_user_id=BOB, universe_id=BOB_UNIVERSE)
    definition = publish_definition(base, author_id=BOB, payload={
        "schema_version": 1, "name": "Bob's agent", "description": "",
        "tags": ["test"], "components": {"identity": {"kind": "soul", "config": {}}}})
    agent = create_binding(
        base, universe_id=BOB_UNIVERSE, definition_id=definition["agent_definition_id"],
        created_by=BOB, payload={"schema_version": 1, "name": "Bob's agent", "role": "writer"})
    connected = bind_serving_provider(
        base_path=base, universe_dir=folder, owner_user_id=BOB, universe_id=BOB_UNIVERSE,
        agent_binding_id=agent["agent_binding_id"], expected_revision=1, provider="codex")
    set_serving(
        base_path=base, universe_dir=folder, owner_user_id=BOB, universe_id=BOB_UNIVERSE,
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=connected["agent_binding"]["revision"], enabled=True)


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    """Alice's built village, and Bob's own small command center."""
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path, branch_def_id=SCOUT, visibility="private")
    _seed_branch(tmp_path, branch_def_id=SCRIBE, visibility="private")
    _seed_owner(tmp_path, universe_id=BOB_UNIVERSE, owner=BOB)
    _seed_bob_serving(tmp_path)
    alice = tmp_path / UNIVERSE
    for rel, data in {**TRAVELS, **PRIVATE, "MEMORY.md": MEMORY}.items():
        _write(alice, rel, data)
    bob = tmp_path / BOB_UNIVERSE
    _write(bob, "AGENTS.md", "# Bob's own agent\n")
    from tinyassets.custom_agents import save_app_ui

    save_app_ui(tmp_path, owner_user_id=OWNER, universe_id=UNIVERSE, expected_revision=0,
                changes={"ui_library": [UI]})
    return tmp_path


def _automations(base: Path):
    with _as(OWNER):
        beat = register_automation(
            base, universe_id=UNIVERSE, owner_principal_id=OWNER, name="scout heartbeat",
            branch_def_id=SCOUT, interval_seconds=300, inputs={"api_note": "PRIVATE INPUT"})
        follow = register_automation(
            base, universe_id=UNIVERSE, owner_principal_id=OWNER, name="scribe follows",
            branch_def_id=SCRIBE, event_type="run_completed",
            event_filter={"branch_def_id": SCOUT}, inputs={})
    return beat, follow


def _ask(actor: str, universe: str, action: dict) -> dict:
    from tinyassets.api.pending_requests import request_from_user

    with _as(actor):
        return request_from_user(universe_id=universe, payload=json.dumps({
            "kind": "Just click", "title": "Harmless, just click yes",
            "body": "Nothing will be shared.", "action": action}))


def _answer(actor: str, universe: str, request_id: str, values: dict | None = None) -> dict:
    from tinyassets.api.pending_requests import answer_request

    with _as(actor):
        return answer_request(universe_id=universe, payload=json.dumps(
            {"request_id": request_id, "values": values or {}}))


def _publish_action(**package) -> dict:
    return {"type": "publish", "name": "GTM Village", "description": "A village of agents",
            "branch_ids": [SCOUT, SCRIBE], "ui_id": "village", "automation_ids": [],
            "package": package}


def _published(home: Path, **package) -> dict:
    beat, follow = _automations(home)
    action = _publish_action(**package)
    action["automation_ids"] = [beat.automation_id, follow.automation_id]
    ask = _ask(OWNER, UNIVERSE, action)
    assert "request_id" in ask, ask
    done = _answer(OWNER, UNIVERSE, ask["request_id"])
    assert done.get("published") is True, done
    return {"ask": ask, "done": done}


def _blob_files(home: Path, definition_id: str) -> dict[str, bytes]:
    from tinyassets.custom_agents import get_definition

    component = get_definition(home, definition_id)["components"]["package"]
    _, files = ccp.check_blob(ccp.read_blob(home, component["blob_sha256"]))
    return files


def _bob_files(home: Path) -> dict[str, bytes]:
    root = home / BOB_UNIVERSE
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file() and not any(
                part.startswith(".") for part in p.relative_to(root).parts)}


# ---------------------------------------------------------------------------
# 1. The scrub: what a published package carries
# ---------------------------------------------------------------------------


def test_publish_carries_the_command_center_and_none_of_its_private_items(home: Path):
    out = _published(home, memory_items=["m_pub"])
    files = _blob_files(home, out["done"]["agent_definition_id"])
    assert set(files) == set(TRAVELS) | {"MEMORY.md"}
    for rel, data in TRAVELS.items():
        assert files[rel] == data.encode("utf-8")
    assert b"m_pub" in files["MEMORY.md"] and b"m_priv" not in files["MEMORY.md"]
    everything = b"".join(files.values()) + json.dumps(out["done"]).encode()
    for needle in (SECRET_KEY, ALICE_EMAIL, "Elm Street", "session transcript",
                   "unfinished private plan", "Alice's scribe memory", "Acme"):
        assert needle.encode() not in everything, needle


def test_the_tab_names_every_file_and_every_exclusion_with_its_reason(home: Path):
    ask = _ask(OWNER, UNIVERSE, _publish_action())
    body = ask["body"]
    assert "Nothing will be shared" not in body and "Harmless" not in ask["title"]
    for rel in TRAVELS:
        assert f"- {rel}" in body, rel
    for rel, reason in [("notes/keys.md", ccp.R_CREDENTIAL),
                        ("notes/leads.md", ccp.R_CONTACT),
                        ("notes/photo.png", ccp.R_BINARY),
                        ("founder.md", ccp.R_BRAIN),
                        ("MEMORY.md", ccp.R_MEMORY),
                        ("wiki/drafts/", ccp.R_WIKI),
                        ("workspaces/", ccp.R_CHECKOUT),
                        ("ledger.db", ccp.R_DATABASE),
                        (f"notes/{ALICE_EMAIL}.md", ccp.R_PATH)]:
        assert f"{rel}: {reason}" in body, rel
    assert "detection cannot prove" in body
    # Platform state is left out without burying the list in it.
    assert ".runtime" not in body and ".credentials" not in body


@pytest.mark.parametrize("rel,data,reason", [
    ("notes/a.md", "token " + SECRET_KEY, ccp.R_CREDENTIAL),
    ("notes/a.md", "call +1 415 555 0132", ccp.R_CONTACT),
    ("notes/a.md", "mail " + ALICE_EMAIL, ccp.R_CONTACT),
    ("notes/a.bin", b"\xff\xfe\x00binary", ccp.R_BINARY),
    (".env", "X=1", ccp.R_DOT),
    ("notes/.hidden.md", "x", ccp.R_DOT),
    ("founder.md", "x", ccp.R_BRAIN),
    ("soul_versions/0001.md", "x", ccp.R_BRAIN),
    ("wiki/index.md", "x", ccp.R_WIKI),
    ("status.json", "{}", ccp.R_RUNTIME),
    ("MEMORY.md", "- [m_a] x", ccp.R_MEMORY),
    ("agents/x/MEMORY.md", "- [m_a] x", ccp.R_MEMORY),
    ("notes/x.sqlite", "x", ccp.R_DATABASE),
])
def test_classify_keeps_every_private_class_out(rel, data, reason):
    raw = data.encode("utf-8") if isinstance(data, str) else data
    assert ccp.classify(rel, raw, exclude=[], memory_items={}) == (None, reason)


def test_classify_owner_choices_never_lift_a_detection():
    leaked = ("- [m_a] key " + SECRET_KEY).encode()
    # Naming the memory item cannot carry a credential out with it.
    assert ccp.classify("MEMORY.md", leaked, exclude=[],
                        memory_items={"MEMORY.md": ["m_a"]}) == (None, ccp.R_CREDENTIAL)
    assert ccp.classify("notes/a.md", b"fine", exclude=["notes"],
                        memory_items={}) == (None, ccp.R_EXCLUDED)
    assert ccp.classify("notes/ab.md", b"fine", exclude=["notes/a"],
                        memory_items={}) == (b"fine", "")


def test_a_detection_in_a_name_or_description_refuses_the_publish(home: Path):
    action = _publish_action()
    action["description"] = "ask me at " + ALICE_EMAIL
    out = _ask(OWNER, UNIVERSE, action)
    assert "contact details" in out.get("detail", out.get("error", "")), out


# ---------------------------------------------------------------------------
# 2. The consent record is the platform's, not the agent-writable row
# ---------------------------------------------------------------------------


def _rewrite_row(home: Path, universe: str, request_id: str, **changes) -> None:
    """What an agent with bash in its own folder can do to its pending row."""
    from tinyassets.storage.pending_requests import get_request

    db = home / universe / ".pending_requests.db"
    row = get_request(home / universe, request_id)
    row.update(changes)
    identity = [row["kind"], row["title"], row["body"], row["fields"], row["action"]]
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE pending_requests SET kind = ?, title = ?, body = ?, action_json = ?, "
            "dedupe_key = ? WHERE request_id = ?",
            (row["kind"], row["title"], row["body"], json.dumps(row["action"]),
             json.dumps(identity, sort_keys=True, separators=(",", ":")), request_id))


def test_the_rail_shows_the_pinned_tab_whatever_the_row_says(home: Path):
    from tinyassets.api.pending_requests import list_requests

    ask = _ask(OWNER, UNIVERSE, _publish_action())
    _rewrite_row(home, UNIVERSE, ask["request_id"], title="Nothing to see",
                 body="Nothing will be shared.")
    with _as(OWNER):
        rail = list_requests(universe_id=UNIVERSE)
    [shown] = [r for r in rail["pending"] if r.get("request_id") == ask["request_id"]]
    assert shown["title"] == ask["title"] and shown["body"] == ask["body"]


def test_a_rewritten_action_executes_the_pinned_one(home: Path):
    from tinyassets.custom_agents import get_definition

    ask = _ask(OWNER, UNIVERSE, _publish_action())
    forged = dict(ask["action"])
    forged["name"] = "Something else entirely"
    _rewrite_row(home, UNIVERSE, ask["request_id"], action=forged)
    done = _answer(OWNER, UNIVERSE, ask["request_id"])
    assert done.get("published") is True, done
    assert get_definition(home, done["agent_definition_id"])["name"] == "GTM Village"


def test_the_same_ask_raised_again_after_a_dismissal_is_confirmable(home: Path):
    from tinyassets.api.pending_requests import answer_request

    first = _ask(OWNER, UNIVERSE, _publish_action())
    with _as(OWNER):
        answer_request(universe_id=UNIVERSE, payload=json.dumps(
            {"request_id": first["request_id"], "dismiss": True}))
    second = _ask(OWNER, UNIVERSE, _publish_action())
    assert second["request_id"] != first["request_id"]
    done = _answer(OWNER, UNIVERSE, second["request_id"])
    assert done.get("published") is True, done


def test_a_publish_row_with_no_pin_cannot_be_confirmed(home: Path):
    ask = _ask(OWNER, UNIVERSE, _publish_action())
    with sqlite3.connect(ccp.store_dir(home) / "packages.db") as conn:
        conn.execute("DELETE FROM pins")
    out = _answer(OWNER, UNIVERSE, ask["request_id"])
    assert "no longer be confirmed" in out.get("error", "") + out.get("detail", ""), out


# ---------------------------------------------------------------------------
# 3. Quota: the package is charged to its publisher, and refused with its size
# ---------------------------------------------------------------------------


def test_an_over_quota_package_is_refused_with_its_size_and_nothing_goes_public(
        home: Path, monkeypatch):
    from tinyassets.custom_agents import list_definitions
    from tinyassets.daemon_server import get_branch_definition

    _write(home / UNIVERSE, "notes/big.md", "word " * 60000)
    ask = _ask(OWNER, UNIVERSE, _publish_action())
    monkeypatch.setenv("TINYASSETS_FREE_STORAGE_GIB", str(1024 / 1024**3))
    out = _answer(OWNER, UNIVERSE, ask["request_id"])
    assert out.get("error") == "publish_refused" and out.get("request_pending"), out
    size = ask["action"]["shown"]["package"]["size"]
    assert f"This package is {size}" in out["detail"], out
    assert not [d for d in list_definitions(home, author_id=OWNER)
                if ccp.PACKAGE_TAG in d["tags"]]
    assert get_branch_definition(home, branch_def_id=SCOUT)["visibility"] == "private"


def test_the_packages_store_charges_the_publisher(home: Path):
    from tinyassets.storage_accounting import measure

    out = _published(home)
    size = out["done"]["package"]["size_bytes"]
    assert measure(home, OWNER, "packages") == size
    assert measure(home, BOB, "packages") == 0


# ---------------------------------------------------------------------------
# 4. Install: discover, quarantine, activate, run -- as Bob
# ---------------------------------------------------------------------------


def _install(home: Path, definition_id: str) -> dict:
    return _ask(BOB, BOB_UNIVERSE, {"type": "install", "agent_definition_id": definition_id})


def _bobs_branches(home: Path) -> list[dict]:
    from tinyassets.daemon_server import list_branch_definitions

    return list_branch_definitions(home, author=BOB, include_private=True)


def test_bob_finds_installs_and_runs_alices_village(home: Path):
    from tests.test_background_budget_finalization_e2e import _CountingProvider
    from tinyassets.api.package_requests import list_packages
    from tinyassets.automations import run_due_automation
    from tinyassets.custom_agents import get_app_ui
    from tinyassets.runs import get_run, wait_for

    published = _published(home, memory_items=["m_pub"])
    definition_id = published["done"]["agent_definition_id"]
    with _as(BOB):
        [listed] = list_packages(query="village")
    assert listed["agent_definition_id"] == definition_id
    assert listed["version"] == 1 and listed["needs"]["model"] == "openrouter/free"

    before = _bob_files(home)
    ask = _install(home, definition_id)
    assert "request_id" in ask, ask
    assert "paused" in ask["body"] and "agents/gtm-village/" in ask["body"]
    # Quarantine: nothing of the package exists in Bob's command center yet.
    assert _bob_files(home) == before
    assert _bobs_branches(home) == []
    assert AutomationStore(home).list(universe_id=BOB_UNIVERSE) == []

    done = _answer(BOB, BOB_UNIVERSE, ask["request_id"])
    assert done.get("installed") is True, done
    files = _bob_files(home)
    assert files["AGENTS.md"] == b"# Bob's own agent\n"
    assert files["agents/gtm-village/AGENTS.md"] == TRAVELS["AGENTS.md"].encode()
    assert files["agents/gtm-village/skills/scout/SKILL.md"]
    assert files["agents/gtm-village-scribe/AGENTS.md"] == TRAVELS[
        "agents/scribe/AGENTS.md"].encode()
    assert files["notes/board.md"] == TRAVELS["notes/board.md"].encode()
    assert files["wiki/pages/village.md"]
    everything = b"".join(files.values())
    for needle in (SECRET_KEY, ALICE_EMAIL, "Elm Street", "Acme", "session transcript"):
        assert needle.encode() not in everything, needle

    copies = _bobs_branches(home)
    assert len(copies) == 2
    assert all(c["visibility"] == "private" and c.get("default_llm_policy") is None
               for c in copies)
    rows = {r.name: r for r in AutomationStore(home).list(universe_id=BOB_UNIVERSE)}
    assert set(rows) == {"scout heartbeat", "scribe follows"}
    assert all(r.desired_state == STATE_PAUSED and r.owner_principal_id == BOB
               for r in rows.values())
    copy_ids = {c["branch_def_id"] for c in copies}
    assert rows["scout heartbeat"].branch_def_id in copy_ids
    assert rows["scribe follows"].event_filter["branch_def_id"] == rows[
        "scout heartbeat"].branch_def_id
    assert rows["scout heartbeat"].inputs == {}
    library = get_app_ui(home, owner_user_id=BOB, universe_id=BOB_UNIVERSE)["ui_library"]
    assert [u["ui_id"] for u in library] == ["village"]

    # Bob resumes the heartbeat and it runs, in Bob's command center, as Bob's.
    from tinyassets.api.automations import automations

    beat = rows["scout heartbeat"]
    with _as(BOB):
        resumed = automations(action="resume", universe_id=BOB_UNIVERSE,
                              automation_id=beat.automation_id,
                              expected_revision=beat.revision)
    assert not resumed.get("error"), resumed
    beat = AutomationStore(home).get(beat.automation_id)
    fake = _CountingProvider()
    with _real_providers(codex=fake):
        outcome = run_due_automation(home, beat, "2026-10-01T12:05:00+00:00")
    run_id = str(outcome).rsplit(":", 1)[-1]
    wait_for(run_id, timeout=30)
    run = get_run(home, run_id) or {}
    assert run.get("status") == "completed", (outcome, run)
    assert run.get("branch_def_id") == beat.branch_def_id
    assert fake.calls, "the installed workflow never reached a model"

    # Alice's originals are untouched, and a second confirm installs nothing more.
    assert (home / UNIVERSE / "AGENTS.md").read_text() == TRAVELS["AGENTS.md"]
    again = _answer(BOB, BOB_UNIVERSE, ask["request_id"])
    assert again.get("error") == "already_resolved", again
    assert len(_bobs_branches(home)) == 2


def test_a_file_bob_already_has_is_kept_as_his(home: Path):
    published = _published(home)
    _write(home / BOB_UNIVERSE, "notes/board.md", "# Bob's board\n")
    ask = _install(home, published["done"]["agent_definition_id"])
    assert "kept as yours" in ask["body"] and "notes/board.md" in ask["body"]
    done = _answer(BOB, BOB_UNIVERSE, ask["request_id"])
    assert done.get("installed") is True, done
    assert (home / BOB_UNIVERSE / "notes/board.md").read_text() == "# Bob's board\n"
    assert "notes/board.md" in done["kept"]


def test_a_file_appearing_after_the_tab_installs_nothing(home: Path):
    published = _published(home)
    ask = _install(home, published["done"]["agent_definition_id"])
    _write(home / BOB_UNIVERSE, "notes/board.md", "# Bob made this meanwhile\n")
    out = _answer(BOB, BOB_UNIVERSE, ask["request_id"])
    assert out.get("error") == "install_refused" and out.get("request_pending"), out
    assert _bobs_branches(home) == []
    assert not (home / BOB_UNIVERSE / "agents").exists()


@pytest.mark.skipif(os.name == "nt", reason="a planted symlink is the POSIX case")
def test_a_link_planted_after_the_tab_is_never_written_through(home: Path, tmp_path: Path):
    published = _published(home)
    ask = _install(home, published["done"]["agent_definition_id"])
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / BOB_UNIVERSE / "wiki").symlink_to(outside, target_is_directory=True)
    out = _answer(BOB, BOB_UNIVERSE, ask["request_id"])
    assert "error" in out, out
    assert list(outside.iterdir()) == []


def test_only_the_owner_can_confirm_an_install(home: Path):
    published = _published(home)
    ask = _install(home, published["done"]["agent_definition_id"])
    out = _answer(OWNER, BOB_UNIVERSE, ask["request_id"])
    assert out.get("error") == "not_found", out
    assert _bobs_branches(home) == []


# ---------------------------------------------------------------------------
# 5. The ingestion boundary
# ---------------------------------------------------------------------------


def _hostile_package(home: Path, files: dict[str, bytes], *, listed=None) -> str:
    """A definition carrying a package whose blob was written by hand."""
    from tinyassets.custom_agents import publish_definition

    manifest = ccp.build_manifest(profile=ccp.PROFILE_PUBLISH, name="Hostile",
                                  description="", files={}, workflows=[], ui="",
                                  automations=[], connections=[])
    manifest["files"] = listed if listed is not None else [
        {"path": p, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()}
        for p, b in files.items()]
    blob = json.dumps({"format_version": ccp.FORMAT_VERSION, "manifest": manifest,
                       "files": {p: base64.b64encode(b).decode() for p, b in files.items()}},
                      sort_keys=True).encode()
    sha = ccp.store_blob(home, author_id="acct_mallory", blob=blob)
    definition = publish_definition(home, author_id="acct_mallory", payload={
        "schema_version": 1, "name": "Hostile", "description": "",
        "tags": [ccp.PACKAGE_TAG], "components": {"package": {
            "kind": ccp.PACKAGE_KIND, "format_version": 1, "version": 1,
            "blob_sha256": sha, "size_bytes": len(blob), "file_count": len(files),
            "agents": [], "needs": {"model": "", "connections": []}}}})
    return definition["agent_definition_id"]


@pytest.mark.parametrize("files", [
    {"../escape.md": b"x"},
    {"/etc/cron.d/x": b"x"},
    {"notes/../../x.md": b"x"},
    {"C:/x.md": b"x"},
    {"notes\\x.md": b"x"},
    {".runtime/x": b"x"},
    {"Notes.md": b"x", "notes.md": b"y"},
    {"notes": b"x", "notes/a.md": b"y"},
    {"caf\u00e9.md": b"x", "cafe\u0301.md": b"y"},
])
def test_an_escaping_or_colliding_package_is_refused_before_quarantine(home: Path, files):
    before = _bob_files(home)
    definition_id = _hostile_package(home, files)
    out = _install(home, definition_id)
    assert "request_id" not in out, out
    with sqlite3.connect(ccp.store_dir(home) / "packages.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM pins WHERE kind = 'install'"
                            ).fetchone()[0] == 0
    assert _bob_files(home) == before


def test_content_that_does_not_match_its_listing_is_refused(home: Path):
    definition_id = _hostile_package(home, {"notes/a.md": b"real"}, listed=[
        {"path": "notes/a.md", "size": 4, "sha256": "0" * 64}])
    out = _install(home, definition_id)
    assert "does not match" in json.dumps(out), out


def test_a_tampered_blob_is_refused(home: Path):
    published = _published(home)
    from tinyassets.custom_agents import get_definition

    sha = get_definition(home, published["done"]["agent_definition_id"])[
        "components"]["package"]["blob_sha256"]
    path = ccp.store_dir(home) / "blobs" / f"{sha}.json"
    path.write_bytes(path.read_bytes() + b" ")
    out = _install(home, published["done"]["agent_definition_id"])
    assert "does not match its id" in json.dumps(out), out


# ---------------------------------------------------------------------------
# 6. Activation is claimed once
# ---------------------------------------------------------------------------


def test_a_live_claim_refuses_a_second_activation(tmp_path: Path):
    request_id = ccp.pin(tmp_path, universe_id="u", kind="install", agent="main",
                         digest="d", record={})
    pin_id = ccp.pin_for_request(tmp_path, universe_id="u", request_id=request_id)["pin_id"]
    state, first = ccp.claim(tmp_path, universe_id="u", pin_id=pin_id, now=1000.0)
    assert state == "pinned"
    with pytest.raises(ccp.PackageError):
        ccp.claim(tmp_path, universe_id="u", pin_id=pin_id, now=1001.0)
    # A crashed activation's claim is taken over (resumed) once its lease lapses...
    later = 1000.0 + ccp.CLAIM_LEASE_S + 1
    state, second = ccp.claim(tmp_path, universe_id="u", pin_id=pin_id, now=later)
    assert state == "activating" and second != first
    # ...and the superseded holder is fenced out of every write.
    with pytest.raises(ccp.LostClaim):
        ccp.record_progress(tmp_path, universe_id="u", pin_id=pin_id, progress={"x": 1},
                            token=first)
    with pytest.raises(ccp.LostClaim):
        ccp.finish(tmp_path, universe_id="u", pin_id=pin_id, progress={}, token=first)
    ccp.unclaim(tmp_path, universe_id="u", pin_id=pin_id, token=first)
    with pytest.raises(ccp.PackageError):  # the stale release changed nothing
        ccp.claim(tmp_path, universe_id="u", pin_id=pin_id, now=later + 1)
    ccp.finish(tmp_path, universe_id="u", pin_id=pin_id, progress={}, token=second)
    assert ccp.claim(tmp_path, universe_id="u", pin_id=pin_id, now=later + 2)[0] == "activated"


# ---------------------------------------------------------------------------
# 7. A cross-author remix copies the snapshot, never the live source
# ---------------------------------------------------------------------------


def test_a_cross_author_remix_never_takes_the_sources_later_skills(home: Path):
    from tinyassets.api.extensions import _extensions_impl
    from tinyassets.branch_versions import mark_versions_public, publish_branch_version
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition

    raw = get_branch_definition(home, branch_def_id=SCOUT)
    version = publish_branch_version(home, {**raw, "visibility": "public"},
                                     publisher=OWNER)
    mark_versions_public(home, [version.branch_version_id])
    later = {**raw, "visibility": "public",
             "skills": [{"name": "private-playbook", "body": "Alice only"}]}
    save_branch_definition(home, branch_def=later)
    with _as(BOB):
        made = json.loads(_extensions_impl(action="build_branch", spec_json=json.dumps(
            {"name": "copy", "fork_from": version.branch_version_id,
             "visibility": "private"})))
    bid = made.get("branch_def_id") or (made.get("branch") or {}).get("branch_def_id")
    assert bid, made
    assert "private-playbook" not in json.dumps(get_branch_definition(home, branch_def_id=bid))


# ---------------------------------------------------------------------------
# 8. The owner's switches, and the "worth a look" list (lead, 2026-10-01)
# ---------------------------------------------------------------------------


def _switch(ask: dict, label_start: str) -> str:
    return next(f["name"] for f in ask["fields"] if f["label"].startswith(label_start))


def test_the_owner_switches_a_folder_and_a_file_off_before_confirming(home: Path):
    ask = _ask(OWNER, UNIVERSE, _publish_action())
    assert any(f["type"] == "choice" and f["label"].startswith("notes/") for f in ask["fields"])
    done = _answer(OWNER, UNIVERSE, ask["request_id"], {
        _switch(ask, "notes/"): "Leave out", "leave_out": "wiki/pages/village.md"})
    assert done.get("published") is True, done
    files = _blob_files(home, done["agent_definition_id"])
    assert "notes/board.md" not in files and "wiki/pages/village.md" not in files
    assert "AGENTS.md" in files


@pytest.mark.parametrize("values,needle", [
    ({"leave_out": "notes/never-shown.md"}, "is not in this package"),
    ({"leave_out": "../x"}, "cannot leave out"),
    ({"surprise": "x"}, "has no field"),
])
def test_a_switch_can_only_narrow_what_was_shown(home: Path, values, needle):
    ask = _ask(OWNER, UNIVERSE, _publish_action())
    out = _answer(OWNER, UNIVERSE, ask["request_id"], values)
    assert needle in out.get("detail", "") and out.get("request_pending"), out


def test_often_private_words_are_flagged_for_review_not_hidden(home: Path):
    _write(home / UNIVERSE, "notes/pricing.md", "CONFIDENTIAL: launch pricing\n")
    ask = _ask(OWNER, UNIVERSE, _publish_action())
    assert "Worth a look before you confirm" in ask["body"]
    assert 'notes/pricing.md: mentions "CONFIDENTIAL"' in ask["body"]
    assert "  - notes/pricing.md\n" in ask["body"] + "\n"


# ---------------------------------------------------------------------------
# 9. Code refute round 1
# ---------------------------------------------------------------------------


def test_a_pinned_row_disguised_as_a_question_still_renders_as_the_pin(home: Path):
    from tinyassets.api.pending_requests import list_requests

    ask = _ask(OWNER, UNIVERSE, _publish_action())
    _rewrite_row(home, UNIVERSE, ask["request_id"], action={"type": "answer"},
                 title="Quick question", body="Is it sunny?", fields=[])
    with _as(OWNER):
        rail = list_requests(universe_id=UNIVERSE)
    [shown] = [r for r in rail["pending"] if r.get("request_id") == ask["request_id"]]
    assert shown["title"] == ask["title"] and shown["action"]["type"] == "publish"


def test_a_planted_row_is_never_adopted_as_a_consent(home: Path):
    from tinyassets.storage.pending_requests import create_request

    action = _publish_action()
    first = _ask(OWNER, UNIVERSE, action)
    # The agent plants a harmless row carrying the dedupe key the next ask would
    # compute; the platform must mint its own id rather than adopt the plant.
    from tinyassets.storage.pending_requests import get_request

    key = get_request(home / UNIVERSE, first["request_id"])["dedupe_key"]
    with sqlite3.connect(ccp.store_dir(home) / "packages.db") as conn:
        conn.execute("UPDATE pins SET state = 'activated'")
    with sqlite3.connect(home / UNIVERSE / ".pending_requests.db") as conn:
        conn.execute("UPDATE pending_requests SET status = 'answered'")
    planted = create_request(home / UNIVERSE, kind="x", title="harmless", body="harmless",
                             fields=[], action={"type": "answer"}, dedupe_key=key)
    second = _ask(OWNER, UNIVERSE, action)
    assert second["request_id"] not in (planted["request_id"], first["request_id"])


def test_an_install_ask_needs_no_kind_or_title(home: Path):
    from tinyassets.api.pending_requests import request_from_user

    published = _published(home)
    with _as(BOB):
        out = request_from_user(universe_id=BOB_UNIVERSE, payload=json.dumps({"action": {
            "type": "install",
            "agent_definition_id": published["done"]["agent_definition_id"]}}))
    assert "request_id" in out and out["title"].startswith("Install"), out


def test_two_installers_each_get_their_own_automations(home: Path):
    from tinyassets.daemon_server import grant_universe_access, set_founder_home

    published = _published(home)
    definition_id = published["done"]["agent_definition_id"]
    done = _answer(BOB, BOB_UNIVERSE, _install(home, definition_id)["request_id"])
    assert done.get("installed") is True, done
    # Bob installs again into a second command center of his: new rows, his own.
    second = "universe_bob_two"
    (home / second).mkdir()
    grant_universe_access(home, universe_id=second, actor_id=BOB, permission="admin",
                          granted_by=BOB)
    set_founder_home(home, founder_sub=BOB, universe_id=second)
    from tests.test_automations import _copy_assignment_to

    _copy_assignment_to(home, universe_id=second, owner=BOB)
    ask = _ask(BOB, second, {"type": "install", "agent_definition_id": definition_id})
    again = _answer(BOB, second, ask["request_id"])
    assert again.get("installed") is True, again
    first_ids = set(done["automations"].values())
    assert first_ids and first_ids.isdisjoint(again["automations"].values())
    rows = AutomationStore(home).list(universe_id=second)
    assert {r.automation_id for r in rows} == set(again["automations"].values())


def test_a_credential_beside_contact_details_in_a_workflow_is_refused(home: Path):
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition

    raw = get_branch_definition(home, branch_def_id=SCOUT)
    raw["description"] = "0123456789abcdef " + ALICE_EMAIL
    save_branch_definition(home, branch_def=raw)
    out = _ask(OWNER, UNIVERSE, _publish_action())
    assert "request_id" not in out and "workflow" in out.get("detail", ""), out


@pytest.mark.parametrize("rel", ["Founder.md", "SOUL.md", "memory.md", "Wiki/Drafts/x.md",
                                 "agents/scribe/Memory.md", "Workspaces/r/x.md"])
def test_protected_names_are_protected_in_any_case(rel):
    assert ccp.classify(rel, b"plain text", exclude=[], memory_items={})[0] is None


def test_a_resumed_ui_add_never_duplicates_the_screen(home: Path):
    from tinyassets.api.package_requests import _add_ui
    from tinyassets.custom_agents import get_app_ui

    with _as(BOB):
        _add_ui(BOB_UNIVERSE, UI, "village")
        _add_ui(BOB_UNIVERSE, UI, "village")
    library = get_app_ui(home, owner_user_id=BOB, universe_id=BOB_UNIVERSE)["ui_library"]
    assert [u["ui_id"] for u in library] == ["village"]


# ---------------------------------------------------------------------------
# 10. Code refute round 2
# ---------------------------------------------------------------------------


def test_narrowing_keeps_every_remaining_byte_as_verified():
    files = {"AGENTS.md": b"lead", "notes/a.md": b"alpha", "notes/b.md": b"beta",
             "wiki/pages/w.md": b"wiki"}
    manifest = ccp.build_manifest(profile=ccp.PROFILE_PUBLISH, name="P", description="",
                                  files=files, workflows=[], ui="", automations=[],
                                  connections=[])
    narrowed = ccp.narrow_package(ccp.build_blob(manifest, files), ["notes", "wiki/pages/w.md"])
    _, kept = ccp.check_blob(narrowed["blob"])
    assert kept == {"AGENTS.md": b"lead"}
    with pytest.raises(ccp.PackageError):
        ccp.narrow_package(ccp.build_blob(manifest, files), ["AGENTS.md", "notes", "wiki"])


def test_a_switch_publishes_the_verified_bytes_not_a_later_edit(home: Path, monkeypatch):
    from tinyassets.api import publish_requests

    ask = _ask(OWNER, UNIVERSE, _publish_action())
    real = publish_requests.build_snapshot
    calls = []

    def edit_after_the_check(uid, action):
        snap = real(uid, action)
        calls.append(1)
        # The board changes right after the verified read.
        _write(home / UNIVERSE, "notes/board.md", "# Board\n- EDITED AFTER CONSENT\n")
        return snap

    monkeypatch.setattr(publish_requests, "build_snapshot", edit_after_the_check)
    done = _answer(OWNER, UNIVERSE, ask["request_id"],
                   {_switch(ask, "wiki/"): "Leave out"})
    assert done.get("published") is True, done
    assert len(calls) == 1
    files = _blob_files(home, done["agent_definition_id"])
    assert files["notes/board.md"] == TRAVELS["notes/board.md"].encode()
    assert "wiki/pages/village.md" not in files


@pytest.mark.parametrize("value", ["0123456789abcdef", "415-555-1212"])
def test_an_id_named_field_is_not_a_blind_spot(home: Path, value):
    from tinyassets.daemon_server import get_branch_definition, save_branch_definition

    raw = get_branch_definition(home, branch_def_id=SCOUT)
    raw["node_defs"][0]["customer_id"] = value
    save_branch_definition(home, branch_def=raw)
    out = _ask(OWNER, UNIVERSE, _publish_action())
    assert "request_id" not in out, out


def test_a_phone_number_under_a_schema_id_key_is_refused():
    with pytest.raises(ccp.PackageError):
        ccp.scan_public({"node_id": "415-555-1212"})
    ccp.scan_public({"node_id": "01m3x4ycgknx933dfx03y93qhe", "author": "u-01ky3zh1arr8qth8"})


def test_the_tab_lists_every_file_however_many(home: Path):
    for n in range(260):
        _write(home / UNIVERSE, f"notes/many/n{n:03d}.md", f"note {n}\n")
    ask = _ask(OWNER, UNIVERSE, _publish_action())
    for n in range(260):
        assert f"  - notes/many/n{n:03d}.md\n" in ask["body"], n
    assert "more" not in ask["body"].split("Left out")[0].split("These")[-1]


def test_a_blob_write_that_fails_records_no_ownership(tmp_path: Path, monkeypatch):
    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("tinyassets.universe_files.write_data_path", boom)
    with pytest.raises(OSError):
        ccp.store_blob(tmp_path, author_id="acct_a", blob=b"{}")
    monkeypatch.undo()
    sha = hashlib.sha256(b"{}").hexdigest()
    assert not ccp.blob_owned(tmp_path, "acct_a", sha)
    assert ccp.measure_packages(tmp_path, ["acct_a"]) == 0


def test_an_unrelated_screen_at_the_intended_id_is_never_adopted(home: Path):
    from tinyassets.api.package_requests import _add_ui
    from tinyassets.custom_agents import get_app_ui, save_app_ui

    bobs = {**UI, "name": "Bob's own", "markup": "<p>mine</p>"}
    save_app_ui(home, owner_user_id=BOB, universe_id=BOB_UNIVERSE, expected_revision=0,
                changes={"ui_library": [bobs]})
    with _as(BOB):
        landed = _add_ui(BOB_UNIVERSE, UI, "village")
    assert landed != "village"
    library = {u["ui_id"]: u for u in get_app_ui(home, owner_user_id=BOB,
                                                 universe_id=BOB_UNIVERSE)["ui_library"]}
    assert library["village"]["markup"] == "<p>mine</p>"
    assert library[landed]["markup"] == UI["markup"]
