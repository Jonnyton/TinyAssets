"""Tests for workflow.attribution schema — DDL, dataclasses, N-generation chains."""

from __future__ import annotations

import sqlite3

import pytest

from workflow.attribution import (
    AttributionCredit,
    AttributionEdge,
    RemixProvenance,
    migrate_attribution_schema,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _edge_row(**overrides) -> dict:
    base = {
        "edge_id": "edge-1",
        "parent_id": "branch-A",
        "child_id": "branch-B",
        "parent_kind": "branch",
        "child_kind": "branch",
        "generation_depth": 1,
        "contribution_kind": "remix",
        "created_at": "2026-04-24T00:00:00Z",
    }
    base.update(overrides)
    return base


def _credit_row(**overrides) -> dict:
    base = {
        "credit_id": "cred-1",
        "artifact_id": "branch-B",
        "artifact_kind": "branch",
        "actor_id": "alice",
        "owner_user_id": "owner-alice",
        "daemon_id": "daemon::alice-worker",
        "runtime_instance_id": "runtime-1",
        "worker_id": "worker-1",
        "credit_share": 0.7,
        "royalty_share": 0.05,
        "generation_depth": 0,
        "contribution_kind": "original",
        "recorded_at": "2026-04-24T00:00:00Z",
    }
    base.update(overrides)
    return base


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrate_attribution_schema(conn)
    yield conn
    conn.close()


# ── AttributionEdge ────────────────────────────────────────────────────────────

class TestAttributionEdge:
    def test_from_row_round_trip(self):
        e = AttributionEdge.from_row(_edge_row())
        assert e.edge_id == "edge-1"
        assert e.parent_id == "branch-A"
        assert e.child_id == "branch-B"
        assert e.generation_depth == 1
        assert e.contribution_kind == "remix"

    def test_defaults_on_missing_optional_fields(self):
        row = {
            "edge_id": "e",
            "parent_id": "p",
            "child_id": "c",
            "created_at": "2026-01-01T00:00:00Z",
        }
        e = AttributionEdge.from_row(row)
        assert e.parent_kind == "branch"
        assert e.child_kind == "branch"
        assert e.generation_depth == 1
        assert e.contribution_kind == "remix"

    def test_generation_depth_zero_raises(self):
        with pytest.raises(ValueError, match="generation_depth"):
            AttributionEdge(**_edge_row(generation_depth=0))

    def test_invalid_parent_kind_raises(self):
        with pytest.raises(ValueError, match="parent_kind"):
            AttributionEdge(**_edge_row(parent_kind="universe"))

    def test_invalid_child_kind_raises(self):
        with pytest.raises(ValueError, match="child_kind"):
            AttributionEdge(**_edge_row(child_kind="universe"))

    def test_invalid_contribution_kind_raises(self):
        with pytest.raises(ValueError, match="contribution_kind"):
            AttributionEdge(**_edge_row(contribution_kind="borrowed"))

    def test_valid_contribution_kinds(self):
        for kind in ("original", "remix", "patch", "template"):
            e = AttributionEdge(**_edge_row(contribution_kind=kind))
            assert e.contribution_kind == kind

    def test_valid_artifact_kinds(self):
        for kind in ("branch", "node"):
            e = AttributionEdge(**_edge_row(parent_kind=kind, child_kind=kind))
            assert e.parent_kind == kind


# ── AttributionCredit ──────────────────────────────────────────────────────────

class TestAttributionCredit:
    def test_from_row_round_trip(self):
        c = AttributionCredit.from_row(_credit_row())
        assert c.credit_id == "cred-1"
        assert c.actor_id == "alice"
        assert c.owner_user_id == "owner-alice"
        assert c.daemon_id == "daemon::alice-worker"
        assert c.runtime_instance_id == "runtime-1"
        assert c.worker_id == "worker-1"
        assert c.credit_share == pytest.approx(0.7)
        assert c.royalty_share == pytest.approx(0.05)
        assert c.generation_depth == 0

    def test_schema_has_optional_identity_tuple_columns(self, db):
        columns = {
            row["name"]
            for row in db.execute("PRAGMA table_info(attribution_credit)")
        }
        assert {
            "owner_user_id",
            "daemon_id",
            "runtime_instance_id",
            "worker_id",
        } <= columns

    def test_is_original_author_true(self):
        c = AttributionCredit.from_row(_credit_row(generation_depth=0))
        assert c.is_original_author is True

    def test_is_original_author_false(self):
        c = AttributionCredit.from_row(_credit_row(generation_depth=2))
        assert c.is_original_author is False

    def test_credit_share_above_one_raises(self):
        with pytest.raises(ValueError, match="credit_share"):
            AttributionCredit(**_credit_row(credit_share=1.001))

    def test_credit_share_negative_raises(self):
        with pytest.raises(ValueError, match="credit_share"):
            AttributionCredit(**_credit_row(credit_share=-0.1))

    def test_royalty_share_above_one_raises(self):
        with pytest.raises(ValueError, match="royalty_share"):
            AttributionCredit(**_credit_row(royalty_share=1.5))

    def test_generation_depth_negative_raises(self):
        with pytest.raises(ValueError, match="generation_depth"):
            AttributionCredit(**_credit_row(generation_depth=-1))

    def test_invalid_artifact_kind_raises(self):
        with pytest.raises(ValueError, match="artifact_kind"):
            AttributionCredit(**_credit_row(artifact_kind="workflow"))

    def test_credit_share_boundary_zero(self):
        c = AttributionCredit(**_credit_row(credit_share=0.0))
        assert c.credit_share == 0.0

    def test_credit_share_boundary_one(self):
        c = AttributionCredit(**_credit_row(credit_share=1.0))
        assert c.credit_share == 1.0

    def test_defaults_on_missing_optional_fields(self):
        row = {
            "credit_id": "c",
            "artifact_id": "branch-X",
            "actor_id": "bob",
            "recorded_at": "2026-01-01T00:00:00Z",
        }
        c = AttributionCredit.from_row(row)
        assert c.artifact_kind == "branch"
        assert c.credit_share == pytest.approx(0.0)
        assert c.royalty_share == pytest.approx(0.0)
        assert c.generation_depth == 0
        assert c.contribution_kind == "original"
        assert c.owner_user_id == ""
        assert c.daemon_id == ""
        assert c.runtime_instance_id == ""
        assert c.worker_id == ""


# ── RemixProvenance ────────────────────────────────────────────────────────────

class TestRemixProvenance:
    def _make_credit(self, actor_id: str, credit_share: float, gen: int = 0) -> AttributionCredit:
        row = _credit_row()
        row.update(
            credit_id=f"cred-{actor_id}",
            actor_id=actor_id,
            credit_share=credit_share,
            generation_depth=gen,
        )
        return AttributionCredit.from_row(row)

    def _make_edge(self, parent: str, child: str, depth: int) -> AttributionEdge:
        return AttributionEdge.from_row(
            _edge_row(
                edge_id=f"edge-{parent}-{child}",
                parent_id=parent,
                child_id=child,
                generation_depth=depth,
            )
        )

    def test_total_credit_share_empty(self):
        prov = RemixProvenance(artifact_id="x", artifact_kind="branch")
        assert prov.total_credit_share == pytest.approx(0.0)

    def test_total_credit_share_single(self):
        prov = RemixProvenance(
            artifact_id="x",
            artifact_kind="branch",
            credits=[self._make_credit("alice", 0.6)],
        )
        assert prov.total_credit_share == pytest.approx(0.6)

    def test_is_credit_valid_within_bounds(self):
        prov = RemixProvenance(
            artifact_id="x",
            artifact_kind="branch",
            credits=[
                self._make_credit("alice", 0.6),
                self._make_credit("bob", 0.3),
            ],
        )
        assert prov.is_credit_valid is True

    def test_is_credit_valid_exactly_one(self):
        prov = RemixProvenance(
            artifact_id="x",
            artifact_kind="branch",
            credits=[
                self._make_credit("alice", 0.5),
                self._make_credit("bob", 0.5),
            ],
        )
        assert prov.is_credit_valid is True

    def test_is_credit_invalid_exceeds_one(self):
        prov = RemixProvenance(
            artifact_id="x",
            artifact_kind="branch",
            credits=[
                self._make_credit("alice", 0.7),
                self._make_credit("bob", 0.4),
            ],
        )
        assert prov.is_credit_valid is False

    def test_max_generation_depth_no_edges(self):
        prov = RemixProvenance(artifact_id="x", artifact_kind="branch")
        assert prov.max_generation_depth == 0

    def test_max_generation_depth_n_generation_chain(self):
        # A → B (depth 1), A → C (depth 2), A → D (depth 3)
        edges = [
            self._make_edge("A", "B", 1),
            self._make_edge("A", "C", 2),
            self._make_edge("A", "D", 3),
        ]
        prov = RemixProvenance(artifact_id="A", artifact_kind="branch", edges=edges)
        assert prov.max_generation_depth == 3

    def test_credits_for_actor_filters_correctly(self):
        alice_credit = self._make_credit("alice", 0.6)
        bob_credit = self._make_credit("bob", 0.3)
        prov = RemixProvenance(
            artifact_id="x",
            artifact_kind="branch",
            credits=[alice_credit, bob_credit],
        )
        assert prov.credits_for_actor("alice") == [alice_credit]
        assert prov.credits_for_actor("carol") == []

    def test_three_generation_chain_share_sum(self):
        # Alice (gen 0) = 60%, Bob (gen 1) = 25%, Carol (gen 2) = 10%
        # Remaining 5% = platform treasury
        credits = [
            self._make_credit("alice", 0.60, gen=0),
            self._make_credit("bob", 0.25, gen=1),
            self._make_credit("carol", 0.10, gen=2),
        ]
        prov = RemixProvenance(artifact_id="D", artifact_kind="branch", credits=credits)
        assert prov.is_credit_valid is True
        assert prov.total_credit_share == pytest.approx(0.95)


# ── DDL / Migration ───────────────────────────────────────────────────────────

class TestMigrateAttributionSchema:
    def test_tables_created(self, db):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor}
        assert "attribution_edge" in tables
        assert "attribution_credit" in tables

    def test_idempotent_double_call(self):
        conn = sqlite3.connect(":memory:")
        try:
            migrate_attribution_schema(conn)
            migrate_attribution_schema(conn)
        finally:
            conn.close()

    def test_idempotent_ten_calls(self):
        conn = sqlite3.connect(":memory:")
        try:
            for _ in range(10):
                migrate_attribution_schema(conn)
        finally:
            conn.close()


# ── SQLite integration ─────────────────────────────────────────────────────────

class TestDDLIntegration:
    def test_insert_edge(self, db):
        db.execute(
            """
            INSERT INTO attribution_edge
                (edge_id, parent_id, child_id, parent_kind, child_kind,
                 generation_depth, contribution_kind, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("e1", "branch-A", "branch-B", "branch", "branch", 1, "remix",
             "2026-04-24T00:00:00Z"),
        )
        db.commit()
        row = db.execute("SELECT * FROM attribution_edge WHERE edge_id='e1'").fetchone()
        assert row["parent_id"] == "branch-A"
        assert row["generation_depth"] == 1

    def test_insert_credit(self, db):
        db.execute(
            """
            INSERT INTO attribution_credit
                (credit_id, artifact_id, artifact_kind, actor_id,
                 credit_share, royalty_share, generation_depth,
                 contribution_kind, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("c1", "branch-B", "branch", "alice",
             0.7, 0.05, 0, "original", "2026-04-24T00:00:00Z"),
        )
        db.commit()
        row = db.execute("SELECT * FROM attribution_credit WHERE credit_id='c1'").fetchone()
        assert row["actor_id"] == "alice"
        assert abs(row["credit_share"] - 0.7) < 1e-9

    def test_duplicate_edge_rejected(self, db):
        db.execute(
            """INSERT INTO attribution_edge
               (edge_id, parent_id, child_id, parent_kind, child_kind,
                generation_depth, contribution_kind, created_at)
               VALUES ('e1','A','B','branch','branch',1,'remix','2026-04-24T00:00:00Z')"""
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO attribution_edge
                   (edge_id, parent_id, child_id, parent_kind, child_kind,
                    generation_depth, contribution_kind, created_at)
                   VALUES ('e2','A','B','branch','branch',1,'remix','2026-04-24T00:00:00Z')"""
            )

    def test_duplicate_credit_rejected(self, db):
        db.execute(
            """INSERT INTO attribution_credit
               (credit_id, artifact_id, artifact_kind, actor_id,
                credit_share, royalty_share, generation_depth,
                contribution_kind, recorded_at)
               VALUES ('c1','branch-B','branch','alice',
                       0.7,0.05,0,'original','2026-04-24T00:00:00Z')"""
        )
        db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO attribution_credit
                   (credit_id, artifact_id, artifact_kind, actor_id,
                    credit_share, royalty_share, generation_depth,
                    contribution_kind, recorded_at)
                   VALUES ('c2','branch-B','branch','alice',
                           0.3,0.0,0,'remix','2026-04-24T00:00:00Z')"""
            )

    def test_invalid_contribution_kind_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO attribution_edge
                   (edge_id, parent_id, child_id, parent_kind, child_kind,
                    generation_depth, contribution_kind, created_at)
                   VALUES ('e1','A','B','branch','branch',1,'borrowed','2026-04-24T00:00:00Z')"""
            )

    def test_credit_share_out_of_range_rejected(self, db):
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """INSERT INTO attribution_credit
                   (credit_id, artifact_id, artifact_kind, actor_id,
                    credit_share, royalty_share, generation_depth,
                    contribution_kind, recorded_at)
                   VALUES ('c1','branch-B','branch','alice',
                           1.5,0.0,0,'original','2026-04-24T00:00:00Z')"""
            )

    def test_edge_roundtrip_via_from_row(self, db):
        db.execute(
            """INSERT INTO attribution_edge
               (edge_id, parent_id, child_id, parent_kind, child_kind,
                generation_depth, contribution_kind, created_at)
               VALUES ('e1','branch-A','branch-B','branch','branch',
                       2,'patch','2026-04-24T00:00:00Z')"""
        )
        db.commit()
        row = dict(db.execute("SELECT * FROM attribution_edge WHERE edge_id='e1'").fetchone())
        edge = AttributionEdge.from_row(row)
        assert edge.generation_depth == 2
        assert edge.contribution_kind == "patch"

    def test_credit_roundtrip_via_from_row(self, db):
        db.execute(
            """INSERT INTO attribution_credit
               (credit_id, artifact_id, artifact_kind, actor_id,
                credit_share, royalty_share, generation_depth,
                contribution_kind, recorded_at)
               VALUES ('c1','branch-B','branch','bob',
                       0.25,0.02,1,'remix','2026-04-24T00:00:00Z')"""
        )
        db.commit()
        row = dict(db.execute("SELECT * FROM attribution_credit WHERE credit_id='c1'").fetchone())
        credit = AttributionCredit.from_row(row)
        assert credit.actor_id == "bob"
        assert credit.credit_share == pytest.approx(0.25)
        assert credit.generation_depth == 1
        assert credit.is_original_author is False
