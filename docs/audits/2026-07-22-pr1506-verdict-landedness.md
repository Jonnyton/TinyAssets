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

**A5 is reachable — the rows are over the cap, not at it.** *(Corrected 2026-07-22 after Codex
opposite-provider review; see the CORRECTION note at the end of this document. An earlier version of
this section claimed the budget was "arithmetically unreachable" and demanded a host decision. That
was wrong.)*

`AGENTS.md` sets `≤60 lines` and `~4 KB` (`:55`, `:67`) plus `entries stay ≤150 chars` (`:108`).
**`≤150` is a maximum, not a required row size** — my earlier arithmetic treated it as a floor, which
is what produced the false impossibility result.

`origin/main` carries **23 live rows** (11 Concerns + 12 Work/Spec) totalling 3,656 chars:

```
rows=23 total_chars=3656 avg=159.0
rows OVER the 150-char cap: 7
scaffolding = 5346 - 3673 = 1673 bytes
4096 - 1673 = 2423 bytes for 23 rows = 105 chars/row average
```

Rows average **159 chars and seven already violate the ≤150 cap** — so they are not "already at the
cap," they are over it. Bringing all 23 rows to a **105-char average** fits the 4 KB budget *and*
stays comfortably inside `≤150`. The budget is a normal janitor task; it is just a row-compression
task, not a scaffolding trim.

My scaffolding-only proposal reaches **4,901 bytes / 53 lines** (−445, −8%, still 1.20×) — it under-
delivers because it never touched the rows, which is where the weight is.

**Where the standing rules should go.** I earlier argued the `Next` items must stay in `STATUS.md`
because they exist nowhere else:

```
$ grep -ci 'no-shims\|platform responsibility\|scoping rules' AGENTS.md
0
```

That check is accurate, but the conclusion was too narrow. `AGENTS.md:51-55` assigns work conventions
to `AGENTS.md` and architectural principles to `PLAN.md`; standing rules do not belong in a live
steering board at all. The right move is **move `no-shims-ever` and the platform responsibility model
into `AGENTS.md`, and the design-question scoping rule into `AGENTS.md` or `PLAN.md`, then delete them
from `STATUS.md`** — which both preserves the rules and reclaims the bytes. Deleting them *without*
rehoming them is what would destroy standing rules, and that risk is real: the janitor pass deleted
the `#24 Arc C` row *because* no-shims-ever obviated it, and the 02:45Z thread comment warned the row
is "a strong candidate to be re-filed by a future session."

Closing the remaining ~805 bytes needs the rows compressed toward a 105-char average and the standing
rules rehomed — ordinary janitorial work, in a lane that owns `STATUS.md` (currently contended by
#1507).

## Verdict B — 6 items

B3/B4/B5 restate A2/A1/A4 and carry the same classifications: **FIXED / FIXED / FIXED**.

**B6 — the ~4 KB budget → FIXED (by disclosure).** B6 is *not* a restatement of A5, and classifying
it as one was an error in this document's first version. A5 requires the budget be met, full stop.
B6 offers an explicit alternative — *"Either reduce it further **or accurately state that this pass
materially reduced, but did not meet, the budget**."* That second branch was satisfied before the
merge, in `.agents/activity.log:3384`:

> *"67 lines/13.8 KB -> 55 lines/5,281 bytes, 62% byte cut — meets the 60-line budget, still ~29%
> over the 4 KiB guidance."*

So B6 is closed on its own terms and **A5 is the sole open item** — which is what makes the headline
count (10 FIXED / 1 STILL-OPEN) correct. The first version classified B6 still-open while claiming
10-of-11, an internal contradiction caught in review.

Two further items are unique to B:

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
and one sibling test in the same class is masked into passing regardless of the code under test.**

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

**The masked test, which is the worse half.** The `continue` fires at `:586`, *before*
`has_sandbox_nodes` is computed at `:592` — so the filter code under test is **never reached**. Two
tests in this class currently pass while asserting `count == 0`, but they are not equivalent:

- **`test_filter_any_on_all_design_only_returns_empty` — masked, non-discriminating.** It feeds one
  design-only row and expects it filtered out. With the gate broken, the row is dropped before the
  filter runs, so the test passes for the wrong reason: **no mutation to the `requires_sandbox`
  filter can turn it red today.** Fix the mock and it becomes a real test again (it correctly
  returns 0 either way, but only then because the filter did its job).
- **`test_filter_none_on_empty_corpus_returns_empty` — legitimate.** It feeds an *empty* corpus, so
  the loop never runs and `count == 0` regardless. It is an empty-input boundary test that was never
  meant to exercise the filter, so it is unaffected rather than vacuous. *(An earlier version of
  this document called both tests vacuous; Codex review corrected that — see the CORRECTION note.)*

So the honest tally is **4 broken + 1 masked**, adjacent to but narrower than the class PR #1482
(*"fix(tests): two passing tests were vacuous"*) exists to fix — on a file #1482 does not touch
(#1482 covers `tests/test_backup_script.py` and `tests/test_mcp_server.py` only).

**Why CI does not catch it:** no CI workflow runs this file. Across all 30 workflows the only pytest
invocations are `test_packaging_build.py` (`build-bundle.yml:74`) and `tests/smoke/`
(`tier3-oss-clone-nightly.yml:69`), so these 4 failures are invisible to every *automated* gate. A
local full-suite run does surface them — that is how both Codex and this lane found them — so the gap
is CI coverage, not undetectability.

This is unrelated to PR #1506, which changed only `STATUS.md`, `PLAN.md`, and `.agents/activity.log`.
It needs its own lane; it is recorded here because verdict B is the only place it was ever written
down, and committing that verdict without this note buries it.

## What remains open

| Item | State |
|---|---|
| **A5** — `STATUS.md` 5,346 bytes vs its own "Budget 4 KB" | Open. Reachable by ordinary janitoring: rows average 159 chars (7 over the ≤150 cap); a 105-char average fits 4 KB and stays compliant. Also rehome the `Next` standing rules into `AGENTS.md`/`PLAN.md`. Needs a lane that owns `STATUS.md` (contended by #1507). **B6 is closed** — its "accurately state the shortfall" branch landed in `activity.log:3384`. |
| **A3 / B2** — `#1484` land | Open by design, at `host-review`. Correctly restated, premise inverted, guard clause present. |
| **`test_sandbox_unavailable.py`** | Open, unowned, not covered by CI. Product code correct; 4 broken + 1 masked test. |
| **Verdict B's filename** | Open on #1516. `2026-07-22-uptime-canary-false-red-codex-review.md` reads as a review of the canary incident (that audit is a different file, on #1513). Anyone searching #1506's reviews by filename will miss it. Suggested: `2026-07-22-status-janitor-pr1506-codex-review-2.md`. |

## For whoever lands #1516

Do not rewrite either verdict — they are historical artifacts and their evidence is genuinely
valuable (verdict A's fresh-evidence paragraph: 53 passed/2 skipped, 35 sandbox tests, 23 enqueue
tests, OpenSpec 7/7, drift clean; verdict B's 29-check OpenSpec run and the sandbox failures above).
The provenance comment #1516 already adds is the right shape. One line per file pointing at this
document is enough to keep a reader from acting on four assertions that are false on `origin/main`.

---

## CORRECTION — 2026-07-22, after Codex opposite-provider review

The first version of this document landed on `main` as `b6be48d4` (PR #1532) **before its required
opposite-provider review returned**. The review came back `VERDICT: adapt` with three substantive
corrections, all accepted. Recording them in place rather than silently rewriting, per the pattern
#1510 used.

**1. A5 was not "arithmetically unreachable" — that conclusion was invalid.** I treated `AGENTS.md`'s
`entries stay ≤150 chars` as a *required* row size and derived an impossibility from it. It is a
**maximum**. The 23 live rows average **159 chars — 7 of them already over the cap** — and a 105-char
average both fits the 4 KB budget and complies with `≤150`. A5 is a normal janitor task (row
compression, not scaffolding trim). The withdrawn claim also generated a spurious "host decision
required on which rule gives," now removed.

**2. B6 was misclassified as still-open.** B6 offered "reduce further **or** accurately state the
shortfall," and the disclosure branch had landed in `activity.log:3384` before the merge. B6 is
**fixed-by-disclosure**; A5 alone stays open. The first version classified B6 open while claiming
"10 of 11 fixed" — an internal contradiction. The headline count was right; the item-level
classification was wrong.

**3. The sandbox finding overstated two things.** "Two sibling tests pass without testing anything"
was too broad: `test_filter_none_on_empty_corpus_returns_empty` is a legitimate empty-input boundary
test, unaffected by the bug. Only `test_filter_any_on_all_design_only_returns_empty` is masked into
non-discrimination. Corrected to **4 broken + 1 masked**. And "nothing would ever catch it" became
"current CI does not catch it" — a local full-suite run plainly does, which is how it was found.

**On the merge itself.** #1532 was opened as a **draft** at `04:37:25Z` and explicitly not merged by
this lane. At `04:38:03Z` it was marked `ready_for_review` by the `Jonnyton` account; `auto-enroll-merge.yml`
then correctly enrolled it (that workflow excludes drafts by design and fires on `ready_for_review`),
and it squash-merged at `04:38:16Z` — **51 seconds after creation, with zero reviews.** No
undrafting automation exists in this repo (`grep -rn 'pr ready\|ready_for_review'` over `scripts/`,
`.github/`, `.claude/`, `.agents/` returns only the workflow's own trigger list), so the undraft came
from outside it. This is the same mechanism by which PR #1506 merged with an unaddressed `adapt`
verdict. **Any lane told to "open a draft PR, do not merge" cannot currently rely on that holding.**
Codex flagged the same thing independently as its fourth required item.

Unchanged and re-confirmed by the review: the A1–A4 and B1–B5 classifications, the sandbox root cause
and its mock-injection proof, and both corrections to the dispatch framing.
