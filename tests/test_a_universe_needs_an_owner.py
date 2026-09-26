"""A universe exists because an ownership row says so, not because a folder is
on disk.

The founder read a universe count and said:

    a universe should only exist if it belongs to a user and I'm really the
    only user and have made only the universe that was created when I workos
    logged in for the first time

The definition used to be "any directory under the data root whose name is not
one of four hardcoded operational names" (``_TOP_LEVEL_OPERATIONAL_DATA_DIRS`` =
``lance``/``output``/``runs``/``wiki``), so a migration backup, a past prune's
archive, and every operational store the denylist had not heard of became a
universe: enumerated, declared ``public`` by the boot backfill, and readable by
id.

The denylist could not be completed either. Five live stores were already
missing from it -- daemon memory, retained user inputs, the brain's vector store
(``lancedb``, which is not the listed ``lance``), the workspace pool, and stored
offers -- and every store added next month would need another name.

What every reader asks instead is one question: **does an ownership row name
this directory?** ``universe_acl`` grants and ``founder_home`` bindings are the
union, because first contact binds the home before any grant is written and a
universe with a live founder must not depend on which landed first.

Routed here: the listing, both direct-id readers (``inspect``, ``switch``),
the ``available`` list both of them publish on a miss, the visibility
backfill/startup enumeration, and both default/home resolvers.

NOT routed, deliberately:
  * ``sync_universes_from_filesystem`` -- a path INDEX, not the definition. A
    self-hoster restoring a directory from a backup needs it indexed before
    anything can grant on it. Indexed is not owned, and this file proves an
    indexed-but-unowned directory is still invisible.
  * ``tinyassets.reset.universe_dirs`` -- a DESTRUCTIVE reader. A cut needs a
    positive reason to believe a directory was a universe, which is a separate
    lane; conflating it with this predicate would have made ``reset`` start
    sparing directories on a read-only change.

Unowned directories become invisible and unreadable. Nothing here deletes.

One harness note that decides what these tests prove: ``conftest``'s autouse
``_emulate_deployed_visibility_backfill`` makes an UNDECLARED universe resolve
``public`` in every module but ``test_universe_visibility``. So the visibility
gate hides nothing here, and every refusal below is the ownership predicate
doing the work -- which is the stricter arrangement and the one worth asserting.
Where a test's subject IS the visibility gate it says so and uses a second
account, because a granted reader is exempt from its own universe's level.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tinyassets.api.helpers as helpers
import tinyassets.api.universe as us
import tinyassets.api.visibility as vis
from tinyassets.daemon_server import (
    ensure_universe_registered,
    grant_universe_access,
    owned_universe_id,
    owned_universe_ids,
    set_founder_home,
    sync_universes_from_filesystem,
)

# The name a past prune gave its archive, and the name production actually held.
ARCHIVE = "_removed_universes_20260829"
# Operational stores the four-name denylist never covered.
UNLISTED_STORES = ("lancedb", "daemon_wikis", "cloud-automation-inputs", "scratch")


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    return root


def _owned_universe(base: Path, uid: str, owner: str, *, level: str = "public") -> Path:
    """A real universe: a directory, an admin grant, and a declared level."""
    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    (udir / "soul.md").write_text(f"# {uid}\n", encoding="utf-8")
    ensure_universe_registered(base, universe_id=uid, universe_path=udir)
    grant_universe_access(
        base, universe_id=uid, actor_id=owner, permission="admin", granted_by=owner,
    )
    vis.set_universe_visibility(uid, level)
    return udir


def _bare_directory(base: Path, name: str) -> Path:
    """A directory nobody owns. What the platform's own operations leave behind."""
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "soul.md").write_text(f"# {name}\n", encoding="utf-8")
    (d / "status.json").write_text(json.dumps({"phase": "idle"}), encoding="utf-8")
    return d


def _boot_backfill(base: Path) -> dict[str, str]:
    """What the daemon runs at boot, and how the archive became ``public``.

    ``backfill_universe_visibility`` declares a level for every id
    ``_discover_universe_ids`` returns. With the denylist as the definition it
    registered the archive as a universe and declared it ``public`` (the
    ``public_read`` default), which is what made the graveyard both listable and
    readable.
    """
    return vis.backfill_universe_visibility()


def _listed_ids(base: Path) -> list[str]:
    return [u["id"] for u in json.loads(us._action_list_universes())["universes"]]


def _filesystem_is_case_sensitive(base: Path) -> bool:
    """Probed, never assumed from the platform name.

    A case-sensitive volume mounted on Windows and a case-insensitive one on
    Linux both exist, and the state under test -- two spellings of one name side
    by side -- is reachable only where the volume keeps them apart.
    """
    probe = base / ".case-probe-Aa"
    probe.mkdir()
    try:
        return not (base / ".case-probe-aA").exists()
    finally:
        probe.rmdir()


# --------------------------------------------------------------------------- #
# 1. The leak, reproduced. Every assertion here is RED without the predicate.
# --------------------------------------------------------------------------- #


class TestTheGraveyardWasBrowsable:
    def test_an_archive_directory_is_not_listed(self, base, signed_in):
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        _bare_directory(base, ARCHIVE)
        _boot_backfill(base)

        assert _listed_ids(base) == ["u-mine"]

    def test_reading_an_archive_directory_by_id_is_refused(self, base, signed_in):
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        _bare_directory(base, ARCHIVE)
        _boot_backfill(base)

        result = json.loads(us._action_inspect_universe(universe_id=ARCHIVE))

        # Filtering the enumeration is only half: reading one BY ID answered
        # with a full universe payload, reproduced against production.
        assert "not found" in result.get("error", "")
        assert "daemon" not in result
        assert "soul" not in result

    def test_switching_to_an_archive_directory_is_refused(self, base, signed_in):
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        _bare_directory(base, ARCHIVE)
        _boot_backfill(base)

        result = json.loads(us._action_switch_universe(universe_id=ARCHIVE))

        assert "not found" in result.get("error", "")
        assert result.get("status") != "selected"

    def test_a_not_found_answer_does_not_publish_the_graveyard(self, base, signed_in):
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        _bare_directory(base, ARCHIVE)
        for name in UNLISTED_STORES:
            _bare_directory(base, name)
        _boot_backfill(base)

        result = json.loads(us._action_inspect_universe(universe_id="no-such-universe"))

        assert result.get("available") == ["u-mine"]

    def test_switch_not_found_does_not_publish_the_graveyard(self, base, signed_in):
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        _bare_directory(base, ARCHIVE)
        _boot_backfill(base)

        result = json.loads(us._action_switch_universe(universe_id="no-such-universe"))

        assert result.get("available") == ["u-mine"]

    def test_a_not_found_answer_still_honours_the_enumeration_gate(self, base, signed_in):
        """``available`` is an enumeration, so the level that withholds
        discovery withholds it here too -- otherwise a wrong id published every
        owned universe, including another account's unlisted one.

        The unlisted universe belongs to a DIFFERENT account on purpose: a
        granted reader is exempt from their own universe's level, so asking as
        its owner would assert a refusal that cannot happen.
        """
        _owned_universe(base, "u-public", "workos|other", level="public")
        _owned_universe(base, "u-unlisted", "workos|other", level="unlisted")
        signed_in("workos|stranger")

        result = json.loads(us._action_inspect_universe(universe_id="no-such-universe"))

        assert result.get("available") == ["u-public"]

    @pytest.mark.parametrize("name", UNLISTED_STORES)
    def test_an_operational_store_the_denylist_missed_is_not_a_universe(
        self, base, signed_in, name,
    ):
        """No name needs adding to any list: these were never owned."""
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        _bare_directory(base, name)
        _boot_backfill(base)

        assert _listed_ids(base) == ["u-mine"]
        assert "not found" in json.loads(
            us._action_inspect_universe(universe_id=name)
        ).get("error", "")

    def test_the_boot_backfill_does_not_declare_an_unowned_directory(
        self, base, signed_in,
    ):
        """The step that TURNED the archive public. It declared a level for
        every directory the denylist allowed, which is how an archive got the
        ``public`` row that made it listable.

        Asserted against the DURABLE ROWS rather than the resolver, because the
        harness emulation answers ``public`` for an undeclared universe -- the
        artefact the backfill leaves behind is the honest oracle here.
        """
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id, level="private")
        _bare_directory(base, ARCHIVE)

        written = _boot_backfill(base)

        assert ARCHIVE not in written

        from tinyassets.storage import _connect

        with _connect(base) as conn:
            assert conn.execute(
                "SELECT 1 FROM universe_rules WHERE universe_id = ?", (ARCHIVE,),
            ).fetchone() is None
            assert conn.execute(
                "SELECT 1 FROM universes WHERE universe_id = ?", (ARCHIVE,),
            ).fetchone() is None

    def test_the_readiness_gate_does_not_wait_on_an_unowned_directory(
        self, base, signed_in,
    ):
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        _bare_directory(base, ARCHIVE)

        assert ARCHIVE not in vis._discover_universe_ids()


# --------------------------------------------------------------------------- #
# 2. The default / home resolvers. A pointer is not a grant.
# --------------------------------------------------------------------------- #


class TestTheResolversAskTheSameQuestion:
    def test_the_default_resolver_skips_an_unowned_directory(self, base, signed_in):
        """``_aaa-scratch`` sorts before ``u-mine``, and the resolver returned
        the first non-hidden directory -- so an operational store sorting first
        was handed out as the default universe."""
        owner = signed_in("workos|founder")
        _bare_directory(base, "_aaa-scratch")
        _owned_universe(base, "u-mine", owner.user_id)

        assert helpers._default_universe() == "u-mine"

    def test_the_public_landing_resolver_skips_an_unowned_directory(
        self, base, signed_in,
    ):
        owner = signed_in("workos|founder")
        _bare_directory(base, "_aaa-scratch")
        _owned_universe(base, "aaa-public", owner.user_id)

        assert helpers._designated_public_universe() == "aaa-public"

    def test_an_active_universe_marker_is_a_pointer_not_a_grant(self, base, signed_in):
        """``.active_universe`` was returned before any ownership check, so a
        stale marker routed requests into an operational directory."""
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        _bare_directory(base, ARCHIVE)
        (base / ".active_universe").write_text(ARCHIVE, encoding="utf-8")

        assert helpers._default_universe() == "u-mine"

    def test_a_configured_default_is_a_pointer_not_a_grant(
        self, base, signed_in, monkeypatch,
    ):
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        _bare_directory(base, "scratch")
        monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "scratch")

        assert helpers._default_universe() == "u-mine"
        assert helpers._designated_public_universe() == "u-mine"

    def test_a_configured_default_still_answers_on_a_fresh_install(
        self, base, monkeypatch,
    ):
        """Nothing is owned yet because nothing has been created yet. The
        configured name is what the install is about to create, and it never
        wins over a real universe (the test above)."""
        monkeypatch.setenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", "first-universe")

        assert helpers._default_universe() == "first-universe"
        assert helpers._designated_public_universe() == "first-universe"

    def test_an_unowned_data_root_resolves_to_the_literal_default(self, base):
        _bare_directory(base, ARCHIVE)

        assert helpers._default_universe() == "default-universe"
        assert helpers._designated_public_universe() == "default-universe"


# --------------------------------------------------------------------------- #
# 3. Nothing an OWNED universe could do before is lost.
# --------------------------------------------------------------------------- #


class TestOwnedUniversesKeepEverything:
    def test_an_acl_grant_alone_makes_a_universe(self, base, signed_in):
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-acl-only", owner.user_id)

        assert _listed_ids(base) == ["u-acl-only"]
        result = json.loads(us._action_inspect_universe(universe_id="u-acl-only"))
        assert result["universe_id"] == "u-acl-only"
        assert result["has_soul"] is True

    def test_a_founder_home_binding_alone_makes_a_universe(self, base, signed_in):
        """First contact binds the home BEFORE any grant is written. A universe
        with a live founder must not depend on which landed first."""
        owner = signed_in("workos|founder")
        udir = base / "u-home-only"
        udir.mkdir()
        (udir / "soul.md").write_text("# home\n", encoding="utf-8")
        ensure_universe_registered(base, universe_id="u-home-only", universe_path=udir)
        set_founder_home(base, founder_sub=owner.user_id, universe_id="u-home-only")
        vis.set_universe_visibility("u-home-only", "public")

        assert _listed_ids(base) == ["u-home-only"]
        assert json.loads(
            us._action_inspect_universe(universe_id="u-home-only")
        )["universe_id"] == "u-home-only"

    def test_a_write_only_collaborator_grant_still_makes_it_a_universe(
        self, base, signed_in,
    ):
        """Ownership here is "somebody has a row", not "somebody is admin".
        A universe shared write-only is still somebody's."""
        signed_in("workos|founder")
        udir = base / "u-shared"
        udir.mkdir()
        ensure_universe_registered(base, universe_id="u-shared", universe_path=udir)
        grant_universe_access(
            base, universe_id="u-shared", actor_id="workos|collab",
            permission="write", granted_by="workos|founder",
        )
        vis.set_universe_visibility("u-shared", "public")

        assert _listed_ids(base) == ["u-shared"]

    def test_two_accounts_one_code_path(self, base, signed_in):
        """The founder's universe and a second account's universe are owned the
        same way and read through the same predicate -- no free/paid branch."""
        founder = signed_in("workos|founder")
        second = signed_in("workos|second-account")
        _owned_universe(base, "u-founder", founder.user_id)
        _owned_universe(base, "u-second", second.user_id)
        _bare_directory(base, ARCHIVE)
        _boot_backfill(base)

        assert _listed_ids(base) == ["u-founder", "u-second"]
        for uid in ("u-founder", "u-second"):
            assert json.loads(
                us._action_inspect_universe(universe_id=uid)
            )["universe_id"] == uid

    def test_the_operational_denylist_names_are_still_not_universes(
        self, base, signed_in,
    ):
        """The four names the denylist carried stay excluded -- by ownership,
        which is why the list itself is gone."""
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        for name in ("lance", "output", "runs", "wiki"):
            _bare_directory(base, name)
        _boot_backfill(base)

        assert _listed_ids(base) == ["u-mine"]

    def test_the_founder_home_still_resolves_on_an_omitted_scope(
        self, base, signed_in,
    ):
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        set_founder_home(base, founder_sub=owner.user_id, universe_id="u-mine")
        _bare_directory(base, "_aaa-scratch")

        assert json.loads(us._action_inspect_universe())["universe_id"] == "u-mine"


# --------------------------------------------------------------------------- #
# 4. One definition of ownership, and its edges.
# --------------------------------------------------------------------------- #


class TestOneDefinition:
    def test_owned_universe_ids_is_the_union_of_both_stores(self, base, signed_in):
        owner = signed_in("workos|founder")
        grant_universe_access(
            base, universe_id="u-acl", actor_id=owner.user_id,
            permission="admin", granted_by=owner.user_id,
        )
        set_founder_home(base, founder_sub=owner.user_id, universe_id="u-home")

        assert owned_universe_ids(base) == {"u-acl", "u-home"}

    def test_a_directory_restored_under_a_different_case_is_still_owned(
        self, base, signed_in,
    ):
        """The prune matched case-insensitively while the listing compared
        exactly, so a restored ``U-Mine`` was protected from the cut and
        invisible in every list at the same time."""
        owner = signed_in("workos|founder")
        udir = base / "U-Mine"
        udir.mkdir()
        (udir / "soul.md").write_text("# restored\n", encoding="utf-8")
        ensure_universe_registered(base, universe_id="U-Mine", universe_path=udir)
        grant_universe_access(
            base, universe_id="u-mine", actor_id=owner.user_id,
            permission="admin", granted_by=owner.user_id,
        )
        vis.set_universe_visibility("U-Mine", "public")

        assert owned_universe_id(base, "U-Mine") == "u-mine"
        assert _listed_ids(base) == ["U-Mine"]

    def test_a_pointer_resolves_to_the_directory_not_the_acl_spelling(
        self, base, signed_in,
    ):
        """A pointer names a DIRECTORY, so the answer is the directory's own
        spelling. Returning the ACL id hands the caller a path that does not
        exist on a case-sensitive filesystem.

        Two directions, because the resolver has two branches. Here the pointer
        matches no directory exactly and the case-folded fallback answers.
        """
        owner = signed_in("workos|founder")
        udir = base / "U-Mine"
        udir.mkdir()
        ensure_universe_registered(base, universe_id="U-Mine", universe_path=udir)
        grant_universe_access(
            base, universe_id="u-mine", actor_id=owner.user_id,
            permission="admin", granted_by=owner.user_id,
        )

        assert helpers._owned_universe_dir_name(base, "u-mine") == "U-Mine"
        assert (base / helpers._owned_universe_dir_name(base, "u-mine")).is_dir()

    def test_an_exact_pointer_answers_its_own_spelling_not_the_rows(
        self, base, signed_in,
    ):
        """The EXACT-match branch. The pointer names a directory that exists,
        and the ownership row spells the id differently -- the answer is still
        the directory, because the caller is about to open it."""
        owner = signed_in("workos|founder")
        udir = base / "u-mine"
        udir.mkdir()
        ensure_universe_registered(base, universe_id="u-mine", universe_path=udir)
        grant_universe_access(
            base, universe_id="U-Mine", actor_id=owner.user_id,
            permission="admin", granted_by=owner.user_id,
        )

        assert owned_universe_id(base, "u-mine") == "U-Mine"  # the ROW's spelling
        assert helpers._owned_universe_dir_name(base, "u-mine") == "u-mine"
        assert (base / helpers._owned_universe_dir_name(base, "u-mine")).is_dir()

    def test_a_dotted_pointer_is_refused_by_the_definition_itself(
        self, base, signed_in,
    ):
        """``owned_universe_id`` carries the authoritative dot guard: its scan
        is over ROWS, which have no directory to skip, so without it a row
        naming ``.deleting`` would make the staging directory an owned id."""
        owner = signed_in("workos|founder")
        grant_universe_access(
            base, universe_id=".deleting", actor_id=owner.user_id,
            permission="admin", granted_by=owner.user_id,
        )

        assert ".deleting" in owned_universe_ids(base)  # the row is really there
        assert owned_universe_id(base, ".deleting") == ""

    def test_an_exact_match_wins_over_a_case_folded_one(self, base, signed_in):
        """With both spellings present, the exact pointer must open the exact
        directory -- case-folding finds a restored directory, it never prefers
        one over the name the caller gave.

        Only reachable on a case-SENSITIVE filesystem; Windows folds the two
        ``mkdir`` calls into one directory, so the state under test cannot
        exist there.
        """
        if not _filesystem_is_case_sensitive(base):
            pytest.skip("two spellings cannot coexist on a case-insensitive filesystem")

        owner = signed_in("workos|founder")
        for uid in ("U-Mine", "u-mine"):
            (base / uid).mkdir()
            ensure_universe_registered(base, universe_id=uid, universe_path=base / uid)
            grant_universe_access(
                base, universe_id=uid, actor_id=owner.user_id,
                permission="admin", granted_by=owner.user_id,
            )

        assert helpers._owned_universe_dir_name(base, "u-mine") == "u-mine"
        assert helpers._owned_universe_dir_name(base, "U-Mine") == "U-Mine"

    def test_a_lowercase_directory_with_a_mixed_case_row_is_owned(
        self, base, signed_in,
    ):
        """The MIRROR of the restore case, and the reason ownership folds both
        sides. Folding only the directory name matches a lowercase row against
        ``U-Mine/`` and misses a ``u-mine/`` directory whose row was written
        ``U-Mine`` -- the same universe, invisible."""
        owner = signed_in("workos|founder")
        udir = base / "u-mine"
        udir.mkdir()
        (udir / "soul.md").write_text("# mine\n", encoding="utf-8")
        ensure_universe_registered(base, universe_id="u-mine", universe_path=udir)
        grant_universe_access(
            base, universe_id="U-Mine", actor_id=owner.user_id,
            permission="admin", granted_by=owner.user_id,
        )

        assert us._name_is_owned("u-mine", {"U-Mine"}) is True
        assert owned_universe_id(base, "u-mine") == "U-Mine"
        assert _listed_ids(base) == ["u-mine"]

    def test_a_dotted_name_is_never_a_universe(self, base, signed_in):
        """Whatever the ACL says. ``.deleting/`` is account deletion's staging
        directory, and a row naming it must not make it readable."""
        owner = signed_in("workos|founder")
        (base / ".deleting").mkdir()
        grant_universe_access(
            base, universe_id=".deleting", actor_id=owner.user_id,
            permission="admin", granted_by=owner.user_id,
        )

        assert owned_universe_id(base, ".deleting") == ""
        assert helpers._owned_universe_dir_name(base, ".deleting") == ""
        assert ".deleting" not in _listed_ids(base)

    def test_an_owned_id_with_no_directory_is_not_a_readable_universe(
        self, base, signed_in,
    ):
        """An ownership row is necessary, not sufficient: the directory has to
        be there too."""
        owner = signed_in("workos|founder")
        grant_universe_access(
            base, universe_id="u-vanished", actor_id=owner.user_id,
            permission="admin", granted_by=owner.user_id,
        )

        assert _listed_ids(base) == []
        assert "not found" in json.loads(
            us._action_inspect_universe(universe_id="u-vanished")
        ).get("error", "")

    def test_an_unreadable_ownership_store_says_so_rather_than_not_found(
        self, base, signed_in, monkeypatch,
    ):
        """Returning "" on a failed read refused the request as "not found",
        which tells a caller an existing universe does not exist -- a lie, from
        a transient SQLite lock. Fail closed AND loudly."""
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)

        import tinyassets.daemon_server as ds

        def _boom(*_a, **_k):
            raise RuntimeError("database is locked")

        monkeypatch.setattr(ds, "owned_universe_id", _boom)

        result = json.loads(us._action_inspect_universe(universe_id="u-mine"))
        assert "not found" not in result.get("error", "")
        assert "unavailable" in result.get("error", "").lower()

        switched = json.loads(us._action_switch_universe(universe_id="u-mine"))
        assert "unavailable" in switched.get("error", "").lower()

    def test_an_unreadable_ownership_store_publishes_nothing(
        self, base, signed_in, monkeypatch,
    ):
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)

        import tinyassets.daemon_server as ds

        monkeypatch.setattr(
            ds, "owned_universe_ids",
            lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("locked")),
        )

        assert us._available_universe_ids() == []


# --------------------------------------------------------------------------- #
# 5. Indexed is not owned.
# --------------------------------------------------------------------------- #


class TestTheIndexIsNotTheDefinition:
    def test_the_path_index_stays_unfiltered_and_shows_nobody_anything(
        self, base, signed_in,
    ):
        """A self-hoster restoring a directory from a backup needs it indexed
        before anything can grant on it -- so the index takes everything, and
        the readers still refuse it."""
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        _bare_directory(base, ARCHIVE)

        sync_universes_from_filesystem(base)

        from tinyassets.storage import _connect

        with _connect(base) as conn:
            indexed = {
                str(row[0])
                for row in conn.execute("SELECT universe_id FROM universes")
            }
        assert ARCHIVE in indexed

        assert owned_universe_id(base, ARCHIVE) == ""
        assert _listed_ids(base) == ["u-mine"]
        assert "not found" in json.loads(
            us._action_inspect_universe(universe_id=ARCHIVE)
        ).get("error", "")

    def test_an_unowned_directory_is_not_deleted(self, base, signed_in):
        """Invisible and unreadable, never removed. The cut is a separate lane
        with a dry-run inventory first."""
        owner = signed_in("workos|founder")
        _owned_universe(base, "u-mine", owner.user_id)
        archive = _bare_directory(base, ARCHIVE)

        _boot_backfill(base)
        _listed_ids(base)
        us._action_inspect_universe(universe_id=ARCHIVE)

        assert archive.is_dir()
        assert (archive / "soul.md").is_file()
