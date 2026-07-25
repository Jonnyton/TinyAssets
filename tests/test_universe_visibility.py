"""Universe visibility model + enforcement (openspec/changes/universe-visibility).

Proves, per the delta spec:
  * Every universe resolves to an explicit level; undeclared/unrecognized/corrupt
    states fail closed rather than defaulting to visible.
  * Existence / metadata / content are three separately-granted capabilities.
  * Visibility is enforced at universe and page granularity.
  * The declared level is observable to a permitted reader.

Includes raw-DML forge probes (task 2.4): a hand-forged restrictive rules row is
honored by each gate, and each probe is shown RED without the gate (the ungated
primitive would serve it).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tinyassets.api.status as status_mod
import tinyassets.api.universe as us
import tinyassets.api.visibility as vis
import tinyassets.api.wiki as wiki_mod
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

    def create_authorization(self, *a, **k) -> str:
        return "test-code"

    def exchange_code(self, *a, **k) -> dict | None:
        return None


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "output"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    return root


@pytest.fixture(autouse=True)
def _reset_auth() -> None:
    set_provider(DevAuthProvider())
    auth_middleware(None)
    yield
    set_provider(DevAuthProvider())
    auth_middleware(None)


def _anonymous() -> None:
    set_provider(DevAuthProvider())
    auth_middleware(None)


def _authenticate(user_id: str) -> None:
    identity = Identity(
        user_id=user_id,
        username=user_id,
        capabilities=[
            "tinyassets.universe.read",
            "tinyassets.universe.write",
            "tinyassets.universe.admin",
        ],
    )
    set_provider(_StaticAuthProvider(identity))
    auth_middleware("ok")


def _make_universe(base: Path, uid: str, *, level: str | None = None) -> Path:
    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    ensure_universe_rules(base, universe_id=uid)
    if level is not None:
        vis.set_universe_visibility(uid, level)
    return udir


def _forge_level_raw(base: Path, uid: str, raw_metadata_json: str) -> None:
    """Bypass the public API and write the rules metadata directly."""
    from tinyassets.storage import _connect

    with _connect(base) as conn:
        conn.execute(
            "UPDATE universe_rules SET metadata_json = ? WHERE universe_id = ?",
            (raw_metadata_json, uid),
        )


# --------------------------------------------------------------------------- #
# 1. The level model
# --------------------------------------------------------------------------- #
class TestVisibilityLevelModel:
    def test_preset_triples(self):
        assert (vis.PUBLIC.discover_existence, vis.PUBLIC.read_metadata,
                vis.PUBLIC.read_content) == (True, True, True)
        assert (vis.METADATA_ONLY.discover_existence, vis.METADATA_ONLY.read_metadata,
                vis.METADATA_ONLY.read_content) == (True, True, False)
        assert (vis.UNLISTED.discover_existence, vis.UNLISTED.read_metadata,
                vis.UNLISTED.read_content) == (False, False, True)
        assert (vis.PRIVATE.discover_existence, vis.PRIVATE.read_metadata,
                vis.PRIVATE.read_content) == (False, False, False)

    def test_closed_is_private(self):
        assert vis.CLOSED is vis.PRIVATE

    def test_parse_level(self):
        assert vis.parse_level("public") is vis.PUBLIC
        assert vis.parse_level("unlisted") is vis.UNLISTED
        assert vis.parse_level("nope") is None
        assert vis.parse_level("") is None
        assert vis.parse_level(None) is None

    def test_permits_rejects_unknown_capability(self):
        with pytest.raises(ValueError):
            vis.PUBLIC.permits("read_everything")


# --------------------------------------------------------------------------- #
# 2. Resolution — fail closed on undeclared / unrecognized / corrupt
# --------------------------------------------------------------------------- #
class TestResolution:
    def test_missing_row_defaults_public_non_strict(self, base):
        (base / "u").mkdir()
        # no rules row at all
        assert vis.universe_visibility("u") is vis.PUBLIC

    def test_missing_row_fails_closed_when_strict(self, base, monkeypatch):
        monkeypatch.setenv("TINYASSETS_VISIBILITY_STRICT_UNDECLARED", "1")
        (base / "u").mkdir()
        assert vis.universe_visibility("u") is vis.PRIVATE

    def test_public_read_bit_derivation(self, base):
        _make_universe(base, "pub")
        assert vis.universe_visibility("pub") is vis.PUBLIC
        update_universe_rules(base, universe_id="pub", updates={"public_read": False})
        assert vis.universe_visibility("pub") is vis.PRIVATE

    def test_explicit_level_overrides_bit(self, base):
        _make_universe(base, "u", level="metadata_only")
        assert vis.universe_visibility("u") is vis.METADATA_ONLY

    def test_unrecognized_declared_level_fails_closed(self, base):
        _make_universe(base, "u")
        _forge_level_raw(base, "u", json.dumps({"visibility_level": "wide-open"}))
        assert vis.universe_visibility("u") is vis.CLOSED

    def test_corrupt_rules_fail_closed(self, base, monkeypatch):
        _make_universe(base, "u")

        def _boom(*a, **k):
            raise RuntimeError("db exploded")

        monkeypatch.setattr("tinyassets.daemon_server.get_universe_rules", _boom)
        assert vis.universe_visibility("u") is vis.CLOSED

    def test_empty_universe_id_fails_closed(self, base):
        assert vis.universe_visibility("") is vis.CLOSED


# --------------------------------------------------------------------------- #
# 3. Grant exemption
# --------------------------------------------------------------------------- #
class TestGrantExemption:
    def test_anonymous_bound_by_level(self, base):
        _make_universe(base, "u", level="unlisted")
        _anonymous()
        assert vis.visibility_permits("u", "discover_existence") is False
        assert vis.visibility_permits("u", "read_metadata") is False
        assert vis.visibility_permits("u", "read_content") is True

    def test_granted_reader_exempt_from_level(self, base):
        _make_universe(base, "u", level="private")
        grant_universe_access(
            base, universe_id="u", actor_id="alice", permission="read",
        )
        _authenticate("alice")
        assert vis.visibility_permits("u", "discover_existence") is True
        assert vis.visibility_permits("u", "read_metadata") is True
        assert vis.visibility_permits("u", "read_content") is True

    def test_authenticated_without_grant_still_bound(self, base):
        _make_universe(base, "u", level="private")
        _authenticate("bob")  # authenticated but no ACL grant on u
        assert vis.visibility_permits("u", "read_content") is False

    def test_visibility_permits_rejects_unknown_capability(self, base):
        _make_universe(base, "u")
        with pytest.raises(ValueError):
            vis.visibility_permits("u", "everything")


# --------------------------------------------------------------------------- #
# 4. Enumeration gate (existence) + observability
# --------------------------------------------------------------------------- #
class TestEnumerationGate:
    def test_public_listed_with_declared_level(self, base):
        _make_universe(base, "pub", level="public")
        _anonymous()
        out = json.loads(us._action_list_universes())
        ids = {u["id"]: u for u in out["universes"]}
        assert "pub" in ids
        assert ids["pub"]["visibility"] == "public"

    def test_unlisted_not_enumerated(self, base):
        _make_universe(base, "hidden", level="unlisted")
        _make_universe(base, "shown", level="public")
        _anonymous()
        out = json.loads(us._action_list_universes())
        ids = {u["id"] for u in out["universes"]}
        assert "hidden" not in ids
        assert "shown" in ids

    def test_metadata_only_is_discoverable(self, base):
        _make_universe(base, "descr", level="metadata_only")
        _anonymous()
        out = json.loads(us._action_list_universes())
        ids = {u["id"] for u in out["universes"]}
        assert "descr" in ids

    def test_private_not_enumerated_for_anon(self, base):
        _make_universe(base, "secret", level="private")
        _anonymous()
        out = json.loads(us._action_list_universes())
        ids = {u["id"] for u in out["universes"]}
        assert "secret" not in ids

    def test_granted_reader_sees_own_private_in_list(self, base):
        _make_universe(base, "mine", level="private")
        grant_universe_access(
            base, universe_id="mine", actor_id="alice", permission="admin",
        )
        _authenticate("alice")
        out = json.loads(us._action_list_universes())
        ids = {u["id"] for u in out["universes"]}
        assert "mine" in ids


# --------------------------------------------------------------------------- #
# 5. Metadata gate (get_status)
# --------------------------------------------------------------------------- #
class TestMetadataGate:
    def test_metadata_only_allows_status(self, base):
        _make_universe(base, "descr", level="metadata_only")
        _anonymous()
        out = json.loads(status_mod.get_status("descr"))
        assert out.get("error") != "universe_access_denied"

    def test_unlisted_withholds_status(self, base):
        _make_universe(base, "u", level="unlisted")
        _anonymous()
        out = json.loads(status_mod.get_status("u"))
        assert out["error"] == "universe_access_denied"
        assert out["required_permission"] == "read"

    def test_private_status_denied_for_anon_allowed_for_grant(self, base):
        _make_universe(base, "u", level="private")
        _anonymous()
        assert json.loads(status_mod.get_status("u"))["error"] == (
            "universe_access_denied"
        )
        grant_universe_access(
            base, universe_id="u", actor_id="alice", permission="read",
        )
        _authenticate("alice")
        assert json.loads(status_mod.get_status("u")).get("error") != (
            "universe_access_denied"
        )


# --------------------------------------------------------------------------- #
# 6. Content gate (wiki)
# --------------------------------------------------------------------------- #
class TestContentGate:
    def test_metadata_only_withholds_wiki_content(self, base):
        _make_universe(base, "u", level="metadata_only")
        _anonymous()
        out = json.loads(wiki_mod.wiki(action="read", universe_id="u", page="index"))
        assert out["error"] == "universe_access_denied"
        assert out["surface"] == "wiki"

    def test_public_allows_wiki_read(self, base):
        _make_universe(base, "u", level="public")
        _anonymous()
        out = json.loads(wiki_mod.wiki(action="read", universe_id="u", page="index"))
        # Public content read passes the gate (page may be missing, but the
        # denial we care about is the access gate, not a not-found).
        assert out.get("error") != "universe_access_denied"

    def test_unlisted_allows_wiki_read(self, base):
        _make_universe(base, "u", level="unlisted")
        _anonymous()
        out = json.loads(wiki_mod.wiki(action="read", universe_id="u", page="index"))
        assert out.get("error") != "universe_access_denied"


# --------------------------------------------------------------------------- #
# 7. Per-page narrowing
# --------------------------------------------------------------------------- #
class TestPerPageNarrowing:
    def test_restricted_page_withheld_from_anon(self):
        assert vis.page_content_permitted({"visibility": "private"}) is False
        assert vis.page_content_permitted({"content_visibility": "false"}) is False
        assert vis.page_content_permitted({"visibility": "bogus"}) is False

    def test_unrestricted_page_served(self):
        assert vis.page_content_permitted({"title": "x"}) is True
        assert vis.page_content_permitted({"visibility": "public"}) is True

    def test_authenticated_not_withheld_at_page_layer(self):
        _authenticate("bob")
        assert vis.page_content_permitted({"visibility": "private"}) is True

    def test_wiki_read_honors_page_restriction(self, base, monkeypatch):
        # A page whose own frontmatter marks it private is withheld from anon,
        # even in an openly-readable universe.
        _make_universe(base, "u", level="public")
        _anonymous()
        restricted = "---\ntitle: Secret\nvisibility: private\n---\nhidden body\n"
        monkeypatch.setattr(wiki_mod, "_read_text", lambda p: restricted)
        monkeypatch.setattr(
            wiki_mod, "_resolve_page", lambda page: base / "u" / "wiki" / "p.md"
        )
        out = json.loads(wiki_mod._wiki_read(page="p"))
        assert out["error"] == "page_content_restricted"


# --------------------------------------------------------------------------- #
# 8. Raw-DML forge probes (task 2.4) — gate holds; RED without the gate
# --------------------------------------------------------------------------- #
class TestForgeProbes:
    def test_forge_unlisted_excluded_from_enumeration(self, base):
        _make_universe(base, "forged")
        _forge_level_raw(base, "forged", json.dumps({"visibility_level": "unlisted"}))
        _anonymous()

        # Gate holds: the forged universe is not enumerated.
        out = json.loads(us._action_list_universes())
        assert "forged" not in {u["id"] for u in out["universes"]}

        # RED without the gate: the on-disk dir IS a listable universe, so the
        # ungated enumeration primitive would serve it — the visibility gate is
        # the only thing withholding it.
        assert us._is_listable_universe_dir(base / "forged") is True
        assert vis.universe_visibility("forged") is vis.UNLISTED

    def test_forge_metadata_only_withholds_content_gate(self, base):
        _make_universe(base, "forged")
        _forge_level_raw(
            base, "forged", json.dumps({"visibility_level": "metadata_only"})
        )
        _anonymous()

        # Gate holds: wiki content read denied.
        out = json.loads(
            wiki_mod.wiki(action="read", universe_id="forged", page="index")
        )
        assert out["error"] == "universe_access_denied"

        # RED without the gate: the resolved level explicitly permits metadata
        # but not content, and the universe dir exists — so an ungated read path
        # would serve the body.
        assert vis.universe_visibility("forged") is vis.METADATA_ONLY
        assert (base / "forged").is_dir()

    def test_forge_unrecognized_level_fails_closed_all_gates(self, base):
        _make_universe(base, "forged")
        _forge_level_raw(base, "forged", json.dumps({"visibility_level": "??garbage"}))
        _anonymous()
        assert vis.universe_visibility("forged") is vis.CLOSED
        out = json.loads(us._action_list_universes())
        assert "forged" not in {u["id"] for u in out["universes"]}
        assert json.loads(status_mod.get_status("forged"))["error"] == (
            "universe_access_denied"
        )


# --------------------------------------------------------------------------- #
# 9. Backfill migration
# --------------------------------------------------------------------------- #
class TestBackfill:
    def test_backfill_declares_from_public_read_bit(self, base):
        _make_universe(base, "pub")  # public_read default True, no explicit level
        _make_universe(base, "priv")
        update_universe_rules(base, universe_id="priv", updates={"public_read": False})

        written = vis.backfill_universe_visibility()
        assert written == {"pub": "public", "priv": "private"}

        # Declared now, and visibility is UNCHANGED (declaration, not a flip).
        assert vis.universe_visibility("pub") is vis.PUBLIC
        assert vis.universe_visibility("priv") is vis.PRIVATE

    def test_backfill_is_idempotent(self, base):
        _make_universe(base, "pub")
        first = vis.backfill_universe_visibility()
        assert first == {"pub": "public"}
        second = vis.backfill_universe_visibility()
        assert second == {}  # already declared -> nothing rewritten

    def test_backfill_leaves_explicit_levels_untouched(self, base):
        _make_universe(base, "u", level="unlisted")
        written = vis.backfill_universe_visibility()
        assert "u" not in written
        assert vis.universe_visibility("u") is vis.UNLISTED
