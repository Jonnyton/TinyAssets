"""T1 — migrations apply cleanly, core tables + extensions present."""

from __future__ import annotations


def test_extensions_present(db):
    with db.cursor() as cur:
        cur.execute("SELECT extname FROM pg_extension WHERE extname IN ('vector','pgcrypto')")
        rows = {r[0] for r in cur.fetchall()}
    assert rows == {"vector", "pgcrypto"}


def test_core_tables_present(db):
    expected = {"users", "nodes", "artifact_field_visibility"}
    with db.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename = ANY(%s)",
            (list(expected),),
        )
        rows = {r[0] for r in cur.fetchall()}
    assert rows == expected


def test_rls_enabled_on_sensitive_tables(db):
    with db.cursor() as cur:
        cur.execute(
            "SELECT tablename, rowsecurity FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename IN ('nodes','artifact_field_visibility')"
        )
        rows = dict(cur.fetchall())
    assert rows == {"nodes": True, "artifact_field_visibility": True}
