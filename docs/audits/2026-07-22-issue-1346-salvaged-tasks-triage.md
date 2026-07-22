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

**Coverage: 9 of 9 verified against `origin/main`. Zero carried over. No silent caps.**
7 already-fixed, 2 still-valid — and **both survivors are documentation-only**. The security
section is entirely stale.

All 10 salvage shas still resolve locally (`git cat-file -e <sha>` succeeds for every one), so
nothing was lost while this sat. Recovery, if ever wanted: `git fetch origin <sha> && git branch
<name> <sha>`.

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

The 39-line residual vs. the salvage post-image is `main`'s *additional* hardening: a whole
`approved_source_hash` staleness regime in `tinyassets/api/branches.py:196-279` that re-validates a
bare `approved=True` against the hash of the *current* source, plus enforcement at
`branches.py:1689-1728`. That is strictly more defence than the salvage proposed.

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

Disposition: the issue itself files this as *"Speculative `status: proposed` doc. Low priority."*
It is a concept page with no code behind it, and the platform's direction has since been reframed
twice (`enabling-primitives-not-prebuilt-complexity`, `platform-shape-democratized-commons`).
**Recommend drop, not port** — re-derive from current direction if the concept is still wanted.

### [9] `github_read` docstring xref — `93cf2317` — **still-valid** (docs, trivial)

Genuinely absent, and the absence is meaningful: the xref *target* exists, so this is a real
dangling cross-reference rather than a stale pointer to deleted code.

- `git show origin/main:tinyassets/effectors/github_read.py | grep -c "search_repo_files\|github_search"` → **0** (whole file, not a narrow pattern).
- Plugin mirror: same check → **0**.
- Target exists: `tinyassets/effectors/github_search.py`, `tests/test_github_search_repo_files.py`,
  design note `docs/design-notes/2026-05-29-repo-search-primitive.md`.

The salvage's exact one-line addition:

```
See also ``search_repo_files`` in ``workflow/effectors/github_search.py`` for the localization/search counterpart.
```

(needs the `workflow/` → `tinyassets/` path rewrite, and the same line in the packaging mirror).

Disposition: trivial docs nicety, no urgency, no security or behaviour impact. Fold into whatever
next touches `github_read.py` rather than spending a lane on it.

---

## Why this sat for 27 days

The issue was filed correctly and in good faith — as a *snapshot* of work-in-flight on
2026-06-25. What it lacks is any expiry semantics. It asserts present tense (*"holes that exist on
`main` today"*) about a `main` that has since absorbed nearly all of it, and it has no labels, no
assignee, and no STATUS row, so nothing ever forced a re-read.

That is the same shape as `stale-backlog-rows-misdirect` (5 of 5 dispatched dev-ready rows wrong on
2026-07-21) and as the `daemon-request` issue backlog triaged separately in
`daemon-request-issues-address-a-deleted-pipeline.md` — **different issue set, same disease**: a
durable artifact asserting present-tense state, with no mechanism to notice it stopped being true.

The specific trap here is that the salvaged work *did* land — mostly through ordinary development
that never referenced the issue number, and partly under renamed symbols
(`WORKFLOW_*` → `TINYASSETS_*`, `workflow/` → `tinyassets/`). A reader grepping the issue's own
vocabulary against `main` gets a false "still missing" on item 7 and would have re-implemented a
solved problem.

**Pattern worth keeping:** when an issue lists salvaged work by recovery sha, classify by diffing
`main` against the salvage commit's *post-image* under the current naming, not by grepping the
issue's prose. Prose ages with the vocabulary; the post-image diff does not.

---

## Recommended disposition

Close #1346 with a summary. Nothing in it is a live security hole; the two survivors are a
speculative concept doc (recommend drop) and a one-line docstring xref (fold into next touch) —
neither justifies keeping a P0-framed issue open. The salvage shas remain reachable, so closing
loses no recovery path.

**The `gh` command is written out in the PR body for the host to run. This audit does not run it —
closing a host-visible issue is an outward-facing action.**
