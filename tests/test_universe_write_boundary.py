"""Executable acceptance gate for the founder/universe write boundary (D0a).

Encodes the invariant from the founder/universe identity design — see
``docs/design-notes/2026-06-26-founder-and-universe-identity.md`` (decision
D0a) and ``openspec/changes/universe-creation`` requirement *"MCP writes are
scoped to the founder's own universe"*:

    A universe created through ``universe action=create_universe`` is OWNED by
    the founder who created it. Another authenticated founder — even one
    holding the ``tinyassets.universe.write`` scope — MUST NOT be able to
    write that universe's brain.

Status (Claude, 2026-06-30 — ACL-synthesis slice): the invariant is now
ENFORCED. ``_action_create_universe`` grants the authenticated founder an
``admin`` ACL row on create (D0a founder-grant-on-create), and the single ACL
path in ``tinyassets.api.permissions`` denies writes to any actor without a
``write``/``admin`` grant. The two cross-founder gates below therefore now
PASS as permanent regression guards; their prior ``xfail(strict=True)`` markers
were removed once D0a landed (as their design note prescribed — an xpass under
strict was the signal to promote them to hard guards).

The anonymous guard is satisfied by the scope gate, which blocks all anonymous
writes when auth is required; it has always been a plain green guard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tinyassets.api.universe as us
from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity
from tinyassets.daemon_server import universe_access_permission


class _StaticAuthProvider(AuthProvider):
    """Auth-required provider that resolves the bearer token ``"ok"`` to a
    fixed identity, mirroring tests/test_universe_server_isolation.py."""

    def __init__(self, identity: Identity | None) -> None:
        self.identity = identity

    def resolve_token(self, token: str) -> Identity | None:
        return self.identity if token == "ok" else None

    def is_auth_required(self) -> bool:
        return True

    def register_client(self, metadata: dict) -> dict:
        return {"client_id": "test-client", **metadata}

    def create_authorization(
        self,
        client_id: str,
        redirect_uri: str,
        scope: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
    ) -> str:
        return "test-code"

    def exchange_code(
        self,
        code: str,
        client_id: str,
        redirect_uri: str,
        code_verifier: str,
    ) -> dict | None:
        return None


# Full founder scope set: read + write + admin + costly (create_universe is a
# costly action, so the creating founder needs the costly scope).
_FOUNDER_SCOPES = [
    "tinyassets.universe.read",
    "tinyassets.universe.write",
    "tinyassets.universe.admin",
    "tinyassets.universe.costly",
]


@pytest.fixture
def universe_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    return base


@pytest.fixture(autouse=True)
def _reset_auth_provider() -> None:
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


def _authenticate(user_id: str, scopes: list[str]) -> None:
    identity = Identity(
        user_id=user_id,
        username=user_id,
        capabilities=list(scopes),
    )
    set_provider(_StaticAuthProvider(identity))
    auth_middleware("ok")


def _authenticate_anonymous() -> None:
    """Auth REQUIRED, but no valid token → identity resolves to ANONYMOUS."""
    set_provider(_StaticAuthProvider(None))
    auth_middleware(None)


def _create_universe_as(founder: str, uid: str, text: str = "A founder seed.") -> dict:
    _authenticate(founder, _FOUNDER_SCOPES)
    return json.loads(us._universe_impl(
        action="create_universe",
        universe_id=uid,
        text=text,
    ))


class TestFounderWriteBoundary:
    """A founder owns the universe they create; other founders cannot write it."""

    def test_created_universe_not_writable_by_other_founder(self, universe_base):
        created = _create_universe_as("alice", "u-acceptance-alice")
        assert created.get("status") == "created", created
        target = created["universe_id"]

        # A *different* authenticated founder, holding the write scope but with
        # no grant on alice's universe, must be denied.
        _authenticate("mallory", ["tinyassets.universe.write"])
        out = json.loads(us._universe_impl(
            action="set_premise",
            universe_id=target,
            text="Hostile cross-founder overwrite.",
        ))

        assert out.get("error") == "universe_access_denied", out
        assert out.get("required_permission") == "write"

    def test_create_universe_grants_founder_owner_acl(self, universe_base):
        created = _create_universe_as("alice", "u-acceptance-owner")
        assert created.get("status") == "created", created
        target = created["universe_id"]

        # The founder must hold an owner-grade (write/admin) ACL on their own
        # created universe — the mechanism that makes the write boundary real.
        # On a zero-ACL universe this returns the public "read" convention.
        perm = universe_access_permission(
            universe_base,
            universe_id=target,
            actor_id="alice",
        )
        assert perm in {"write", "admin"}, (
            f"founder 'alice' has permission {perm!r} on her own created "
            "universe; expected an owner (write/admin) grant"
        )

    def test_created_universe_rejects_anonymous_write(self, universe_base):
        # Green guard: already enforced on origin/main in auth-required mode —
        # the scope gate blocks every anonymous write regardless of ownership.
        created = _create_universe_as("alice", "u-acceptance-anon")
        assert created.get("status") == "created", created
        target = created["universe_id"]

        _authenticate_anonymous()
        out = json.loads(us._universe_impl(
            action="set_premise",
            universe_id=target,
            text="Anonymous overwrite.",
        ))

        assert "error" in out, out
        # Denied — never an accepted write.
        assert out.get("status") != "updated", out


class TestPrivateCanonScoping:
    """Finding C (2026-07-02 live test): a founder's ``write_page`` content is
    private canon and must land in THEIR universe wiki, not the shared global
    commons; issue filings (``kind=``) stay on the commons."""

    def test_page_write_omitted_id_lands_in_founder_home_not_commons(
        self, universe_base
    ):
        from tinyassets.universe_server import write_page

        created = _create_universe_as("carol", "u-canon-carol")
        assert created.get("status") == "created", created
        uid = created["universe_id"]
        # carol stays the founder (home = her universe) + gains wiki write scope.
        _authenticate(
            "carol",
            _FOUNDER_SCOPES + ["tinyassets.wiki.write", "tinyassets.wiki.read"],
        )
        out = json.loads(write_page(
            category="lore",
            filename="the-resonance",
            content="The Resonance links cells and bonds across Aurelith.",
            dry_run=False,
        ))
        assert "error" not in out, out
        universe_hits = list(
            (universe_base / uid / "wiki").rglob("the-resonance.md")
        )
        assert universe_hits, f"page not in founder's universe wiki; out={out}"
        commons = universe_base / "wiki"
        commons_hits = (
            list(commons.rglob("the-resonance.md")) if commons.is_dir() else []
        )
        assert not commons_hits, (
            f"private canon leaked to global commons: {commons_hits}"
        )

    def test_issue_filing_stays_on_commons_not_founder_home(self, universe_base):
        from tinyassets.universe_server import write_page

        created = _create_universe_as("dave", "u-commons-dave")
        assert created.get("status") == "created", created
        uid = created["universe_id"]
        _authenticate(
            "dave",
            _FOUNDER_SCOPES + ["tinyassets.wiki.write", "tinyassets.wiki.read"],
        )
        out = json.loads(write_page(
            kind="bug",
            title="Widget crashes on save",
            component="widget",
            severity="major",
            repro="open widget, click save",
            observed="crash",
            expected="saves cleanly",
        ))
        assert "error" not in out, out
        # The bug filing did NOT land in dave's private universe wiki.
        home_bugs_dir = universe_base / uid / "wiki" / "pages" / "bugs"
        home_bugs = (
            list(home_bugs_dir.rglob("*.md")) if home_bugs_dir.is_dir() else []
        )
        assert not home_bugs, (
            f"issue filing leaked into founder's universe: {home_bugs}"
        )

    def test_anonymous_page_write_does_not_resolve_to_a_universe(
        self, universe_base
    ):
        # Anonymous/dev callers keep legacy commons routing — an omitted id is
        # NOT silently resolved to a founder home (there is no authenticated
        # founder to resolve to).
        from tinyassets.universe_server import write_page

        _create_universe_as("erin", "u-anon-guard-erin")
        _authenticate_anonymous()
        write_page(
            category="lore",
            filename="stray-note",
            content="An anonymous stray note.",
            dry_run=False,
        )
        # Either denied by the write gate, or written to the commons — but never
        # into erin's private universe.
        erin_hits = list(
            (universe_base / "u-anon-guard-erin" / "wiki").rglob("stray-note.md")
        )
        assert not erin_hits, f"anonymous write leaked into a founder universe: {erin_hits}"

    def test_authed_founder_without_home_write_denied_by_acl(self, universe_base):
        # Resolution is NOT authorization (Codex gap): a founder with no home and
        # no ACL grant, whose omitted write resolves to the designated public
        # universe, must still be denied by the write gate.
        from tinyassets.universe_server import write_page

        _authenticate(
            "frank",
            _FOUNDER_SCOPES + ["tinyassets.wiki.write", "tinyassets.wiki.read"],
        )
        out = json.loads(write_page(
            category="lore",
            filename="sneaky",
            content="should be denied — frank owns nothing.",
            dry_run=False,
        ))
        assert out.get("status") not in {"drafted", "updated"}, out
