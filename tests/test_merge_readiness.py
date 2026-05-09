from __future__ import annotations

from scripts.merge_readiness import (
    CHECKER_CLAUDE_LABEL,
    READY_FOR_CHECKER_LABEL,
    WRITER_CODEX_LABEL,
    PullRequestFacts,
    classify_many,
    classify_pr,
)


def _codex_pr(**overrides):
    data = {
        "number": 701,
        "title": "[auto-change] WIKI-PATCH: PR-063 fold legacy MCP surface",
        "mergeStateStatus": "CLEAN",
        "labels": [
            {"name": WRITER_CODEX_LABEL},
            {"name": CHECKER_CLAUDE_LABEL},
            {"name": READY_FOR_CHECKER_LABEL},
        ],
    }
    data.update(overrides)
    return data


def test_codex_written_ready_pr_needs_claude_checker_first():
    result = classify_pr(PullRequestFacts.from_mapping(_codex_pr()))

    assert result.state == "needs_claude_checker"
    assert result.merge_executor_state == "blocked"
    assert result.next_action == "route to Cowork/Claude checker"


def test_consensus_send_back_advisory_blocks_checker_routing():
    result = classify_pr(
        PullRequestFacts.from_mapping(
            _codex_pr(
                number=673,
                comments=[
                    {
                        "body": (
                            "Phase 2 rollout routing update: classified as "
                            "send-back/amend, not approval-ready."
                        )
                    }
                ],
            )
        )
    )

    assert result.state == "send_back_amend"
    assert result.next_action == "amend or regenerate before checker review"


def test_precheck_block_comment_blocks_unlabeled_pr_before_label_repair():
    result = classify_pr(
        PullRequestFacts.from_mapping(
            _codex_pr(
                number=710,
                labels=[],
                comments=[
                    {
                        "body": (
                            "**Pre-checker self-review blocked `ready_for_checker`**\n\n"
                            "- stale-base check failed: status=diverged behind_by=1"
                        )
                    }
                ],
            )
        )
    )

    assert result.state == "blocked_precheck"
    assert result.next_action == "resolve pre-check failures before checker review"


def test_dirty_or_stale_branch_blocks_before_review():
    result = classify_pr(PullRequestFacts.from_mapping(_codex_pr(mergeStateStatus="DIRTY")))

    assert result.state == "blocked_merge_state"
    assert "merge_state_status=DIRTY" in result.reasons


def test_opposite_checker_plus_host_key_plus_green_checks_is_executor_ready():
    result = classify_pr(
        PullRequestFacts.from_mapping(
            _codex_pr(
                opposite_family_checker_approved=True,
                host_keyed=True,
                checks_green=True,
            )
        )
    )

    assert result.state == "merge_executor_ready"
    assert result.merge_executor_state == "ready"


def test_opposite_checker_without_host_key_needs_implication_summary():
    result = classify_pr(
        PullRequestFacts.from_mapping(_codex_pr(opposite_family_checker_approved=True))
    )

    assert result.state == "needs_host_key"
    assert result.next_action == "summarize implications and ask host for explicit PR key"


def test_consensus_mirror_self_clearance_is_canary_only():
    result = classify_pr(
        PullRequestFacts.from_mapping(
            _codex_pr(
                consensus_mirror={
                    "engaged_aligned_source": True,
                    "cross_family_source": True,
                    "source_hash_matches": True,
                    "no_semantic_delta": True,
                    "no_frontmatter_delta": True,
                    "no_scope_delta": True,
                }
            )
        )
    )

    assert result.state == "consensus_mirror_self_clearance_canary"
    assert result.merge_executor_state == "blocked_policy_canary"
    assert "do not auto-merge" in result.next_action


def test_same_family_checker_labels_are_routing_anomaly():
    result = classify_pr(
        PullRequestFacts.from_mapping(
            _codex_pr(labels=[WRITER_CODEX_LABEL, "checker:codex", READY_FOR_CHECKER_LABEL])
        )
    )

    assert result.state == "routing_anomaly"
    assert "Codex-written PR cannot require Codex checker" in result.reasons


def test_partial_writer_checker_labels_are_routing_anomaly():
    result = classify_pr(
        PullRequestFacts.from_mapping(
            _codex_pr(labels=[WRITER_CODEX_LABEL, READY_FOR_CHECKER_LABEL])
        )
    )

    assert result.state == "routing_anomaly"
    assert "missing checker-family label" in result.reasons


def test_classify_many_counts_states():
    payload = classify_many(
        [
            _codex_pr(number=672),
            _codex_pr(number=673, send_back_advisory=True),
            _codex_pr(
                number=710,
                labels=[],
                comments=[{"body": "Pre-checker self-review blocked ready_for_checker"}],
            ),
        ]
    )

    assert payload["by_state"] == {
        "blocked_precheck": 1,
        "needs_claude_checker": 1,
        "send_back_amend": 1,
    }
