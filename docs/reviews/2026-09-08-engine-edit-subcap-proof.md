# Engine-edit subcap retirement: deployed technical proof

September 8 PDT / September 9 UTC. Implementation PR #3577, approved head
`d22c11054d08928246448e4b4a6d9e5720679a47`, merged revision
`8f1b47609330f06924246a692740448836672a48`.

## Scope

Engine edits now use the existing 900 total admissions per rolling hour without
an independent 600-edit share. The 300 write-run ceiling and 900 total remain;
row kinds, settlement, transactions, fail modes, status ACL, provider authority
and workspace/effect safeguards are unchanged. Engine usage remains observable.
No workflow, PLAN, storage schema, threshold or credential change.

## Independent and automated verification

Claude shape review APPROVE, followed by exact-head APPROVE, each terminal exit
0 after 228 seconds. Code receipt:
https://github.com/Jonnyton/TinyAssets/pull/3577#issuecomment-5595878957.

Windows focused candidate: 231 passed, 7 unchanged platform skips, with Ruff,
plugin mirror and strict OpenSpec validation passing. Linux Tests run
34311535677 passed required and slow jobs. Actual tested merge checkout
55920e0d8874e4800edc11d8a76848cf5f7c879a is full-tree identical to d22c1105
(`git diff --exit-code`). Focused JUnit identity/outcome comparison against
unchanged-source baseline 34306784859 proves 238 passes, zero skips/regressions,
including 13 new policy tests and one scheduler recovery test. Only the old
engine-share-reservation scenario was deliberately replaced. Commands and
baseline detail are in the change's REVIEW.md and the Linux PR receipt:
https://github.com/Jonnyton/TinyAssets/pull/3577#issuecomment-5596013939.

## Live verification

Image build 34312713141 succeeded, followed automatically by deploy 34312901542.
Inspected with `gh run view 34312901542 --json status,conclusion,jobs` and its
actual job log on September 9 UTC. Deployment succeeded at 04:57:38Z:

- Fail-safe image deployment and health check succeeded at 04:57:27Z.
- Authenticated `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles`
  succeeded at 04:57:32Z.
- Authenticated `python scripts/deployed_sha.py --url https://tinyassets.io/mcp --assert-contains 8f1b47609330f06924246a692740448836672a48`
  reported `SHIPPED (per receipt)` at 04:57:34Z, with production reporting
  8f1b47609330. Credentials remained in CI.

Immutable digest: sha256:35f877a2e3edba5ad4b2feccb3d9b09f3200dd8a6741c46ce375fbf19a61ad8f.
Deployment receipt: https://github.com/Jonnyton/TinyAssets/actions/runs/34312901542.

Rollback if total/write admission, authority or settlement regresses: revert
the implementation merge and deploy through normal reviewed guards; no data
migration or ledger reinterpretation is required. No rollback was needed.

## Not completion

No post-deploy rendered acceptance of this engine-edit retirement is yet observed.
Do not impose a 900-call production workload to replace focused technical proof.
The owner's organic 21:39 report preceded this deploy and proves a different
retirement (workspace starts), not the newly shipped engine-edit behavior.

Full goal: remaining concurrency/activity/retained-space simplification plus
the five app gaps, with explicit rendered agent confirmation of closure, as
recorded in `openspec/changes/consolidate-platform-resource-policy/goal-completion-contract.md`.
This change remains unarchived pending its separate acceptance gate.
