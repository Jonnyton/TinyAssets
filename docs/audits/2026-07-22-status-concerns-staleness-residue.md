# The five STATUS.md Concerns the janitor pass left unverified

**Date:** 2026-07-22 · **Lane:** `claude/status-concerns-audit` · **Scope:** `origin/main:STATUS.md` Concerns block only.

PR #1506 (`docs(status): janitor pass`, merged `398b3256` 2026-07-22T03:53:42Z) re-stamped five
Concern rows `verified:2026-07-22` with file:line evidence and cut STATUS.md from 67 lines to 54.
It left five rows untouched. Three of those carry a newest stamp ~3 months old. This audit
classifies each of the five against first-party evidence.

**It does not fix anything.** It establishes what is true, so whoever next edits STATUS.md can
edit it correctly. Proposed replacement lines are in the PR body, not applied here — STATUS.md is
contended (PR #1507 is `CONFLICTING/DIRTY` against it).

## The rule

`AGENTS.md` §"Truth And Freshness": every Concern row begins `[filed:YYYY-MM-DD]` and gains
`verified:YYYY-MM-DD` *once someone re-checks the concern is still valid*. Rationale, per
`docs/audits/2026-04-28-status-md-coordination-gap.md` Rule 1: single-date stamps decay into stale
state without explicit re-verification semantics.

## Headline

**Three of five rows are discharged and should be deleted. One is inverted — a `P1` whose premise
is false today.** That P1 (line 16) has been the highest-severity row on the board since
2026-04-30, directing attention by its severity while its truth went unchecked for 83 days.

| Line | Row | Verdict | Disposition |
|---|---|---|---|
| 14 | `add_canon_from_path` sensitivity — 3 host-Qs REFRAMED | **resolved** | delete; residue is a Work row, not a Concern |
| 15 | Task #9 GROQ/GEMINI/XAI secrets + rotation e2e | **resolved** | delete — both halves discharged |
| 16 | **P1** Castles II `provider_exhausted` (BUG-038/039) | **inverted** | delete — fix merged, writers green live |
| 17 | Wiki drift to agent scratch space (81% of 614) | **current, figures stale** | restamp with 1,418 |
| 19 | `workflow-voice` 3 stale `pending` rows | **current** | keep, restamp |

---

## Line 14 — `add_canon_from_path` sensitivity → RESOLVED (delete)

> `[filed:2026-04-18 verified:2026-04-28]` `add_canon_from_path` sensitivity: 3 host-Qs REFRAMED by commons-first audit F3 (structured caveats).

The row's literal claim is that three host questions *were reframed*. That is true, and it
completed on 2026-04-28. A completed reframe is a landed item, and per `AGENTS.md` landed items
leave STATUS.md — the row records history, not an open concern.

**The 3 host-Qs are Q7.1/Q7.2/Q7.3** of `docs/design-notes/2026-04-18-add-canon-from-path-sensitivity.md`
§7. All three are marked **REFRAMED** in
`docs/audits/2026-04-28-rows-6-7-8-community-build-obviation-addendum.md:76` — Q7.1 ("has MCP
shipped `sensitiveHint`?") explicitly noted as *moot* because "F3 doesn't need protocol features
that don't exist". **No host question remains open.**

**What is still open is not what the row says.** F3's actual prescribed deliverable —
`docs/audits/2026-04-28-commons-first-tool-surface-audit.md:146-166`, a self-auditing response
carrying `commons_visibility`, `host_path_recorded`, `whitelist_check` — **never landed**:

```
$ git grep -n 'commons_visibility\|host_path_recorded\|whitelist_check' origin/main -- tinyassets/
(no output)
```

Those three identifiers exist only in audit docs and `.agents/activity.log:292`, which records the
work as filed Work row #21 (~1h, blockedBy #1). It was never built.

**The live enforcement primitive did ship.** `TINYASSETS_UPLOAD_WHITELIST` is enforced at
`tinyassets/api/universe.py:4003-4021`, and the check resolves the path first
(`src.resolve(strict=False)`) so `/allowed/../secret` cannot slip past; prefixes are parsed at
`tinyassets/api/engine_helpers.py:91`. Unset = permissive, with a host-facing reminder at
`engine_helpers.py:148-160`.

**Verdict: resolved as written.** Delete the row. If the F3 evidence-shape addition is still
wanted, it is a Work row with a Files cell, not a Concern — Concerns are for open risk, and this
one has a shipped enforcement primitive and no pending host input.

## Line 15 — Task #9 provider secrets → RESOLVED (delete)

> `[filed:2026-04-24]` Task #9 host Qs: GROQ/GEMINI/XAI GH Actions secrets present + rotation e2e validated once the deploy step ships.

Never verified in 89 days. Both halves are now discharged.

**Half 1 — secrets present: CONFIRMED.** `gh secret list` shows `GEMINI_API_KEY`, `GROQ_API_KEY`,
and `XAI_API_KEY`, all created 2026-04-24 (the day the row was filed). This was unanswerable in
April from a local checkout — `docs/audits/2026-04-28-status-md-concerns-staleness-pass.md:38`
marked it NEEDS-HOST-VERIFY for exactly that reason. `gh` settles it now.

**Half 2 — the precondition is met, and the ask is moot.** The row gates on "once the deploy step
ships." It has: `.github/workflows/deploy-prod.yml` exists and the last green prod deploy was
2026-07-22T01:09:05Z (`gh run list --workflow=deploy-prod.yml`), with the live release receipt
reporting `git_sha: 1605349e…` (verified an ancestor of `origin/main`) deployed at
2026-07-22T01:11:27Z.

But rotating those three secrets **cannot affect production**, because production never receives
or uses them:

- `git grep -n -i 'gemini\|groq\|xai' origin/main -- .github/` returns **zero hits**. No workflow
  plumbs these secrets anywhere.
- `deploy/compose.yml:54,169` sets `TINYASSETS_ALLOW_API_KEY_PROVIDERS: "0"`.
- `deploy/docker-entrypoint.sh:67-80` actively unsets `GEMINI_API_KEY` / `GROQ_API_KEY` /
  `XAI_API_KEY` unless that flag is truthy, logging `ignoring ${_name}: default daemon auth is
  subscription-only`.
- Live confirmation today: `read_graph target=status` against `https://tinyassets.io/mcp` returns
  `active_host.api_key_providers_enabled: false`.

This matches the `AGENTS.md` invariant "Subscription-only by default." The secrets are inert
residue in the GH secret store.

**Verdict: resolved.** Delete. The one durable fact worth keeping is not a concern but a cleanup
candidate: three unused API-key secrets sit in the repo's GH secret store with no consumer.

## Line 16 — **P1** Castles II `provider_exhausted` → INVERTED (delete)

> **`[filed:2026-04-30]`** Castles II run `28479d8ddfb44488`: `provider_exhausted` at `candidate_discovery` (BUG-038/039); blocks branch-run proof.

**This is the highest-risk row on the board and its premise is false today.**

**The named bug has a merged fix.** `65241e98` (2026-05-05) —
`[auto-change] BUG-038: Live branch run fails provider_exhausted before install-planning nodes (#464)`
— is an ancestor of `origin/main`. It is a real fix with a test: `workflow/graph_compiler.py` +11/-4,
mirrored in the plugin runtime, plus 39 lines of new test in `tests/test_llm_policy_override.py`.
`1f7b069b` (FEAT-006 Slice 2) later propagated provider-chain diagnostics through `CompilerError`.

**The live blocker is gone.** `read_graph target=status` against the production connector,
2026-07-22:

```
provider_auth.writers.codex       = ok  ("auth.json present at /data/.codex;
                                          live auth probe passed (real call ok)")
provider_auth.writers.claude-code = ok  ("CLAUDE_CODE_OAUTH_TOKEN set")
all_writers_unauthenticated       = false
per_provider_cooldown_remaining   = {claude-code:0, codex:0, gemini-free:0,
                                     groq-free:0, grok-free:0, ollama-local:0}
```

Both writer-role providers are authenticated — codex verified by a *live probe*, not just a
config read — and every cooldown is zero. "Blocks branch-run proof" does not describe today.

**The live-brain records are stale.** `pages/bugs/bug-038-…md` and `pages/bugs/bug-039-…md` both
still carry `status: open`, `updated: 2026-04-30`. Neither was touched after the fix merged
2026-05-05. Correcting them is a live-brain hygiene action, not a STATUS.md edit.

**The honest caveat — the failure *class* recurred, under different ids.** After the BUG-038 fix,
`AllProvidersExhaustedError` for `role=writer` reappeared as **BUG-087**, **BUG-089**, and
**BUG-097** (filed 2026-05-20, `status: open`). BUG-097 is notable: its own automated investigation
task failed with `CompilerError: Provider call failed in node 'intake_router': All providers
exhausted for role=writer` — the bug blocked its own investigation. So the *class* is real history.
What is false is this row: the April run id, the April bug pair, and the present-tense "blocks."

**Verdict: inverted.** Delete. The successor bugs live in the brain, which STATUS.md's own header
designates as primary for substantive work. Re-filing a Concern here would duplicate them — and
would need a fresh check first, because writers are green as of 2026-07-22.

## Line 17 — Wiki drift to agent scratch space → CURRENT, figures stale (restamp)

> `[filed:2026-05-19]` Wiki drifting to agent scratch space (81% of post-05-01 notes); host conversation: split coordination off the knowledge wiki?

**The direction is still true; the numbers are two months old; the 81% is not reproducible.**

**Fresh corpus measurement, 2026-07-22.** `read_page changed_since=2026-05-01T00:00:00Z` against
the live connector returns `total_matches: 1418`. The row was filed against 614. The corpus has
grown ~2.3× in the two months since, so the pressure the row describes has increased, not eased.

**Drift direction, qualitatively unchanged.** Agent-coordination notes dominate retrieval: the top
hit for the generic query `checker key PR merged review` is a Cowork operator-checker-key note
whose *title alone* runs ~1,100 characters; 8 of 12 hits on a `BUG-038` search were coordination
notes (`cowork-checker-key-*`, `codex-loop-health-*`, `codex-phase-1-queue-audit-*`).

**The 81% cannot be recomputed, and this is itself a finding.** Its enumeration artifact is
`.claude/agent-memory/navigator/wiki_sweep_cursor.md` — gitignored (`.gitignore:38`), untracked,
and absent from this checkout. `scripts/navigator_wiki_sweep.py` diffs against that cursor and
exits 4 without it. The public read surface cannot substitute: `read_page` search returns no total
and self-describes as "lexical best-effort, not a complete discovery or change-feed proof", and the
`changed_since` feed gives a total but no category/type breakdown.

**Secondary:** `STATUS.md`'s "Live brain notes" section still points at that same
`wiki_sweep_cursor.md` as the authority for "full enumeration + theme distribution (refresh before
relying)". It is a dangling pointer for anyone without that local file — which is every fresh
checkout and every other provider.

**Verdict: current.** Keep the row and the host question, which is genuinely un-had. Restamp
`verified:2026-07-22` and replace 614 with 1,418. Recomputing the percentage needs a fresh full
sweep, which needs the cursor rebuilt or an enumeration path that does not depend on one agent's
untracked memory file.

## Line 19 — `workflow-voice` stale `pending` rows → CURRENT (restamp)

> `[filed:2026-07-13 verified:2026-07-15]` `workflow-voice` (dormant) has 3 stale `pending` queue rows — review before ever activating it.

**Still true, and the guard condition still holds.**

Corroborated by `docs/audits/2026-07-15-workflow-data-volume-audit.md` §5 (D2): workflow-voice was
revived from archive 2026-07-15 and "workflow-voice's restored queue carries 3 month-old `pending`
rows — restored VERBATIM (inert while dormant; dispatcher polls the active universe only).
Review/cancel them before ever making workflow-voice the active universe, or they will be claimed
and executed."

Live check 2026-07-22 — `read_graph target=graphs` confirms the dormancy the safety argument rests
on: `workflow-voice` is `phase_human: paused`, `staleness: dormant`,
`last_activity_at: 2026-05-20T04:14:05Z`, and it is **not** the active universe. So the rows remain
inert and the row remains a correct pre-activation warning.

**Honest limit on "3".** I could not re-count the pending rows through the public read surface —
`read_graph target=runs graph_id=workflow-voice` returns `No runs match the filter`, because the
queue is `branch_tasks`, not runs. The count 3 rests on the 2026-07-15 audit, not a fresh
enumeration. The *warning* is verified; the *number* is inherited.

**Verdict: current.** Keep, restamp `verified:2026-07-22`. Lowest priority of the five — it was
already the freshest.

---

## Secondary: STATUS.md is over its own byte budget

`origin/main:STATUS.md` is **5,346 bytes** against its stated "**Budget 4 KB / 60 lines**" — 30%
over. The line budget is met (54 of 60); the byte budget is not. The file *grew* 65 bytes during
the janitor pass that shortened it by 13 lines, because the surviving rows absorbed evidence
citations.

Codex flagged this as the one unaddressed `Required:` item on PR #1506. Deleting lines 14, 15, and
16 as this audit recommends removes ~490 bytes, which does not close the gap alone but is most of
the way from 5,346 to a defensible number. The budget line itself may also deserve a look: "4 KB /
60 lines" is two budgets that have drifted out of proportion with each other, since 54 rows of
≤150 chars cannot fit in 4 KB.

## Method note — where each verdict came from

Three of the five rows were **not settleable from the repo alone**, which is why they sat:

| Row | Settled by |
|---|---|
| 14 | repo only (`git grep`, audit + design-note cross-read) |
| 15 | repo + `gh secret list` + `gh run list` + live `read_graph` |
| 16 | git history + **live brain** (`read_page` BUG pages) + live `read_graph` provider health |
| 17 | **live brain** corpus count; repo for the missing-cursor finding |
| 19 | repo audit + live `read_graph target=graphs` dormancy check |

The reusable lesson: a Concern that depends on live state will never be discharged by a
repo-only janitor pass, and will therefore sit accumulating severity. Line 16 was a `P1` for 83
days because nobody with the live connector in reach looked at `provider_auth`. The check that
settled it took one read call. **When a row names a live surface, verify against the live surface —
`get_status` / `read_graph target=status` is one call and it carries provider health, release sha,
and queue state.**
