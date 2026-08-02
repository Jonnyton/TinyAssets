"""Static contract for reserved PostgreSQL migration 011.

Migration 010 belongs to a parallel lane. Migration 011 creates its own table
without that substrate and conditionally backfills once public.goals exists.
"""

from pathlib import Path

MIGRATION = (
    Path(__file__).parents[1]
    / "prototype"
    / "full-platform-v0"
    / "migrations"
    / "011_goal_canonicals.sql"
)


def test_migration_011_defines_actor_scoped_goal_canonicals():
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "CREATE TABLE public.goal_canonicals" in sql
    assert "PRIMARY KEY (goal_id, scope_actor)" in sql
    assert "IF to_regclass('public.goals') IS NOT NULL THEN" in sql
    for column in (
        "goal_id",
        "scope_actor",
        "branch_version_id",
        "set_at",
        "set_by",
    ):
        assert column in sql
    assert "goals.canonical_branch_version_id" in sql
