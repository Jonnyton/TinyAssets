"""First-contact (D10): an authenticated founder's first get_status births their
home universe; anonymous callers never create; the home binding is idempotent.
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


def test_founder_home_set_get_roundtrip(data_dir):
    from tinyassets.daemon_server import get_founder_home, set_founder_home

    assert get_founder_home(data_dir, "founder-1") == ""
    set_founder_home(data_dir, founder_sub="founder-1", universe_id="u-01x")
    assert get_founder_home(data_dir, "founder-1") == "u-01x"
    # anonymous / empty never has a home
    assert get_founder_home(data_dir, "anonymous") == ""
    assert get_founder_home(data_dir, "") == ""


def test_first_contact_births_and_binds_home(data_dir):
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.ids import is_universe_serial

    _login("founder-1")
    out = json.loads(get_status())

    home = get_founder_home(data_dir, "founder-1")
    assert is_universe_serial(home)          # generated u-+ULID id
    assert (data_dir / home).is_dir()        # brain seeded on disk
    assert (data_dir / home / "soul.md").is_file()
    assert "persona" in out                  # speaks as the (blank) universe


def test_first_contact_is_idempotent(data_dir):
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home

    _login("founder-1")
    json.loads(get_status())
    home1 = get_founder_home(data_dir, "founder-1")
    json.loads(get_status())
    home2 = get_founder_home(data_dir, "founder-1")

    assert home1 == home2                     # same home, no re-birth
    assert len(_universe_dirs(data_dir)) == 1  # exactly one universe


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


def test_two_founders_get_distinct_homes(data_dir):
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home

    _login("founder-A")
    json.loads(get_status())
    _login("founder-B")
    json.loads(get_status())

    home_a = get_founder_home(data_dir, "founder-A")
    home_b = get_founder_home(data_dir, "founder-B")
    assert home_a and home_b and home_a != home_b
    assert len(_universe_dirs(data_dir)) == 2


def test_founder_create_does_not_write_active_universe_marker(data_dir):
    # universe-creation spec "First MCP contact": an authenticated founder's
    # create records their `founder_home` binding but must NOT clobber the
    # host-global `.active_universe` marker.
    from tinyassets.api.status import _resolve_entry_universe
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.ids import is_universe_serial

    _login("founder-A")
    _resolve_entry_universe("")
    home_a = get_founder_home(data_dir, "founder-A")
    assert is_universe_serial(home_a)
    assert not (data_dir / ".active_universe").exists()


def test_first_contact_event_surfaces_in_get_status_once(data_dir):
    # Convergence (host directive 2026-07-02): whatever the user's opening
    # words, the FIRST authenticated get_status carries a `first_contact`
    # data event (the assistant offers the meeting off this fact — no magic
    # words). Subsequent calls do NOT re-announce the birth.
    from tinyassets.api.status import get_status

    _login("founder-1")
    first = json.loads(get_status())
    assert first["first_contact"]["created"] is True
    assert first["first_contact"]["universe_id"] == first["universe_id"]
    assert "bound to the founder" in first["first_contact"]["note"]
    # DATA ONLY: no reply-shaping in the payload (round-5 dogfood — a
    # suggested_response script tripped the host's injection detector; the
    # reply shape lives in server instructions instead).
    assert "suggested_response" not in first["first_contact"]
    assert set(first["first_contact"]) == {
        "event", "created", "universe_id", "note",
    }
    # Welcome card: one-sentence pitch + a user-facing CTA string (product
    # copy the user can say — reliably relayed, unlike model-performed asks).
    assert "TinyAssets" in first["about"]
    assert 'say: "personify my universe"' in first["next_step_for_user"]
    # Round 6: the BIRTH call returns a MINIMAL payload — the model narrates
    # whatever it is handed, so at the birth moment it is handed only the
    # birth + persona. Full snapshot is one call away.
    assert set(first) == {
        "first_contact", "about", "next_step_for_user", "persona", "universe_id",
        "schema_version", "status_detail",
    }
    assert "queue_state" not in first and "storage" not in first
    # The event is the birth, not the session: second call has no block.
    second = json.loads(get_status())
    assert "first_contact" not in second


def test_no_first_contact_event_for_anonymous_or_existing(data_dir):
    from tinyassets.api.status import get_status

    # anonymous: no birth, no event
    out = json.loads(get_status())
    assert "first_contact" not in out
    # explicit universe_id: no event either
    _login("founder-1")
    json.loads(get_status())  # birth
    out = json.loads(get_status(universe_id="default-universe"))
    assert "first_contact" not in out


def test_omitted_universe_never_leaks_another_founders_home(data_dir, monkeypatch):
    # Codex 2026-07-02 adapt: get_status was fixed but `universe action=inspect`
    # (and friends) still fell through the first-dir default and returned
    # founder A's serial home to founder B. The shared resolver closes it.
    from tinyassets.api import universe as universe_api
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.ids import is_universe_serial

    monkeypatch.setattr(universe_api, "_base_path", lambda: data_dir)
    _login("founder-A")
    json.loads(get_status())  # births A's home
    home_a = get_founder_home(data_dir, "founder-A")
    assert is_universe_serial(home_a)

    _login("reader-B", caps=["read", "submit_request", "list"])
    out = json.loads(universe_api._universe_impl(action="inspect"))
    assert out.get("universe_id") != home_a  # never another founder's home


def test_omitted_universe_routes_founder_to_their_home(data_dir, monkeypatch):
    # UX win of the shared resolver: a founder with a home omits universe_id
    # and lands on THEIR universe across actions, not a global default.
    from tinyassets.api import universe as universe_api
    from tinyassets.api.status import get_status
    from tinyassets.daemon_server import get_founder_home

    monkeypatch.setattr(universe_api, "_base_path", lambda: data_dir)
    _login("founder-A")
    json.loads(get_status())  # births A's home
    home_a = get_founder_home(data_dir, "founder-A")

    out = json.loads(universe_api._universe_impl(action="inspect"))
    assert out.get("universe_id") == home_a


def test_first_contact_create_is_ledgered(data_dir):
    # First-contact create must go through the ledgered dispatch — the durable
    # creation lands in the new universe's ledger.json (Codex adapt: direct
    # _action_create_universe() call skipped the ledger contract).
    from tinyassets.api.status import _resolve_entry_universe
    from tinyassets.daemon_server import get_founder_home

    _login("founder-1")
    _resolve_entry_universe("")
    home = get_founder_home(data_dir, "founder-1")

    ledger = data_dir / home / "ledger.json"
    assert ledger.is_file()
    entries = json.loads(ledger.read_text(encoding="utf-8"))
    assert any(e.get("action") == "create_universe" for e in entries)


def test_stale_founder_home_rebinds_instead_of_looping(data_dir):
    # If the bound home dir is removed, the next contact must rebind to a single
    # new home — not spawn a fresh serial dir on every get_status (Codex adapt:
    # _action_create_universe won't rebind over a stale founder_home row).
    import shutil

    from tinyassets.api.status import _resolve_entry_universe
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.ids import is_universe_serial

    _login("founder-1")
    _resolve_entry_universe("")
    home1 = get_founder_home(data_dir, "founder-1")
    shutil.rmtree(data_dir / home1)  # binding is now stale

    resolved2, _ = _resolve_entry_universe("")
    home2 = get_founder_home(data_dir, "founder-1")
    assert home2 == resolved2 and home2 != home1 and is_universe_serial(home2)

    # A third call returns the SAME rebound home — no further serial dirs.
    assert _resolve_entry_universe("")[0] == home2
    serial = [p for p in _universe_dirs(data_dir) if is_universe_serial(p.name)]
    assert len(serial) == 1


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


def test_readonly_founder_omitted_scope_does_not_leak_other_home(data_dir):
    # Codex-reproduced cross-founder leak: founder A first contact births home
    # u-A; founder B (authenticated, read-only, no home) then reads with no
    # universe_id and must NOT be routed to A's serial home (previously leaked
    # via the `.active_universe` marker A's create had clobbered).
    from tinyassets.api.status import _resolve_entry_universe
    from tinyassets.daemon_server import get_founder_home
    from tinyassets.ids import is_universe_serial

    _login("founder-A")
    _resolve_entry_universe("")
    home_a = get_founder_home(data_dir, "founder-A")
    assert is_universe_serial(home_a)

    _login("reader-B", caps=["read", "submit_request", "list"])
    resolved_b, _ = _resolve_entry_universe("")
    assert resolved_b != home_a               # no cross-founder leak
    assert not is_universe_serial(resolved_b)  # never another founder's serial home
