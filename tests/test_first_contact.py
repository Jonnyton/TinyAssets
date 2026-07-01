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
