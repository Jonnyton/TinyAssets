# Executable gates

Which of this project's rules are enforced by something that can fail, where
that enforcement runs, and which rules are deliberately still judgement.

Written 2026-08-25 during the harness reset. The reset's rule was **every gate
is either executable or honestly labelled as judgement** — a rule that reads
like a gate but enforces nothing is worse than no rule, because it buys
confidence it has not earned.

## Enforced

| Rule | Mechanism | Runs where |
|---|---|---|
| Always-loaded context budget | `scripts/check_context_budget.py` → `context-budget` invariant | pre-commit hook **and** `invariants.yml` CI |
| Cross-provider rule-file drift | `scripts/check_cross_provider_drift.py` → `cross-provider-drift` | same |
| Skill tree valid + mirrored | `validate_skills.py`, `mirror-parity` | same |
| No CP-1252 mojibake in tracked text | `mojibake` invariant | same |
| Behavioural test gate on `main` | `required-tests` + `.github/known-failing-tests.txt` | required check |
| Diff scope declared | `pr-scope-guard.yml` | required check |
| Exact-head review receipt on gate-defining files | `scripts/drain_review_gate.py` | `pr-scope-guard.yml`, `auto-enroll-merge.yml` |
| Public MCP surface + canonical handles | `scripts/mcp_public_canary.py --assert-handles` | `deploy-prod.yml`, and by hand after DNS/tunnel/connector edits |
| **Merged is not deployed** (Hard Rule 14) | `scripts/deployed_sha.py --assert-contains <sha>` | post-deploy, by hand or from a deploy job — **never** a merge-required check |

### Two shapes worth copying

**Three exit codes, not two.** `deployed_sha.py` returns 0 shipped, 1 not
shipped, **2 could not determine**. Collapsing 2 into 0 would make a network
blip read as "yes, it shipped" — the exact failure Hard Rule 14 exists to
prevent. Any gate that talks to an external service needs this third state.

**A gate that cannot fail is decoration.** Every gate above was mutation-tested:
break the thing it guards, confirm it goes red, restore, confirm green. Two
findings came straight out of doing that during the reset — the invariant
framework was downgrading crashed checks to `SKIPPED` (so a broken gate reported
as fine), and `tests/test_validate_skills.py` had two tests failing with
`FileNotFoundError` on `origin/main`, testing nothing. Neither was visible
without trying to make them fail.

## Deliberately still judgement

**Cross-family review** (`AGENTS.md` § *Project Skills* / § *Quality Gates*).
Opposite-provider review gates build, push, and rollout for research-derived
findings and high-risk changes. It is **not** mechanically enforced for product
code, and the harness reset deliberately did not build a `crossfamily` gate.

The plan proposed one that read a committed `.agents/verdicts/<sha>.json`.
Codex refuted it, correctly: **committing the verdict changes the SHA it claims
to approve**, and anything the author can write from their own checkout is
self-attestation, not review.

The sound mechanism already exists and is already wired —
`scripts/drain_review_gate.py` requires an exact-head receipt in the **PR body**
(GitHub-hosted, outside the commit, invalidated by any head change):

```
Drain-Review-Verdict: APPROVE
Drain-Review-Head: <40-char sha>
Drain-Review-Artifact: docs/... | https://github.com/...
```

Today it fires for `drain/` branches and, via `force=true`, for PRs touching the
files that *define* the required-tests gate — `.github/workflows/`,
`known-failing-tests.txt`, `ci_required_tests.py`, `drain_review_gate.py`,
`deploy/`, `Dockerfile`. That is the "a PR can neuter its own judge" class.

It does **not** fire for the high-risk *product* paths `AGENTS.md` names — auth,
storage, migration, concurrency, public-surface, data-loss. Closing that gap
means adding those paths to `SENSITIVE_RE` in `pr-scope-guard.yml`, which reuses
the proven mechanism and needs no new code.

**That was left undone on purpose.** Widening a required check's scope changes
what merges, which is a founder policy decision, not a harness cleanup — and a
reset whose premise is "this project over-built process" should not quietly add
review requirements on its way out. Recorded here so the choice is visible
rather than forgotten. See `docs/host-actions.md` if you decide to take it.

## Not gates, and should not become gates

- **Evidence-before-completion.** A script can confirm a command and its output
  are present; it cannot confirm the evidence supports the claim. Checking the
  string would create exactly the false confidence this file warns about.
- **Shape-before-hardening review sequencing.** The ordering is a judgement
  about what a change *is*. Encoding it would mean encoding "is this
  foundation or feature," which is the judgement itself.
