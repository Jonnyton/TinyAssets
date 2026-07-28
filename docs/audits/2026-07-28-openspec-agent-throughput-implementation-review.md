Verification is complete — I've read all artifacts, run the tests, exercised the CLI on the real repo, and validated counts against ground truth. Here is the full report.

## Verification summary

**What checks out (evidence, all run 2026-07-28 on this worktree, Windows):**

- **Tests/lint/validation:** `pytest tests/test_openspec_flow.py` → 8 passed; `ruff check` clean on both new files; `openspec validate restore-openspec-delivery-flow --strict` → valid; `check_cross_provider_drift.py` → clean.
- **Delta-spec conformance:** audit enumerates all 35 active changes, task counts have *exact* parity with the audit's `openspec list --json` numbers (1,200 total / 366 done / 834 unchecked for the 34 audit-basis changes; +7/5/2 for this change itself). Text and JSON expose the same summary/recommendations/provider-WIP; output is byte-deterministic across runs; tracked tree unchanged after inspection (test + live `git status` check).
- **Admission:** 13-task candidate exits 2 naming the ceiling; exact-identity WIP=1 rejects a second change and self-excludes the candidate (re-checking your own claimed change passes — verified live with `codex-gpt5-desktop-throughput`); a different session suffix passes but gets the suffix-violation warning plus global WIP (11 today); umbrella language warns without blocking (it even fires on this change's own proposal, correctly as warning-only).
- **Legacy debt:** 29 oversized changes on the real repo; audit still exits 0 and stays read-only.
- **Git flow counts:** for the window I tested (`43d031e5..HEAD`, 63 commits), the tool's 14 admitted / 1 archived matches per-commit ground truth exactly — all 14 counted admissions are genuinely new dirs, and the single archive shows as `A` lines (no rename collapse in practice). The audit doc's "5 archives" figure used a different 100-commit base, not a tool defect.
- **No session-start gate; cross-provider consistent:** AGENTS.md, `openspec/config.yaml`, and both SKILL.md mirrors (byte-identical blobs) all say dispatch/triage-time only.
- **Prior ADAPT folded:** all four required corrections from the Claude review are present (exact-identity WIP + global visibility + suffix violation; invocation pinning; dated 12-task calibration incl. the corrected Anthropic framing in the audit doc; no `.codex/` mirror in the STATUS row).

## Findings

**Blocking (fold before land):**

1. **Owner attribution can be wrong, and the WIP=1 gate has an ordering-dependent bypass** — `scripts/openspec_flow.py:58-77,180-181`. `_row_mentions` matches the change name anywhere in the raw row (including the Depends cell), and `_classify` takes the *first* active row as owner. Live instance today: `universe-visibility`'s own STATUS row is `pending` (STATUS.md:40), but the tool reports it `in-flight` owned by `codex-gpt5-desktop-full-product` because that provider's public-read-completeness row (STATUS.md:24) mentions it in its Depends cell. Worse, the latent inverse: if a change's own `claimed:A` row sits *below* another claimed row (provider B) that merely mentions it, the change is attributed to B, provider A's WIP reads empty, and A passes `check-change` for a second change — bypassing the delta spec's SHALL-reject (`specs/development-coordination-runtime/spec.md:36-39`). The design's documented false-positive risk (design.md:115-116) covers over-attribution, not this fail-open. Small fix: count the change against *every* matching active row's provider (which also matches design.md:73-74's counting language), or prefer the row whose Files cell contains `openspec/changes/<name>`.

2. **The documented pre-creation invocation always returns a confusing BLOCK** — AGENTS.md ("Before creating or claiming a change, run … check-change"), `openspec/config.yaml:35`, both SKILL.md files. For a change that doesn't exist yet, `check-change` exits 2 with `Unknown active change` (`scripts/openspec_flow.py:245-247`) and never evaluates the WIP rule — verified live. Fail-closed, so no unsafe admission, but a provider following the canonical text verbatim gets what reads as tool failure. Fix in text ("when creating — after scaffolding artifacts — or before claiming") or behavior (unknown change → run the provider-WIP check and report it with a "not yet created" note).

**Non-blocking suggestions:**

3. The Claude review doc's first line points to `docs/reviews/2026-07-28-restore-openspec-delivery-flow-claude-review.md`, which doesn't exist — the content lives at `docs/audits/2026-07-28-openspec-agent-throughput-claude-review.md:1`. Fix the self-reference.
4. Delta-spec scenario "Active change is absent from live coordination → untracked" (spec.md:22-27) conflicts with the implementation's complete-but-unarchived precedence (`openspec_flow.py:68-69`): a complete change absent from STATUS is classified complete-but-unarchived, not untracked. The behavior is the more useful one; tighten the scenario to "with unchecked tasks" before sync.
5. `_git_flow` (`openspec_flow.py:80-118`) is an endpoint diff: it misses changes admitted *and* archived within the window, would skip `R` rename lines if git ever emits them for archive moves, and counts a pre-existing change gaining a brand-new file as "admitted." Empirically exact on the checked window; keep as a caveat or switch to `git log --diff-filter=A`.
6. A `--since` value starting with `-` is passed into git's argv (`openspec_flow.py:84-91`); e.g. `--output=x` would make the read-only tool write a file. Same-user local tool, so hardening only: reject `since.startswith("-")`.
7. A change dir without `tasks.md` is silently invisible to audit (`openspec_flow.py:144-148`); consider reporting it for triage. Test gaps: the unknown-change error path, `check-change --json`, and audit text via `main()` are untested.
8. The STATUS row's Depends text ("fold four required text corrections before build") is now stale since the corrections are folded — normal living-board upkeep for the lane owner, not a diff defect.

Findings 1 and 2 are exactly the kind of small correction task 4.1 ("adapt all blocking findings") anticipates, and the lane is still open (4.1/4.2 unchecked), so they land naturally here without a new change.

VERDICT: ADAPT
