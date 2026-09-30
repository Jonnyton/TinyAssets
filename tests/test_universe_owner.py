"""One owning account per universe -- the resolver storage and seats both charge.

account-storage-quota D2 (founder decisions 2026-09-30): the owner is written by
the creation transaction, backfilled ONLY from `founder_home`, never inferred from
`universe_acl`, and the tier is the subscription on the account's home universe.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import tinyassets.api.universe as us
import tinyassets.daemon_server as ds
from tinyassets import universe_owner as uo
from tinyassets.daemon_server import (
    grant_universe_access,
    grant_universe_ownership,
    initialize_author_server,
    set_founder_home,
)
from tinyassets.storage.subscription_state import TIER_FREE, TIER_PAID

A = "workos|alice"
B = "workos|bob"


@pytest.fixture
def base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(root))
    monkeypatch.delenv("UNIVERSE_SERVER_DEFAULT_UNIVERSE", raising=False)
    return root


def _owner_rows(base: Path) -> list[tuple[str, str, str]]:
    with sqlite3.connect(ds.db_path(base)) as conn:
        return conn.execute(
            "SELECT universe_id, owner_id, source FROM universe_owner ORDER BY universe_id"
        ).fetchall()


def _set_paid(universe_dir: Path) -> None:
    from tinyassets.storage import subscription_state as ss

    conn = ss._connect(universe_dir)
    try:
        conn.executescript(ss._SCHEMA)
        conn.execute(
            "INSERT OR REPLACE INTO subscription_meta (key, value) VALUES ('tier', ?)",
            (TIER_PAID,),
        )
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Creation writes the owner, atomically with the grant
# --------------------------------------------------------------------------- #


class TestCreationRecordsTheOwner:
    def test_a_created_universe_is_owned_by_its_creator(self, base, signed_in):
        signed_in(A)
        uid = json.loads(us._action_create_universe(text="a seed."))["universe_id"]

        assert uo.owner_of(base, uid) == A
        assert _owner_rows(base) == [(uid, A, uo.SOURCE_CREATION)]
        assert uo.owned_universes(base, A) == [uid]

    def test_a_second_universe_joins_the_same_account(self, base, signed_in):
        signed_in(A)
        first = json.loads(us._action_create_universe(text="one."))["universe_id"]
        second = json.loads(us._action_create_universe(text="two."))["universe_id"]

        assert uo.owned_universes(base, A) == sorted([first, second])

    def test_a_failed_create_takes_the_owner_back_with_the_grant(
        self, base, signed_in, monkeypatch,
    ):
        signed_in(A)

        def _boom(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(us, "_normalize_escaped_text", _boom)
        out = json.loads(us._action_create_universe(universe_id="u-doomed", text="x"))

        assert "error" in out, out
        assert uo.owner_of(base, "u-doomed") is None
        assert uo.owned_universes(base, A) == []

    def test_ownership_never_moves_and_the_grant_rolls_back_with_it(self, base):
        grant_universe_ownership(base, universe_id="u-x", owner_id=A)

        with pytest.raises(uo.OwnershipConflict):
            grant_universe_ownership(base, universe_id="u-x", owner_id=B)

        assert uo.owner_of(base, "u-x") == A
        # B's admin grant was in the same transaction, so it is not there either.
        assert ds.universe_access_permission(base, universe_id="u-x", actor_id=B) != "admin"

    def test_a_repeated_grant_for_the_same_owner_is_idempotent(self, base):
        grant_universe_ownership(base, universe_id="u-x", owner_id=A)
        grant_universe_ownership(base, universe_id="u-x", owner_id=A)

        assert _owner_rows(base) == [("u-x", A, uo.SOURCE_CREATION)]

    def test_a_shared_universe_charges_only_its_owner(self, base):
        grant_universe_ownership(base, universe_id="u-x", owner_id=A)
        grant_universe_access(
            base, universe_id="u-x", actor_id=B, permission="admin", granted_by=A,
        )

        assert uo.owner_of(base, "u-x") == A
        assert uo.owned_universes(base, B) == []


# --------------------------------------------------------------------------- #
# Backfill: founder_home only, once
# --------------------------------------------------------------------------- #


def _legacy_db_without_owner_table(base: Path) -> None:
    """A pre-existing install: the author-server DB exists, the table does not."""
    initialize_author_server(base)
    with sqlite3.connect(ds.db_path(base)) as conn:
        conn.execute("DROP TABLE universe_owner")
    ds._AUTHOR_SERVER_INITIALIZED.discard(str(ds.db_path(base)))


class TestBackfill:
    def test_a_home_binding_is_backfilled(self, base):
        initialize_author_server(base)
        set_founder_home(base, founder_sub=A, universe_id="u-home-a")
        _legacy_db_without_owner_table(base)

        initialize_author_server(base)

        assert _owner_rows(base) == [("u-home-a", A, uo.SOURCE_FOUNDER_HOME)]

    def test_an_admin_grant_alone_is_never_inferred_to_be_an_owner(self, base):
        """The founder's rule: never infer identity from adjacent tables -- not
        even the self-granted admin row creation used to write."""
        initialize_author_server(base)
        (base / "u-legacy").mkdir()
        grant_universe_access(
            base, universe_id="u-legacy", actor_id=A, permission="admin", granted_by=A,
        )
        _legacy_db_without_owner_table(base)

        initialize_author_server(base)

        assert uo.owner_of(base, "u-legacy") is None
        assert uo.unattributed_universes(base) == ["u-legacy"]

    def test_a_universe_two_homes_point_at_stays_unattributed(self, base):
        initialize_author_server(base)
        set_founder_home(base, founder_sub=A, universe_id="u-shared")
        set_founder_home(base, founder_sub=B, universe_id="u-shared")
        _legacy_db_without_owner_table(base)

        initialize_author_server(base)

        assert uo.owner_of(base, "u-shared") is None

    def test_the_backfill_runs_once_so_a_later_rebind_owns_nothing(self, base):
        """A home rebound after the table exists must not re-own anything: only
        creation records owners from then on."""
        initialize_author_server(base)
        set_founder_home(base, founder_sub=A, universe_id="u-later")
        ds._AUTHOR_SERVER_INITIALIZED.discard(str(ds.db_path(base)))

        initialize_author_server(base)

        assert uo.owner_of(base, "u-later") is None


# --------------------------------------------------------------------------- #
# Tier: the home universe's subscription, free on anything else
# --------------------------------------------------------------------------- #


class TestTierOf:
    def test_no_home_is_free(self, base):
        assert uo.tier_of(base, A) == TIER_FREE

    def test_the_home_subscription_is_the_account_tier(self, base):
        initialize_author_server(base)
        home = base / "u-home"
        home.mkdir()
        set_founder_home(base, founder_sub=A, universe_id="u-home")
        _set_paid(home)

        assert uo.tier_of(base, A) == TIER_PAID
        assert uo.tier_of(base, B) == TIER_FREE

    def test_a_paid_non_home_universe_does_not_make_the_account_paid(self, base):
        initialize_author_server(base)
        (base / "u-home").mkdir()
        other = base / "u-other"
        other.mkdir()
        set_founder_home(base, founder_sub=A, universe_id="u-home")
        _set_paid(other)

        assert uo.tier_of(base, A) == TIER_FREE

    def test_a_traversal_home_is_free_not_read(self, base):
        initialize_author_server(base)
        set_founder_home(base, founder_sub=A, universe_id="../outside")

        assert uo.tier_of(base, A) == TIER_FREE

    def test_an_unnamed_principal_is_free(self, base):
        assert uo.tier_of(base, "") == TIER_FREE


# --------------------------------------------------------------------------- #
# Account deletion takes the person's owner rows
# --------------------------------------------------------------------------- #


def test_account_deletion_plans_the_owner_rows(base):
    from tinyassets.account_deletion import deletion_plan

    grant_universe_ownership(base, universe_id="u-x", owner_id=A)
    with sqlite3.connect(ds.db_path(base)) as conn:
        plan = deletion_plan(conn, principal=A, home="u-home")

    assert ("owner_id", "principal") in plan["universe_owner"]
