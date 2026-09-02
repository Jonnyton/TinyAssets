"""Universe visibility model + enforcement (openspec/changes/universe-visibility).

Proves, per the delta spec:
  * Every universe resolves to an explicit level; undeclared / blank / null /
    unrecognized / corrupt / non-dict states fail closed (never default open).
  * The layer is tighten-only by construction: an inconsistent row with
    public_read=False plus a permissive explicit level cannot open a read.
  * Existence / metadata / content are three separately-granted capabilities.
  * Visibility is enforced at universe and page granularity, including the
    sibling read paths (search / since / list) — not just direct read.
  * Authentication is NOT page ACL authority.
  * The declared level is observable; denials do not leak hidden identity/count.

The fail-closed truth table from the cross-family review is encoded row-by-row
in ``TestResolutionFailClosed`` — every row that previously returned a fail-open
result is now asserted CLOSED. Raw-DML forge probes (task 2.4) prove each gate
holds and is RED without the gate.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tinyassets.api.status as status_mod
import tinyassets.api.universe as us
import tinyassets.api.visibility as vis
import tinyassets.api.wiki as wiki_mod
from tinyassets.api.wiki import _ensure_wiki_scaffold, _wiki_pages_dir
from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity
from tinyassets.daemon_server import (
    ensure_universe_registered,
    grant_universe_access,
)
from tinyassets.storage import _connect


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


@pytest.fixture
def wiki_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "output"
    root.mkdir()
    wiki_root = tmp_path / "wiki"
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(wiki_root))
    _ensure_wiki_scaffold(wiki_root)
    return wiki_root


@pytest.fixture(autouse=True)
def _reset_auth() -> None:
    set_provider(DevAuthProvider())
    auth_middleware("dev")
    yield
    set_provider(DevAuthProvider())
    auth_middleware("dev")


def _anonymous() -> None:
    set_provider(DevAuthProvider())
    auth_middleware("dev")


def _authenticate(user_id: str) -> None:
    identity = Identity(
        user_id=user_id,
        username=user_id,
        capabilities=[
            "tinyassets.universe.read",
            "tinyassets.universe.write",
            "tinyassets.universe.admin",
            "tinyassets.wiki.read",
        ],
    )
    set_provider(_StaticAuthProvider(identity))
    auth_middleware("ok")


def _make_universe(base: Path, uid: str, *, level: str | None = None) -> Path:
    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    if level is not None:
        vis.set_universe_visibility(uid, level)
    return udir


def _forge_metadata_raw(base: Path, uid: str, metadata_json: str) -> None:
    """Bypass the public API and write the rules metadata_json directly."""
    with _connect(base) as conn:
        conn.execute(
            "UPDATE universe_rules SET metadata_json = ? WHERE universe_id = ?",
            (metadata_json, uid),
        )


def _forge_public_read_raw(base: Path, uid: str, raw_value: object) -> None:
    """Force an arbitrary public_read cell value (raw DML)."""
    with _connect(base) as conn:
        conn.execute(
            "UPDATE universe_rules SET public_read = ? WHERE universe_id = ?",
            (raw_value, uid),
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
# 2. Resolution — the fail-closed truth table (review-derived, row by row)
# --------------------------------------------------------------------------- #
class TestResolutionFailClosed:
    def test_blank_universe_id(self, base):
        assert vis.universe_visibility("") is vis.CLOSED
        assert vis.universe_visibility("   ") is vis.CLOSED

    def test_no_rules_row_is_undeclared_and_closed(self, base):
        (base / "u").mkdir()  # dir exists, no rules row at all
        assert vis.universe_visibility("u") is vis.CLOSED

    def test_rules_row_without_explicit_level_is_closed(self, base):
        # A registered universe with a rules row (public_read defaults True) but
        # no explicit visibility_level is UNDECLARED -> fail closed. It never
        # derives an open default from public_read.
        _make_universe(base, "u")
        assert vis.universe_visibility("u") is vis.CLOSED

    def test_explicit_recognized_levels(self, base):
        for name in ("public", "metadata_only", "unlisted", "private"):
            _make_universe(base, name, level=name)
            assert vis.universe_visibility(name) is vis.LEVELS[name]

    def test_unrecognized_string_closed(self, base):
        _make_universe(base, "u")
        _forge_metadata_raw(base, "u", json.dumps({"visibility_level": "wide-open"}))
        assert vis.universe_visibility("u") is vis.CLOSED

    def test_blank_and_whitespace_string_closed(self, base):
        _make_universe(base, "b")
        _forge_metadata_raw(base, "b", json.dumps({"visibility_level": ""}))
        assert vis.universe_visibility("b") is vis.CLOSED
        _make_universe(base, "w")
        _forge_metadata_raw(base, "w", json.dumps({"visibility_level": "   "}))
        assert vis.universe_visibility("w") is vis.CLOSED

    def test_null_level_closed(self, base):
        _make_universe(base, "u")
        _forge_metadata_raw(base, "u", json.dumps({"visibility_level": None}))
        assert vis.universe_visibility("u") is vis.CLOSED

    def test_wrong_type_level_closed(self, base):
        for i, val in enumerate([False, 0, True, 1, [1], {"a": 1}, 3.5]):
            uid = f"wt{i}"
            _make_universe(base, uid)
            _forge_metadata_raw(base, uid, json.dumps({"visibility_level": val}))
            assert vis.universe_visibility(uid) is vis.CLOSED

    def test_malformed_metadata_json_closed(self, base):
        _make_universe(base, "u")
        _forge_metadata_raw(base, "u", "{not-json")
        assert vis.universe_visibility("u") is vis.CLOSED

    def test_non_object_metadata_json_closed(self, base):
        for i, raw in enumerate(["[]", '"text"', "null", "42"]):
            uid = f"no{i}"
            _make_universe(base, uid)
            _forge_metadata_raw(base, uid, raw)
            assert vis.universe_visibility(uid) is vis.CLOSED

    def test_wrong_type_public_read_still_closed_when_undeclared(self, base):
        # public_read forged to a truthy string must NOT open an undeclared
        # universe — resolution ignores public_read entirely.
        _make_universe(base, "u")
        _forge_public_read_raw(base, "u", "false")
        assert vis.universe_visibility("u") is vis.CLOSED

    def test_corrupt_rules_fail_closed(self, base, monkeypatch):
        _make_universe(base, "u")

        def _boom(*a, **k):
            raise RuntimeError("db exploded")

        monkeypatch.setattr("tinyassets.daemon_server.get_universe_rules", _boom)
        assert vis.universe_visibility("u") is vis.CLOSED


# --------------------------------------------------------------------------- #
# 3. Tighten-only composition — new layer can never grant what legacy denies
# --------------------------------------------------------------------------- #
class TestTightenOnlyComposition:
    def _inconsistent(self, base, uid, level):
        """A forged row: explicit permissive level + public_read=False."""
        _make_universe(base, uid, level=level)
        _forge_public_read_raw(base, uid, 0)  # legacy gate would deny

    def test_enumeration_gate_denies_inconsistent(self, base):
        self._inconsistent(base, "enum-wide", "public")
        _anonymous()
        # visibility_permits ANDs with the legacy gate -> denied despite level.
        assert vis.visibility_permits("enum-wide", "discover_existence") is False
        out = json.loads(us._action_list_universes())
        assert "enum-wide" not in {u["id"] for u in out["universes"]}

    def test_metadata_gate_denies_inconsistent(self, base):
        self._inconsistent(base, "meta-wide", "metadata_only")
        _anonymous()
        assert vis.visibility_permits("meta-wide", "read_metadata") is False
        assert json.loads(status_mod.get_status("meta-wide"))["error"] == (
            "universe_access_denied"
        )

    def test_content_gate_denies_inconsistent(self, wiki_env):
        base = Path(wiki_env).parent / "output"
        self._inconsistent(base, "content-wide", "unlisted")
        _anonymous()
        assert vis.visibility_permits("content-wide", "read_content") is False
        out = json.loads(
            wiki_mod.wiki(action="read", universe_id="content-wide", page="index")
        )
        assert out["error"] == "universe_access_denied"


# --------------------------------------------------------------------------- #
# 4. Grant exemption (universe level)
# --------------------------------------------------------------------------- #
class TestGrantExemption:
    def test_anonymous_bound_by_level(self, base):
        _make_universe(base, "u", level="unlisted")
        _anonymous()
        assert vis.visibility_permits("u", "discover_existence") is False
        assert vis.visibility_permits("u", "read_metadata") is False
        assert vis.visibility_permits("u", "read_content") is True

    def test_granted_reader_exempt(self, base):
        _make_universe(base, "u", level="private")
        grant_universe_access(base, universe_id="u", actor_id="alice", permission="read")
        _authenticate("alice")
        assert vis.visibility_permits("u", "discover_existence") is True
        assert vis.visibility_permits("u", "read_metadata") is True
        assert vis.visibility_permits("u", "read_content") is True

    def test_authenticated_without_grant_still_bound(self, base):
        _make_universe(base, "u", level="private")
        _authenticate("bob")  # authenticated, no ACL grant on u
        assert vis.visibility_permits("u", "read_content") is False

    def test_rejects_unknown_capability(self, base):
        _make_universe(base, "u", level="public")
        with pytest.raises(ValueError):
            vis.visibility_permits("u", "everything")


# --------------------------------------------------------------------------- #
# 5. Enumeration gate (existence) + observability + note-leak
# --------------------------------------------------------------------------- #
class TestEnumerationGate:
    def test_public_listed_with_declared_level(self, base):
        _make_universe(base, "pub", level="public")
        _anonymous()
        out = json.loads(us._action_list_universes())
        ids = {u["id"]: u for u in out["universes"]}
        assert ids["pub"]["visibility"] == "public"

    def test_unlisted_not_enumerated(self, base):
        _make_universe(base, "hidden", level="unlisted")
        _make_universe(base, "shown", level="public")
        _anonymous()
        ids = {u["id"] for u in json.loads(us._action_list_universes())["universes"]}
        assert "hidden" not in ids and "shown" in ids

    def test_metadata_only_is_discoverable(self, base):
        _make_universe(base, "descr", level="metadata_only")
        _anonymous()
        ids = {u["id"] for u in json.loads(us._action_list_universes())["universes"]}
        assert "descr" in ids

    def test_private_and_undeclared_not_enumerated(self, base):
        _make_universe(base, "secret", level="private")
        _make_universe(base, "undeclared")  # no explicit level
        _anonymous()
        ids = {u["id"] for u in json.loads(us._action_list_universes())["universes"]}
        assert "secret" not in ids and "undeclared" not in ids

    def test_hidden_only_note_does_not_leak_count_or_path(self, base):
        _make_universe(base, "a", level="private")
        _make_universe(base, "b", level="private")
        _anonymous()
        out = json.loads(us._action_list_universes())
        assert out["count"] == 0
        note = out.get("note", "")
        assert note == "No universes are visible to you."
        assert "2" not in note and str(base) not in note

    def test_granted_reader_sees_own_private_in_list(self, base):
        _make_universe(base, "mine", level="private")
        grant_universe_access(base, universe_id="mine", actor_id="alice", permission="admin")
        _authenticate("alice")
        ids = {u["id"] for u in json.loads(us._action_list_universes())["universes"]}
        assert "mine" in ids


# --------------------------------------------------------------------------- #
# 6. Metadata gate (get_status + inspect) + blank-id name leak
# --------------------------------------------------------------------------- #
def test_nobody_bound_cannot_read_any_status(base):
    _make_universe(base, "descr", level="metadata_only")
    _anonymous()
    with pytest.raises(PermissionError, match="Authentication required"):
        status_mod.get_status("descr")


class TestMetadataGate:
    def test_metadata_only_allows_status(self, base):
        _make_universe(base, "descr", level="metadata_only")
        _authenticate("stranger")  # a signed-in reader who is not the owner
        assert json.loads(status_mod.get_status("descr")).get("error") != (
            "universe_access_denied"
        )

    def test_unlisted_withholds_status(self, base):
        _make_universe(base, "u", level="unlisted")
        _anonymous()
        out = json.loads(status_mod.get_status("u"))
        assert out["error"] == "universe_access_denied"

    def test_nonexistent_universe_status_is_diagnostic_not_denied(self, base):
        # A universe that does not exist has no metadata to protect; the
        # not-found diagnostic stays ungated for any signed-in reader.
        _authenticate("stranger")
        out = json.loads(status_mod.get_status("does-not-exist"))
        assert out.get("error") != "universe_access_denied"

    def test_inspect_gates_unlisted_metadata(self, base):
        # unlisted sets public_read=True (content readable) which the legacy
        # preflight allows; inspect must still withhold metadata.
        _make_universe(base, "u", level="unlisted")
        _anonymous()
        out = json.loads(us._action_inspect_universe(universe_id="u"))
        assert out["error"] == "universe_access_denied"

    def test_inspect_allows_metadata_only(self, base):
        _make_universe(base, "descr", level="metadata_only")
        _anonymous()
        out = json.loads(us._action_inspect_universe(universe_id="descr"))
        assert out.get("error") != "universe_access_denied"
        assert out["visibility"] == "metadata_only"

    def test_blank_id_denial_does_not_leak_resolved_name(self, base):
        # Only a private universe exists; a blank-scope status probe must not
        # echo its identity anywhere in the response.
        _make_universe(base, "only-hidden", level="private")
        _anonymous()
        raw = status_mod.get_status("")
        assert "only-hidden" not in raw


# --------------------------------------------------------------------------- #
# 7. Content gate (wiki read)
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
        assert out.get("error") != "universe_access_denied"

    def test_unlisted_allows_wiki_read(self, base):
        _make_universe(base, "u", level="unlisted")
        _anonymous()
        out = json.loads(wiki_mod.wiki(action="read", universe_id="u", page="index"))
        assert out.get("error") != "universe_access_denied"


# --------------------------------------------------------------------------- #
# 8. Per-page narrowing — authentication is NOT page ACL authority
# --------------------------------------------------------------------------- #
class TestPerPageNarrowing:
    def test_restricted_page_withheld_from_anon(self, base):
        _anonymous()
        assert vis.page_content_permitted({"visibility": "private"}) is False
        assert vis.page_content_permitted({"content_visibility": "false"}) is False
        assert vis.page_content_permitted({"visibility": "bogus"}) is False

    def test_unrestricted_page_served(self, base):
        _anonymous()
        assert vis.page_content_permitted({"title": "x"}) is True
        assert vis.page_content_permitted({"visibility": "public"}) is True

    def test_authentication_alone_does_not_bypass_page_restriction(self, base):
        _make_universe(base, "u", level="public")
        _authenticate("bob")  # authenticated but NO ACL grant on u
        assert vis.page_content_permitted({"visibility": "private"}, "u") is False

    def test_granted_reader_bypasses_page_restriction(self, base):
        _make_universe(base, "u", level="public")
        grant_universe_access(base, universe_id="u", actor_id="alice", permission="read")
        _authenticate("alice")
        assert vis.page_content_permitted({"visibility": "private"}, "u") is True

    def test_wiki_read_honors_page_restriction(self, base, monkeypatch):
        _make_universe(base, "u", level="public")
        _anonymous()
        restricted = "---\ntitle: Secret\nvisibility: private\n---\nhidden body\n"
        monkeypatch.setattr(wiki_mod, "_read_text", lambda p: restricted)
        monkeypatch.setattr(
            wiki_mod, "_resolve_page", lambda page: base / "u" / "wiki" / "p.md"
        )
        out = json.loads(wiki_mod._wiki_read(page="p", universe_id="u"))
        assert out["error"] == "page_content_restricted"


# --------------------------------------------------------------------------- #
# 9. Sibling read-path leaks (search / since / list)
# --------------------------------------------------------------------------- #
class TestSiblingReadLeaks:
    def _seed_pages(self):
        pages = _wiki_pages_dir()
        pages.mkdir(parents=True, exist_ok=True)
        (pages / "public-note.md").write_text(
            "---\ntitle: Public Note\ntype: note\n---\nPUBLIC-BODY canary\n",
            encoding="utf-8",
        )
        (pages / "secret.md").write_text(
            "---\ntitle: Secret\ntype: note\nvisibility: private\n---\n"
            "ULTRASECRET canary body\n",
            encoding="utf-8",
        )

    def test_search_excludes_restricted_page(self, wiki_env):
        self._seed_pages()
        _anonymous()
        out = json.loads(wiki_mod._wiki_search(query="canary", universe_id=""))
        blob = json.dumps(out.get("results", []))
        assert "PUBLIC-BODY" in blob or "Public Note" in blob
        assert "ULTRASECRET" not in blob
        assert "Secret" not in blob

    def test_list_excludes_restricted_page(self, wiki_env):
        self._seed_pages()
        _anonymous()
        out = json.loads(wiki_mod._wiki_list(universe_id=""))
        paths = {p["path"] for p in out["promoted"]}
        assert any("public-note" in p for p in paths)
        assert not any("secret" in p for p in paths)

    def test_since_excludes_restricted_page(self, wiki_env):
        self._seed_pages()
        _anonymous()
        out = json.loads(
            wiki_mod._wiki_since(changed_since="1970-01-01T00:00:00Z", universe_id="")
        )
        blob = json.dumps(out)
        assert "ULTRASECRET" not in blob and "Secret" not in blob


# --------------------------------------------------------------------------- #
# 10. Raw-DML forge probes (task 2.4) — gate holds; RED without the gate
# --------------------------------------------------------------------------- #
class TestForgeProbes:
    def test_forge_unlisted_excluded_from_enumeration(self, base):
        _make_universe(base, "forged")
        _forge_metadata_raw(base, "forged", json.dumps({"visibility_level": "unlisted"}))
        _anonymous()
        out = json.loads(us._action_list_universes())
        assert "forged" not in {u["id"] for u in out["universes"]}
        # RED without the gate: the on-disk dir IS a listable universe; only the
        # visibility gate withholds it.
        assert us._is_listable_universe_dir(base / "forged") is True
        assert vis.universe_visibility("forged") is vis.UNLISTED

    def test_forge_metadata_only_withholds_content(self, base):
        _make_universe(base, "forged")
        _forge_metadata_raw(
            base, "forged", json.dumps({"visibility_level": "metadata_only"})
        )
        _anonymous()
        out = json.loads(
            wiki_mod.wiki(action="read", universe_id="forged", page="index")
        )
        assert out["error"] == "universe_access_denied"
        assert vis.universe_visibility("forged") is vis.METADATA_ONLY
        assert (base / "forged").is_dir()

    def test_forge_unrecognized_level_fails_closed_all_gates(self, base):
        _make_universe(base, "forged")
        _forge_metadata_raw(base, "forged", json.dumps({"visibility_level": "??garbage"}))
        _anonymous()
        assert vis.universe_visibility("forged") is vis.CLOSED
        out = json.loads(us._action_list_universes())
        assert "forged" not in {u["id"] for u in out["universes"]}
        assert json.loads(status_mod.get_status("forged"))["error"] == (
            "universe_access_denied"
        )


# --------------------------------------------------------------------------- #
# 11. Backfill migration
# --------------------------------------------------------------------------- #
class TestBackfill:
    def test_backfill_declares_from_public_read_bit(self, base):
        _make_universe(base, "pub")  # public_read default True, no explicit level
        u_priv = _make_universe(base, "priv")
        _forge_public_read_raw(base, "priv", 0)
        assert vis.universe_visibility("pub") is vis.CLOSED  # undeclared pre-backfill
        assert u_priv.is_dir()

        written = vis.backfill_universe_visibility()
        assert written == {"pub": "public", "priv": "private"}
        assert vis.universe_visibility("pub") is vis.PUBLIC
        assert vis.universe_visibility("priv") is vis.PRIVATE

    def test_backfill_is_idempotent(self, base):
        _make_universe(base, "pub")
        assert vis.backfill_universe_visibility() == {"pub": "public"}
        assert vis.backfill_universe_visibility() == {}

    def test_backfill_leaves_explicit_levels_untouched(self, base):
        _make_universe(base, "u", level="unlisted")
        assert "u" not in vis.backfill_universe_visibility()
        assert vis.universe_visibility("u") is vis.UNLISTED


# --------------------------------------------------------------------------- #
# 12. Enforceable startup gate (auto-backfill-at-boot, fail-loud on remainder)
# --------------------------------------------------------------------------- #
class TestStartupGate:
    def test_gate_declares_undeclared_universes(self, base):
        _make_universe(base, "reg")   # registered rules row, no explicit level
        (base / "bare").mkdir()       # bare dir, no rules row at all
        assert not vis.is_declared("reg") and not vis.is_declared("bare")

        summary = vis.run_visibility_startup_gate()

        assert vis.is_declared("reg") and vis.is_declared("bare")
        assert vis.universe_visibility("reg") is vis.PUBLIC
        assert set(summary["declared_now"]) >= {"reg", "bare"}
        assert summary["undeclared_remaining"] == []

    def test_gate_derives_private_from_public_read(self, base):
        _make_universe(base, "priv")
        _forge_public_read_raw(base, "priv", 0)  # public_read False, undeclared
        vis.run_visibility_startup_gate()
        assert vis.is_declared("priv")
        assert vis.universe_visibility("priv") is vis.PRIVATE

    def test_gate_is_idempotent(self, base):
        _make_universe(base, "u", level="public")
        first = vis.run_visibility_startup_gate()
        assert first["undeclared_remaining"] == []
        second = vis.run_visibility_startup_gate()
        assert second["declared_now"] == {}

    def test_gate_refuses_readiness_on_undeclared_remainder(self, base, monkeypatch):
        _make_universe(base, "u")  # undeclared
        # Simulate a backfill that could not declare it (e.g. corruption): the
        # gate must fail loudly rather than serve it CLOSED.
        monkeypatch.setattr(vis, "backfill_universe_visibility", lambda *a, **k: {})
        with pytest.raises(vis.VisibilityStartupGateError):
            vis.run_visibility_startup_gate()


# --------------------------------------------------------------------------- #
# 13. Creation-time declaration — no universe is born undeclared
# --------------------------------------------------------------------------- #
class TestCreationDeclaration:
    """These once called `_anonymous()` and asserted a universe was created.

    That encoded the contract the founder removed on 2026-08-28: a universe must
    belong to a WorkOS person. Creation now refuses without an authenticated owner,
    so these authenticate — their real subject is visibility-at-birth, never
    anonymity. `TestCreationRequiresAnOwner` below covers the refusal itself.
    """

    def test_create_declares_default_level(self, base):
        _authenticate("user_01OWNER")
        out = json.loads(us._action_create_universe(universe_id="u1", text="hi"))
        assert out.get("status") == "created"
        assert out["visibility"] == vis.DEFAULT_CREATE_VISIBILITY
        assert vis.is_declared("u1")
        assert vis.universe_visibility("u1") is vis.LEVELS[vis.DEFAULT_CREATE_VISIBILITY]

    def test_create_honors_explicit_visibility(self, base):
        _authenticate("user_01OWNER")
        out = json.loads(
            us._action_create_universe(universe_id="u2", text="hi", visibility="private")
        )
        assert out["visibility"] == "private"
        assert vis.is_declared("u2")
        assert vis.universe_visibility("u2") is vis.PRIVATE

    def test_create_rejects_invalid_visibility_without_partial_dir(self, base):
        _anonymous()
        out = json.loads(
            us._action_create_universe(universe_id="u3", text="hi", visibility="wide-open")
        )
        assert "error" in out
        assert not (base / "u3").exists()  # rejected before mkdir; no partial create


class TestCreationRequiresAnOwner:
    """No unowned universe, ever (founder rule 2026-08-28).

    `_action_create_universe` used to fall through to `founder_id: ""` — it created
    the universe, granted nobody, bound nobody, and reported success. Nothing in
    production reached that branch, which made it latent rather than live; "no caller
    does that today" is exactly the reasoning that has been wrong twice in this repo.
    """

    def test_an_anonymous_caller_cannot_create_a_universe(self, base):
        _anonymous()
        out = json.loads(us._action_create_universe(universe_id="u-orphan", text="hi"))
        assert "error" in out, f"anonymous create was allowed: {out}"
        assert "belong to someone" in out["error"]
        assert out.get("status") != "created"

    def test_the_refusal_leaves_no_partial_universe_behind(self, base):
        """A bare directory reads as a LIVING home to `get_status` and would announce
        a broken universe — so the rollback matters as much as the refusal."""
        _anonymous()
        json.loads(us._action_create_universe(universe_id="u-orphan2", text="hi"))
        assert not (base / "u-orphan2").exists()

    def test_no_acl_row_or_home_binding_is_left_for_a_refused_create(self, base):
        """The refusal must not half-register the universe either."""
        from tinyassets.daemon_server import list_universe_acl

        _anonymous()
        json.loads(us._action_create_universe(universe_id="u-orphan3", text="hi"))
        assert list_universe_acl(base, universe_id="u-orphan3") == []

    def test_an_authenticated_caller_still_gets_an_owner_and_a_home(self, base):
        _authenticate("user_01REAL")
        out = json.loads(us._action_create_universe(universe_id="u-owned", text="hi"))
        assert out["founder_id"] == "user_01REAL", (
            "the accept direction: a gate that refuses everyone is not a gate"
        )
        from tinyassets.daemon_server import get_founder_home, universe_access_permission

        assert universe_access_permission(
            base, universe_id="u-owned", actor_id="user_01REAL"
        ) == "admin"
        assert get_founder_home(base, "user_01REAL") == "u-owned"
