"""Capability: an ordinary author sets the two branch-wide execution choices.

`BranchDefinition` declares exactly two workflow-wide execution choices --
``default_llm_policy`` and ``concurrency_budget`` (``tinyassets/branches.py``) --
and ``to_dict()`` emits both. PR #3933 made ``publish_branch_version`` preserve
set values into the immutable snapshot (``tinyassets/branch_versions.py``).

This module asserts the capability that change requires and that the earlier
diagnostic pass proved missing: through the SERVED surface an author can set,
read back, describe, clear and fork-inherit both choices, and a value the run
would silently reinterpret is refused at authoring time. It drives the real
route functions (`_ext_branch_build`, `_ext_branch_patch`, `_ext_branch_get`)
and the real storage helpers against a temp data dir with a credential-derived
request subject.

Red-first accounting, measured against the unfixed tree at `ff1320d5`: of the
45 collected cases in the capability pass, **29 were RED and 16 were GREEN**.
Not every assertion here is red-first, and this module does not claim so. The
16 green-on-both cases are the deliberately-kept compatibility pins (unknown-op
refusal, legacy-row absence, the unset snapshot form, unknown-spec-key
tolerance, the `validate_concurrency_budget` unit checks) and they are marked
as such at each site.

`TestLegacyDatabaseMigration` was added afterwards, in the verification pass,
and is NOT part of that 29/16 count. It was not executed against `ff1320d5`;
it reads columns that do not exist there, so it could not pass — that is
reasoning about the unfixed tree, not a measured red run.

No new action or field name is invented -- the two canonical fields above are
the only ones exercised.
"""

from __future__ import annotations

import json

import pytest

from tinyassets.branch_versions import publish_branch_version
from tinyassets.daemon_server import (
    get_branch_definition,
    initialize_author_server,
    save_branch_definition,
)

_SUBJECT = "exec-choice-author"

#: The canonical valid policy shape (`_validate_llm_policy_shape` reads
#: `policy["preferred"]["provider"]`).
_POLICY = {"preferred": {"provider": "codex"}}

#: A policy the validator explicitly rejects (the named footgun key).
_BAD_POLICY = {"preferred_provider": "codex"}

_FIELDS = ("default_llm_policy", "concurrency_budget")

#: Largest value a SQLite INTEGER column can represent.
_MAX_INT64 = 2**63 - 1


@pytest.fixture(autouse=True)
def _isolated_author(tmp_path, monkeypatch, authenticate_request):
    """Temp data dir + credential-derived subject.

    Both are required: the served authoring routes resolve the caller through
    `_request_branch_actor()` (never an env actor), and they write through
    `_base_path()`, which reads `TINYASSETS_DATA_DIR`.
    """
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    initialize_author_server(tmp_path)
    authenticate_request(_SUBJECT)


def _minimal_spec(**extra) -> dict:
    spec = {
        "name": "Execution choice probe",
        "domain_id": "workflow",
        "visibility": "private",
        "entry_point": "n1",
        "node_defs": [
            {
                "node_id": "n1",
                "display_name": "N1",
                "prompt_template": "do the thing",
            }
        ],
        "edges": [{"from": "n1", "to": "END"}],
    }
    spec.update(extra)
    return spec


def _build(spec: dict, **kwargs) -> dict:
    from tinyassets.api.branches import _ext_branch_build

    payload = {"spec_json": json.dumps(spec)}
    payload.update(kwargs)
    return json.loads(_ext_branch_build(payload))


def _patch(branch_def_id: str, ops: list[dict]) -> dict:
    from tinyassets.api.branches import _ext_branch_patch

    return json.loads(
        _ext_branch_patch(
            {"branch_def_id": branch_def_id, "changes_json": json.dumps(ops)}
        )
    )


def _read(branch_def_id: str) -> dict:
    from tinyassets.api.branches import _ext_branch_get

    return json.loads(_ext_branch_get({"branch_def_id": branch_def_id}))


def _receipt_choices(payload: dict) -> dict:
    """The applied execution choices the receipt echoes back to the author."""
    return payload["batch_receipt"]["execution_choices"]


def _definition_with_choices(branch_id: str = "seeded"):
    """An in-memory `BranchDefinition` carrying both choices."""
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )

    return BranchDefinition(
        branch_def_id=branch_id,
        name="Seeded with choices",
        author=_SUBJECT,
        visibility="private",
        graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
        edges=[EdgeDefinition(from_node="n1", to_node="END")],
        entry_point="n1",
        node_defs=[
            NodeDefinition(node_id="n1", display_name="N1", prompt_template="do X")
        ],
        state_schema=[],
        default_llm_policy=dict(_POLICY),
        concurrency_budget=4,
    )


def _seed(tmp_path, branch_id: str = "seeded") -> dict:
    """Persist that definition through the real storage writer."""
    return save_branch_definition(
        tmp_path, branch_def=_definition_with_choices(branch_id).to_dict()
    )


class TestPremises:
    """Guard the constants so this module fails loudly if the shapes move."""

    def test_valid_policy_validates_clean(self):
        assert _definition_with_choices().validate() == []

    def test_model_emits_both_fields(self):
        row = _definition_with_choices().to_dict()
        assert row["default_llm_policy"] == _POLICY
        assert row["concurrency_budget"] == 4


class TestStoragePersistsBothChoices:
    """The row writer carries both choices in their own additive columns.

    `_branch_definition_insert` builds the column tuple and
    `_BRANCH_DEFINITION_INSERT_SQL` names the columns; the migration adds
    `default_llm_policy_json TEXT` and `concurrency_budget INTEGER` through the
    `PRAGMA table_info` probe pattern. The choices are written in exactly one
    place -- the new columns -- and are NOT also folded into `graph_json`.
    """

    def test_save_round_trip_preserves_both_values(self, tmp_path):
        saved = _seed(tmp_path)
        assert saved["default_llm_policy"] == _POLICY
        assert saved["concurrency_budget"] == 4
        row = get_branch_definition(tmp_path, branch_def_id="seeded")
        assert row["default_llm_policy"] == _POLICY
        assert row["concurrency_budget"] == 4

    def test_rehydrated_definition_carries_both(self, tmp_path):
        from tinyassets.branches import BranchDefinition

        _seed(tmp_path)
        row = get_branch_definition(tmp_path, branch_def_id="seeded")
        rehydrated = BranchDefinition.from_dict(row)
        assert rehydrated.default_llm_policy == _POLICY
        assert rehydrated.concurrency_budget == 4
        assert rehydrated.entry_point == "n1"
        assert [n.node_id for n in rehydrated.node_defs] == ["n1"]

    def test_choices_are_not_double_written_into_graph_json(self, tmp_path):
        """One definition of one fact: the columns, never the topology blob."""
        from tinyassets.storage import _connect

        _seed(tmp_path)
        with _connect(tmp_path) as conn:
            graph_json, policy_json, budget = conn.execute(
                "SELECT graph_json, default_llm_policy_json, concurrency_budget "
                "FROM branch_definitions WHERE branch_def_id = 'seeded'"
            ).fetchone()
        graph = json.loads(graph_json)
        for field in _FIELDS:
            assert field not in graph, f"{field} double-written into graph_json"
        assert json.loads(policy_json) == _POLICY
        assert budget == 4

    def test_snapshot_from_a_stored_row_preserves_both(self, tmp_path):
        """The landed PR #3933 preservation becomes reachable from storage."""
        stored = _seed(tmp_path, "stored")
        snapshot = publish_branch_version(
            tmp_path, stored, publisher=_SUBJECT
        ).snapshot
        assert snapshot["default_llm_policy"] == _POLICY
        assert snapshot["concurrency_budget"] == 4

    def test_a_row_written_before_the_migration_reads_as_unset(self):
        """Guarded row read: a row lacking the columns is unset, not a crash.

        `_branch_def_from_row` reads both through the existing `row.keys()`
        guard, the `goal_id` precedent. Honestly still true of the unfixed
        tree -- kept because it is the backward-compatibility assertion.

        This is the reader-level guard only: the mapping below stands in for a
        row, it is not one. The real pre-migration SQLite table, the migration
        over it and the old-writer boundary are proven in
        `TestLegacyDatabaseMigration`.
        """
        from tinyassets.daemon_server import _branch_def_from_row

        legacy = {
            "branch_def_id": "legacy",
            "name": "Legacy",
            "description": "",
            "author": _SUBJECT,
            "domain_id": "workflow",
            "tags_json": "[]",
            "version": 1,
            "parent_def_id": None,
            "entry_point": "n1",
            "graph_json": "{}",
            "node_defs_json": "[]",
            "state_schema_json": "[]",
            "published": 0,
            "stats_json": "{}",
            "created_at": 1.0,
            "updated_at": 1.0,
        }
        result = _branch_def_from_row(legacy)
        assert result["default_llm_policy"] is None
        assert result["concurrency_budget"] is None

    def test_an_unset_branch_keeps_the_absent_key_snapshot_form(self, tmp_path):
        """No backfill, no hash-form change for a branch that sets neither.

        Honestly still true of the unfixed tree: it pins the form this change
        must not disturb.
        """
        built = _build(_minimal_spec())
        row = get_branch_definition(
            tmp_path, branch_def_id=built["branch_def_id"]
        )
        snapshot = publish_branch_version(
            tmp_path, row, publisher=_SUBJECT
        ).snapshot
        for field in _FIELDS:
            assert field not in snapshot


class TestBuildReadsSubmittedChoices:
    """`_staged_branch_from_spec` reads both choices from the spec.

    Presence is resolved separately from `_spec_get`, which falls through on an
    explicit null: the top-level key wins even when null, then the nested
    `graph` key wins even when null, and only a wholly absent key inherits.
    """

    def test_build_stores_both_values_and_echoes_them(self, tmp_path):
        payload = _build(
            _minimal_spec(default_llm_policy=dict(_POLICY), concurrency_budget=4)
        )
        assert payload["status"] == "built", payload
        assert _receipt_choices(payload) == {
            "default_llm_policy": _POLICY,
            "concurrency_budget": 4,
        }
        stored = _read(payload["branch_def_id"])
        assert stored["default_llm_policy"] == _POLICY
        assert stored["concurrency_budget"] == 4

    def test_build_reads_them_from_the_nested_graph_shape_too(self):
        """The `graph` blob is the shape `get_branch` RETURNS, so a
        read-modify-rebuild author goes through it."""
        payload = _build(
            _minimal_spec(
                graph={
                    "default_llm_policy": dict(_POLICY),
                    "concurrency_budget": 4,
                }
            )
        )
        assert payload["status"] == "built", payload
        stored = _read(payload["branch_def_id"])
        assert stored["default_llm_policy"] == _POLICY
        assert stored["concurrency_budget"] == 4

    def test_an_explicit_top_level_null_beats_a_nested_value(self):
        """Root correction: explicit null clears rather than re-inheriting."""
        payload = _build(
            _minimal_spec(
                default_llm_policy=None,
                concurrency_budget=None,
                graph={
                    "default_llm_policy": dict(_POLICY),
                    "concurrency_budget": 4,
                },
            )
        )
        assert payload["status"] == "built", payload
        stored = _read(payload["branch_def_id"])
        for field in _FIELDS:
            assert stored.get(field) is None, stored

    def test_unrelated_topology_keys_keep_their_fall_through(self):
        """`_spec_get`'s null fall-through is unchanged for topology.

        A top-level `edges: null` alongside a nested `graph.edges` must still
        pick up the nested edges -- this change must not move that behaviour.
        """
        payload = _build(
            {
                "name": "Topology fall-through",
                "domain_id": "workflow",
                "visibility": "private",
                "entry_point": "n1",
                "node_defs": [
                    {
                        "node_id": "n1",
                        "display_name": "N1",
                        "prompt_template": "do the thing",
                    }
                ],
                "edges": None,
                "graph": {"edges": [{"from": "n1", "to": "END"}]},
            }
        )
        assert payload["status"] == "built", payload
        assert payload["edge_count"] == 1

    def test_build_does_not_refuse_unknown_spec_keys(self):
        """No repo-wide unknown-key refusal is introduced (explicit non-goal).

        Honestly still true of the unfixed tree. The silent-typo hole is closed
        by the receipt echo instead, asserted above.
        """
        payload = _build(_minimal_spec(definitely_not_a_field="x"))
        assert payload["status"] == "built", payload


class TestPatchSetsAndClearsBothChoices:
    """Two ops on the existing op table, modelled on `set_io_manifest`."""

    def test_set_default_llm_policy_applies_and_echoes(self, tmp_path):
        built = _build(_minimal_spec())
        bid = built["branch_def_id"]
        result = _patch(
            bid, [{"op": "set_default_llm_policy", "default_llm_policy": dict(_POLICY)}]
        )
        assert result.get("status") == "patched", result
        assert _receipt_choices(result)["default_llm_policy"] == _POLICY
        assert get_branch_definition(tmp_path, branch_def_id=bid)[
            "default_llm_policy"
        ] == _POLICY

    def test_set_concurrency_budget_applies_and_echoes(self, tmp_path):
        built = _build(_minimal_spec())
        bid = built["branch_def_id"]
        result = _patch(bid, [{"op": "set_concurrency_budget", "concurrency_budget": 6}])
        assert result.get("status") == "patched", result
        assert _receipt_choices(result)["concurrency_budget"] == 6
        assert (
            get_branch_definition(tmp_path, branch_def_id=bid)["concurrency_budget"] == 6
        )

    def test_null_clears_each_choice(self, tmp_path):
        built = _build(
            _minimal_spec(default_llm_policy=dict(_POLICY), concurrency_budget=4)
        )
        bid = built["branch_def_id"]
        result = _patch(
            bid,
            [
                {"op": "set_default_llm_policy", "default_llm_policy": None},
                {"op": "set_concurrency_budget", "concurrency_budget": None},
            ],
        )
        assert result.get("status") == "patched", result
        after = get_branch_definition(tmp_path, branch_def_id=bid)
        for field in _FIELDS:
            assert after.get(field) is None, after
        assert _receipt_choices(result) == {
            "default_llm_policy": None,
            "concurrency_budget": None,
        }

    @pytest.mark.parametrize(
        "op,needle",
        [
            ({"op": "set_default_llm_policy"}, "requires a default_llm_policy"),
            ({"op": "set_concurrency_budget"}, "requires a concurrency_budget"),
        ],
    )
    def test_a_missing_field_is_an_explicit_error_not_a_silent_clear(
        self, tmp_path, op, needle
    ):
        built = _build(
            _minimal_spec(default_llm_policy=dict(_POLICY), concurrency_budget=4)
        )
        bid = built["branch_def_id"]
        result = _patch(bid, [op])
        assert result.get("status") == "rejected", result
        assert needle in json.dumps(result), result
        after = get_branch_definition(tmp_path, branch_def_id=bid)
        assert after["concurrency_budget"] == 4

    def test_unknown_ops_still_refuse(self, tmp_path):
        """Honestly still true: only the two named ops were added."""
        _seed(tmp_path, "target")
        result = _patch("target", [{"op": "set_execution_choices", "concurrency_budget": 4}])
        assert "unknown op" in json.dumps(result), result
        assert result.get("status") != "patched", result

    def test_an_accepted_op_carrying_the_fields_still_changes_nothing(self, tmp_path):
        """`set_name` must not quietly become a second way to set a choice."""
        built = _build(_minimal_spec())
        bid = built["branch_def_id"]
        result = _patch(
            bid,
            [
                {
                    "op": "set_name",
                    "name": "Renamed",
                    "default_llm_policy": dict(_POLICY),
                    "concurrency_budget": 9,
                }
            ],
        )
        assert result.get("status") == "patched", result
        after = get_branch_definition(tmp_path, branch_def_id=bid)
        assert after["name"] == "Renamed"
        for field in _FIELDS:
            assert after.get(field) is None


class TestReadAndDescribeSurfaceTheChoices:
    def test_read_returns_both_values(self, tmp_path):
        _seed(tmp_path, "seeded")
        stored = _read("seeded")
        assert stored["default_llm_policy"] == _POLICY
        assert stored["concurrency_budget"] == 4

    def test_read_of_an_unset_branch_reports_unset(self):
        payload = _build(_minimal_spec())
        stored = _read(payload["branch_def_id"])
        for field in _FIELDS:
            assert stored.get(field) is None

    def test_the_prose_receipt_describes_the_choices(self):
        """The text an author actually reads makes the controls discoverable."""
        payload = _build(
            _minimal_spec(default_llm_policy=dict(_POLICY), concurrency_budget=4)
        )
        text = payload["text"].lower()
        assert "concurrency budget" in text
        assert "model policy" in text

    def test_the_prose_receipt_stays_silent_when_neither_is_set(self):
        payload = _build(_minimal_spec())
        text = payload["text"].lower()
        assert "concurrency budget" not in text


class TestForkInheritsBothChoices:
    def _published_parent(self, tmp_path) -> str:
        parent = _definition_with_choices("parent")
        save_branch_definition(tmp_path, branch_def=parent.to_dict())
        version = publish_branch_version(
            tmp_path, parent.to_dict(), publisher=_SUBJECT,
        )
        assert version.snapshot["default_llm_policy"] == _POLICY
        assert version.snapshot["concurrency_budget"] == 4
        return version.branch_version_id

    def test_a_fork_inherits_both(self, tmp_path):
        bvid = self._published_parent(tmp_path)
        payload = _build(
            {
                "name": "Fork of parent",
                "domain_id": "workflow",
                "visibility": "private",
                "fork_from": bvid,
            }
        )
        assert payload["status"] == "built", payload
        forked = _read(payload["branch_def_id"])
        assert forked["entry_point"] == "n1"
        assert forked["default_llm_policy"] == _POLICY
        assert forked["concurrency_budget"] == 4

    def test_a_forks_own_spec_overrides_the_parent(self, tmp_path):
        bvid = self._published_parent(tmp_path)
        payload = _build(
            {
                "name": "Fork restating choices",
                "domain_id": "workflow",
                "visibility": "private",
                "fork_from": bvid,
                "concurrency_budget": 7,
            }
        )
        assert payload["status"] == "built", payload
        forked = _read(payload["branch_def_id"])
        assert forked["concurrency_budget"] == 7
        assert forked["default_llm_policy"] == _POLICY

    def test_an_explicit_nested_null_clears_instead_of_inheriting(self, tmp_path):
        """Root correction, fork edition: null beats the parent's value."""
        bvid = self._published_parent(tmp_path)
        payload = _build(
            {
                "name": "Fork clearing choices",
                "domain_id": "workflow",
                "visibility": "private",
                "fork_from": bvid,
                "graph": {
                    "default_llm_policy": None,
                    "concurrency_budget": None,
                },
            }
        )
        assert payload["status"] == "built", payload
        forked = _read(payload["branch_def_id"])
        for field in _FIELDS:
            assert forked.get(field) is None, forked

    def test_inheriting_a_policy_grants_no_credential(self, tmp_path):
        """A policy names a provider; it never carries authority to use one."""
        bvid = self._published_parent(tmp_path)
        payload = _build(
            {
                "name": "Fork authority check",
                "domain_id": "workflow",
                "visibility": "private",
                "fork_from": bvid,
            }
        )
        forked = _read(payload["branch_def_id"])
        blob = json.dumps(forked)
        for secretish in ("api_key", "token", "credential", "secret"):
            assert secretish not in blob.lower(), blob
        assert set(forked["default_llm_policy"]) == {"preferred"}


class TestValidationMatchesTheExecutionContract:
    """`type(v) is int and v > 0`, matching the per-run override contract.

    `ConcurrencyTracker.__init__` does `Semaphore(budget) if budget else None`,
    so today `0` silently means unbounded, `True` means `Semaphore(1)`, `-1`
    raises inside compile and `"4"` raises inside compile.
    """

    @pytest.mark.parametrize("bogus", [0, -1, True, "4", 2.0])
    def test_a_meaningless_budget_is_refused_at_build(self, bogus):
        payload = _build(_minimal_spec(concurrency_budget=bogus))
        assert payload["status"] == "rejected", payload
        blob = json.dumps(payload).lower()
        assert "concurrency_budget" in blob, payload
        assert "positive integer" in blob, payload

    @pytest.mark.parametrize("bogus", [0, -1, True, "4"])
    def test_a_meaningless_budget_is_refused_at_patch(self, tmp_path, bogus):
        built = _build(_minimal_spec())
        result = _patch(
            built["branch_def_id"],
            [{"op": "set_concurrency_budget", "concurrency_budget": bogus}],
        )
        assert result.get("status") == "rejected", result
        after = get_branch_definition(
            tmp_path, branch_def_id=built["branch_def_id"]
        )
        assert after.get("concurrency_budget") is None

    def test_a_bool_is_refused_rather_than_coerced(self):
        """`type(...) is int`, not `isinstance`: `True` is not a budget of 1."""
        from tinyassets.branches import validate_concurrency_budget

        assert validate_concurrency_budget(True)
        assert validate_concurrency_budget(1) == []

    def test_the_validator_imposes_no_structural_ceiling(self):
        """Usage limits live at admission, not in a field validator."""
        from tinyassets.branches import validate_concurrency_budget

        for large in (128, 10_000, 1_000_000):
            assert validate_concurrency_budget(large) == [], large

    def test_a_budget_sqlite_cannot_represent_is_refused_as_a_storage_limit(self):
        """Signed 64-bit representability -- refused before binding, with an
        error that does not read as a provider concurrency cap."""
        payload = _build(_minimal_spec(concurrency_budget=_MAX_INT64 + 1))
        assert payload["status"] == "rejected", payload
        blob = json.dumps(payload).lower()
        assert "store" in blob or "represent" in blob, payload
        assert "9223372036854775807" in json.dumps(payload), payload

    def test_the_representability_boundary_itself_is_accepted(self, tmp_path):
        payload = _build(_minimal_spec(concurrency_budget=_MAX_INT64))
        assert payload["status"] == "built", payload
        stored = get_branch_definition(
            tmp_path, branch_def_id=payload["branch_def_id"]
        )
        assert stored["concurrency_budget"] == _MAX_INT64

    def test_the_policy_footgun_key_is_still_refused(self):
        payload = _build(_minimal_spec(default_llm_policy=dict(_BAD_POLICY)))
        assert payload["status"] == "rejected", payload
        assert "preferred_provider" in json.dumps(payload), payload

    def test_an_unknown_policy_key_is_tolerated_but_observable(self):
        """Forward-compat stays, and the receipt reports what was stored.

        Note what this does NOT prove: the echo is a report, not a detector.
        The unknown key comes back because it was stored verbatim, so a typo
        *inside* the policy dict still reads as applied. The echo only makes a
        FIELD-level miss visible (a misspelled top-level key leaves the choice
        `null` while the call reports success). Detecting an in-dict typo
        needs an allowlist, which this change deliberately does not add.
        """
        payload = _build(
            _minimal_spec(default_llm_policy={"totally_unknown_key": "x"})
        )
        assert payload["status"] == "built", payload
        assert _receipt_choices(payload)["default_llm_policy"] == {
            "totally_unknown_key": "x"
        }

    def test_clearing_is_indistinguishable_from_never_having_set(self, tmp_path):
        never_set = _build(_minimal_spec())
        never_set_row = get_branch_definition(
            tmp_path, branch_def_id=never_set["branch_def_id"]
        )

        set_then_cleared = _build(
            _minimal_spec(
                name="Cleared", default_llm_policy=dict(_POLICY), concurrency_budget=4
            )
        )
        _patch(
            set_then_cleared["branch_def_id"],
            [
                {"op": "set_default_llm_policy", "default_llm_policy": None},
                {"op": "set_concurrency_budget", "concurrency_budget": None},
            ],
        )
        cleared_row = get_branch_definition(
            tmp_path, branch_def_id=set_then_cleared["branch_def_id"]
        )
        for field in _FIELDS:
            assert never_set_row.get(field) == cleared_row.get(field) is None

        never_snapshot = publish_branch_version(
            tmp_path, never_set_row, publisher=_SUBJECT
        ).snapshot
        cleared_snapshot = publish_branch_version(
            tmp_path, cleared_row, publisher=_SUBJECT
        ).snapshot
        for field in _FIELDS:
            assert field not in never_snapshot
            assert field not in cleared_snapshot

    def test_build_idempotency_now_compares_a_field_an_author_can_set(self):
        """`immutable_fields` lists both fields; the comparison becomes live.

        A same-`request_id` replay differing only in an execution choice must
        report `branch_idempotency_conflict` -- intended semantics, not a
        regression.
        """
        first = _build(
            _minimal_spec(concurrency_budget=4), request_id="exec-choice-replay"
        )
        assert first["status"] == "built", first
        replay = _build(
            _minimal_spec(concurrency_budget=8), request_id="exec-choice-replay"
        )
        assert replay.get("error") == "branch_idempotency_conflict", replay
        assert "concurrency_budget" in replay.get("conflicting_fields", []), replay


#: `branch_definitions` exactly as `CREATE TABLE` declares it at `ff1320d5`
#: (`tinyassets/daemon_server.py:312-330` on that sha) -- 17 columns, before
#: the `goal_id` / `visibility` / `fork_from` ALTERs and before this change's
#: two. A database created by an older image looks like this, so this is the
#: shape the migration has to survive.
_LEGACY_BRANCH_DEFINITIONS_DDL = """
    CREATE TABLE IF NOT EXISTS branch_definitions (
        branch_def_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        author TEXT NOT NULL DEFAULT '',
        domain_id TEXT NOT NULL DEFAULT 'workflow',
        tags_json TEXT NOT NULL DEFAULT '[]',
        version INTEGER NOT NULL DEFAULT 1,
        skills_json TEXT NOT NULL DEFAULT '[]',
        parent_def_id TEXT,
        entry_point TEXT NOT NULL DEFAULT '',
        graph_json TEXT NOT NULL DEFAULT '{}',
        node_defs_json TEXT NOT NULL DEFAULT '[]',
        state_schema_json TEXT NOT NULL DEFAULT '[]',
        published INTEGER NOT NULL DEFAULT 0,
        stats_json TEXT NOT NULL DEFAULT '{}',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
"""

#: The 20-column writer at `ff1320d5` (`_BRANCH_DEFINITION_INSERT_SQL` on that
#: sha), used verbatim to stand in for an older image's writer.
_OLD_WRITER_SQL = """
    INSERT OR REPLACE INTO branch_definitions (
        branch_def_id, name, description, author, domain_id,
        tags_json, version, skills_json, parent_def_id, entry_point,
        graph_json, node_defs_json, state_schema_json,
        published, stats_json, created_at, updated_at, goal_id,
        visibility, fork_from
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

#: Every field the legacy row carries, so "preserved" can be asserted as a
#: whole row rather than a sampled column.
_LEGACY_ROW = {
    "branch_def_id": "pre-migration",
    "name": "Written by an older image",
    "description": "predates the execution-choice columns",
    "author": _SUBJECT,
    "domain_id": "workflow",
    "tags_json": '["legacy"]',
    "version": 3,
    "skills_json": "[]",
    "parent_def_id": None,
    "entry_point": "n1",
    "graph_json": json.dumps(
        {
            "graph_nodes": [{"id": "n1", "node_def_id": "n1"}],
            "edges": [{"from": "n1", "to": "END"}],
            "entry_point": "n1",
        }
    ),
    "node_defs_json": json.dumps(
        [{"node_id": "n1", "display_name": "N1", "prompt_template": "do X"}]
    ),
    "state_schema_json": "[]",
    "published": 1,
    "stats_json": '{"runs": 7}',
    "created_at": 1700000000.5,
    "updated_at": 1700000001.5,
}


class TestLegacyDatabaseMigration:
    """A real pre-migration SQLite database, migrated in place.

    Added in the verification pass, and NOT part of the 29 RED / 16 GREEN
    red-first count in the module docstring: it was not executed against
    `ff1320d5`. `TestStoragePersistsBothChoices` proves the reader tolerates a
    mapping without the keys; that is not the same claim as "an existing
    database survives the migration", which is what a live install actually
    depends on and what is proven here.

    The temp root is pytest's `tmp_path`, which `tests/conftest.py` already
    refuses to site inside the repo; nothing here touches a real data dir.
    """

    def _legacy_base(self, tmp_path):
        """A base path whose DB holds the ff1320d5 table and one row."""
        import sqlite3

        from tinyassets.storage import db_path

        base = tmp_path / "legacy-install"
        base.mkdir()
        conn = sqlite3.connect(str(db_path(base)))
        try:
            conn.executescript(_LEGACY_BRANCH_DEFINITIONS_DDL)
            columns = ", ".join(_LEGACY_ROW)
            conn.execute(
                f"INSERT INTO branch_definitions ({columns}) VALUES "
                f"({', '.join('?' for _ in _LEGACY_ROW)})",
                tuple(_LEGACY_ROW.values()),
            )
            conn.commit()
        finally:
            conn.close()
        return base

    def _migrate(self, base) -> None:
        """Run the migration itself, past the once-per-base-path guard.

        `initialize_author_server` short-circuits on `_AUTHOR_SERVER_INITIALIZED`,
        so calling it twice would prove the cache works, not that the migration
        is re-runnable. `_initialize_author_server_locked` is the migration.
        """
        from tinyassets.daemon_server import _initialize_author_server_locked

        _initialize_author_server_locked(base)

    def _raw_row(self, base, branch_def_id: str = "pre-migration") -> dict:
        import sqlite3

        from tinyassets.storage import db_path

        conn = sqlite3.connect(str(db_path(base)))
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM branch_definitions WHERE branch_def_id = ?",
                (branch_def_id,),
            ).fetchone()
        finally:
            conn.close()
        return dict(row) if row is not None else {}

    def _columns(self, base) -> list[str]:
        import sqlite3

        from tinyassets.storage import db_path

        conn = sqlite3.connect(str(db_path(base)))
        try:
            return [
                r[1]
                for r in conn.execute(
                    "PRAGMA table_info(branch_definitions)"
                ).fetchall()
            ]
        finally:
            conn.close()

    def test_the_fixture_really_is_pre_migration(self, tmp_path):
        """Guard the premise: without it the rest of this class is vacuous."""
        base = self._legacy_base(tmp_path)
        columns = self._columns(base)
        assert columns == list(_LEGACY_ROW), columns
        for field in ("default_llm_policy_json", "concurrency_budget"):
            assert field not in columns

    def test_migrating_adds_the_columns_and_preserves_every_old_field(
        self, tmp_path
    ):
        base = self._legacy_base(tmp_path)
        self._migrate(base)

        columns = self._columns(base)
        for field in (
            "goal_id",
            "visibility",
            "fork_from",
            "default_llm_policy_json",
            "concurrency_budget",
        ):
            assert field in columns, columns

        row = self._raw_row(base)
        for field, expected in _LEGACY_ROW.items():
            assert row[field] == expected, field
        assert row["default_llm_policy_json"] is None
        assert row["concurrency_budget"] is None

    def test_the_migrated_row_reads_back_as_unset_through_the_real_reader(
        self, tmp_path
    ):
        """`_branch_def_from_row` over an actual migrated row, not a mapping."""
        base = self._legacy_base(tmp_path)
        self._migrate(base)

        read = get_branch_definition(base, branch_def_id="pre-migration")
        assert read["name"] == _LEGACY_ROW["name"]
        assert read["entry_point"] == "n1"
        assert read["version"] == 3
        for field in _FIELDS:
            assert read[field] is None, read

    def test_rerunning_the_migration_is_idempotent(self, tmp_path):
        """Three passes: no duplicate-column error, no row rewritten.

        The ALTERs are guarded by a `PRAGMA table_info` probe, so a second pass
        must be a no-op rather than `duplicate column name`.
        """
        base = self._legacy_base(tmp_path)
        self._migrate(base)
        before = self._raw_row(base)
        columns_before = self._columns(base)

        self._migrate(base)
        self._migrate(base)

        assert self._columns(base) == columns_before
        assert self._raw_row(base) == before

    def test_a_migrated_install_can_then_store_and_clear_both_choices(
        self, tmp_path
    ):
        """The point of the migration: the legacy install becomes authorable."""
        base = self._legacy_base(tmp_path)
        self._migrate(base)

        save_branch_definition(
            base, branch_def=_definition_with_choices("post-migration").to_dict()
        )
        stored = get_branch_definition(base, branch_def_id="post-migration")
        assert stored["default_llm_policy"] == _POLICY
        assert stored["concurrency_budget"] == 4

        cleared = dict(_definition_with_choices("post-migration").to_dict())
        cleared["default_llm_policy"] = None
        cleared["concurrency_budget"] = None
        save_branch_definition(base, branch_def=cleared)
        after = get_branch_definition(base, branch_def_id="post-migration")
        for field in _FIELDS:
            assert after[field] is None, after

        # The untouched legacy row stays untouched.
        assert self._raw_row(base)["updated_at"] == _LEGACY_ROW["updated_at"]

    def test_an_old_writer_erases_the_choices_it_does_not_know_about(
        self, tmp_path
    ):
        """The compatibility boundary `design.md` promises a regression for.

        An older image can READ the migrated table, but its writer is
        `INSERT OR REPLACE` over 20 columns. Replacing a row therefore drops
        the two it does not name, silently, on the next ordinary save. This
        test is the proof that additive nullable columns do NOT by themselves
        make a rollback data-preserving — it pins the failure so the rollback
        note cannot quietly become false.
        """
        import sqlite3

        from tinyassets.daemon_server import _branch_definition_insert
        from tinyassets.storage import db_path

        base = self._legacy_base(tmp_path)
        self._migrate(base)
        save_branch_definition(
            base, branch_def=_definition_with_choices("contested").to_dict()
        )
        assert (
            get_branch_definition(base, branch_def_id="contested")[
                "concurrency_budget"
            ]
            == 4
        )

        # The current writer builds 22 values; the first 20 are the old
        # column order unchanged, so values[:20] IS the ff1320d5 writer.
        _, values = _branch_definition_insert(
            _definition_with_choices("contested").to_dict()
        )
        assert len(values) == 22, values
        conn = sqlite3.connect(str(db_path(base)))
        try:
            conn.execute(_OLD_WRITER_SQL, values[:20])
            conn.commit()
        finally:
            conn.close()

        after = get_branch_definition(base, branch_def_id="contested")
        assert after["name"] == "Seeded with choices"
        for field in _FIELDS:
            assert after[field] is None, (
                "old-writer replace must be shown to ERASE the choices; if "
                "this now passes them through, the rollback note in design.md "
                "is stale"
            )
