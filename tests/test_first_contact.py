"""Founder-home resolution and first-contact universe conversation.

`get_status` is a pure read. Omitted-scope authenticated `converse` resolves or
atomically creates the founder's home, loads its soul, and returns its own voice.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity
from tinyassets.ids import is_universe_serial

_RESERVED = {"wiki", "output", "runs", "lance"}


class _StaticAuthProvider(AuthProvider):
    """Resolve-always provider (like WorkOS): anon reads, authed founder writes."""

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


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch) -> Path:
    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    return base


@pytest.fixture(autouse=True)
def _reset_auth():
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


def _login(sub: str = "founder-1", caps: list[str] | None = None) -> None:
    ident = Identity(
        user_id=sub, username=sub,
        capabilities=caps or ["read", "write", "costly", "submit_request", "list"],
    )
    set_provider(_StaticAuthProvider(ident))
    auth_middleware("ok")


def _universe_dirs(base: Path) -> list[Path]:
    return [
        p for p in base.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in _RESERVED
    ]


def _serial_dirs(base: Path) -> list[Path]:
    return [p for p in _universe_dirs(base) if is_universe_serial(p.name)]


def _create_via_action(base, monkeypatch):
    """Create a universe the explicit way (ledgered MCP route)."""
    from tinyassets.api import universe as universe_api

    monkeypatch.setattr(universe_api, "_base_path", lambda: base)
    out = json.loads(universe_api._universe_impl(action="create_universe"))
    assert out.get("error") is None, out
    return out["universe_id"]


def _capture_universe_reply(monkeypatch, reply: str) -> dict:
    """Stub only the external engine while keeping real persona assembly."""
    import tinyassets.universe_intelligence as intelligence

    captured: dict = {}

    def fake_call_provider(prompt, system="", *, role="writer", **kwargs):
        if "strict JSON" in system:
            return "{}"
        captured.update(
            prompt=prompt,
            system=system,
            role=role,
            universe_context=kwargs.get("universe_context"),
        )
        return reply

    monkeypatch.setattr(intelligence, "call_provider", fake_call_provider)
    return captured


def test_get_status_without_home_is_repeatable_and_side_effect_free(data_dir):
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home

    _login("founder-1")
    first = json.loads(get_status())
    second = json.loads(get_status())

    assert first == second
    assert first["first_contact"]["event"] == "no_universe_yet"
    assert get_founder_home(data_dir, "founder-1") == ""
    assert _serial_dirs(data_dir) == []


def test_get_status_does_not_first_create_or_mutate_new_universe_soul(
    data_dir, monkeypatch
):
    from tinyassets.api.status import get_status

    _login("founder-1")
    uid = _create_via_action(data_dir, monkeypatch)
    udir = data_dir / uid
    soul_paths = sorted(
        p for p in udir.rglob("*")
        if p.is_file() and (p.suffix == ".md" or "soul_versions" in p.parts)
    )
    assert soul_paths
    assert (udir / "soul.md").is_file()  # creation, not status, seeded it
    before = {p.relative_to(udir): p.read_bytes() for p in soul_paths}

    first = json.loads(get_status(universe_id=uid))
    second = json.loads(get_status(universe_id=uid))
    after = {p.relative_to(udir): p.read_bytes() for p in soul_paths}

    assert first["universe_id"] == uid
    assert second["universe_id"] == uid
    assert after == before


def test_first_connect_new_founder_births_seed_and_returns_universe_voice(
    data_dir, monkeypatch
):
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.universe_server import converse

    _login("founder-1")
    captured = _capture_universe_reply(
        monkeypatch,
        "I am here. I do not have a name yet—who are you?",
    )

    out = json.loads(converse(message="Hello"))

    assert out["reply"].startswith("I ")
    uid = out["universe_id"]
    assert is_universe_serial(uid)
    assert get_founder_home(data_dir, "founder-1") == uid
    assert (data_dir / uid / "soul.md").is_file()
    assert "first person" in captured["system"].lower()
    assert "name yet" in captured["system"].lower()
    assert not (data_dir / ".active_universe").exists()


def test_first_connect_existing_founder_loads_learned_home_voice(
    data_dir, monkeypatch
):
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.soul_edit import apply_soul_edit
    from tinyassets.universe_server import converse

    _login("founder-1")
    uid = _create_via_action(data_dir, monkeypatch)
    apply_soul_edit(
        data_dir / uid,
        changes={"identity.md": "# Identity\n\nI am Aetheria.\n"},
        source="founder conversation",
        context="The founder named the universe Aetheria.",
        name="Aetheria",
    )
    captured = _capture_universe_reply(monkeypatch, "I am Aetheria. Welcome back.")

    out = json.loads(converse(message="Hello again"))

    assert out == {"reply": "I am Aetheria. Welcome back.", "universe_id": uid}
    assert get_founder_home(data_dir, "founder-1") == uid
    assert len(_serial_dirs(data_dir)) == 1
    assert "You are Aetheria." in captured["system"]


def test_first_connect_anonymous_cannot_birth_or_reach_universe(data_dir):
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.universe_server import converse

    out = json.loads(converse(message="Hello"))

    assert out.get("auth_required") is True
    assert "reply" not in out
    assert get_founder_home(data_dir, "anonymous") == ""
    assert _serial_dirs(data_dir) == []


def test_first_connect_cannot_target_another_founders_universe(
    data_dir, monkeypatch
):
    from tinyassets.universe_server import converse

    _login("founder-A")
    home_a = _create_via_action(data_dir, monkeypatch)
    _login("founder-B")
    _capture_universe_reply(monkeypatch, "I should never be reached.")

    out = json.loads(converse(message="Hello", graph_id=home_a))

    assert out.get("auth_scope_required") is True
    assert "reply" not in out


def test_founder_home_set_get_roundtrip(data_dir):
    from tinyassets.daemon_server import get_founder_home, set_founder_home

    assert get_founder_home(data_dir, "founder-1") == ""
    set_founder_home(data_dir, founder_sub="founder-1", universe_id="u-01x")
    assert get_founder_home(data_dir, "founder-1") == "u-01x"
    # anonymous / empty never has a home
    assert get_founder_home(data_dir, "anonymous") == ""
    assert get_founder_home(data_dir, "") == ""


def test_claim_founder_home_serializes_single_home(data_dir):
    # The atomic serialization primitive behind concurrent first-contact: the
    # first claim wins; a later claim (a racing worker) gets the already-bound id
    # back — never its own candidate — so no second universe is ever minted.
    from tinyassets.daemon_server import claim_founder_home, get_founder_home
    from tinyassets.ids import new_universe_id

    first, second = new_universe_id(), new_universe_id()
    assert claim_founder_home(data_dir, "founder-1", first) == first
    assert claim_founder_home(data_dir, "founder-1", second) == first  # loser adopts
    assert get_founder_home(data_dir, "founder-1") == first
    # anonymous / empty candidate never claims
    assert claim_founder_home(data_dir, "anonymous", new_universe_id()) == ""
    assert claim_founder_home(data_dir, "founder-1", "") == ""


def test_ensure_founder_home_births_complete_seed(data_dir):
    from tinyassets.api.first_contact import ensure_founder_home
    from tinyassets.daemon_server import get_founder_home

    _login("founder-1")
    uid = ensure_founder_home(data_dir, "founder-1")

    assert is_universe_serial(uid)
    assert get_founder_home(data_dir, "founder-1") == uid
    assert (data_dir / uid / "soul.md").is_file()


def test_auto_birth_is_idempotent(data_dir):
    from tinyassets.api.first_contact import ensure_founder_home
    from tinyassets.daemon_server import get_founder_home

    _login("founder-1")
    first = ensure_founder_home(data_dir, "founder-1")
    ensure_founder_home(data_dir, "founder-1")
    ensure_founder_home(data_dir, "founder-1")
    assert get_founder_home(data_dir, "founder-1") == first
    assert [p.name for p in _serial_dirs(data_dir)] == [first]


def test_auto_birth_is_ledgered(data_dir):
    # The auto-birth create routes through the ledgered dispatch, same as an
    # explicit create — the new universe records a create_universe ledger entry.
    from tinyassets.api.first_contact import ensure_founder_home

    _login("founder-1")
    uid = ensure_founder_home(data_dir, "founder-1")
    ledger = data_dir / uid / "ledger.json"
    assert ledger.is_file()
    entries = json.loads(ledger.read_text(encoding="utf-8"))
    assert any(e.get("action") == "create_universe" for e in entries)


def test_ensure_home_materializes_pending_reserved_id(data_dir):
    # A racing worker reserved the home id (atomic claim) but has not finished
    # creating the dir yet. ensure_founder_home must ADOPT the reserved id and
    # materialize it — never mint a second universe under a fresh id.
    from tinyassets.api.first_contact import ensure_founder_home
    from tinyassets.daemon_server import claim_founder_home
    from tinyassets.ids import new_universe_id

    _login("founder-1")
    reserved = new_universe_id()
    assert claim_founder_home(data_dir, "founder-1", reserved) == reserved
    assert not (data_dir / reserved).is_dir()          # reserved, not yet on disk
    got = ensure_founder_home(data_dir, "founder-1")
    assert got == reserved
    assert (data_dir / reserved / "soul.md").is_file()
    assert [p.name for p in _serial_dirs(data_dir)] == [reserved]


def test_ensure_home_returns_existing_no_double_birth(data_dir):
    from tinyassets.api.first_contact import ensure_founder_home

    _login("founder-1")
    a_home = ensure_founder_home(data_dir, "founder-1")
    b_home = ensure_founder_home(data_dir, "founder-1")   # a racer / a retry
    assert is_universe_serial(a_home)
    assert b_home == a_home
    assert len(_serial_dirs(data_dir)) == 1


def test_concurrent_first_contact_births_single_home(data_dir):
    # Real thread race: N first-contact home resolutions fire at once on
    # a FRESH data dir. Must yield exactly one home with zero errors — this guards
    # both the atomic home claim AND the serialized schema/migration init (a naive
    # version intermittently raised `duplicate column name` / `database is locked`
    # from concurrent initialize_author_server; Codex 2026-07-15 finding).
    import threading

    from tinyassets.api.first_contact import ensure_founder_home
    from tinyassets.daemon_server import get_founder_home

    ident = Identity(
        user_id="founder-race", username="founder-race",
        capabilities=["read", "write", "costly", "submit_request", "list"],
    )
    provider = _StaticAuthProvider(ident)
    set_provider(provider)

    n = 6
    barrier = threading.Barrier(n)
    results: list[str] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker() -> None:
        # Each thread starts with a fresh contextvar context — authenticate it so
        # current_identity() resolves to the founder inside creation.
        set_provider(provider)
        auth_middleware("ok")
        try:
            barrier.wait(timeout=15)          # release all threads together
            out = ensure_founder_home(data_dir, "founder-race")
            with lock:
                results.append(out)
        except Exception as exc:              # capture the race, don't swallow it
            with lock:
                errors.append(repr(exc))

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []                        # no duplicate-column / db-locked race
    home = get_founder_home(data_dir, "founder-race")
    assert is_universe_serial(home)
    assert len(_serial_dirs(data_dir)) == 1    # exactly ONE universe, never two
    assert set(results) == {home}
    # Exactly ONE create_universe ledger row — materialization is serialized, so
    # racing workers never double-create under the shared reserved id.
    ledger = json.loads((data_dir / home / "ledger.json").read_text(encoding="utf-8"))
    assert len([e for e in ledger if e.get("action") == "create_universe"]) == 1


def test_first_contact_birth_failure_is_graceful(data_dir, monkeypatch):
    # If creation fails after mkdir, conversation entry must not return a broken
    # home. The partial dir is rolled back and the retained binding self-heals.
    from tinyassets.api import universe as universe_api
    from tinyassets.api.first_contact import ensure_founder_home
    from tinyassets.daemon_server import get_founder_home

    real_seed = universe_api.seed_okf_bundle

    def _boom(*a, **k):
        raise OSError("seed failed mid-bundle")

    monkeypatch.setattr(universe_api, "seed_okf_bundle", _boom)

    _login("founder-1")
    assert ensure_founder_home(data_dir, "founder-1") == ""
    assert _serial_dirs(data_dir) == []                         # partial dir rolled back
    # No COMPLETE home exists even if a home id was reserved (self-heals on retry).
    bound = get_founder_home(data_dir, "founder-1")
    if bound:
        assert not (data_dir / bound / "soul.md").is_file()

    # Recovery: restore only the seed; the next conversation entry materializes
    # the home under the retained base path.
    monkeypatch.setattr(universe_api, "seed_okf_bundle", real_seed)
    healed_uid = ensure_founder_home(data_dir, "founder-1")
    assert (data_dir / healed_uid / "soul.md").is_file()


def test_forged_home_binding_cannot_escape_data_root(data_dir, tmp_path, monkeypatch):
    import tinyassets.daemon_server as daemon_server
    from tinyassets.api.first_contact import ensure_founder_home

    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("do not delete", encoding="utf-8")
    root_sentinel = data_dir / "keep.txt"
    root_sentinel.write_text("do not delete", encoding="utf-8")

    _login("founder-1")
    monkeypatch.setattr(daemon_server, "get_founder_home", lambda *_: "")
    monkeypatch.setattr(
        daemon_server,
        "claim_founder_home",
        lambda *_: "../outside",
    )

    assert ensure_founder_home(data_dir, "founder-1") == ""
    assert sentinel.read_text(encoding="utf-8") == "do not delete"

    monkeypatch.setattr(daemon_server, "claim_founder_home", lambda *_: ".")
    assert ensure_founder_home(data_dir, "founder-1") == ""
    assert root_sentinel.read_text(encoding="utf-8") == "do not delete"


def test_bound_incomplete_dir_repairs_on_conversation_entry(data_dir):
    # A founder bound to an EXISTING but incomplete home dir (no soul.md — a birth
    # interrupted / not rolled back) must be repaired on conversation entry, not
    # wedged in no_universe_yet forever because create refuses an existing dir
    # (Codex 2026-07-15).
    from tinyassets.api.first_contact import ensure_founder_home
    from tinyassets.daemon_server import get_founder_home, set_founder_home
    from tinyassets.ids import new_universe_id

    _login("founder-1")
    stuck = new_universe_id()
    (data_dir / stuck).mkdir()                  # incomplete: dir exists, no soul.md
    set_founder_home(data_dir, founder_sub="founder-1", universe_id=stuck)

    # First retry repairs it — same bound id, now materialized (not stuck).
    assert ensure_founder_home(data_dir, "founder-1") == stuck
    assert get_founder_home(data_dir, "founder-1") == stuck
    assert (data_dir / stuck / "soul.md").is_file()
    assert len(_serial_dirs(data_dir)) == 1


def test_anonymous_first_contact_births_no_home(data_dir):
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home

    # anonymous (DevAuthProvider from the autouse reset) — must NOT birth a
    # founder home or a generated universe. (get_status may still materialize
    # the legacy `default-universe` fallback dir — that's pre-existing behavior,
    # unrelated to first-contact, which never fires for anonymous.)
    out = json.loads(get_status())
    assert "first_contact" not in out
    assert get_founder_home(data_dir, "anonymous") == ""
    assert _serial_dirs(data_dir) == []


def test_readonly_founder_gets_awaiting_not_birth(data_dir):
    # An authenticated founder whose token lacks create/costly scope must NOT
    # auto-birth a universe via get_status (get_status is not a scope bypass) —
    # they fall back to the compact awaiting card, and no home is bound.
    from tinyassets.api.first_contact import ensure_founder_home
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home

    _login("reader-1", caps=["read", "submit_request", "list"])
    out = json.loads(get_status())
    assert out["first_contact"]["event"] == "no_universe_yet"
    assert "conversation" in out["next_step_for_user"]
    assert ensure_founder_home(data_dir, "reader-1") == ""
    assert get_founder_home(data_dir, "reader-1") == ""
    assert _serial_dirs(data_dir) == []


def test_two_founders_get_distinct_homes(data_dir):
    # Each founder's first contact auto-births their OWN home; the homes and
    # their ACL/ownership are distinct.
    from tinyassets.api.first_contact import ensure_founder_home
    from tinyassets.daemon_server import get_founder_home

    _login("founder-A")
    home_a = ensure_founder_home(data_dir, "founder-A")
    _login("founder-B")
    home_b = ensure_founder_home(data_dir, "founder-B")

    assert home_a != home_b
    assert get_founder_home(data_dir, "founder-A") == home_a
    assert get_founder_home(data_dir, "founder-B") == home_b
    assert len(_serial_dirs(data_dir)) == 2


def test_founder_auto_birth_does_not_write_active_universe_marker(data_dir):
    # universe-creation spec "First MCP contact": a founder's home birth records
    # their `founder_home` binding but must NOT clobber the host-global
    # `.active_universe` marker (that would leak across founders).
    from tinyassets.api.first_contact import ensure_founder_home

    _login("founder-A")
    ensure_founder_home(data_dir, "founder-A")
    assert not (data_dir / ".active_universe").exists()


def test_read_graph_status_stays_pure_no_birth(data_dir):
    # read_graph target=status is the canonical read-only handle: an authenticated
    # founder with no home reading through it gets the awaiting card and NOTHING
    # is created. The dedicated get_status handle is equally pure; conversation
    # entry owns provisioning.
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.universe_server import read_graph

    _login("founder-1")
    out = json.loads(read_graph(target="status"))
    assert out["first_contact"]["event"] == "no_universe_yet"   # pure: no birth
    assert get_founder_home(data_dir, "founder-1") == ""
    assert _serial_dirs(data_dir) == []
    # The dedicated get_status handle is also pure.
    from tinyassets.api.status import get_status

    status = json.loads(get_status())
    assert status["first_contact"]["event"] == "no_universe_yet"
    assert get_founder_home(data_dir, "founder-1") == ""


def test_no_card_for_anonymous_or_explicit_id(data_dir):
    from tinyassets.api.status import get_status

    # anonymous: legacy default resolution, no card
    out = json.loads(get_status())
    assert "first_contact" not in out
    # explicit universe_id: normal read of that universe, no auto-birth, no card
    _login("founder-1")
    out = json.loads(get_status(universe_id="default-universe"))
    assert "first_contact" not in out


def test_explicit_create_is_ledgered(data_dir, monkeypatch):
    # An explicit create (additional universe) still goes through the ledgered
    # MCP dispatch.
    _login("founder-1")
    uid = _create_via_action(data_dir, monkeypatch)
    ledger = data_dir / uid / "ledger.json"
    assert ledger.is_file()
    entries = json.loads(ledger.read_text(encoding="utf-8"))
    assert any(e.get("action") == "create_universe" for e in entries)


def test_additional_explicit_create_does_not_reassign_home(data_dir, monkeypatch):
    # After the auto-birthed home exists, an EXPLICIT create makes an additional
    # universe but must NOT reassign the founder's home binding.
    from tinyassets.api.first_contact import ensure_founder_home
    from tinyassets.daemon_server import get_founder_home

    _login("founder-1")
    home = ensure_founder_home(data_dir, "founder-1")
    extra = _create_via_action(data_dir, monkeypatch)
    assert extra != home
    assert get_founder_home(data_dir, "founder-1") == home    # unchanged
    assert len(_serial_dirs(data_dir)) == 2


def test_stale_founder_home_rematerializes_same_id_on_conversation_entry(data_dir):
    # If the bound home dir is removed, conversation entry re-materializes a
    # living home under the SAME bound id (stable home identity; race-safe — the
    # atomic claim keeps the existing binding rather than minting a competing id).
    import shutil

    from tinyassets.api.first_contact import ensure_founder_home
    from tinyassets.daemon_server import get_founder_home

    _login("founder-1")
    home1 = ensure_founder_home(data_dir, "founder-1")
    shutil.rmtree(data_dir / home1)  # binding is now stale (dir gone)

    home2 = ensure_founder_home(data_dir, "founder-1")
    assert home2 == home1                       # same id, freshly re-materialized
    assert (data_dir / home2 / "soul.md").is_file()
    assert get_founder_home(data_dir, "founder-1") == home2
    assert len(_serial_dirs(data_dir)) == 1


def test_omitted_universe_never_leaks_another_founders_home(data_dir, monkeypatch):
    # Codex 2026-07-02 adapt: `universe action=inspect` (and friends) must not
    # fall through to another founder's serial home on an omitted-scope read.
    from tinyassets.api import universe as universe_api

    monkeypatch.setattr(universe_api, "_base_path", lambda: data_dir)
    _login("founder-A")
    home_a = _create_via_action(data_dir, monkeypatch)
    assert is_universe_serial(home_a)

    _login("reader-B", caps=["read", "submit_request", "list"])
    out = json.loads(universe_api._universe_impl(action="inspect"))
    assert out.get("universe_id") != home_a  # never another founder's home


def test_omitted_universe_routes_founder_to_their_home(data_dir, monkeypatch):
    from tinyassets.api import universe as universe_api
    from tinyassets.daemon_server import get_founder_home

    monkeypatch.setattr(universe_api, "_base_path", lambda: data_dir)
    _login("founder-A")
    home_a = _create_via_action(data_dir, monkeypatch)
    assert get_founder_home(data_dir, "founder-A") == home_a

    out = json.loads(universe_api._universe_impl(action="inspect"))
    assert out.get("universe_id") == home_a


def test_authenticated_switch_universe_does_not_write_marker(data_dir):
    from tinyassets.api.universe import (
        _action_create_universe,
        _action_switch_universe,
    )

    _login("founder-A")
    uid = json.loads(_action_create_universe())["universe_id"]

    out = json.loads(_action_switch_universe(universe_id=uid))
    assert out["status"] == "selected"
    assert out.get("scope") == "request"
    assert not (data_dir / ".active_universe").exists()


def test_readonly_founder_omitted_scope_does_not_leak_other_home(data_dir, monkeypatch):
    # Cross-founder leak guard at the resolver: founder A has a home; founder B
    # (authenticated, read-only, no home) resolves with no universe_id and must
    # NOT be routed to A's serial home. The resolver stays pure (needs_birth); the
    # read-only founder is denied auto-birth at the get_status scope gate.
    from tinyassets.api.status import _resolve_entry_universe

    _login("founder-A")
    home_a = _create_via_action(data_dir, monkeypatch)
    assert is_universe_serial(home_a)

    _login("reader-B", caps=["read", "submit_request", "list"])
    resolved_b, needs_birth = _resolve_entry_universe("")
    assert needs_birth is True                 # no home -> get_status handles it
    assert resolved_b != home_a                # no cross-founder leak
    assert not is_universe_serial(resolved_b)  # never another founder's home


def test_write_graph_target_universe_creates_and_binds(data_dir, monkeypatch):
    # The canonical connector surface has no `universe` tool — explicit birth
    # routes through write_graph target=universe.
    from tinyassets.api import universe as universe_api
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.universe_server import write_graph

    monkeypatch.setattr(universe_api, "_base_path", lambda: data_dir)
    _login("founder-1")
    out = json.loads(write_graph(target="universe"))
    assert out.get("error") is None, out
    assert out["status"] == "born"
    assert "persona" in out and "first_run_checklist" not in out
    assert out["persona"]["self_model"]["open_questions"]
    uid = out["universe_id"]
    assert is_universe_serial(uid)
    assert get_founder_home(data_dir, "founder-1") == uid
    assert (data_dir / uid / "soul.md").is_file()


def test_write_graph_unknown_target_lists_universe(data_dir):
    from tinyassets.universe_server import write_graph

    out = json.loads(write_graph(target="nope"))
    assert out["error"] == "unknown_target"
    assert "universe" in out["allowed_targets"]
