# Auth surface sweep — completed finding-ownership map

**Date:** 2026-07-22
**Lane:** `claude/auth-audit-owner-map` (claude-code)
**Subject audit:** `docs/audits/2026-07-22-auth-surface-sweep.md`, carried by **PR #1544**
**Measured against:** all **95** open PRs, re-verified at `origin/main @ de64fe57`
**Scope:** classification and carry only. **No finding is fixed here.**

> **Freshness note.** The map was first built against `origin/main @ 0bc841aa` / 96 open PRs
> and re-verified mid-lane at `de64fe57` / 95 open PRs. Two things moved, and both are
> recorded below rather than silently absorbed: **#1435 closed without merging** (the 96→95
> delta), and **#1546 landed a partial fix for finding 1**. All four AMBIGUOUS verdicts were
> re-checked against `de64fe57` and are unchanged; all nine findings' cited symbols are still
> present there.

---

## Why this note exists

A completed auth surface sweep audited `origin/main @ 220a1fc8` and returned
**"Reject current auth posture for unattended auto-deploy"** — 1 Critical, 2 High,
6 lower findings on the public MCP surface. Two things were wrong with its life so far:

1. **It was produced into a gitignored directory** (`output/s2-gate/auth-surface-sweep.md`;
   `.gitignore:70` `output/`) and nothing carried it. PR #1544 carries it; that PR is
   **still a draft with 0 reviews, and the audit is still absent from `main`.**
2. **Nothing mapped the 9 findings to owners.** Without that map, every session either
   rebuilds a ~95-PR file cache or — worse — assumes a finding is handled because some
   open PR happens to touch the same file.

This note publishes the map so the next sessions read it instead of rebuilding it.

### The trap this map exists to prevent

**A file appearing in a PR's file-set says nothing about whether that PR fixes the finding.**
Four open PRs touch `tinyassets/auth/provider.py`; not one of them is about finding 5.
Ownership below is asserted from a PR's *stated purpose plus its actual diff hunks*, never
from file overlap. Every UNOWNED verdict names the hunk that was checked and rejected.

The sharpest instance is finding 8: PR **#1571** edits
`tests/test_quality_leaderboard_auth_boundary.py` — finding 8's own action, its own test
file, under a title about making vacuous tests fail. It still does not touch the finding.
Overlap that close is indistinguishable from ownership until you read the hunks.

---

## The completed map

| # | Sev | Finding | Key files | Ownership |
|---|---|---|---|---|
| 1 | Critical | `run_graph` drops universe credential context → host credentials used | `api/runs.py`, `providers/base.py`, `credential_vault.py` | **OWNED, PARTIALLY LANDED** — #1546 on main mitigates *other* paths; the audited `run_graph` scenario is **still live**. #1549 / R2-1 still owns the real fix. See below. |
| 2 | High | "private" Goals anonymously readable | `api/market.py`, `daemon_server.py` | **OWNED** — PR #1554 |
| 3 | High | gate-event attester/verifier identity is caller-supplied | `gate_events/schema.py`, `gate_events/store.py` | **UNOWNED** — briefed this cycle (`_backlog/codex/`) |
| 4 | Medium | scheduler `owner_actor` is caller-supplied and trusted as proof | `scheduler.py`, `api/runtime_ops.py` | **UNOWNED** — briefed this cycle (`_backlog/codex/`) |
| 5 | Med/cond | every request inherits `UNIVERSE_SERVER_CAPABILITIES` | `api/market.py:70-86`, `api/runs.py:51-67`, `auth/provider.py:281-325` | **UNOWNED** ← *resolved from AMBIGUOUS* |
| 6 | Med/cond | `_current_actor()` env fallback is an authorization input | `api/engine_helpers.py`, `api/branches.py` | **UNOWNED** — briefed this cycle; also a standing STATUS P2 Concern |
| 7 | Low | anonymous `read_page` creates durable universe state | `api/wiki.py`, `api/permissions.py` | **UNOWNED** ← *resolved from AMBIGUOUS* |
| 8 | Medium | read-classified actions execute LLMs / write ledgers | `auth/provider.py`, `api/extensions.py`, `api/auto_ship_actions.py` | **UNOWNED** ← *resolved from AMBIGUOUS* |
| 9 | Latent | paid-market escrow authority via `_current_actor()` | `api/engine_helpers.py`, `paid_market/` | **UNOWNED** ← *resolved from AMBIGUOUS* |

**Net: 2 of 9 have an owner (findings 1 and 2). 7 are unowned — including one of the two
High findings (#3).** Of those seven, three (3, 4, 6) have implementation briefs this cycle.
**Findings 5, 7, 8, and 9 have no owner and no brief at all.**

Neither owned finding is closed: #1549 (finding 1) and #1554 (finding 2) are both open, and
both are titled *"stranded lane, DO NOT MERGE"*. So **at the time of writing, zero of the nine
findings have a landed fix for the scenario the audit described** — including the Critical one,
whose partial fix (#1546) is discussed immediately below.

---

## Freshness correction: finding 1 is partially fixed on main, and the Critical path is not the part that got fixed

While this lane ran, **`92dd60c5` (#1546) landed on `main`** — *"a universe with no credential ran
on the host's subscription."* It adds to `tinyassets/providers/base.py`:

```python
HOST_SUBSCRIPTION_ENV_VARS = ("CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR", "CODEX_HOME")
...
resolved = Path(universe_dir) if universe_dir is not None else resolve_universe_from_env(env)
if resolved is not None and all(env.get(k) == before.get(k) for k in HOST_SUBSCRIPTION_ENV_VARS):
    for name in HOST_SUBSCRIPTION_ENV_VARS:
        env.pop(name, None)          # fail closed, not open
```

This is a real fix and it is well built. **It does not close finding 1's audited scenario**, and
that distinction is the whole reason this note re-verified rather than trusting the row:

1. `tinyassets/api/runs.py` still has **zero `UniverseContext` references** on `de64fe57`. The
   audit's remediation #1 — *thread a mandatory `UniverseContext` through `run_graph` → async run
   → compiler* — has not been done. So `run_graph` still reaches the provider with
   `universe_dir=None`.
2. The guard's fallback is `resolve_universe_from_env(env)`
   (`credential_vault.py:427-431`), which reads **only** the env var `TINYASSETS_UNIVERSE`.
3. `TINYASSETS_UNIVERSE` is set in exactly one place in the tree — `cloud_worker.py:183`. It is
   **not** set in `api/runs.py`, `runs.py`, or `graph_compiler.py`.
4. It is **not** set in `deploy/compose.yml` either — while `CODEX_HOME: /data/.codex` and
   `CLAUDE_CONFIG_DIR: /data/.claude` *are* set there.

So on a `run_graph` call in production: `universe_dir` is `None`, `TINYASSETS_UNIVERSE` is unset,
`resolved` is `None`, the `resolved is not None` condition is False, **the strip never executes**,
and the host subscription variables survive into the provider subprocess — exactly the Critical
failure the audit described.

**What #1546 does close:** the `converse` path (which constructs `UniverseContext` explicitly and
passes `universe_dir`) and the `cloud_worker` path (which sets `TINYASSETS_UNIVERSE` itself).
Those are genuine wins and the audit's finding 1 evidence section names `converse` as the
correctly-scoped contrast.

**Why this matters for how the row is read:** a reasonable session seeing "#1546 — fix(credentials):
a universe with no credential ran on the host's subscription" merged into `main` would mark
finding 1 closed. The commit title matches the finding almost word for word. It is still open on
the path the audit rated Critical. **Do not retire R2-1 or #1549 on the strength of #1546.**

---

## Resolution of the four AMBIGUOUS rows

Method: build a file→PR map over all 96 open PRs, take every PR touching a file the
finding cites, then read that PR's **actual hunks** for the cited symbol.

```bash
export MSYS_NO_PATHCONV=1; mkdir -p .tmp && : > .tmp/pr-files-cache.txt
for n in $(gh pr list --state open --limit 150 --json number --jq '.[].number'); do
  gh pr view $n --json files --jq '.files[].path' | sed "s|^|$n\t|" >> .tmp/pr-files-cache.txt; done
```

The brief's candidate lists were **incomplete**; the cache surfaced PRs it did not name
(#1468, #1549, #1554, #1571, #1572 on finding-5 files; #1465 on `permissions.py`;
**#1571 on `test_quality_leaderboard_auth_boundary.py`**, which is finding 8's own test file).
Each of those was checked. The verdicts did not change, but they were not free.

### Finding 5 — ambient `UNIVERSE_SERVER_CAPABILITIES` → **UNOWNED**

The defect, confirmed present at `origin/main`:

```python
# tinyassets/api/market.py:70-86
ENV_CAPABILITIES_VAR = "UNIVERSE_SERVER_CAPABILITIES"

def _current_actor_grants() -> tuple[str, ...]:
    raw = os.environ.get(ENV_CAPABILITIES_VAR, "")      # process-global, not actor-bound
    return tuple(part for part in raw.replace(",", " ").split() if part)
```

`resolve_permission` (`auth/provider.py:281-325`) then decides purely on
`required_scope in presented_grants` — it never binds a grant to `actor_id`.
The same `ENV_CAPABILITIES_VAR` pattern is in `api/runs.py:51` and `api/universe.py:90`.

**Eight** open PRs touch a cited file — `market.py`: #1554 · `runs.py`: #1466 #1467 #1468 #1549
#1572 · `auth/provider.py`: #1465 #1466 #1467 #1493 (plus #1435, since **closed unmerged**).
Grepping every one of those diffs for `UNIVERSE_SERVER_CAPABILITIES`, `ENV_CAPABILITIES_VAR`,
`resolve_permission`, and `_env_capabilities` returns **zero hits in all of them**. The
`auth/provider.py` hunks that do exist land elsewhere entirely: #1466 at `:385` and #1467 at
`:406` (`to_dict`), #1465 and #1493 in `build_action_scope_registry` (~`:502-590`), and the
now-closed #1435 at `:1071` (`is_auth_required`). None reaches `resolve_permission` at
`:281-325`.

> **UNOWNED.** No open PR modifies the ambient-grant read or the actor-unbound verdict.

### Finding 7 — anonymous `read_page` creates durable state → **UNOWNED**

Two PRs touch `api/wiki.py` (#1464, #1550); one touches `api/permissions.py` (#1465).

- **#1464** — its only `_ensure_wiki_scaffold` changes are five added *call sites inside
  `tests/test_bug_investigation_wiring.py`*. Test setup, not a gate.
- **#1550** — genuinely edits `_ensure_wiki_scaffold` (`@@ -144,6 +157,13 @@`), but only to
  write **one more file** (a workflow-schema asset) into the scaffold. It adds no
  universe-existence check, and the ACL-gate→scaffold call site is unchanged. This
  **slightly widens** finding 7: an anonymous `read_page` against an unknown universe would
  create the same directories plus an additional file.
- **#1465** — its `permissions.py` hunk is `@@ -149,3 +149,72 @@`, appending
  `current_github_handle` and `current_actor_is_universe_owner`. It does not touch
  `universe_public_read_allowed` at `:59-89`, where the "missing rules row ⇒ publicly
  readable" default lives.

> **UNOWNED.** And #1550 marginally expands the blast radius rather than reducing it.

### Finding 8 — read-classified actions execute/persist → **UNOWNED**

This is the row where file-overlap reasoning is most seductive.

- **#1571** is titled *"test: make four vacuous test groups able to fail"* and edits
  **`tests/test_quality_leaderboard_auth_boundary.py`** — finding 8's own action, its own
  test file. But its added assertions are about **branch visibility** (`assert
  _mock_selector_passthrough == [{"pub-eve","pub-bob","pub-bob-public-fork"}]`, `assert
  "PRIVATE" not in result["rationale"]`). It never touches the action's scope
  classification, and the selector dispatch it asserts against is *mocked out*. Adjacent to
  the finding; not the finding.
- **#1493** removes `_action_open_auto_ship_pr` and drops `"open_auto_ship_pr"` from
  `extension_writes` — a legacy-route retirement. `validate_ship_packet` keeps both its
  `read` classification and its `record_in_ledger` write path; the diff's only
  `validate_ship_packet` lines are the unchanged `_AUTO_SHIP_ACTIONS` registry entry and a
  removed docstring reference inside the deleted function.
- **#1465** only *adds* `review_queue_*` to `extension_writes`. The
  `"quality_leaderboard", "recommended_parent_for_fork",` line in its diff is a **context
  line**, not an addition — it is an error-message action list, and the `+` lines beneath it
  are all `review_queue_*`.

> **UNOWNED.** No open PR reclassifies `quality_leaderboard`,
> `recommended_parent_for_fork`, or `validate_ship_packet`.

### Finding 9 — paid-market escrow via `_current_actor()` → **UNOWNED**

The strongest of the four, and the cheapest to check:

```bash
awk -F'\t' '$2 ~ /engine_helpers|paid_market/' .tmp/pr-files-cache.txt   # -> no rows
```

**No open PR touches `tinyassets/api/engine_helpers.py` or `tinyassets/paid_market/` at all.**
Finding 9 shares its root cause with finding 6, so the finding-6 brief in `_backlog/codex/`
is the natural place for it — but as written that brief covers the private-branch read path,
not escrow authority. Worth confirming the escrow surface is inside its scope.

Note this is *latent*, not live: `TINYASSETS_PAID_MARKET=off` and the live probe confirmed
`paid_market_flag_on=false`. It is a correctness debt that becomes exploitable the moment the
flag flips.

---

## Cross-family review

Per `AGENTS.md` § *Project Skills*, the classifications above were dispatched to Codex
(opposite family) as a **refutation** gate — "prove these four are actually owned" — with the
explicit worry named: *an indirect fix in a file I did not think to grep, a renamed/removed
symbol, or a finding already fixed on `main` (stale audit)*.

<!-- CODEX_VERDICT_BLOCK -->

### Three dispatch hazards hit in one lane — all three produce a *plausible* wrong verdict

Recorded because each would have yielded a fabricated or false cross-family sign-off, and each
was caught only by checking the verdict's **shape** before its substance.

1. **Shared `/tmp` output paths are not safe on a saturated fleet.** The first dispatch wrote to
   `/tmp/codex_verdict.txt`; a *different concurrently-running lane* clobbered it. The file came
   back holding `VERDICT_A/B/C` about PRs #1435/#1432 and design notes — a fluent, confident
   answer to **someone else's question**. Read at face value it was a cross-family approval of
   work it had never looked at. Fix: lane-local output path (`.lane/codex_verdict*.txt`).
   Extends the known "stale `--out` file returned as a fresh verdict" failure.
2. **Codex asserted a false premise with total confidence.** Run 2 opened with *"GitHub currently
   reports only 1 open PR, not 96 … I'm treating the supplied PR map as historical"* and began
   re-deriving everything from that. The real count was **95**; its sandboxed `gh` call had
   returned a truncated result. An unverified reviewer premise silently invalidates the entire
   review. Fix: state the ground truth in the ask *and* tell the reviewer that a contradicting
   result means its own call failed and must be retried.
3. **A verdict-token grep matches your own prompt.** Grepping `^VERDICT_` — and even
   `^VERDICT_.*(approve|adapt|reject)` — matched the **output-contract template echoed back in
   the transcript**, reporting "5 verdicts" and then "6 verdicts" while Codex was still running
   greps. Fix: match a *single* verdict word and exclude the literal `|` of the template
   alternation.

The general rule these share: **on a busy fleet, treat a returned verdict as untrusted input.**
Confirm it answers *your* contract, about *your* subject, from *true* premises — before reading
a word of its reasoning.

---

## The other half of the job: #1544 is ready and nothing is moving it

| | |
|---|---|
| PR | **#1544** — `docs(audit): carry the completed auth surface sweep out of gitignored output/` |
| Diff | **1 file, +416/-0**, `docs/audits/2026-07-22-auth-surface-sweep.md` — docs-only |
| Checks | `Diff scope declared` **pass** · `policy` **pass** |
| Reviews | **0** |
| State | **draft**, `MERGEABLE`, auto-merge **not** enabled |
| On main? | **No** — `git ls-tree origin/main docs/audits/2026-07-22-auth-surface-sweep.md` → empty |

**#1544 is ready. It needs a human review and an undraft — nothing else.** It is docs-only,
its diff scope is declared and passing, and it carries the body byte-identical (the carrier
verified with `cmp`). This lane deliberately does **not** merge it: not this lane's PR, and
per the standing repo hazard a `--draft` flag is not a gate — 20+ drafts were undrafted and
squash-merged at 1-second intervals on 2026-07-22, three of them titled "DO NOT MERGE".
The correct action is a review, by a human, on purpose.

Until it merges, the only durable copy of a reject-verdict security audit is an unmerged
draft branch plus an untracked working-tree file.

---

## The process defect

**A lane's deliverable is only real if it lands on a ref someone else can fetch, and nothing
in the pipeline checks that.** The auth sweep was dispatched read-only, correctly refused to
create a tracked file, and wrote its output to `output/s2-gate/` — gitignored at
`.gitignore:70`. The lane reported success and exited; the audit was invisible to git, to
every other provider session, and to any fresh checkout. PR #1539 is the same defect with a
different cause: 36 finished lanes committed locally and could not `git push` because the
Codex sandbox blocked egress. Different mechanism, identical outcome — **work that is done,
correct, and unreachable, with the dispatcher reporting success either way.** In both cases
the failure was silent precisely because "the lane finished" and "the lane published" were
never distinguished.

**Smallest concrete change:** make the lane-report path tracked instead of ignored — add a
`!output/s2-gate/` negation to `.gitignore` — so a finished report is a normal untracked-then-
committable file that `git status` and `worktree_status.py` already surface, instead of one
git is configured not to see. That is one line and it closes the #1544 class. It does **not**
close the #1539 class (blocked push), which needs its own fix; the shared lesson is that a
lane's exit code must not be accepted as evidence of publication.

---

## Proposed STATUS.md Concern row — NOT applied here

`STATUS.md` is untouched by this lane (16 open PRs write it). If a steward agrees, the
proposed row is:

```
- **[P1 filed:2026-07-22]** Auth sweep: 7 of 9 findings unowned (both remaining
  High). Map: `docs/audits/2026-07-22-auth-finding-ownership-map.md`; audit carried
  by #1544 (draft, 0 reviews, absent from main).
```

At 148 characters it fits the ≤150-char Concern budget.

---

## Reproduce this map

```bash
# 1. file -> PR map over every open PR
export MSYS_NO_PATHCONV=1; mkdir -p .tmp && : > .tmp/pr-files-cache.txt
for n in $(gh pr list --state open --limit 150 --json number --jq '.[].number'); do
  gh pr view $n --json files --jq '.files[].path' | sed "s|^|$n\t|" >> .tmp/pr-files-cache.txt; done

# 2. candidates for a finding = PRs touching its cited files
awk -F'\t' '$2=="tinyassets/api/engine_helpers.py"{print $1}' .tmp/pr-files-cache.txt | sort -un

# 3. the step that actually decides ownership — read the HUNKS, not the file list
gh pr diff <N> | grep -n '<the-cited-symbol>'
```

Step 3 is the one that cannot be skipped. Steps 1–2 only produce suspects.
