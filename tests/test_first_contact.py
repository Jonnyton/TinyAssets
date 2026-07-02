"""First-contact, OPT-IN BIRTH (host decision 2026-07-02): a status read NEVER
creates anything — an authenticated founder with no home gets the compact
awaiting-creation card, and the universe is created when the founder asks to
meet it (universe action=create_universe; the request is the consent).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity

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


def _create_via_action(base, monkeypatch):
    """Create the founder's universe the opt-in way (ledgered MCP route)."""
    from tinyassets.api import universe as universe_api

    monkeypatch.setattr(universe_api, "_base_path", lambda: base)
    out = json.loads(universe_api._universe_impl(action="create_universe"))
    assert out.get("error") is None, out
    return out["universe_id"]


def test_founder_home_set_get_roundtrip(data_dir):
    from tinyassets.daemon_server import get_founder_home, set_founder_home

    assert get_founder_home(data_dir, "founder-1") == ""
    set_founder_home(data_dir, founder_sub="founder-1", universe_id="u-01x")
    assert get_founder_home(data_dir, "founder-1") == "u-01x"
    # anonymous / empty never has a home
    assert get_founder_home(data_dir, "anonymous") == ""
    assert get_founder_home(data_dir, "") == ""


def test_first_contact_read_is_pure_and_awaits_optin(data_dir, monkeypatch):
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.ids import is_universe_serial

    _login("founder-1")
    out = json.loads(get_status())

    # PURE READ: no universe created, no home bound, nothing on disk.
    assert out["first_contact"]["event"] == "no_universe_yet"
    assert "TinyAssets" in out["about"]
    assert "personify my universe" in out["next_step_for_user"]
    assert get_founder_home(data_dir, "founder-1") == ""
    assert _universe_dirs(data_dir) == []

    # OPT-IN: the founder asks -> create binds home + seeds the brain.
    uid = _create_via_action(data_dir, monkeypatch)
    assert is_universe_serial(uid)
    assert get_founder_home(data_dir, "founder-1") == uid
    assert (data_dir / uid / "soul.md").is_file()
    # And the next status read is the full snapshot for their home.
    after = json.loads(get_status())
    assert "first_contact" not in after
    assert after["universe_id"] == uid
    assert "persona" in after


def test_status_reads_never_create(data_dir):
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home

    _login("founder-1")
    json.loads(get_status())
    json.loads(get_status())
    assert get_founder_home(data_dir, "founder-1") == ""
    assert _universe_dirs(data_dir) == []      # reads are reads


def test_anonymous_first_contact_births_no_home(data_dir):
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.ids import is_universe_serial

    # anonymous (DevAuthProvider from the autouse reset) — must NOT birth a
    # founder home or a generated universe. (get_status may still materialize
    # the legacy `default-universe` fallback dir — that's pre-existing behavior,
    # unrelated to first-contact, which never fires for anonymous.)
    json.loads(get_status())
    assert get_founder_home(data_dir, "anonymous") == ""
    serial = [p for p in _universe_dirs(data_dir) if is_universe_serial(p.name)]
    assert serial == []


def test_readonly_founder_does_not_birth_universe(data_dir):
    # An authenticated founder whose token lacks create/costly scope must NOT
    # birth a universe via get_status (get_status is not a scope bypass).
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.ids import is_universe_serial

    _login("reader-1", caps=["read", "submit_request", "list"])
    json.loads(get_status())
    assert get_founder_home(data_dir, "reader-1") == ""
    # No generated (u-+ULID) universe was birthed. (get_status may still
    # materialize the legacy `default-universe` fallback dir — pre-existing.)
    assert [p for p in _universe_dirs(data_dir) if is_universe_serial(p.name)] == []


def test_two_founders_get_distinct_homes(data_dir, monkeypatch):
    from tinyassets.daemon_server import get_founder_home

    _login("founder-A")
    home_a = _create_via_action(data_dir, monkeypatch)
    _login("founder-B")
    home_b = _create_via_action(data_dir, monkeypatch)

    assert home_a != home_b
    assert get_founder_home(data_dir, "founder-A") == home_a
    assert get_founder_home(data_dir, "founder-B") == home_b
    assert len(_universe_dirs(data_dir)) == 2


def test_founder_create_does_not_write_active_universe_marker(data_dir, monkeypatch):
    # universe-creation spec "First MCP contact": an authenticated founder's
    # create records their `founder_home` binding but must NOT clobber the
    # host-global `.active_universe` marker.
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.ids import is_universe_serial

    _login("founder-A")
    home_a = _create_via_action(data_dir, monkeypatch)
    assert is_universe_serial(home_a)
    assert get_founder_home(data_dir, "founder-A") == home_a
    assert not (data_dir / ".active_universe").exists()


def test_awaiting_card_until_optin_create(data_dir, monkeypatch):
    # Convergence: any opener -> the model calls get_status -> the compact
    # awaiting-creation card (about + CTA). After the opt-in create, status
    # reads return the full snapshot with no first_contact block.
    from tinyassets.api.status import get_status

    _login("founder-1")
    card = json.loads(get_status())
    assert card["first_contact"]["event"] == "no_universe_yet"
    assert set(card) == {"first_contact", "about", "next_step_for_user", "schema_version"}
    assert "personify my universe" in card["next_step_for_user"]
    # Still awaiting on a second read (reads never create).
    again = json.loads(get_status())
    assert again["first_contact"]["event"] == "no_universe_yet"

    _create_via_action(data_dir, monkeypatch)
    full = json.loads(get_status())
    assert "first_contact" not in full
    assert "persona" in full


def test_no_awaiting_card_for_anonymous_or_explicit_id(data_dir):
    from tinyassets.api.status import get_status

    # anonymous: legacy default resolution, no card
    out = json.loads(get_status())
    assert "first_contact" not in out
    # explicit universe_id: normal read, no card
    _login("founder-1")
    out = json.loads(get_status(universe_id="default-universe"))
    assert "first_contact" not in out


def test_omitted_universe_never_leaks_another_founders_home(data_dir, monkeypatch):
    # Codex 2026-07-02 adapt: get_status was fixed but `universe action=inspect`
    # (and friends) still fell through the first-dir default and returned
    # founder A's serial home to founder B. The shared resolver closes it.
    from tinyassets.api import universe as universe_api
    from tinyassets.ids import is_universe_serial

    monkeypatch.setattr(universe_api, "_base_path", lambda: data_dir)
    _login("founder-A")
    home_a = _create_via_action(data_dir, monkeypatch)
    assert is_universe_serial(home_a)

    _login("reader-B", caps=["read", "submit_request", "list"])
    out = json.loads(universe_api._universe_impl(action="inspect"))
    assert out.get("universe_id") != home_a  # never another founder's home


def test_omitted_universe_routes_founder_to_their_home(data_dir, monkeypatch):
    # UX win of the shared resolver: a founder with a home omits universe_id
    # and lands on THEIR universe across actions, not a global default.
    from tinyassets.api import universe as universe_api
    from tinyassets.daemon_server import get_founder_home

    monkeypatch.setattr(universe_api, "_base_path", lambda: data_dir)
    _login("founder-A")
    home_a = _create_via_action(data_dir, monkeypatch)
    assert get_founder_home(data_dir, "founder-A") == home_a

    out = json.loads(universe_api._universe_impl(action="inspect"))
    assert out.get("universe_id") == home_a


def test_optin_create_is_ledgered(data_dir, monkeypatch):
    # The opt-in create goes through the ledgered MCP dispatch.
    uid = None
    _login("founder-1")
    uid = _create_via_action(data_dir, monkeypatch)
    ledger = data_dir / uid / "ledger.json"
    assert ledger.is_file()
    entries = json.loads(ledger.read_text(encoding="utf-8"))
    assert any(e.get("action") == "create_universe" for e in entries)


def test_stale_founder_home_rebinds_on_next_create(data_dir, monkeypatch):
    # If the bound home dir is removed, status shows the awaiting card again
    # and the next opt-in create rebinds to the fresh universe.
    import shutil

    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.ids import is_universe_serial

    _login("founder-1")
    home1 = _create_via_action(data_dir, monkeypatch)
    shutil.rmtree(data_dir / home1)  # binding is now stale

    card = json.loads(get_status())
    assert card["first_contact"]["event"] == "no_universe_yet"

    home2 = _create_via_action(data_dir, monkeypatch)
    assert home2 != home1 and is_universe_serial(home2)
    assert get_founder_home(data_dir, "founder-1") == home2


def test_authenticated_switch_universe_does_not_write_marker(data_dir):
    # universe-creation spec "Explicit universe selection is not global": an
    # authenticated founder's switch_universe applies to their request scope and
    # must NOT clobber the host-global `.active_universe` marker.
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
    # Cross-founder leak guard: founder A creates their home (opt-in); founder
    # B (authenticated, read-only, no home) reads with no universe_id and must
    # NOT be routed to A's serial home.
    from tinyassets.api.status import _resolve_entry_universe
    from tinyassets.ids import is_universe_serial

    _login("founder-A")
    home_a = _create_via_action(data_dir, monkeypatch)
    assert is_universe_serial(home_a)

    _login("reader-B", caps=["read", "submit_request", "list"])
    resolved_b, awaiting = _resolve_entry_universe("")
    assert awaiting is True                   # no home -> awaiting card
    assert resolved_b != home_a               # no cross-founder leak
    assert not is_universe_serial(resolved_b)  # never another founder's home


def test_write_graph_target_universe_creates_and_binds(data_dir, monkeypatch):
    # The canonical connector surface has no `universe` tool — opt-in birth
    # routes through write_graph target=universe (round-12 finding: the model
    # literally could not create a universe on the public handle set).
    from tinyassets.api import universe as universe_api
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.ids import is_universe_serial
    from tinyassets.universe_server import write_graph

    monkeypatch.setattr(universe_api, "_base_path", lambda: data_dir)
    _login("founder-1")
    out = json.loads(write_graph(target="universe"))
    assert out.get("error") is None, out
    # Birth card, not the ops-shaped create payload (round-14: the model
    # narrates what it's handed — checklist fields produce third-person
    # workflow talk instead of the newborn's voice).
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
