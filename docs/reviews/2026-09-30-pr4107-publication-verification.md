# PR #4107 publication verification

Verified aa4ebb86, merged origin/main (fb39b118), and closed additional public
history paths. P1-b held as written. P1-a held for direct get/list, refused accepts
and confirmed-history isolation, but indirect paths needed the fixes below.

## Evidence

- `tinyassets/api/branches.py:588`: single-version readers, remix and ancestor
  traversal require the author's identity or the publication mark, plus branch
  readability. `test_a_public_branchs_unpublished_history_stays_its_authors` and
  `test_publishing_exposes_the_confirmed_version_never_the_history` prove it.
- `tinyassets/api/evaluation.py:959`: non-author version lists filter the mark.
  The same history tests prove this independently from single-version reads.
- `tinyassets/api/publish_requests.py:335`: mint unmarked, compare-and-set all
  branches, then mark exactly confirmed versions. Tests:
  `test_a_refused_accept_leaves_its_minted_versions_unreadable` and
  `test_a_bundle_that_fails_to_publish_leaves_nothing_public`; both also make the
  branches public later and assert the refused versions remain unreadable.
- `tinyassets/api/publish_requests.py:95`: only visibility, published and updated_at
  are exempt. `test_stats_and_version_are_pinned_too` separately changes stats and
  version after consent and proves refusal.
- `tinyassets/api/branches.py:1585` and `:4517`: descendant projections filter
  unreadable version IDs; counts include marked versions only.
  `test_lineage_hides_unpublished_versions` covers describe_branch and fork_tree.
- `tinyassets/api/evaluation.py:531`: private node edit audits remain author-only.
  `test_public_node_history_does_not_expose_private_edit_audits` proves the public
  reader sees only the current node and the author still sees history.
- `tinyassets/graph_compiler.py:3301`: nested invocation requires the mark or
  delegated authorship, checked without loading the snapshot. Tested by
  `test_nested_invoke_cannot_run_unpublished_history` for a foreign actor and for
  foreign-authored code running as the snapshot owner.
- `tinyassets/api/quality_leaderboard.py:740`,
  `tinyassets/api/canonical_dispatch.py:759`, `tinyassets/handoffs/service.py:123`:
  indirect version readers check publication. Proven by
  `test_indirect_readers_hide_unpublished_versions` for each path.
- `tinyassets/api/evaluation.py:325` and `:353`: suggest-edit context checks run
  readability for outputs and judgments. `test_suggest_edit_filters_private_run_context`.

## Cross-family review disposition

Used `.agents/skills/peer-agents/SKILL.md`, Claude fable, one read-only round.
AGREE: node-history and lineage fixes correct; stats/version digest pins hold.
AGREE and fixed: nested invocation, leaderboard/canonical selection, handoff
version declarations, and suggest-edit run context. Each has a red mutation.
AGREE, separate P2 follow-up: compensation withdraws previously-public state on
storage failure; tracked in `docs/concerns/publish-failure-restores-prior-publication.md`.
No new review round requested; the review did not rerun tests.

## Mutation evidence

All production and test edits were committed before mutation. Each mutation ran
alone, and each file was restored with `git checkout -- <file>` in a finally block.
All 14 mutants failed their target tests (pytest exit 1, assertion failures):

| Removed protection | Result |
| --- | --- |
| Single-version mark check | RED |
| Version-list mark filter | RED |
| Mint unmarked until confirmation | RED |
| Clear marks after bundle failure | RED |
| Pin stats | RED |
| Pin version | RED |
| Filter descendant history IDs | RED |
| Keep node edit audits author-only | RED |
| Nested invocation mark/authorship gate | RED |
| Leaderboard mark filter | RED |
| Canonical selection mark filter | RED |
| Handoff declaration mark check | RED |
| Suggest-edit run-output readability | RED |
| Suggest-edit judgment readability | RED |

## Integration

Removed the app-event admit_detail/usage_limit block and all four requested meter
tests; retained the no-run-can-emit capability test. Specs now say owner compute,
bounded by concurrent seats, no rate meters. Merged main with both activity-log
sides retained, regenerated the plugin mirror and brand receipt. The app is /app.

## Final validation

- Windows, requested suites plus branch-version/publish suites and affected
  evaluation, authoring, metadata, node-key, composite, nested-invocation,
  handoff, canonical, leaderboard and branch-runner suites: **580 passed,
  2 skipped** (124.83s). Skips are host symlink support / POSIX-only listing.
- Linux oracle, in-platform systems and version-read authority: **62 passed,
  1 skipped** (14.74s). The skip is explicitly the Windows-only junction test;
  POSIX traversal and descriptor tests passed.
- Ruff on all changed canonical Python and test files: passed.
- `git diff --check origin/main`: passed.
- Plugin mirror rebuilt; commit hooks verified mirror parity and import graph.
- This builder validated and pushed the PR branch; deployment and live-user
  acceptance remain the lead's pending OpenSpec tasks, not claimed here.
