"""Origin is an immutable admitted fact, never guessed from file presence."""

import pytest

from tests.test_run_input_admissions import accept, conn  # noqa: F401
from tinyassets.run_input_origin import OriginHeld, decode_origin, encode_origin
from tinyassets.storage import run_input_admissions as admissions


def test_stamp_replay_conflict_and_exact_original_options(conn):  # noqa: F811
    options = {"recursion_limit": 7, "concurrency_budget_override": 3}
    row = accept(conn, origin_kind="direct", origin_version=1, origin_options=options)
    assert decode_origin(row) == options
    assert accept(conn, origin_kind="direct", origin_version=1, origin_options=options) == row
    for changes in (
        {"origin_kind": "canonical_consumer", "origin_options": {}},
        {"origin_options": {**options, "recursion_limit": 8}},
    ):
        values = dict(origin_kind="direct", origin_version=1, origin_options=options)
        values.update(changes)
        with pytest.raises(admissions.RunInputRefused, match="conflict"):
            accept(conn, **values)


def test_legacy_remains_unknown_not_inferred_or_relabelled(conn):  # noqa: F811
    legacy = accept(conn)
    with pytest.raises(OriginHeld, match="unknown"):
        decode_origin(legacy)
    with pytest.raises(admissions.RunInputRefused, match="conflict"):
        accept(conn, origin_kind="canonical_consumer", origin_version=1, origin_options={})


@pytest.mark.parametrize("options", [
    {}, {"recursion_limit": True, "concurrency_budget_override": None},
    {"recursion_limit": 0, "concurrency_budget_override": None},
    {"recursion_limit": 100, "concurrency_budget_override": False},
    {"recursion_limit": 100, "concurrency_budget_override": 0},
    {"recursion_limit": 100, "concurrency_budget_override": None, "provider": "secret"},
])
def test_direct_options_are_strict_and_have_no_authority_selectors(options):
    with pytest.raises(OriginHeld):
        encode_origin("direct", 1, options)


@pytest.mark.parametrize("kind,version", [("", 0), ("future", 1), ("direct", True), ("direct", 2)])
def test_unknown_origins_hold(kind, version):
    with pytest.raises(OriginHeld):
        encode_origin(kind, version, {})


def test_additive_legacy_schema_upgrade_retains_unknown_defaults(conn):  # noqa: F811
    conn.execute("DROP TABLE run_input_admissions")
    conn.execute("CREATE TABLE run_input_admissions(run_id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO run_input_admissions VALUES('old')")
    admissions.ensure_schema(conn)
    row = dict(conn.execute("SELECT * FROM run_input_admissions").fetchone())
    assert row == {"run_id": "old", "origin_kind": "", "origin_version": 0,
                   "origin_options_json": "{}"}
    assert conn.in_transaction
