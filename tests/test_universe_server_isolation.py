"""Tests that universe action responses include `universe_id` for isolation.

Context: Task #15. Claude.ai cross-universe hallucination was enabled by
tool responses that didn't name the universe they came from. When the bot
reads premise, canon, world-state, activity, etc., the response shape now
leads with `universe_id` so downstream reasoning can ground each fact to
its source universe.

Pairs with #47 (on-disk quarantine), #48 (retrieval audit), #51/#49/#53
(live-code hardening). This is the chat-side half of the cross-universe
cluster.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tinyassets.api.universe as us
from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity
from tinyassets.daemon_server import (
    ensure_universe_registered,
    ensure_universe_rules,
    grant_universe_access,
    update_universe_rules,
)


class _StaticAuthProvider(AuthProvider):
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


def _authenticate(user_id: str, scopes: list[str] | None = None) -> None:
    identity = Identity(
        user_id=user_id,
        username=user_id,
        capabilities=scopes or [
            "tinyassets.universe.read",
            "tinyassets.universe.write",
            "tinyassets.universe.admin",
        ],
    )
    set_provider(_StaticAuthProvider(identity))
    auth_middleware("ok")


def _make_universe(base: Path, uid: str) -> Path:
    udir = base / uid
    udir.mkdir(parents=True)
    return udir


def _make_private_universe(base: Path, uid: str) -> Path:
    """Create a universe made *private* the ratified way — via the
    ``public_read`` visibility rule, NOT by seeding an ACL row. In the D0c
    model ownership (ACL grants) and visibility (public_read) are orthogonal:
    an admin grant alone does not hide a universe.
    """
    udir = _make_universe(base, uid)
    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    ensure_universe_rules(base, universe_id=uid)
    update_universe_rules(base, universe_id=uid, updates={"public_read": False})
    return udir


class TestUniverseIdInResponses:
    """Every read response that pulls universe-scoped content must name it."""

    def test_read_premise_includes_universe_id(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "PROGRAM.md").write_text("An alpha premise.", encoding="utf-8")
        out = json.loads(us._action_read_premise(universe_id="alpha"))
        assert out["universe_id"] == "alpha"
        assert out["premise"] == "An alpha premise."

    def test_read_premise_missing_still_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_read_premise(universe_id="alpha"))
        assert out["universe_id"] == "alpha"
        assert out["premise"] is None

    def test_read_output_includes_universe_id(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "output").mkdir()
        (udir / "output" / "note.md").write_text("hello", encoding="utf-8")
        out = json.loads(us._action_read_output(universe_id="alpha", path="note.md"))
        assert out["universe_id"] == "alpha"
        assert out["content"] == "hello"

    def test_list_canon_includes_universe_id(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "canon").mkdir()
        (udir / "canon" / "a.md").write_text("x", encoding="utf-8")
        out = json.loads(us._action_list_canon(universe_id="alpha"))
        assert out["universe_id"] == "alpha"

    def test_list_canon_no_canon_dir_still_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_list_canon(universe_id="alpha"))
        assert out["universe_id"] == "alpha"

    def test_read_canon_includes_universe_id(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "canon").mkdir()
        (udir / "canon" / "a.md").write_text("hello", encoding="utf-8")
        out = json.loads(us._action_read_canon(universe_id="alpha", filename="a.md"))
        assert out["universe_id"] == "alpha"
        assert out["filename"] == "a.md"

    def test_query_world_no_data_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_query_world(universe_id="alpha", query_type="timeline"))
        # timeline has no store; should still echo the universe
        assert out["universe_id"] == "alpha"

    def test_get_activity_includes_universe_id(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "activity.log").write_text("[..] line\n", encoding="utf-8")
        out = json.loads(us._action_get_activity(universe_id="alpha", limit=5))
        assert out["universe_id"] == "alpha"

    def test_get_activity_missing_log_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_get_activity(universe_id="alpha"))
        assert out["universe_id"] == "alpha"

    def test_get_ledger_empty_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_get_ledger(universe_id="alpha"))
        assert out["universe_id"] == "alpha"

    def test_control_daemon_status_includes_universe_id(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_control_daemon(universe_id="alpha", text="status"))
        assert out["universe_id"] == "alpha"

    def test_different_universes_stay_distinct(self, universe_base):
        """Two universes must never cross-contaminate through the response."""
        udir_a = _make_universe(universe_base, "alpha")
        udir_b = _make_universe(universe_base, "beta")
        (udir_a / "PROGRAM.md").write_text("Alpha premise.", encoding="utf-8")
        (udir_b / "PROGRAM.md").write_text("Beta premise.", encoding="utf-8")

        out_a = json.loads(us._action_read_premise(universe_id="alpha"))
        out_b = json.loads(us._action_read_premise(universe_id="beta"))

        assert out_a["universe_id"] == "alpha"
        assert out_a["premise"] == "Alpha premise."
        assert out_b["universe_id"] == "beta"
        assert out_b["premise"] == "Beta premise."

    def test_inspect_includes_universe_id(self, universe_base):
        """Pre-existing behaviour — regression guard."""
        _make_universe(universe_base, "alpha")
        out = json.loads(us._action_inspect_universe(universe_id="alpha"))
        assert out["universe_id"] == "alpha"


class TestUniverseAclEnforcement:
    """The D0c model: VISIBILITY is ``public_read`` (a missing rule = public);
    OWNERSHIP is the ACL grant set. Writes always require an explicit ``write``
    or ``admin`` grant. An admin grant does NOT make a universe private.
    """

    def test_anonymous_cannot_write_public_universe(self, universe_base):
        # Dev/no-auth caller (anonymous). Reads are open on a public universe,
        # but a write must be denied — an authenticated grant is required.
        _make_universe(universe_base, "public")

        out = json.loads(us._universe_impl(
            action="set_premise",
            universe_id="public",
            text="Anonymous write attempt.",
        ))

        assert out["error"] == "universe_access_denied"
        assert out["actor_id"] == "anonymous"
        assert out["required_permission"] == "write"
        assert not (universe_base / "public" / "PROGRAM.md").exists()

    def test_anonymous_can_read_public_universe(self, universe_base):
        _make_universe(universe_base, "public")

        out = json.loads(us._universe_impl(action="inspect", universe_id="public"))

        assert out["universe_id"] == "public"
        assert "error" not in out

    def test_authenticated_founder_cannot_write_public_universe_without_grant(
        self, universe_base,
    ):
        # A universe with no ACL rows returns the public "read" convention for
        # every actor; a write still requires an explicit write/admin grant.
        _make_universe(universe_base, "other")
        _authenticate(
            "alice", ["tinyassets.universe.read", "tinyassets.universe.write"],
        )

        out = json.loads(us._universe_impl(
            action="set_premise",
            universe_id="other",
            text="Cross-universe write attempt.",
        ))

        assert out["error"] == "universe_access_denied"
        assert out["required_permission"] == "write"
        assert out["actor_id"] == "alice"
        assert not (universe_base / "other" / "PROGRAM.md").exists()

    def test_public_universe_read_stays_open_for_authenticated_reader(
        self, universe_base,
    ):
        _make_universe(universe_base, "public")
        _authenticate("alice", ["tinyassets.universe.read"])

        out = json.loads(us._universe_impl(action="inspect", universe_id="public"))

        assert out["universe_id"] == "public"
        assert "error" not in out

    def test_create_universe_grants_creator_admin_write(self, universe_base):
        # D0a: an authenticated founder OWNS the universe they create.
        _authenticate(
            "alice",
            ["tinyassets.universe.costly", "tinyassets.universe.write"],
        )

        created = json.loads(us._universe_impl(
            action="create_universe",
            universe_id="mine",
            text="A seed.",
        ))
        updated = json.loads(us._universe_impl(
            action="set_premise",
            universe_id="mine",
            text="Founder-owned update.",
        ))

        assert created["status"] == "created"
        assert created["founder_id"] == "alice"
        assert updated["status"] == "updated"
        assert (universe_base / "mine" / "PROGRAM.md").read_text(
            encoding="utf-8",
        ) == "Founder-owned update."

    def test_create_universe_denies_other_founder_write(self, universe_base):
        # D0a: a *different* authenticated founder, even holding the write
        # scope, cannot write a universe founded by someone else.
        _authenticate(
            "alice",
            ["tinyassets.universe.costly", "tinyassets.universe.write"],
        )
        created = json.loads(us._universe_impl(
            action="create_universe",
            universe_id="alice-world",
            text="Alice's seed.",
        ))
        assert created["founder_id"] == "alice"

        _authenticate("bob", ["tinyassets.universe.write"])
        out = json.loads(us._universe_impl(
            action="set_premise",
            universe_id="alice-world",
            text="Hostile cross-founder overwrite.",
        ))

        assert out["error"] == "universe_access_denied"
        assert out["required_permission"] == "write"
        assert out["actor_id"] == "bob"

    def test_owner_admin_grant_does_not_make_universe_private(self, universe_base):
        # Ownership != visibility. An admin grant with no public_read=False rule
        # leaves the universe publicly readable.
        _make_universe(universe_base, "owned-public")
        grant_universe_access(
            universe_base,
            universe_id="owned-public",
            actor_id="owner",
            permission="admin",
            granted_by="owner",
        )
        _authenticate("reader", ["tinyassets.universe.read"])

        out = json.loads(us._universe_impl(
            action="inspect",
            universe_id="owned-public",
        ))

        assert out["universe_id"] == "owned-public"
        assert "error" not in out

    def test_private_universe_rejects_unlisted_reader(self, universe_base):
        udir = _make_private_universe(universe_base, "private")
        (udir / "output").mkdir()
        (udir / "output" / "secret.md").write_text("secret", encoding="utf-8")
        grant_universe_access(
            universe_base,
            universe_id="private",
            actor_id="owner",
            permission="admin",
            granted_by="owner",
        )

        _authenticate("intruder", ["tinyassets.universe.read"])

        inspect_out = json.loads(us._universe_impl(
            action="inspect",
            universe_id="private",
        ))
        read_out = json.loads(us._universe_impl(
            action="read_output",
            universe_id="private",
            path="secret.md",
        ))

        assert inspect_out["error"] == "universe_access_denied"
        assert inspect_out["universe_id"] == "private"
        assert inspect_out["required_permission"] == "read"
        assert read_out["error"] == "universe_access_denied"

    def test_private_universe_rejects_reader_write(self, universe_base):
        _make_private_universe(universe_base, "private")
        grant_universe_access(
            universe_base,
            universe_id="private",
            actor_id="reader",
            permission="read",
            granted_by="owner",
        )

        _authenticate("reader", ["tinyassets.universe.write"])

        out = json.loads(us._universe_impl(
            action="set_premise",
            universe_id="private",
            text="Overwrite attempt.",
        ))

        assert out["error"] == "universe_access_denied"
        assert out["required_permission"] == "write"
        assert not (universe_base / "private" / "PROGRAM.md").exists()

    def test_private_universe_allows_granted_writer(self, universe_base):
        # {write, admin} write-set: a "write" grant CAN write (matches current
        # main). Only no-grant / read-only actors are denied writes.
        _make_private_universe(universe_base, "private")
        grant_universe_access(
            universe_base,
            universe_id="private",
            actor_id="writer",
            permission="write",
            granted_by="owner",
        )

        _authenticate("writer", ["tinyassets.universe.write"])

        out = json.loads(us._universe_impl(
            action="set_premise",
            universe_id="private",
            text="Allowed update.",
        ))

        assert out["status"] == "updated"
        assert (universe_base / "private" / "PROGRAM.md").read_text(
            encoding="utf-8",
        ) == "Allowed update."

    def test_private_universe_allows_owner_admin_write(self, universe_base):
        _make_private_universe(universe_base, "private")
        grant_universe_access(
            universe_base,
            universe_id="private",
            actor_id="owner",
            permission="admin",
            granted_by="owner",
        )

        _authenticate("owner", ["tinyassets.universe.write"])

        out = json.loads(us._universe_impl(
            action="set_premise",
            universe_id="private",
            text="Owner update.",
        ))

        assert out["status"] == "updated"
        assert (universe_base / "private" / "PROGRAM.md").read_text(
            encoding="utf-8",
        ) == "Owner update."

    def test_list_filters_private_universes_without_grant(self, universe_base):
        _make_universe(universe_base, "public")
        _make_private_universe(universe_base, "private")
        grant_universe_access(
            universe_base,
            universe_id="private",
            actor_id="owner",
            permission="admin",
            granted_by="owner",
        )

        _authenticate("intruder", ["tinyassets.universe.read"])

        out = json.loads(us._universe_impl(action="list"))

        assert [row["id"] for row in out["universes"]] == ["public"]


class TestScopeHeader:
    """#15: the dispatcher wraps every universe-scoped response with a
    phone-legible `Universe: <id>` `text` lead-in, puts `universe_id`
    first, and leaves everything else structurally intact.
    """

    def test_dispatch_injects_text_header_on_read(self, universe_base):
        _make_universe(universe_base, "alpha")
        (universe_base / "alpha" / "PROGRAM.md").write_text(
            "An alpha premise.", encoding="utf-8",
        )
        out = json.loads(us._dispatch_with_ledger(
            "read_premise",
            us._action_read_premise,
            {"universe_id": "alpha"},
        ))
        assert "text" in out
        assert out["text"].startswith("Universe: alpha")
        assert out["premise"] == "An alpha premise."

    def test_universe_id_is_first_key(self, universe_base):
        _make_universe(universe_base, "alpha")
        out_str = us._dispatch_with_ledger(
            "read_premise",
            us._action_read_premise,
            {"universe_id": "alpha"},
        )
        out = json.loads(out_str)
        first_key = next(iter(out.keys()))
        assert first_key == "universe_id"

    def test_text_header_on_write_path(self, universe_base):
        _make_universe(universe_base, "alpha")
        out = json.loads(us._dispatch_with_ledger(
            "set_premise",
            us._action_set_premise,
            {"universe_id": "alpha", "text": "Fresh premise."},
        ))
        assert out["universe_id"] == "alpha"
        assert "text" in out
        assert out["text"].startswith("Universe: alpha")
        assert out["status"] == "updated"

    def test_error_without_universe_id_is_unchanged(self, universe_base):
        # An error response with no universe_id must NOT get a fake scope
        # header — we don't want to falsely claim a universe.
        out = json.loads(us._dispatch_with_ledger(
            "set_premise",
            us._action_set_premise,
            {"universe_id": "alpha", "text": ""},  # empty → error
        ))
        assert "error" in out
        if "text" in out:
            assert not out["text"].startswith("Universe: ")

    def test_multi_universe_list_not_scoped(self, universe_base):
        # list_universes returns a multi-universe response with no
        # single universe_id — must not get a scope header.
        _make_universe(universe_base, "alpha")
        _make_universe(universe_base, "beta")
        out = json.loads(us._dispatch_with_ledger(
            "list",
            us._action_list_universes,
            {},
        ))
        assert "universes" in out
        if "text" in out:
            assert not out["text"].startswith("Universe: ")

    def test_existing_text_field_preserved_under_header(self):
        # If a handler already emits a `text` field, the helper prepends
        # the header rather than clobbering it.
        fake = json.dumps({"universe_id": "alpha", "text": "Prior prose."})
        wrapped = json.loads(us._scope_universe_response(fake))
        assert wrapped["text"].startswith("Universe: alpha")
        assert "Prior prose." in wrapped["text"]

    def test_preserves_all_other_fields(self, universe_base):
        udir = _make_universe(universe_base, "alpha")
        (udir / "canon").mkdir()
        (udir / "canon" / "a.md").write_text("x", encoding="utf-8")
        out = json.loads(us._dispatch_with_ledger(
            "list_canon",
            us._action_list_canon,
            {"universe_id": "alpha"},
        ))
        assert out["universe_id"] == "alpha"
        assert out["count"] == 1
        assert out["canon_files"][0]["filename"] == "a.md"

    def test_non_universe_scoped_response_unchanged(self):
        # `_scope_universe_response` should leave dicts without
        # universe_id alone.
        payload = json.dumps({"branches": [], "count": 0})
        out = us._scope_universe_response(payload)
        assert json.loads(out) == {"branches": [], "count": 0}

    def test_non_json_response_unchanged(self):
        out = us._scope_universe_response("not json at all")
        assert out == "not json at all"
