# Executable gates

Which rules are enforced by something that can fail, where that enforcement runs,
and which rules are deliberately still judgement. **Every gate is either
executable or honestly labelled as judgement** — a rule that reads like a gate
but enforces nothing buys confidence it has not earned.

## Enforced

| Rule | Mechanism | Runs where |
|---|---|---|
| Rulebook byte ratchet + always-loaded context budget | `scripts/check_context_budget.py` → `context-budget` invariant, plus the pin-total and slack assertions in `tests/test_rulebook_ratchet.py` | `invariants.yml` CI and `required-tests`. NOT the pre-commit hook: it runs only the two checks below |
| Cross-provider rule-file drift | `scripts/check_cross_provider_drift.py` → `cross-provider-drift` | pre-commit hook **and** `invariants.yml` CI |
| Skill tree valid + mirrored | `scripts/validate_skills.py`, `mirror-parity` | same |
| Plugin mirror ships the current code | `scripts/check_mirror_parity.py` — a canonical `tinyassets/**` file that diverges from its mirror copy **or has none** fails, by name. | pre-commit (staged set) **and** `invariants.yml` CI (whole tree) |
| No CP-1252 mojibake in tracked text | `mojibake` invariant | same |
| Behavioural test gate on `main` | `required-tests` + `.github/known-failing-tests.txt` | required check |
| Diff scope declared | `pr-scope-guard.yml` | required check |
| Exact-head review receipt on gate-defining and authority-critical files | `scripts/drain_review_gate.py` | `pr-scope-guard.yml`, `auto-enroll-merge.yml` |
| Public MCP surface + canonical handles | `scripts/mcp_public_canary.py --assert-handles` | `deploy-prod.yml`, and by hand after DNS/tunnel/connector edits |
| **Merged is not deployed** (Hard Rule 14) | `scripts/deployed_sha.py --assert-contains <sha>` against bearer-protected `/mcp/pulse`. Three exit codes: 0 shipped, 1 not, **2 cannot tell** — collapsing 2 into 0 makes a network blip read as shipped, so any gate calling an external service needs the third state. | `deploy-prod.yml` after receipt publication; by hand with `TINYASSETS_WIKI_CANARY_TOKEN` — **never** a merge-required check |

`.github/known-failing-tests.txt` is a one-way ratchet: a line excusing a test you
broke is a visible, reviewable edit on a scope-guarded path.

## Cross-family review — partly enforced

A committed verdict file cannot be the gate: committing it changes the sha it
claims to approve, and anything the author writes from their own checkout is
self-attestation. `scripts/drain_review_gate.py` instead requires an exact-head
receipt in the **PR body** — GitHub-hosted, outside the commit, invalidated by any
head change:

```
Drain-Review-Verdict: APPROVE
Drain-Review-Head: <40-char sha>
Drain-Review-Artifact: docs/... | https://github.com/...
```

It runs from the trusted base checkout, so a PR cannot weaken the rule judging
it, and fires on three classes:

1. **`drain/` branches.**
2. **Gate-defining files** — `.github/workflows/tests.yml`,
   `known-failing-tests.txt`, `heavy-test-files.txt`, `ci_required_tests.py`,
   `drain_review_gate.py`. The "a PR can neuter its own judge" class.
3. **Authority-critical files** — `tinyassets/auth/`, `credential_vault.py`, and
   `api/{permissions,interlocutor,visibility,engine_helpers}.py`. Each is named in
   a finding that **landed** and was caught later: the gap was review not bound to
   the merge.

Deliberately narrow — ~7% of commits touch these paths; a blanket receipt
requirement across `tinyassets/` would be bloat. The regex is mutation-tested
against lookalikes like `visibility_helpers.py`.

**Still judgement:** everything else. Whether a design is right, whether a
finding is real, whether a shape should ship — no path regex reaches those.

## Required checks, and why each earns it

| Check | Time | Unique value |
|---|---|---|
| `required-tests` | ~7 min | The behavioural gate. All tests minus the heavy files, `-m "not slow"`. |
| `slow-tests` | ~1 min | The ONLY place `-m slow` race/stress tests run. |
| `invariants` | ~15 s | Mechanical checks. Best signal per second here. |
| `Diff scope declared` | ~10 s | Blast-radius guard: a small-looking PR carrying an unmerged lineage. |

They run in parallel, so the wall clock is `required-tests` alone
(`docs/decisions/ADR-003-required-test-aggregator.md`). `heavy-tests` is NOT
required, runs only the excluded files, and is red at baseline — compare a failure
there against the previous run, never read it as a regression
(`docs/concerns/2026-08-27-full-tests-permanently-red.md`).

**Branch protection `strict` is off, deliberately** (2026-08-27). It marks every
other open PR `BEHIND`, and GitHub's auto-merge does not update a behind branch,
so `strict` + auto-merge deadlocks above one concurrent PR; merge queue, the
supported fix, needs an organization-owned repo. The compensator that must not
rot: `tests.yml` on `push: main`, and **revert first, diagnose after** on a red
`main`.

## Not gates, and should not become gates

- **Evidence-before-completion**, and **shape-before-hardening sequencing.** A
  script can confirm a command and its output are present, never that the evidence
  supports the claim; the ordering is a judgement about what a change *is*.
- **"Nothing references this" checks.** A module is referenced as `scripts/x.py`,
  as `scripts.x`, and through agent frontmatter, so emptiness from a narrow search
  is not evidence of emptiness. A script with its own test suite was deleted
  this way.
