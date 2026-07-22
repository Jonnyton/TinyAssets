# Landedness of the two Codex `adapt` verdicts on PR #1506

**Verified 2026-07-22T04:28Z against `origin/main` at `398b3256`** (which *is* PR #1506's merge
commit — main's tip at time of writing). Every classification below was re-derived this session with
the command shown; nothing is carried from a prior summary. Windows, Python 3.14, primary checkout
`C:/Users/Jonathan/Projects/TinyAssets`.

## The governing facts

Codex reviewed PR #1506 (*"docs(status): janitor pass — 67 lines/13.8 KB -> 55 lines/5.3 KB"*) at
`8cba3ace` and returned **`VERDICT: adapt` twice**, in two independent runs:

| | Verdict | Written to | Items |
|---|---|---|---|
| **A** | `adapt` | `docs/audits/2026-07-22-status-janitor-pr1506-codex-review.md` (mtime 2026-07-21 18:55) | 5, all `Required:` |
| **B** | `adapt` | `docs/audits/2026-07-22-uptime-canary-false-red-codex-review.md` (mtime 2026-07-21 19:01) — **misfiled**; the name reads as a review of the uptime-canary incident audit, but every citation is to `STATUS.md` / `PLAN.md` / `.agents/activity.log` from the `wf-status-janitor-0722` lane | 6: 2 `Critical:` + 4 `Required:` |

Both were written to disk and **neither was committed**. Both are still untracked in the primary
checkout; [PR #1516](https://github.com/Jonnyton/TinyAssets/pull/1516) carries them into git verbatim.

PR #1506 **merged at 2026-07-22T03:53:42Z** as `398b3256`, by `app/github-actions`.

**Across both verdicts, 11 numbered items: 10 are FIXED on `origin/main`, 1 is STILL-OPEN.** The one
still open is the 4 KiB `STATUS.md` byte budget — and it is *further* from budget than when Codex
measured it.

## Correction to the framing this lane was dispatched with

Two premises in the dispatch brief are wrong, and the corrections change the story materially. Per
AGENTS.md §"Truth And Freshness" (*contradictions must be downgraded immediately*), they are recorded
here rather than silently worked around.

**1. "The verdict was never posted to the PR" — false as of merge time.** It was true at authoring:
`gh pr view 1506` showed 0 comments and 0 reviews until 2026-07-22T02:31Z. But a later fleet lane
relayed **both** verdicts onto the thread at `02:31:22Z` and `02:31:26Z` — **82 minutes before the
merge** — each with a per-finding current-state table. A third comment at `02:45:45Z` added an
independent deletion-safety audit. The public record existed before the merge.

**2. The required items were not "already fixed" by coincidence — the PR fixed them, deliberately.**
The author read both verdicts off local disk and responded in-PR. Commit `c8c0e09e` (rebased to
`2f1178c0`) is titled *"docs(status): correct four false premises the janitor pass left behind"* and
opens:

> *"Codex reviewed #1506 at 8cba3ace and returned ADAPT twice. The verdicts were written to
> docs/audits/ but never reached the PR, so this is the response."*

So this is not a case of a review being ignored and the fixes landing by luck. **The feedback loop
worked; only its durable artifact was missing.** What failed was archival, not review. That
distinction matters for what to do about it: the fix is committing the artifacts (#1516's job), not
re-opening the review.

What *is* accurate in the brief, and is the reason this record is worth having: committing verdict A
verbatim puts four present-tense assertions into `docs/audits/` that are false on the day they land.

## Verdict A — 5 items

Read `origin/main` directly (`git cat-file blob origin/main:<path>`); the working tree is behind and
dirty. `export MSYS_NO_PATHCONV=1` first, or `git show origin/main:path` can silently return empty.

### A1 — `STATUS.md:9` falsely calls live `converse` "unconfined" → **FIXED**

```
$ git cat-file blob origin/main:STATUS.md | grep -n 'unconfined'
(no match, exit 1)
$ git cat-file blob origin/main:STATUS.md | sed -n '9p'
```
> `- **[P1 filed:2026-07-02 verified:2026-07-22]** No OS engine sandbox. Live `converse` is`
> `in-process-confined only (WebFetch-only, cwd-pin, rot-prone denylist); #1485 is a fail-closed seam.`

This is the exact distinction Codex asked for ("the missing piece is OS-level confinement, not all
confinement"), and the new wording is independently true — not merely different. Verified against the
code the verdict cited:

```
$ git cat-file blob origin/main:tinyassets/universe_intelligence.py | grep -n 'sandbox_workspace\|_ENGINE_ALLOWED_TOOLS'
60:_ENGINE_ALLOWED_TOOLS = ("WebFetch",)
109:        sandbox_workspace=True,
110:        allowed_tools=_ENGINE_ALLOWED_TOOLS,
111:        disallowed_tools=_ENGINE_DISALLOWED_TOOLS,
```

### A2 — `PLAN.md:569` overstates "built and deployed" / "sole action-taker" → **FIXED**

```
$ git cat-file blob origin/main:PLAN.md | sed -n '569p'
```
Both qualifications Codex demanded are present verbatim:

- *"The relay/`converse` M1 is built and deployed, and **is turn-scoped — the proactive 24/7
  persistent loop remains planned, not shipped**."*
- *"**'Sole action-taker' scopes to that control flow, not to every write**: the data-plane primitives
  (`write_graph`/`write_page`) stay daemon-free and directly callable, so **founders remain a second
  authorized write principal**."*

### A3 — `STATUS.md:37` repeats the premise PR #1484 disproved → **FIXED (row rewritten, premise inverted)**

```
$ git cat-file blob origin/main:STATUS.md | grep -n 'repo_root_not_resolvable\|community-pool'
(no match, exit 1)
```

Stronger than deletion: the row survives at line 37 with its diagnosis **inverted**, and it now
carries an explicit anti-recurrence warning —

> `| Land #1484 — `_repo_root()` conflated `TINYASSETS_REPO_ROOT` (storage) with the bundled-source`
> `root, emptying deployed review context. The env is load-bearing; do NOT drop it | ... | host-review |`

That "do NOT drop it" clause is the durable guard against the row being re-filed in its original
disproven form. Note this is *not* a landed fix — it is a correctly-restated open item at
`host-review`.

### A4 — `STATUS.md:34` says the §14 concurrency proof is missing → **FIXED**

```
$ git cat-file blob origin/main:STATUS.md | sed -n '34p'
```
> `| In-node enqueue flag flip — Codex ADAPT asks landed (`graph_compiler.py:1406-1560`), still dark;`
> `§14 proof passes but global-queue + per-origin lineage caps have no concurrent boundary coverage | ... |`

Precisely the narrower gap Codex asked be named. The proof it pointed at does exist on main and says
so in its own docstring:

```
$ git cat-file blob origin/main:tests/test_node_enqueue_concurrency.py | head -3
"""§14 concurrency / load proof for the in-node paced enqueue verb (PR #1214).
```

### A5 — `STATUS.md` is 5,281 bytes vs the stated ~4 KB budget → **STILL OPEN, and 65 bytes worse**

```
$ git cat-file blob origin/main:STATUS.md | wc -c
5346
$ git cat-file blob origin/main:STATUS.md | wc -l
54
```

Against the file's own line 3 — *"**Budget 4 KB / 60 lines.**"* — main is **5,346 bytes / 54 lines**:
line budget met, byte budget missed by ~30% (5,346 / 4,096 = 1.305). Codex measured 5,281; the
corrections in `c8c0e09e` added 65 bytes, so **fixing A1–A4 is what pushed A5 further out**. Those
were the right trade.

Verdict B's item 6 offered an alternative branch — *"or accurately state that this pass materially
reduced, but did not meet, the budget."* **That branch is satisfied**, in `.agents/activity.log:3384`
on main:

> *"67 lines/13.8 KB -> 55 lines/5,281 bytes, 62% byte cut — meets the 60-line budget, still ~29%
> over the 4 KiB guidance."*

So A5 is honestly disclosed but not closed. Classifying it **still-open** rather than
satisfied-by-disclosure, because the disclosure lives in `activity.log` while the budget claim the
next reader trips over is on `STATUS.md:3`. (The log's "5,281 bytes" is also now stale by 65.)

**A5 is not a janitor task — the budget is arithmetically unreachable.** `AGENTS.md` sets three
constraints on `STATUS.md` that cannot all hold at once:

| Constraint | Source |
|---|---|
| ≤60 lines | `AGENTS.md:55`, `:67` |
| ~4 KB (4,096 bytes) | `AGENTS.md:55`, `:67` |
| entries ≤150 chars | `AGENTS.md:108` |

`origin/main` carries **23 live rows** (11 Concerns + 12 Work/Spec). At the documented 150-char cap
those rows alone permit 3,450 bytes, leaving **646 bytes** for every heading, section intro, table
header, the `Next` block, and all blank lines — against the **1,673 bytes** of scaffolding main
actually has. The rows are not bloated; they average 146–150 bytes, i.e. *already at the cap*. The
file is over budget because it holds 23 legitimate rows.

The best trim I could construct without deleting live state — compress the two preamble lines and the
live-brain pointer, and drop the one `Next` item that duplicates `AGENTS.md` verbatim — reaches
**4,901 bytes / 53 lines**: −445 bytes (−8%), still **1.20×** the guidance. Full proposed text is in
this PR's body.

I first drafted a larger cut (−694, to 4,652) by dropping three `Next` items as "duplication of
`AGENTS.md`." **That was wrong and I withdrew it.** Only item 4 (spec-driven development) is
duplicated. Checked:

```
$ grep -ci 'no-shims\|platform responsibility\|scoping rules' AGENTS.md
0
```

`no-shims-ever`, the platform responsibility model, and the design-question scoping rule appear
**nowhere in `AGENTS.md`** — `STATUS.md` is their only home, so deleting them destroys standing
rules. That is not hypothetical here: the janitor pass deleted the `#24 Arc C` Work row *because*
no-shims-ever obviated it, and the 02:45Z thread comment warned the row is "a strong candidate to be
re-filed by a future session." Deleting the rule that obviated it would guarantee that. Only item 2's
public-surface-probe clause is genuinely redundant (`AGENTS.md` Hard Rule 11), so the proposal trims
that clause and keeps the two rules.

Closing the remaining ~805 bytes requires deleting live rows or changing a rule, so this is a host
decision, not a janitor pass. Options: raise the byte guidance to ~5 KB (what 23 rows at the
documented cap actually cost); cut the row cap to ~110 chars; cap live row count near 16; or drop the
byte number and let the 60-line budget be the real gate. This is also the likeliest reason successive
janitor passes keep meeting the line budget and missing the byte budget.

## Verdict B — 6 items

B3/B4/B5/B6 restate A2/A1/A4/A5 and carry the same classifications: **FIXED / FIXED / FIXED /
STILL-OPEN**. Two items are unique to B:

### B1 — Critical: PR #1506 is `CONFLICTING` and 3 commits behind `origin/main` → **FIXED (rebase)**

Resolved before merge. The PR thread records the rebase at `03:55:57Z` — `c8c0e09e` → `2f1178c0`
onto `144eaba7`, force-pushed with `--force-with-lease`, conflict on `.agents/activity.log` only. The
merged result confirms the rebase was clean:

```
$ git log -1 --format='%H %cI %s' 398b3256
398b32561f927ffcf0f97608cd683f4b20c44f93 2026-07-22T03:53:41Z docs(status): janitor pass ... (#1506)
```

The comment notes the naive "take theirs" resolution would have silently deleted main's entire #1501
block, and that the root cause (every lane appends to the same final hunk of `activity.log`) is fixed
separately by `merge=union` in #1523.

### B2 — Critical: the `TINYASSETS_REPO_ROOT` row, **plus** correct the `activity.log` "every deletion verified" claim → **FIXED, both halves**

The row half is A3. The second half — an ask no other item makes — also landed:

```
$ git cat-file blob origin/main:.agents/activity.log | sed -n '3384p'
```
> *"Deletions were verified against code; **the RETAINED rows were not**, and Codex review of PR
> #1506 ... found four false premises among them — corrected in the same PR."*

The blanket verification claim is gone, replaced by an accurate statement of the asymmetry. Note that
this half is what motivated the 02:45Z deletion-safety audit on the thread, which independently
checked the *deleted* rows neither verdict covered and approved them.

## A sixth thing neither verdict raised as a finding

Verdict B's evidence section mentions in passing: *"Broader sandbox selection: 119 passed, **4
failures in `test_sandbox_unavailable.py`**; apparently unrelated to this documentation-only diff,
but the broader surface is not fully green."* It was filed as context, not as a numbered item, so
nothing acted on it and it merged with the PR.

**Those 4 failures still reproduce on `origin/main`, the product code is fine, the tests are broken —
and two sibling tests in the same class pass without testing anything.**

```
$ python -m pytest tests/test_sandbox_unavailable.py -q
FAILED TestExtBranchListSandboxFilter::test_no_filter_returns_all_with_has_sandbox_nodes - assert 0 == 2
FAILED TestExtBranchListSandboxFilter::test_filter_none_excludes_sandbox_branches      - assert 0 == 1
FAILED TestExtBranchListSandboxFilter::test_filter_any_excludes_design_only_branches   - assert 0 == 1
FAILED TestExtBranchListSandboxFilter::test_unknown_filter_value_passes_all_through    - assert 0 == 2
4 failed, 33 passed in 5.99s
```

**Root cause — an unmocked second dependency, not a stale patch target.** The class mocks
`tinyassets.daemon_server.list_branch_definitions` and never passes `scope`, so `_ext_branch_list`
takes its default `scope="published"` (`tinyassets/api/branches.py:552`). That branch calls the
**real** `list_branch_versions` per row (`:583-587`); fabricated branch ids have no versions, so every
row hits `continue` and `count` is 0 unconditionally.

Mocking that one extra call makes all four pass with exactly their asserted values — proving the
`requires_sandbox` filter itself is correct and only the harness is wrong:

| `requires_sandbox` | as the tests call it | with `list_branch_versions` mocked | asserted |
|---|---|---|---|
| *(omitted)* | 0 | 2 — `['sb','db']` | 2 |
| `none` | 0 | 1 — `['db']` | 1 |
| `any` | 0 | 1 — `['sb']` | 1 |
| `invalid_value` | 0 | 2 — `['sb','db']` | 2 |

**The vacuity, which is the worse half.** The `continue` fires at `:586`, *before*
`has_sandbox_nodes` is computed at `:592` — so the filter code under test is **never reached**. The
two tests in this class that currently pass both assert `count == 0`:

- `test_filter_none_on_empty_corpus_returns_empty`
- `test_filter_any_on_all_design_only_returns_empty`

Under the broken path they return 0 no matter what. **No mutation to the `requires_sandbox` filter
can turn them red** — they are non-discriminating, exactly the class PR #1482
(*"fix(tests): two passing tests were vacuous"*) exists to fix, on a file that PR does not touch
(#1482 covers `tests/test_backup_script.py` and `tests/test_mcp_server.py` only).

**Why nothing caught it:** no CI workflow runs this file. The only pytest invocations under
`.github/workflows/` are `test_packaging_build.py` (`build-bundle.yml:74`) and `tests/smoke/`
(`tier3-oss-clone-nightly.yml:69`). These 4 failures are invisible to every gate.

This is unrelated to PR #1506, which changed only `STATUS.md`, `PLAN.md`, and `.agents/activity.log`.
It needs its own lane; it is recorded here because verdict B is the only place it was ever written
down, and committing that verdict without this note buries it.

## What remains open

| Item | State |
|---|---|
| **A5 / B6** — `STATUS.md` 5,346 bytes vs its own "Budget 4 KB" | Open, and **not closable by trimming**. `AGENTS.md`'s 4 KB / 60-line / ≤150-char rules are mutually inconsistent at 23 live rows; best honest trim reaches 4,901 (1.20×). Needs a host decision on which rule gives. `STATUS.md` is contended (#1507). |
| **A3 / B2** — `#1484` land | Open by design, at `host-review`. Correctly restated, premise inverted, guard clause present. |
| **`test_sandbox_unavailable.py`** | Open, unowned, invisible to CI. Product code correct; 4 broken + 2 vacuous tests. |
| **Verdict B's filename** | Open on #1516. `2026-07-22-uptime-canary-false-red-codex-review.md` reads as a review of the canary incident (that audit is a different file, on #1513). Anyone searching #1506's reviews by filename will miss it. Suggested: `2026-07-22-status-janitor-pr1506-codex-review-2.md`. |

## For whoever lands #1516

Do not rewrite either verdict — they are historical artifacts and their evidence is genuinely
valuable (verdict A's fresh-evidence paragraph: 53 passed/2 skipped, 35 sandbox tests, 23 enqueue
tests, OpenSpec 7/7, drift clean; verdict B's 29-check OpenSpec run and the sandbox failures above).
The provenance comment #1516 already adds is the right shape. One line per file pointing at this
document is enough to keep a reader from acting on four assertions that are false on `origin/main`.
