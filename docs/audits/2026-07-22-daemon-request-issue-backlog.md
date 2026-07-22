# 212 open issues addressed to a pipeline deleted 2026-06-25

**Date:** 2026-07-22
**Author:** claude-code (`claude/dr-issue-backlog`)
**Scope:** audit only — no issue was closed, relabelled, or commented on.
**Evidence base:** `origin/main` at fetch time 2026-07-22; GitHub issue state via `gh` at the same time.

---

## 1. The finding

`gh issue list --state open --label daemon-request` returns **212 open issues**. Every one is a
work order addressed to the community-patch-loop "cheat loop" — the intake/writer/checker machinery
that was **removed from the codebase on 2026-06-25**. Nothing will ever pick them up.

The removal is not in dispute. The as-built spec on main says so, and names the trap:

> `openspec/specs/community-patch-loop/spec.md:104`
> *"As-built limitation: the historical cheat-loop intake/writer/checker machinery has been removed
> from the codebase (retired 2026-06-25), so 'auto-fix disabled' denotes the absence of that
> machinery rather than a runtime toggle — **there is no `AUTO_FIX_DISABLED` code gate**."*

First-party confirmation that the machinery is gone (both paths absent from `origin/main`):

```
$ git ls-tree origin/main scripts/wiki_bug_sync.py .github/workflows/auto-fix-bug.yml
(no output)
```

Only historical mentions survive, in `.agents/activity.log`.

### 1.1 The count correction

The originating brief for this lane reported **100** open `daemon-request` issues. That number was
`--limit 100` being hit, not a count. The real figure:

```
$ gh api -X GET search/issues -f q='repo:Jonnyton/TinyAssets is:issue is:open label:daemon-request' --jq '.total_count'
212
$ gh issue list --state open --label daemon-request --limit 400 --json number | jq length
212
```

**212 of the repo's 294 open issues (72%) are addressed to the deleted pipeline.**

The brief also named **#769 (2026-05-11)** as the oldest. That was the oldest *on the sampled page*.
The true oldest is **#187, 2026-05-02T20:21:52Z**.

---

## 2. Shape of the backlog

**Date range:** 2026-05-02 → 2026-06-05. Nothing has been filed against this label in **47 days** —
filing stopped ~3 weeks *before* the 2026-06-25 retirement, so the pipeline was already inert when
it was formally removed.

| Month | Open issues |
|---|---|
| 2026-05 | 207 |
| 2026-06 | 5 |

Heaviest filing days: 2026-05-06 (40), 2026-05-05 (39), 2026-05-24 (29), 2026-05-29 (24),
2026-05-11 (22), 2026-05-04 (17). The backlog is six burst-days, not a steady stream.

**Title prefix** (the filing lane):

| Prefix | Count |
|---|---|
| `[WIKI-PATCH]` | 85 |
| `[WIKI-DOCS]` | 49 |
| `[WIKI-DESIGN]` | 37 |
| `[BUG-NNN]` (no bracket prefix) | 32 |
| `[WIKI-FEATURE]` | 9 |

**Label shape.** Six labels are on all 212 — they are the pipeline's contract stamp, carrying no
per-issue signal:

| Count | Label |
|---|---|
| 212 | `daemon-request`, `payment:free-ok`, `writer-pool:claude-codex`, `checker:cross-family`, `gate-required`, `auto-change` |

The labels that *do* carry signal:

| Count | Label | Reading |
|---|---|---|
| 176 | `auto-fix-attempted` | the loop tried |
| 150 | `auto-fix-reviewed` | and a checker looked |
| 85 / 49 / 37 / 32 / 9 | `request:patch` / `request:docs-ops` / `request:project-design` / `request:bug` / `request:feature` | lane |
| 43 / 42 / 30 | `priority:primitive-surface` / `priority:loop-discipline` / `priority:primitive-layer` | the loop's own priority vocabulary |
| 34 | `await-primitive-layer` | blocked on substrate that may now exist |
| 32 | `auto-bug` | |
| 24 | `auto-fix-stale-gate` | |
| 20 / 6 / 5 / 1 | `severity:major` / `minor` / `critical` / `cosmetic` | only 32 carry any severity at all |
| 11 | `needs-human` | |
| 9 | `auto-fix-blocked` | |
| 1 each | `auto-fix-auth-missing`, `auth-expired`, `codex-subscription-missing`, `exhausted`, `retries-5`, `complete` | terminal failure states |

`auto-fix-attempted` on 176 of 212 means the loop *did* work most of these and still could not land
them. That is not a queue waiting for a worker; it is a queue the worker already failed at.

---

## 3. Verified sample — 20 issues checked against current main

**I checked 20 of 212 (9.4%).** Every classification below is from reading the code on
`origin/main`, not from the title. The sample is deliberately weighted toward the
2026-05-29 security/correctness audit batch (#1155–#1181), which is where the real engineering is;
it is *not* a uniform random sample, so the fixed/valid ratio below should not be extrapolated to
the `WIKI-DOCS` and `WIKI-DESIGN` lanes.

**Path translation:** issue bodies cite the pre-rename package `workflow/`. That package is now
`tinyassets/`. Every citation below is the current path.

**Result: 10 already-fixed, 9 still-valid, 1 obsolete.** Half the sample is dead.

### 3.1 Already fixed — 10

| # | Title (abridged) | Evidence on main |
|---|---|---|
| **#1157** | BUG-114 `backup_prune.py` emits every non-archive file as a delete target (data-loss) | `scripts/backup_prune.py:22-25` carries the fix note verbatim: *"Names not matching one of these patterns are NEVER deleted … Before 2026-06-10 the delete set was computed as all-names minus kept."* Line 88 filters `[n for n in names if re.match(pattern, n)]`. Fixed 2026-06-10. |
| **#1158** | BUG-115 `release_bonus` missing the `is_retracted` guard | `tinyassets/gates/actions.py:279` — `if claim.is_retracted: return {"status": "rejected", "error": "Cannot release bonus on a retracted claim."}`, inside `release_bonus` (`def` at :238). Siblings `stake_bonus` (:104) and `unstake_bonus` (:184) guard identically. |
| **#1159** | BUG-116 `GuardrailPipeline.apply` silently swallows a failed step | `tinyassets/context/guardrails.py:423-431` — the `except` now logs *and* `raise GuardrailPipelineError(step, step_index, e) from e`. No longer fails open. |
| **#1160** | BUG-117 SQLite connections never closed by `with _connect(...)` | `tinyassets/storage/__init__.py:752-764` — `_connect` is a generator context manager with `try: … finally: conn.close()`. |
| **#1176** | PR-155 `idempotent_results` grows unbounded | `tinyassets/idempotency.py:70` — `DELETE FROM idempotent_results WHERE accessed_at < ?`; plus the `accessed_at` column migration and index at :95-107 that TTL eviction needs. |
| **#1180** | PR-159 canon filenames can path-traverse out of canon | `tinyassets/ingestion/canon_names.py` exists and is titled *"Sandbox-safe canon filename helpers"* — `safe_canon_slug` (:33), `safe_canon_filename` (:45), `resolve_within_canon` (:11, rejects `..` and symlink escapes). Wired through `safe_canon_path` at ~9 call sites in `tinyassets/api/universe.py` (:3915, :4069, :4131, :4154, :4172, :4292, :4362, :4382). This is precisely what the issue asked for. |
| **#1181** | PR-160 `compute_payout_shares` returns floats | `tinyassets/attribution/calc.py:146-197` — signature returns `dict[str, MicroToken]`; implementation floors each share to `int`, then distributes the remainder largest-remainder-first (:180-192) so the result sums exactly to `total_payout`. |
| **#852** | BUG-081 `patch_branch` has no authority gate — any caller can mutate any public branch | `tinyassets/api/branches.py:2606` — comment reads *"BUG-081: author-gate. Reject patch_branch on a non-author branch"*; denial raised at :2621. |
| **#1169** | PR-148 wire OAuth/identity through the MCP edge — transport runs with no auth | `tinyassets/auth/{middleware,provider,workos_provider,wellknown}.py` all present; `middleware.py:159` registers pure-write handles for the anonymous 401 challenge; `provider.py:1142-1145` selects `WorkOSAuthProvider.from_env()`. Landed via PR #1437 (`b91a6b07`, 2026-07-15). |
| **#1283** | Retire the compiled cheat writer pipeline (`wiki_bug_sync.py` + `auto-fix-bug.yml`) | Both paths absent from `origin/main` (`git ls-tree` empty). **This issue asks for the very retirement that orphaned it** — the request was granted 2026-06-25 and the requester was deleted in the same act. |

### 3.2 Still valid — 9

| # | Title (abridged) | Evidence on main |
|---|---|---|
| **#1156** | BUG-113 ASP hard-failure check is fed the wrong type and fails open, so world-rule violations never trigger REVERT | **Both halves confirmed.** `tinyassets/evaluation/structural.py:1012` passes `state.get("extracted_facts", [])` — a **list** — into `ASPEngine.validate(scene_facts: str, …)` (`tinyassets/constraints/asp_engine.py:70-74`, parameter documented as *"ASP facts describing the current scene state"*, type `str`). The resulting exception is caught at :1024-1030 and returns `CheckResult(passed=True, score=0.5)`. A type error is silently converted into a pass. Severity `critical` as filed. |
| **#1163** | BUG-120 Escrow release/refund use non-atomic SELECT-then-UPDATE — concurrent resolves can double-resolve a lock | `tinyassets/payments/escrow.py:196-212` — `SELECT * FROM escrow_locks WHERE lock_id = ?`, then a Python-side `if not lock.is_locked: raise`, then `UPDATE escrow_locks SET status='released' … WHERE lock_id = ?` **with no `AND status='locked'` guard**. Two concurrent callers both pass the check. `refund_bonus` (:219-249) has the same shape. Money path. |
| **#1161** | BUG-118 `execution_cursor` step advanced non-atomically; parallel branches collide and lose events | `tinyassets/runs.py:2123` `execution_cursor = {"step": 0}`, then read-then-increment on a plain dict at :2188-2189, :2480-2481, :2508-2509, :2550-2551, :2565-2566 (and :3353-3354 for the resume cursor). No lock. |
| **#1175** | PR-154 Route `source_code` execution through the subprocess `NodeSandbox` — implemented but never used | `NodeSandbox` is defined at `tinyassets/node_sandbox.py:208`. A repo-wide grep finds references only in `tests/test_node_sandbox.py` and the class's own docstring example (:16). The live paths still use raw `exec()`: `tinyassets/graph_compiler.py:1781` and `tinyassets/executors/node_bid.py:177`, guarded only by the substring pattern scan at `graph_compiler.py:263` (`"os.system", "subprocess", "eval(", "exec(", "__import__"`) — which the design itself states is not a security boundary. |
| **#1173** | PR-152 Wire the six `memory_*` agent tools through the real memory manager — they return fake success | `tinyassets/memory/tools.py` — `memory_search` :63-78 (`TODO … route through ScopedMemoryRouter.query()`, returns `results: [], count: 0`), `memory_promote` :156, `memory_forget` :204-206 (`# Placeholder`), `memory_consolidate` :249-256 (counts hardcoded `0`), `memory_assert` :304, `memory_conflicts` :349-356. Six tools return `success: true` while doing nothing — a direct violation of AGENTS.md Hard Rule #8 (*"Fail loudly, never silently. Mock fallbacks that look like real output are worse than crashes."*). |
| **#1179** | PR-158 Sanitize caller-facing error payloads — handlers return raw `str(exc)` leaking paths/SQL/git internals | **116** occurrences of `str(exc)` across `tinyassets/**/*.py`; no sanitizer helper exists (the only `redact` hits are `directory_server.py:42-68`, scoped to directory status, unrelated). Worst concentrations: `api/market.py` (15), `api/universe.py` (13), `api/runtime_ops.py` (10), `api/runs.py` (7). Filed as "~59 handlers"; the current count is higher. |
| **#1177** | PR-156 Cache `build_igraph` / invalidate on edge write — KG rebuilt from a full SQL load every call | `tinyassets/knowledge/knowledge_graph.py:727` — `build_igraph` calls `self.get_edges(...)` and reconstructs the whole `ig.Graph` on every invocation. No cache attribute, no invalidation hook anywhere in the file. Callers: `knowledge/hipporag.py:125`, `knowledge/leiden.py:122`. Performance, not correctness. |
| **#1178** | PR-157 Mount the `api/*` routers in `create_app` — it returns a bare empty FastAPI shell | Literally true: `tinyassets/api/__init__.py:37` returns `FastAPI(title="TinyAssets Engine API")` with zero `include_router`. **But** the module docstring (:6-8) declares this deliberate — *"create_app() is a stub — the FastMCP submodule extraction is in-flight… import from fantasy_daemon.api directly, not from this package."* Classified still-valid on the literal claim; the disposition is a design question, not a bug fix. See §5. |
| **#1202** | Cross-reference `search_repo_files` in the `github_read.py` module docstring | Confirmed absent — zero occurrences of `search_repo_files` in `tinyassets/effectors/github_read.py`; `tinyassets/effectors/github_search.py` exists. A one-line docs fix. |

### 3.3 Obsolete — 1

| # | Title (abridged) | Evidence on main |
|---|---|---|
| **#1170** | PR-149 Bind the authenticated GitHub user into the OAuth code/token flow — tokens currently resolve to `anonymous` | **Premise superseded, not fixed.** The issue rests on *"PLAN.md:191 GitHub OAuth as the single identity primitive"*. Production identity is now **WorkOS**: `tinyassets/auth/provider.py:1142-1145` returns `WorkOSAuthProvider.from_env()`. The legacy local provider's `authorization_codes` table still carries `user_id TEXT NOT NULL DEFAULT 'anonymous'` (`provider.py:884`), but that path is `OptionalOAuthProvider`/`DevAuthProvider`, not the production identity path. Closing as-filed is correct; the residual `DEFAULT 'anonymous'` on the legacy table is a separate, much smaller hygiene item. |

---

## 4. What this sample means for the other 192

**Do not extrapolate the 50% already-fixed rate.** The sample is concentrated in the 2026-05-29
code-audit batch, the one lane most likely to have been fixed by subsequent work. Two structural
reasons the rest will classify differently:

- **The 49 `[WIKI-DOCS]` and 37 `[WIKI-DESIGN]` issues are mostly not code claims at all — verified,
  not inferred from titles.** I read the bodies of #1030, #947, and #555. All three carry
  `**Request kind:** docs-ops`, a `**Wiki path:** pages/…` pointer, and the footer
  *"Auto-filed by wiki-change-sync from wiki page `<path>`"*. They are **mirrors of wiki pages**,
  not independent claims, so there is nothing about them to verify as fixed-or-not.

  **The originals survive.** Checked #555's source page against the live brain through the MCP
  connector — `pages/concepts/chatbot-friction-as-loop-learning-telemetry.md` returns 4,822 chars
  with `source_read_proof` `sha256 853d15b0f1675d95…`, `updated 2026-05-06T22:26:15Z`. Closing the
  mirror issue therefore loses no content. Expect most of this class to disposition as
  **obsolete (wrong surface)**.

  *Method caveat for whoever re-checks:* the wiki root a local session resolves
  (`wiki_path()` → `%APPDATA%\TinyAssets\wiki`) is an **empty category scaffold — 0 md files**. A
  local `wiki_read` returns "Page not found" for pages that exist in production. Verify wiki
  survival against the **live brain** via the MCP connector, never the local root, or you will
  conclude the originals are gone and that closing these destroys content.
- **The 34 `await-primitive-layer` issues are blocked on substrate that may now exist.** Each needs
  a "does the primitive exist now?" check before disposition. `scripts/check_primitive_exists.py`
  is the calibrated tool for exactly this (AGENTS.md § Orient).

**Estimated remaining verification cost:** the ~85 `[WIKI-PATCH]` + 32 `[BUG-NNN]` code claims are
the set worth checking individually — roughly 117 issues at the ~5 minutes each this audit took.
The 86 docs/design issues can be dispositioned as a class without per-issue code verification.

---

## 5. Proposed disposition

### 5.1 Promote to a STATUS Work row or an OpenSpec change — 5

Ranked by severity. Each is confirmed live on main and each is a real defect, not a stale premise.

| # | Why it earns a lane | Suggested route |
|---|---|---|
| **#1156** | ASP world-rule violations **never trigger REVERT**. A type error is laundered into a pass. This is a quality gate that cannot fail — the exact "green tests that can't go red" class already recorded in memory. Filed `severity:critical`. | Failing test first (assert a list input raises, and that a violating scene reverts), then the fix. Small enough for a Work row. |
| **#1163** | Money. Concurrent resolve double-releases an escrow lock. Fix is a one-line `AND status='locked'` on the UPDATE plus a rowcount check — but it needs a concurrency test, so it is not a drive-by. | OpenSpec change against `openspec/specs/paid-market-economy`; it neighbours the existing P2 escrow-authz concern in STATUS. |
| **#1175** | User-supplied `source_code` runs in-process behind a substring scan the design itself disclaims as a non-boundary, while a real subprocess sandbox sits unused. Directly adjacent to the `universe-engine-sandbox-p0` finding already in memory. | OpenSpec change. Not a small edit — two call sites, and routing through a subprocess changes the state contract. |
| **#1179** | 116 raw `str(exc)` on caller-facing paths, concentrated in `api/`. Information disclosure on a **public** MCP surface. | OpenSpec change (needs a sanitizer primitive + a lint rule, or it regresses). |
| **#1161** | Parallel branches collide on `(run_id, step_index)` and **lose events**. Data loss, silent. | Work row. |

`#1173` (six tools faking success) is a sixth candidate and violates Hard Rule #8, but the fix is
"implement six subsystems," which is a program, not a task. Recommend it becomes an OpenSpec
proposal only when the memory subsystem is otherwise being worked; until then the honest fix is
one line each — raise `NotImplementedError` instead of returning `success: true`. That much *is* a
Work row, and it converts a silent lie into a loud failure.

### 5.2 Close as already-fixed — the 10 in §3.1

Each has a file:line above. Closing these is safe and I have verified each one.

### 5.3 Everything else — host decision

**A labelled bulk close is a host action.** It is outward-facing and hard to reverse, so I have not
run it. The command, for when the host decides:

```bash
# DO NOT RUN WITHOUT HOST APPROVAL — closes 212 issues.
# Dry run first: confirm the count and eyeball the list.
gh issue list --state open --label daemon-request --limit 400 \
  --json number,title --jq '.[] | "\(.number)\t\(.title)"' | less

# Then, per issue, with a comment that preserves the trail:
gh issue list --state open --label daemon-request --limit 400 --json number --jq '.[].number' \
| while read -r n; do
    gh issue close "$n" --reason "not planned" --comment \
"Closing as unroutable: this was auto-filed for the community-patch-loop intake/writer/checker \
pipeline, which was retired 2026-06-25 and removed from the codebase \
(openspec/specs/community-patch-loop/spec.md:104). No worker exists to claim it.

Triage record: docs/audits/2026-07-22-daemon-request-issue-backlog.md. If this issue described a \
real defect, it was either verified fixed there, or should be refiled against current main — the \
wiki page named in the body remains the original record either way."
  done
```

**Two guards on that command, both load-bearing:**

1. **Exclude the promoted set first.** Whichever of §5.1 the host accepts must be refiled (as a
   STATUS Work row or an OpenSpec change) *before* the bulk close runs, or add
   `--label keep-open` to them and filter the loop on `-label:keep-open`. Otherwise the close
   destroys the five findings this audit exists to rescue.
2. **The comment is what makes this reversible-in-spirit.** A bare close loses the reasoning; the
   comment leaves every future reader a pointer to the wiki original and to this audit.

**Cheaper alternative worth considering:** relabel all 212 `unroutable-legacy-loop` and leave them
open but filtered out of default views. Preserves everything, costs one label, and defers the
irreversible step. Recommend this if the host is at all unsure — the backlog has been inert for 47
days and is not urgent.

---

## 6. STATUS.md `Next` #1 is false and should be replaced

**Do not fold this in from here — `STATUS.md` is contended (#1506 landed 2026-07-21; #1507/#1510
in flight). This lane deliberately did not edit it.**

Current text, `origin/main:STATUS.md:51` — note this is the text **as rewritten by #1506
yesterday**, which reworded the row but kept its false premise:

> 1. **Cheat-loop CI retired (host 2026-06-25)** — `AUTO_FIX_DISABLED=true`; strip
>    intake/writer/checker machinery, keep get_status, deploy lanes, MCP canaries, dispatcher.

**It is false on two counts,** both contradicted by `openspec/specs/community-patch-loop/spec.md:104`:

1. It reads as a standing instruction to *strip* machinery that was already deleted 27 days ago.
2. It names `AUTO_FIX_DISABLED=true` as the mechanism. The spec states plainly: **there is no
   `AUTO_FIX_DISABLED` code gate.** A provider acting on this row would go looking for an env
   toggle that does not exist.

This is the failure class that cost the fleet 5 of 5 dispatched rows on 2026-07-21 — a stale row
whose premise nobody re-checked — and it is sitting in the `## Next` section that every provider
reads at session start.

### Proposed replacement — verbatim

Per AGENTS.md (*"Landed items leave STATUS.md — don't mark concerns DONE, delete them"*), the
directive is complete and the row should go. Replace it with a pointer to the one part that is
still open (the 212-issue residue), so the completed instruction stops being actionable:

```markdown
1. **Cheat-loop retired 2026-06-25 — done, no action.** Machinery is deleted (`wiki_bug_sync.py`, `auto-fix-bug.yml` absent from main); there is no `AUTO_FIX_DISABLED` gate (`openspec/specs/community-patch-loop/spec.md:104`). Residue: 212 open `daemon-request` issues, host-decision — `docs/audits/2026-07-22-daemon-request-issue-backlog.md`.
```

If the host bulk-closes or relabels the 212, delete the row outright — nothing remains.

---

## 7. Cross-family review

Dispatched to Codex (`scripts/codex_review.py`, read-only sandbox) as an adversarial refutation
pass over all 20 classifications in §3 — verdict recorded in §7.1 below. The review matters most
for the ten `already-fixed` calls: a wrong one there closes a live security bug.

### 7.1 Codex verdict

<!-- VERDICT -->

---

## 8. Method, and what would make this audit wrong

- Counts from the GitHub search API `total_count` **and** cross-checked against a
  `--limit 400` list length. Both say 212. If a future reader gets a different number, issues have
  been closed or filed since 2026-07-22.
- Every §3 classification was made by reading code on `origin/main`, never from the title. Titles in
  this backlog are unreliable: #1283 asks for a retirement that already happened, #1170 rests on an
  identity model the platform has since replaced.
- **The known weakness:** 20 of 212 is 9.4%, non-randomly sampled toward the code-audit batch. The
  fixed/valid split in §3 describes the sample, not the population. §4 says what would need to
  change to extend it.
- Issue bodies cite `workflow/` paths that no longer exist. Anyone re-checking these must translate
  to `tinyassets/` first — a naive grep of the cited path returns nothing and reads as
  "already deleted," which would misclassify live defects as fixed.
