"""Immutable branch snapshots must carry the user's model and concurrency choices.

Scope: `tinyassets.branch_versions._canonical_snapshot` only, plus the one
reconstruction path that turns a stored snapshot back into an executable
`BranchDefinition` (`tinyassets.runs._load_branch_version`).

What is actually proven here: a run executed from an immutable version
(`execute_branch_version` -> `_load_branch_version`) compiles the *stored
snapshot*, not the live author store. If the snapshot does not carry
`default_llm_policy` / `concurrency_budget`, that run executes under global
role-based routing and unbounded node concurrency instead of the choices the
owner authored.

This is a *precondition* for any resume surface that re-compiles from a pinned
version -- it is not a claim that today's resume path already pins one. No
resume behaviour is asserted, changed, or relied on by this module.

Two groups, deliberately opposed:

* `TestExecutionRelevantFieldsSurviveSnapshot` — round-trip of a branch that
  *sets* the fields. Expected RED at da0dd350; the allowlist in
  `_canonical_snapshot` (branch_versions.py:214-226) drops both.
* `TestLegacyAbsentFieldIdentityCompatibility` — a branch that *does not* set
  them must keep byte-identical snapshot content, hence an identical
  `content_hash` and `branch_version_id`. Expected GREEN now and required to
  stay GREEN after the fix; this is what forces the fix to be conditional
  inclusion (the `io_manifest` pattern) rather than unconditional.

No assertion here is relaxed to obtain a pass.
"""
from __future__ import annotations

import pytest

from tinyassets.branch_versions import (
    _canonical_snapshot,
    compute_content_hash,
    get_branch_version,
    publish_branch_version,
)

# A concrete user model choice: "run my graph on this provider/model, with
# this fallback" — the thing a user selects through the chatbot.
#
# Shape matters: the runtime reads `policy["preferred"]["provider"]`, and
# `_validate_llm_policy_shape` (branches.py:845) rejects the look-alike
# `preferred_provider`. A bare top-level `provider`/`model` pair is neither
# validated nor read — it is forward-compat slack, so a regression written
# against it would not prove that a *supported* policy survives.
USER_MODEL_CHOICE = {
    "preferred": {"provider": "anthropic", "model": "claude-opus-5"},
    "fallback_chain": [{"provider": "anthropic", "model": "claude-sonnet-5"}],
}
OTHER_MODEL_CHOICE = {
    "preferred": {"provider": "codex", "model": "gpt-5"},
}
USER_CONCURRENCY_CHOICE = 3


def _branch(
    branch_id: str = "snap-b1",
    *,
    default_llm_policy=None,
    concurrency_budget=None,
):
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )

    nd = NodeDefinition(node_id="n1", display_name="N1", prompt_template="do X")
    return BranchDefinition(
        branch_def_id=branch_id,
        name=f"Branch {branch_id}",
        graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
        edges=[EdgeDefinition(from_node="n1", to_node="END")],
        entry_point="n1",
        node_defs=[nd],
        state_schema=[],
        default_llm_policy=default_llm_policy,
        concurrency_budget=concurrency_budget,
    )


# ── the fields a user chose must survive the snapshot ────────────────────────


class TestExecutionRelevantFieldsSurviveSnapshot:
    def test_to_dict_emits_both_fields(self):
        """Baseline: the loss is in _canonical_snapshot, not in to_dict.

        Pins where the defect is NOT, so the fix is not aimed at branches.py.
        """
        d = _branch(
            default_llm_policy=USER_MODEL_CHOICE,
            concurrency_budget=USER_CONCURRENCY_CHOICE,
        ).to_dict()
        assert d["default_llm_policy"] == USER_MODEL_CHOICE
        assert d["concurrency_budget"] == USER_CONCURRENCY_CHOICE

    def test_canonical_snapshot_preserves_default_llm_policy(self):
        snap = _canonical_snapshot(
            _branch(default_llm_policy=USER_MODEL_CHOICE).to_dict()
        )
        assert snap.get("default_llm_policy") == USER_MODEL_CHOICE

    def test_canonical_snapshot_preserves_concurrency_budget(self):
        snap = _canonical_snapshot(
            _branch(concurrency_budget=USER_CONCURRENCY_CHOICE).to_dict()
        )
        assert snap.get("concurrency_budget") == USER_CONCURRENCY_CHOICE

    def test_model_choice_changes_content_identity(self):
        """Two branches differing ONLY in model choice must not share identity.

        A shared content_hash means publishing the new choice returns the OLD
        version record (branch_versions.py:270-276 short-circuits on an
        existing hash), so the user's change is silently not published.
        """
        a = _canonical_snapshot(
            _branch(default_llm_policy=USER_MODEL_CHOICE).to_dict()
        )
        b = _canonical_snapshot(
            _branch(default_llm_policy=OTHER_MODEL_CHOICE).to_dict()
        )
        assert compute_content_hash(a) != compute_content_hash(b)

    def test_concurrency_choice_changes_content_identity(self):
        a = _canonical_snapshot(_branch(concurrency_budget=1).to_dict())
        b = _canonical_snapshot(_branch(concurrency_budget=8).to_dict())
        assert compute_content_hash(a) != compute_content_hash(b)

    def test_published_version_round_trips_both_fields(self, tmp_path):
        """End to end through the real store: publish → stored snapshot."""
        branch = _branch(
            default_llm_policy=USER_MODEL_CHOICE,
            concurrency_budget=USER_CONCURRENCY_CHOICE,
        )
        bvid = publish_branch_version(
            tmp_path, branch.to_dict(), publisher="alice"
        ).branch_version_id

        stored = get_branch_version(tmp_path, branch_version_id=bvid).snapshot
        assert stored.get("default_llm_policy") == USER_MODEL_CHOICE
        assert stored.get("concurrency_budget") == USER_CONCURRENCY_CHOICE

    def test_reconstructed_branch_executes_under_user_choices(self, tmp_path):
        """The execution-facing consequence.

        `_load_branch_version` is what an immutable-version run (and therefore
        a resumed one) compiles. `compile_branch` reads
        `getattr(branch, "concurrency_budget", None)` (graph_compiler.py:3948)
        and `branch.default_llm_policy` (graph_compiler.py:964, :3985). If the
        reconstruction yields None, the pinned run executes unbounded and
        under global role-based routing instead of the user's choice.
        """
        from tinyassets.runs import _load_branch_version

        branch = _branch(
            default_llm_policy=USER_MODEL_CHOICE,
            concurrency_budget=USER_CONCURRENCY_CHOICE,
        )
        bvid = publish_branch_version(
            tmp_path, branch.to_dict(), publisher="alice"
        ).branch_version_id

        rebuilt = _load_branch_version(tmp_path, bvid)
        assert rebuilt.default_llm_policy == USER_MODEL_CHOICE
        assert rebuilt.concurrency_budget == USER_CONCURRENCY_CHOICE

    def test_compiler_resolves_the_owners_policy_on_the_rebuilt_branch(
        self, tmp_path
    ):
        """Not just the attribute: the compiler's own resolution agrees.

        ``inspect_node_dry`` runs the same node>branch>default precedence the
        compiler uses at :964/:3985 (side-effect free, no provider calls). On
        the dropped-field tree this resolves to source "default" with
        ``effective_policy`` None -- i.e. global role-based routing -- for a
        node that declares no policy of its own.
        """
        from tinyassets.graph_compiler import inspect_node_dry
        from tinyassets.runs import _load_branch_version

        branch = _branch(
            branch_id="snap-compile", default_llm_policy=USER_MODEL_CHOICE
        )
        bvid = publish_branch_version(
            tmp_path, branch.to_dict(), publisher="alice"
        ).branch_version_id

        inspected = inspect_node_dry(
            _load_branch_version(tmp_path, bvid), node_id="n1"
        )
        resolution = inspected["policy_resolution"]
        assert resolution["source"] == "branch"
        assert resolution["effective_policy"] == USER_MODEL_CHOICE
        assert resolution["fallback_chain"] == USER_MODEL_CHOICE["fallback_chain"]

    def test_provider_admission_reads_the_policy_from_the_stored_snapshot(
        self, tmp_path
    ):
        """Provider-side sizing reads the snapshot dict, not the branch object.

        ``work_candidate_data.fit`` and ``foreground_run_provider`` both do
        ``node.get("llm_policy") or snapshot.get("default_llm_policy")``
        (work_candidate_data.py:135, foreground_run_provider.py:590) against
        the *stored* snapshot. Two branches differing only in model choice must
        not collapse to one admission policy key.
        """
        from tinyassets.providers.work_candidate_data import policy_key

        def _stored(branch_id, policy):
            bvid = publish_branch_version(
                tmp_path,
                _branch(branch_id, default_llm_policy=policy).to_dict(),
                publisher="alice",
            ).branch_version_id
            return get_branch_version(tmp_path, branch_version_id=bvid).snapshot

        chosen = _stored("adm-a", USER_MODEL_CHOICE)
        other = _stored("adm-b", OTHER_MODEL_CHOICE)
        node = chosen["node_defs"][0]
        assert node.get("llm_policy") is None  # node defers to the branch

        resolved = node.get("llm_policy") or chosen.get("default_llm_policy")
        assert resolved == USER_MODEL_CHOICE
        assert policy_key(resolved) != policy_key(
            other["node_defs"][0].get("llm_policy")
            or other.get("default_llm_policy")
        )
        assert policy_key(resolved) != policy_key(None)


# ── legacy snapshots keep their identity ─────────────────────────────────────


class TestLegacyAbsentFieldIdentityCompatibility:
    """Must pass BEFORE and AFTER the fix.

    Every already-published version was minted from a snapshot without these
    keys. `branch_version_id` is `f"{branch_def_id}@{content_hash[:8]}"`
    (branch_versions.py:278) and is referenced by `runs.branch_version_id`,
    rollback pointers and parent_version_id edges. A fix that adds the keys
    unconditionally re-hashes every unset branch and forks those references.
    """

    LEGACY_KEYS = {
        "branch_def_id",
        "author",
        "visibility",
        "skills",
        "entry_point",
        "graph_nodes",
        "edges",
        "conditional_edges",
        "node_defs",
        "state_schema",
    }

    def test_unset_branch_snapshot_has_exactly_the_legacy_keys(self):
        """No new key may appear when the user chose nothing.

        io_manifest is already conditional (branch_versions.py:225); these two
        must follow that pattern, not the unconditional one.
        """
        snap = _canonical_snapshot(_branch().to_dict())
        assert set(snap) == self.LEGACY_KEYS

    def test_absent_key_and_explicit_none_are_the_same_version(self, tmp_path):
        """A dict that never had the keys and one holding None are one version.

        Guards against a fix keyed on `in` rather than `is not None`, which
        would split identity for dicts that round-tripped through to_dict().
        """
        branch = _branch(branch_id="legacy-b")
        absent = branch.to_dict()
        absent.pop("default_llm_policy", None)
        absent.pop("concurrency_budget", None)

        explicit_none = branch.to_dict()
        assert explicit_none["default_llm_policy"] is None
        assert explicit_none["concurrency_budget"] is None

        first = publish_branch_version(tmp_path, absent, publisher="alice")
        second = publish_branch_version(
            tmp_path, explicit_none, publisher="alice"
        )
        assert first.branch_version_id == second.branch_version_id
        assert first.content_hash == second.content_hash

    def test_legacy_snapshot_still_reconstructs(self, tmp_path):
        """An old row lacking the keys must not become SnapshotSchemaDrift."""
        from tinyassets.runs import _load_branch_version

        branch = _branch(branch_id="legacy-exec")
        bvid = publish_branch_version(
            tmp_path, branch.to_dict(), publisher="alice"
        ).branch_version_id

        rebuilt = _load_branch_version(tmp_path, bvid)
        assert rebuilt.default_llm_policy is None
        assert rebuilt.concurrency_budget is None

    def test_unset_branch_hash_equals_the_recorded_legacy_digest(self):
        """A literal, deterministic digest -- not a self-referential recompute.

        Pinned from the absent-key snapshot form, which this change leaves
        byte-identical (the two new keys are conditional and both absent here).
        Any change that alters that form -- reordering, a new unconditional key,
        a different default -- changes this value and forks every existing
        absent-key snapshot bytes -- reordering, a new unconditional key, a
        ``branch_version_id``, which is exactly the outcome this module exists
        to prevent.
        """
        snap = _canonical_snapshot(_branch(branch_id="legacy-digest").to_dict())
        assert compute_content_hash(snap) == (
            "f818b000898b505077e43e5ef9e21a5ed27548dffbb4184c13c2e3ed771404cb"
        )

    def test_stored_legacy_row_is_not_rewritten_by_a_later_publish(
        self, tmp_path
    ):
        """An old row survives a later publish that DOES carry choices.

        Publishing a version with execution choices must mint a new row, never
        touch the bytes of the row published before the fields existed.
        """
        branch = _branch(branch_id="legacy-row")
        legacy = publish_branch_version(
            tmp_path, branch.to_dict(), publisher="alice"
        )
        before = get_branch_version(
            tmp_path, branch_version_id=legacy.branch_version_id
        ).snapshot

        withchoices = publish_branch_version(
            tmp_path,
            _branch(
                branch_id="legacy-row",
                default_llm_policy=USER_MODEL_CHOICE,
                concurrency_budget=USER_CONCURRENCY_CHOICE,
            ).to_dict(),
            publisher="alice",
        )
        assert withchoices.branch_version_id != legacy.branch_version_id

        after = get_branch_version(
            tmp_path, branch_version_id=legacy.branch_version_id
        ).snapshot
        assert after == before
        assert "default_llm_policy" not in after
        assert "concurrency_budget" not in after


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__]))
