# Issue #1346 triage — "Salvaged tasks from branch cleanup (2026-06-25)"

**Date:** 2026-07-22
**Auditor:** claude-code (`claude/issue-1346-triage`)
**Subject:** [issue #1346](https://github.com/Jonnyton/TinyAssets/issues/1346), opened
`2026-06-25T02:08:22Z` — open 27 days, no labels, no assignee, no STATUS row.
**Baseline:** `origin/main` @ `398b3256` (fetched 2026-07-22).
**Class:** `stale-backlog-rows-misdirect`.

## Headline

The issue closes with:

> *"The 3 security/correctness fixes are the highest priority — they patch holes that exist on
> `main` today."*

**That sentence is false, 3 for 3.** All three named security/correctness fixes — and the fourth
item in the same section — are already on `main`. So are three of the remaining five. Nothing in
this issue is a live security hole.

| # | Item | Salvage sha | Verdict |
|---|------|-------------|---------|
| 1 | Node self-approval privilege gate | `dd7a4a1b` | **already-fixed** (verbatim + test) |
| 2 | Canon filename path-traversal | `a195e1ba` | **already-fixed** (superset) |
| 3 | Outcome-evaluator self-attestation | `c3f20055` | **already-fixed** (incl. contract change) |
| 4 | Escrow test broken on main | `2f086075` | **already-fixed** (48 tests pass) |
| 5 | Base-testnet money loop | `878a3680` / `ed168e2d` | **already-fixed** (superset) |
| 6 | `twitter_post` effector (PR-173) | `424461c8` | **already-fixed** (superset test) |
| 7 | Secrets-vendor push-cred centralization | `42569fa2` | **already-fixed** (renamed env) |
| 8 | Capability-provisioning concept doc | `1c73ac26` | **still-valid** (docs, speculative) |
| 9 | `github_read` docstring xref | `93cf2317` | **still-valid** (docs, trivial) |

**Coverage: 9 of 9 items verified against `origin/main`. None deferred, sampled, or carried over to
a later pass. No silent caps.** (That is a statement about *verification* coverage; two items
remain genuinely open, both documentation-only, tracked in §3.) 7 already-fixed, 2 still-valid. The
security section is entirely stale.

### Recovery shas — use the full sha, the short one does not work

All 10 salvage commits still resolve locally, so nothing was lost while this sat. **But the
recovery recipe in the issue body does not work as written.** The issue displays short shas, and
`git fetch origin <short-sha>` fails against GitHub:

```
$ git fetch origin dd7a4a1b
fatal: couldn't find remote ref dd7a4a1b

$ git fetch origin dd7a4a1b2db3061b83e3db61588f85a3637b1449
 * branch dd7a4a1b2db3061b83e3db61588f85a3637b1449 -> FETCH_HEAD   # ok
```

Full shas, and the original PR ref as a fallback (`refs/pull/<n>/head` also resolves):

| # | Item | Full sha | PR ref |
|---|------|----------|--------|
| 1 | Node self-approval gate | `dd7a4a1b2db3061b83e3db61588f85a3637b1449` | `refs/pull/1189/head` |
| 2 | Canon path-traversal | `a195e1ba02809ecfd8123da7bbc1835b2f2cfc09` | `refs/pull/1187/head` |
| 3 | Outcome-evaluator self-attestation | `c3f20055ef18a43d29016fac7ae814028ce2e51b` | `refs/pull/1185/head` |
| 4 | Escrow test | `2f08607552db374f75ebfdb688e418234106c6b7` | `refs/pull/1299/head` |
| 5 | Money loop (slice1a) | `878a36808ba8a2a40eccb8974de63af47b551346` | `refs/pull/1301/head` |
| 5 | Money loop (slice0, superseded) | `ed168e2dd677a968820a29c4cd8350eaf688dbf3` | `refs/pull/1300/head` |
| 6 | `twitter_post` effector | `424461c8bc158ee0809e4752f8ef6abcf10d298a` | `refs/pull/1327/head` |
| 7 | Secrets-vendor push-cred | `42569fa2b9d65605994bc4a3b6ce4cad9f2fe067` | `refs/pull/1286/head` |
| 8 | Capability-provisioning doc | `1c73ac267c4e09740d7d459dc72f62743ca93fd8` | `refs/pull/1195/head` |
| 9 | `github_read` docstring xref | `93cf23171e075f9bc492d308b08ec7bdf88d7b57` | `refs/pull/1329/head` |

Working recovery: `git fetch origin <full-sha> && git branch <name> FETCH_HEAD`.

---

## Method

Every verdict below cites the command that decided it. Two guards against the failure modes that
burned earlier lanes:

- **A grep miss is not proof of absence.** For the two `still-valid` verdicts I grepped the whole
  file and the plugin mirror, and confirmed the *counterpart* symbol exists (so the xref target is
  real and the absence is meaningful), rather than inferring absence from one narrow pattern.
- **A function body is not the defect when the guard lives at the call site.** For the fixes I
  claim landed, I diffed `main` against the salvage commit's *post-image* (normalizing the
  `workflow/` → `tinyassets/` package rename) rather than eyeballing one function, and ran the
  tests to confirm the guards actually execute.

Normalized comparison used throughout:

```bash
git show <sha>:workflow/<path> | sed 's/\bworkflow\./tinyassets./g; s/from workflow /from tinyassets /g' > /tmp/sal.txt
git show origin/main:tinyassets/<path> > /tmp/main.txt
diff /tmp/sal.txt /tmp/main.txt | grep -c '^[<>]'
```

Result — differing lines vs. the salvage post-image:
`tinyassets/outcomes/evaluators.py` = **2**, `tinyassets/api/extensions.py` = **39**,
`tinyassets/ingestion/canon_names.py` = **22**. The residual in the latter two is `main` having
gone *further* than the salvage (extra containment primitive, extra hardening), not the fix being
absent — detailed per item below.

**Independent adversarial pass.** For each fix I claim landed, I additionally looked for the
bypass rather than the guard: other write sites for the same field, whether the admin-action
frozenset is actually read by an enforcement path, whether the removed substring test survives
anywhere, and — for the two `still-valid` verdicts — whether the work landed under a renamed
symbol. Those checks are recorded inline per item. Item 7 is the proof this mattered: it *is* a
rename, and the issue's own vocabulary greps clean on `main`.

**Test evidence** (`origin/main` baseline, 2026-07-22, Windows/py3.11):

```
$ python -m pytest tests/test_standalone_node_approval_gate.py tests/test_outcome_evaluators.py \
    tests/test_canon_io.py tests/test_twitter_post_effector.py \
    tests/test_settlement_backend.py tests/test_escrow_withdraw.py -q
108 passed, 10 skipped in 18.70s

$ python -m pytest tests/test_payments_escrow_mcp.py -q
48 passed in 7.51s
```

---

## Section 1 — Security / correctness (all four stale)

### [1] Node self-approval privilege gate — `dd7a4a1b` — **already-fixed**

Issue claims: *"On main, `_ext_manage` does a bare `approved=True` with no actor check and
`approve` isn't an admin action."* Both halves are false.

The salvage had three parts; all three are on `main`:

1. **Distinct-approver check** — `tinyassets/api/extensions.py:880` (`_ext_manage`) rejects
   self-approval with the exact sentinel from the salvage:
   ```
   if actor == registrant:
       return json.dumps({"status": "rejected",
           "error": "node_approval_requires_distinct_actor", ...})
   ```
2. **Persistence** — the same block sets `approved_by`, `approved_at`, and
   `approved_source_hash = _source_code_hash(...)`.
3. **Admin classification** — `approve` is the **first entry** of `_EXTENSIONS_ADMIN_ACTIONS`,
   `tinyassets/auth/provider.py:410-411`, consumed at `provider.py:587` via
   `admin_actions=_EXTENSIONS_ADMIN_ACTIONS`.

The salvage's own test file landed too: `tests/test_standalone_node_approval_gate.py` is present on
`main` (`git ls-tree origin/main tests/`). The sentinel string appears in three places on `main` —
canonical module, plugin mirror, and the test — so the guard is exercised, not decorative.

Two separate facts, which an earlier draft of this audit wrongly merged (caught by the Codex
review, §"Review gate"):

1. **The 39-line residual in `extensions.py` is NOT security hardening.** Inspecting the diff
   directly, those lines are unrelated drift — the `workflow/` → `tinyassets/` docstring rename,
   phase-vocabulary changes (`worldbuild` → `enrich` plus a `__post_init__` validator), and escrow
   fields. `diff /tmp/sal.txt /tmp/main.txt | grep '^[<>]' | grep -ci "approv\|hash"` = **0**.
2. **`main` does carry extra approval hardening, but it lives elsewhere** — an
   `approved_source_hash` staleness regime in `tinyassets/api/branches.py:196-279` re-validating a
   bare `approved=True` against the hash of the *current* source, enforced at `:1689-1728`. Real,
   but not attributable to the `extensions.py` comparison above.

Adversarial follow-ups, since a guard in one function body proves nothing about the other call
sites:

- **Is `_ext_manage` the only approve path?** No, and the other is guarded *differently* — do not
  read this as equivalent protection. `git grep -n 'approved.*= *True' origin/main -- "tinyassets/**.py"`
  finds one further *write* (as opposed to comment): `tinyassets/api/branches.py:516`, the
  branch-node `approve_source_code` path — a different action from the standalone-node `approve`
  this item is about. It records identity and binds the hash (`:517` `approved_by = actor`, `:519`
  `approved_source_hash = source_hash`) and requires admin scope, **but it does not enforce a
  distinct approver.** Whether admin self-approval is intended there is out of scope for this
  triage; flagging it rather than asserting it is fine. The separate in-process helper at
  `tinyassets/branches.py:511` (a distinct module from `tinyassets/api/branches.py` — both exist)
  records the invariant: *"the ONLY sanctioned in-process approval helper… must call it instead of
  setting `approved=True` directly, so the hash is always bound to the source actually being
  approved."*
- **Is the admin frozenset actually enforced, or dead config?** Enforced.
  `tinyassets/auth/provider.py:441-443` is the consumer — `admin_actions` parameter, then
  `if action in admin_actions:` — reached for this surface via `:587`
  `admin_actions=_EXTENSIONS_ADMIN_ACTIONS`. It is not a frozenset nothing reads.

**Command of record:** `git grep -n "node_approval_requires_distinct_actor" origin/main`

### [2] Canon filename path-traversal — `a195e1ba` — **already-fixed** (superset)

Issue asks for a `safe_canon_slug/filename` helper with `is_relative_to(canon_root)` containment.
`main` has that **and more**.

- `tinyassets/ingestion/canon_names.py:32` `safe_canon_slug`, `:45` `safe_canon_filename` — as
  requested.
- `main` additionally has `resolve_within_canon()` (same file, line 10), the actual
  `is_relative_to(canon_root)` containment primitive, which the salvage commit **did not
  contain**. Its docstring records it as *"the single containment primitive reused by every canon
  I/O path"* — new files, contradiction/expansion overwrites, provenance markers, synthesis source
  reads, manifest I/O, KG/premise reads.

Call sites route through the helpers (this is the call-site check, not just the body):
`domains/fantasy_daemon/phases/worldbuild.py:21,483,514,533,602,902,1078` and
`tinyassets/ingestion/extractors.py:21,283`.

Note on tests: the salvage's assertions did **not** land under their original filenames
(`git grep -c "safe_canon" origin/main -- tests/test_ingestion.py` = 0). Equivalent coverage lives
in `tests/test_canon_io.py` and `tests/test_universe_nodes.py` instead — both grep positive for
`safe_canon` / `resolve_within_canon` / `escapes canon directory`, and both pass. Coverage moved,
it wasn't dropped.

**Command of record:** `git grep -n "safe_canon_slug\|safe_canon_filename" origin/main -- "tinyassets/**.py" "domains/**.py"`

### [3] Outcome-evaluator self-attestation — `c3f20055` — **already-fixed**

This is the item the incoming brief explicitly did **not** check and flagged as most likely live.
It is stale too. `tinyassets/outcomes/evaluators.py` differs from the salvage post-image by
**2 lines** (module-docstring wording only).

All three sub-fixes are present:

Adversarial follow-up: the substring bug is gone repo-wide, not just relocated —
`git grep -n '"accept" in\|in decision' origin/main -- "tinyassets/**.py"` returns **zero** hits.

| Salvage requirement | On `main` |
|---|---|
| Default prober returns explicit "unverified", not silent `False` | `_unverified_prober` returns `None` (line 40); `_verification_status()` line 45; `_ProbeResult = bool \| None`. Used as the default arg by `PublishedPaperEvaluator` (62), `MergedPREvaluator` (101), `DeployedAppEvaluator` (138). `_no_network_prober` is gone. |
| Match decisions against an allow-set, not `"accept" in decision` | `_ACCEPTED_DECISIONS` frozenset (line 27) + `_is_accepted_decision()` (line 49), called by `PeerReviewAcceptedEvaluator` (189) **and** `ConferenceAcceptedEvaluator` (234). The substring test is gone from both. |
| `ConferenceAcceptedEvaluator` gates on a `decision` field ⚠ contract change | `evaluators.py:220-224` — `missing = [k for k in ("conference_name", "decision", "talk_date", "accepted_at") if not state.get(k)]`. The required field landed; the evaluator now returns `verdict="fail"` on a non-accepting decision instead of hardcoded `pass`. |

The flagged contract change is therefore **already in production behaviour** — it needs no
scoping, because it was scoped and shipped. `tests/test_outcome_evaluators.py` on `main` greps 4
hits for `verification_status` / `_is_accepted_decision` / `unverified` and passes.

**Command of record:** `git show origin/main:tinyassets/outcomes/evaluators.py | sed -n '220,226p'`

### [4] Escrow test broken on main — `2f086075` — **already-fixed**

Issue claims `tests/test_payments_escrow_mcp.py` calls `_connect` as a non-contextmanager and is
therefore broken on `main`. It is not broken.

`tests/test_payments_escrow_mcp.py:537` defines the `_conn()` raw-sqlite helper the issue asked to
port, carrying the explanatory comment at `:538` — *"storage._connect is a context manager (closes
on exit); these unit…"* — and 9 call sites use it (`:560,569,577,585,595,611,625,632,…`).

```
$ python -m pytest tests/test_payments_escrow_mcp.py -q
48 passed in 7.51s
```

The issue's advice to *"discard the stale `test_api_market.py` handler-count half"* is moot; the
surviving half is what landed.

---

## Section 2 — Features (both stale)

### [5] Base-testnet money loop — `878a3680` (supersedes `ed168e2d`) — **already-fixed** (superset)

Every file the salvage added is on `main`, in the canonical tree (not only the plugin mirror):

- `tinyassets/payments/settlement_backend.py`, `wallets.py`, `funding.py`, `actions.py` — all
  PRESENT.
- `escrow_withdraw` is wired end to end in the canonical tree: `tinyassets/payments/actions.py:613`
  (`action_escrow_withdraw`), `tinyassets/api/market.py:665,706,721` (handler + dispatch table),
  `tinyassets/api/extensions.py:750` (action list), `tinyassets/auth/provider.py:565` (scope
  classification — with a comment recording that these were *previously* mis-classified as read).
- Both salvage tests landed: `tests/test_escrow_withdraw.py`, `tests/test_settlement_backend.py`.

`main` again went further than the salvage. The salvage was explicitly *"mock, no network"*;
`settlement_backend.py` on `main` carries `SettlementBackend` (ABC), `InternalBackend`,
`OnChainClient`, `MockOnChainClient`, **and** `BaseSepoliaBackend`, plus `get_settlement_backend()`
and idempotency-key helpers. The rebase-onto-current-main the issue asked for happened.

The superseded slice0 doc (`ed168e2d`) also landed:
`docs/design-notes/proposed/2026-06-08-base-testnet-money-slice1-scoping.md`.

**Command of record:** `git grep -n "escrow_withdraw" origin/main -- "tinyassets/**.py"`

### [6] `twitter_post` effector (PR-173) — `424461c8` — **already-fixed** (superset)

`tinyassets/effectors/twitter_post.py` exists and is registered in the current dispatcher:
`tinyassets/effectors/__init__.py:39-41` imports `run_twitter_post_effector`, exported at `:138`.
The re-apply-onto-current-layout work the issue asked for is done.

The salvage contributed a 250-line test; `main`'s `tests/test_twitter_post_effector.py` is **340
lines / 10 tests**, a strict superset covering dry-run, authority-denied fail-closed, missing
consent, evidence recording, idempotency dedup + hint derivation, handle/destination mismatch, and
branch dispatch routing. Passes.

**Command of record:** `git grep -n "twitter_post" origin/main -- tinyassets/effectors/__init__.py`

---

## Section 3 — Infra / docs (the only survivors)

### [7] Secrets-vendor push-cred centralization — `42569fa2` — **already-fixed** (renamed)

The issue names `WORKFLOW_GITHUB_PUSH_CAPABILITIES`, which greps clean on `main` — an easy
false-positive "still-valid". It landed under the post-rename name.

`tinyassets/auth/provider.py:42-58` defines `_GITHUB_SECRET_CAPABILITY_ENVS` mapping `push` →
`("TINYASSETS_GITHUB_PUSH_CAPABILITIES", "TINYASSETS_GITHUB_PR_CAPABILITIES")` — i.e. the canonical
map **plus the legacy fallback** the issue specified as the backward-compatibility requirement,
with `_load_destination_secret_map()` below it. The consumer side is
`tinyassets/effectors/github_pr.py:39,124,130,182,1273`.

The comment at `provider.py:38-41` records that the per-universe credential vault
(`tinyassets.credential_vault`) is now the higher-priority source and this is the operator
(process-env) tier — so the design has moved on past the salvage as well.

**Command of record:** `git grep -n "TINYASSETS_GITHUB_PUSH_CAPABILITIES" origin/main -- "tinyassets/**.py"`

### [8] Capability-provisioning concept doc — `1c73ac26` — **still-valid** (docs, speculative)

Genuinely absent. `git ls-tree -r origin/main --name-only | grep capability-provisioning` returns
nothing; `pages/` exists on `main` and `pages/concepts/skill-sync-via-brain-pages.md` is there, so
this is a real absence in a live directory, not a moved tree.

The salvage's companion edit is also absent: it added a `requires_capability` frontmatter key and a
`[[capability-provisioning-via-brain-pages]]` backlink to the skill-sync page, and
`git show origin/main:pages/concepts/skill-sync-via-brain-pages.md | grep capability` returns
nothing.

Adversarial follow-up — did it land under a different name? No.
`git grep -rln "requires_capability\|capability-provisioning\|capability_provisioning" origin/main`
returns **zero** hits across the entire tree, in any file type. The concept is absent, not renamed.

Disposition: **host-decision — do not drop by default.** An earlier draft of this audit recommended
dropping it as "superseded by the enabling-primitives reframe." The Codex review challenged that as
an unsupported assertion, and reading the salvaged page itself shows the assertion was not just
unsupported but **backwards**. `1c73ac26`'s frontmatter and body describe a deliberately
runtime-neutral, user-buildable, portable capability declaration:

> *"Use brain pages as the canonical exchange record for portable capability requirements and
> declarations. Local runtime configuration remains a projection, not the semantic source of
> truth."*

with `capability_id` / `kind` fields and no automatic installation and no new MCP handles. That
**aligns** with `enabling-primitives-not-prebuilt-complexity` (ship reduced composable primitives;
let power users build and share the complex thing) rather than being superseded by it.

So the honest classification is: still-valid, genuinely absent, and the keep-or-drop call the issue
asked for is a real host decision — not one this triage should quietly make. The issue's own
framing (*"Speculative `status: proposed` doc. Low priority."*) still applies to its urgency, not
to its merit.

### [9] `github_read` docstring xref — `93cf2317` — **still-valid** (docs, trivial)

Genuinely absent, and the absence is meaningful: the xref *target* exists, so this is a real
dangling cross-reference rather than a stale pointer to deleted code.

- `git show origin/main:tinyassets/effectors/github_read.py | grep -c "search_repo_files\|github_search"` → **0** (whole file, not a narrow pattern).
- Plugin mirror: same check → **0**.
- Target exists: `tinyassets/effectors/github_search.py`, `tests/test_github_search_repo_files.py`,
  design note `docs/design-notes/2026-05-29-repo-search-primitive.md`.
- Adversarial follow-up — did an equivalent xref land under different wording? No. Grepping the
  module for `counterpart` / `see also` returns only line 3, *"The read counterpart to the
  github_pull_request **write** effector"* — the write xref, not the search one.

The salvage's exact one-line addition:

```
See also ``search_repo_files`` in ``workflow/effectors/github_search.py`` for the localization/search counterpart.
```

(needs the `workflow/` → `tinyassets/` path rewrite, and the same line in the packaging mirror).

Disposition: **track it as a `dev-ready` STATUS Work row** (row text in the PR body). Trivial docs
nicety, no urgency, no security or behaviour impact — but "fold it into the next touch of that
file" is a hope, not a disposition, and hoping is what produced a 27-day-old issue. Either it is
tracked or it is dropped; this audit recommends tracked, since it is a two-line change (canonical
module + packaging mirror) against a cross-reference target that demonstrably exists.

---

## Why this sat for 27 days

The issue was filed correctly and in good faith — as a *snapshot* of work-in-flight on
2026-06-25. What it lacks is any expiry semantics. It asserts present tense (*"holes that exist on
`main` today"*) about a `main` that has since absorbed nearly all of it, and it has no labels, no
assignee, and no STATUS row, so nothing ever forced a re-read.

That is the same shape as `stale-backlog-rows-misdirect` (5 of 5 dispatched dev-ready rows wrong on
2026-07-21) and as the `daemon-request` issue backlog (≥100 issues) triaged separately under the
`daemon-request-issues-address-a-deleted-pipeline` lane — **different issue set, same disease**: a
durable artifact asserting present-tense state, with no mechanism to notice it stopped being true.
That lane's scope is deliberately not duplicated here.

The specific trap here is that the salvaged work *did* land — mostly through ordinary development
that never referenced the issue number, and partly under renamed symbols
(`WORKFLOW_*` → `TINYASSETS_*`, `workflow/` → `tinyassets/`). A reader grepping the issue's own
vocabulary against `main` gets a false "still missing" on item 7 and would have re-implemented a
solved problem.

**Pattern worth keeping:** when an issue lists salvaged work by recovery sha, classify by diffing
`main` against the salvage commit's *post-image* under the current naming, not by grepping the
issue's prose. Prose ages with the vocabulary; the post-image diff does not.

---

## Review gate — Codex (opposite-provider), verdict: ADAPT

Dispatched via `scripts/codex_review.py` and asked to *refute* the "all security items are stale"
conclusion, defaulting to refuted if uncertain. Codex independently re-ran verification and
**confirmed the seven `already-fixed` classifications** (`108 passed, 10 skipped`; escrow
`48 passed`; adjacent approval/scope tests `8 passed`; universe-node tests `154 passed, 9 skipped`),
finding no functional regression — hence adapt rather than reject. Five required adaptations, four
accepted and applied above:

| # | Codex finding | Outcome |
|---|---|---|
| 1 | `approve_source_code` records actor/hash and requires admin scope but does **not** enforce a distinct approver; don't call it "guarded too" | **Accepted** — §1 rewritten to state the difference explicitly and flag rather than assert intent |
| 2 | The "39-line residual = extra hardening" attribution is false; those lines are unrelated phase/escrow drift | **Accepted** — verified (`grep -ci "approv\|hash"` = 0 over the diff) and split into two separate facts |
| 3 | "Zero carried over" contradicts two still-valid verdicts; item 8's obsolescence claim is uncited; "fold into next touch" is not a disposition for item 9 | **Accepted** — coverage wording disambiguated; item 8 corrected (the salvaged doc is runtime-neutral and *aligns* with the reframe — my claim was backwards); item 9 now a tracked row |
| 4 | The documented recovery command is not reproducible: `git fetch origin <short-sha>` fails | **Accepted** — reproduced the failure, added a full-sha + PR-ref table and a working command |
| 5a | `tinyassets/branches.py:511` should be `tinyassets/api/branches.py` | **Rejected** — both modules exist on `main` (`git ls-tree -r origin/main --name-only \| grep -E "^tinyassets/(api/)?branches\.py$"` returns two paths) and line 511 of `tinyassets/branches.py` is the quoted invariant. Original citation was correct. |
| 5b | Soften "P0-framed" (the issue carries no P0 label); use resolvable paths for sibling docs | **Accepted** — applied below |

Finding 4 is the most useful thing this review produced: the issue's own recovery recipe, which
everyone reading it would have trusted, does not execute.

**Process note — the first dispatch silently reviewed the wrong thing.** The initial
`codex_review.py` call returned a confident, well-formatted `VERDICT: adapt` about an entirely
different lane (`wf-unified-authority` / selector dispatch — a task this session never asked
about), evidently from ambient context. It was caught only because the content was recognizably
off-topic; had it been plausibly adjacent, it would have been accepted as this audit's review gate.
The re-dispatch added a scope lock naming the exact issue and shas. This is the
`silent-failure-dispatch-and-tests` class: **a dispatch that returns *something* reads as success**,
and a cross-family gate that reviews the wrong artifact is worse than no gate, because it
manufactures unearned confidence. Worth a validation step (echo-the-scope, or assert the response
cites the artifact under review) in `codex_review.py` itself.

## Recommended disposition

Close #1346 with a summary, **after** re-homing the two survivors so closing does not drop them.
Nothing in the issue is a live security hole; the two survivors are a concept doc (host keep-or-drop
decision) and a two-line docstring xref (`dev-ready` row). Neither justifies keeping open an issue
whose headline claim is a present-tense security assertion that is no longer true — the issue
carries no P0 label, but its closing line functions as a priority claim, and that is what makes it
a hazard to the next reader.

The salvage shas remain reachable, so closing loses no recovery path — **provided the full shas
above are used**, since the issue's own short-sha recipe does not execute.

**The `gh` command is written out in the PR body for the host to run. This audit does not run it —
closing a host-visible issue is an outward-facing action.**
