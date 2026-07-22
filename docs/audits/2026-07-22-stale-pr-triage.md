<!--
Provenance: carried verbatim from the lane's own artifact, committed locally on
branch `audit/2026-07-22-stale-pr-triage` (commit d4286864) but never pushed —
the lane had no `gh` login and no HTTPS egress to GitHub, so it could not open
its own PR. Body below is that commit's file unmodified; only this comment was
added.
-->

# Stale PR premise triage — 2026-07-22

## Scope and method

This audit treats each PR patch as untrusted. It compares the exact locally cached
PR head against current `origin/main`, not the PR title.

- Evidence captured: **2026-07-21, America/Los_Angeles**.
- Current `origin/main`: `220a1fc8c69d3ae07b7673494e30d1267a220f69`.
- Founder/universe integration merge: `b91a6b077729bc44831ec042c959f688b685be16`
  (`Founder & universe identity — all slices + multi-tenant + anon-write OAuth
  challenge (#1437)`, merged 2026-07-15).
- PR refs were identified by exact head/stat match: #1435 = `c9b2f62d` (6 files,
  +712); #1432 = `13ec047b` (2 files, +338); #1397 = `74a125ad` (1 file,
  +204).
- Checks used: full changed-file lists, per-path main history, `git cherry`,
  direct tree diffs, current code inspection, and `git merge-tree --write-tree`.
- Focused current-main verification:
  `python -m pytest tests/test_workos_provider.py
  tests/test_universe_write_boundary.py tests/test_persona.py
  tests/test_universe_intelligence.py tests/test_universe_bundle.py -q
  --basetemp .pytest-tmp-stale-pr` → **106 passed** on 2026-07-21.

## Verdicts

| PR | Verdict | Recommended action |
|---|---|---|
| [#1435](https://github.com/Jonnyton/TinyAssets/pull/1435) | **ALREADY-LANDED** | Do not enroll or rebase. Comment that #1437 landed a hardened superset; human may close as superseded. |
| [#1432](https://github.com/Jonnyton/TinyAssets/pull/1432) | **INVERTED** | Do not enroll. Its app note landed separately and its D0a tests now encode the opposite state; human may close as superseded. |
| [#1397](https://github.com/Jonnyton/TinyAssets/pull/1397) | **INVERTED** | Do not enroll. Preserve only as history; its surviving blank-brain principle is implemented, but its chatbot/persona architecture is superseded by relay/converse. |

## PR #1435 — WorkOS AuthKit Resource Server

**Verdict: ALREADY-LANDED.** The intended capability is present on main through
`b91a6b07`, with later enforcement and test coverage that make the stale patch an
unsafe source of truth.

### Patch inspected

- Head `c9b2f62d915d86b52ec3949d397698a612427d49`, merge-base
  `d7b8e0791e58a60c7bc46088c8168a9b696ccc44`.
- Six files, +712: root/plugin `auth/provider.py`, root/plugin
  `auth/workos_provider.py`, `pyproject.toml`, and
  `tests/test_workos_provider.py`.
- `git cherry HEAD c9b2f62d` reports `+`, not because the capability is absent,
  but because #1437 squash-landed an evolved patch rather than the original
  commit identity. Every changed path has a `b91a6b07` main-history entry.

### Current-main code evidence

- WorkOS mode selects `WorkOSAuthProvider.from_env()` at
  `tinyassets/auth/provider.py:1135-1145`.
- Audience binding fails closed without `WORKOS_MCP_RESOURCE` at
  `tinyassets/auth/workos_provider.py:90-121`.
- JWT validation pins RS256 and requires issuer, `exp`, and `sub` at
  `tinyassets/auth/workos_provider.py:135-155`.
- Anonymous reads remain open while every write/costly/admin action requires a
  resolved founder at `tinyassets/auth/workos_provider.py:186-196`; connector
  OAuth challenge behavior follows at lines 198-205.
- The dependency is present at `pyproject.toml:51-53`, and root/plugin WorkOS
  provider files are byte-for-byte equal.
- Current guards include `tests/test_workos_provider.py:101-124` (identity and
  capabilities), `:322-325` (resolve-always writes), and `:476-500` (401
  challenge). These passed in the 106-test focused run.

### Landed-since contradiction

The stale head explicitly says gating is unchanged and returns `False` from
`is_auth_required()` at
`c9b2f62d:tinyassets/auth/workos_provider.py:170-174`; it has no
`resolve_always_writes()` override. Current main deliberately added that override
at `tinyassets/auth/workos_provider.py:192-196`. Reinstating the stale file would
erase the anonymous-write security posture now specified in
`openspec/specs/identity-auth-and-access-control/spec.md:32-45`.

`git merge-tree --write-tree HEAD c9b2f62d` confirms add/add conflicts in both
root/plugin `workos_provider.py` and `tests/test_workos_provider.py`. This PR is
not a missing slice to refresh; its desired slice already landed and its exact
file versions are obsolete.

**Action:** post the ALREADY-LANDED verdict; do not auto-merge, update, or rebase.
Leave closure to a human, with #1437 named as the superseding route.

## PR #1432 — Founder/universe identity: D0a write gate

**Verdict: INVERTED.** Half the patch is already landed byte-for-byte; the other
half asserts the opposite of current behavior and would downgrade live regression
guards back to expected failures.

### Patch inspected

- Head `13ec047b1d72ff608be3554defa670bdc0a141de`, merge-base
  `97e0f91467906d6903452eb3c64be735446c28c0`.
- Two files, +338: a 134-line app experience note and a 204-line D0a acceptance
  test.
- `git cherry HEAD 13ec047b` marks the app-note commit `13ec047b` as patch-
  equivalent (`-`); it landed on main as `07f6ac95` via PR #1433. Direct file
  diff is empty.

### Current-main code evidence

- Universe creation grants the authenticated founder an `admin` ACL at
  `tinyassets/api/universe.py:4781-4791`.
- Writes require an authenticated actor with `write`/`admin` permission at
  `tinyassets/api/permissions.py:93-127`.
- The D0a tests are permanent passing guards at
  `tests/test_universe_write_boundary.py:131-163`; their header records the
  enforced state at lines 13-20. They passed in the focused run.
- `b91a6b07` is the main-history source for the evolved D0a test file.

### Landed-since contradiction

The stale test says D0a “is NOT yet enforced” at
`13ec047b:tests/test_universe_write_boundary.py:13-20` and marks both ownership
checks `xfail(strict=True)` at lines 138-170. Current main removed both xfails
because the tests now pass. It also added relay/write-door coverage at
`tests/test_universe_write_boundary.py:185-346`.

`git merge-tree --write-tree HEAD 13ec047b` produces an add/add conflict in the
test file. Resolving toward the PR would conceal regressions by converting two
hard green isolation guards back into expected failures.

**Action:** post the INVERTED verdict; do not auto-merge, update, or rebase.
Leave closure to a human, citing #1433 for the note and #1437 for D0a.

## PR #1397 — blank-slate universe brain design note

**Verdict: INVERTED.** Its central “blank, learning, sole-author brain” principle
survives and is implemented, but the PR as a whole is a proposed architecture
whose chatbot/persona delivery model and build status were superseded after it
was written. Merging it now would add contradictory design truth.

### Patch inspected

- Head `74a125adcb2f800d5bc736ff1e1661d6ddb41590`, merge-base
  `859e44404643226c603c6d3dc92983deec277dcb`.
- One new 204-line file:
  `docs/design-notes/2026-06-25-blank-slate-universe-brain.md`.
- None of its three commits is patch-equivalent to current main, and the file is
  absent from main. A merge-tree simulation is clean because it merely adds the
  stale document; clean application is not proof of a valid premise.

### What is already present by another route

- Blank OKF soul seeding is current code at `tinyassets/universe_bundle.py:1-23`
  and `_identity_md()` at line 168.
- The assigned universe intelligence extracts only founder-grounded learning at
  `tinyassets/universe_intelligence.py:198-224`, commits guarded soul/canon changes
  at lines 334-405, and serves first-person conversation at lines 408-423.
- `tests/test_persona.py:203-263` covers blank/curious learned identity, and line
  314 records retirement of `set_persona_name`.
- These paths reached main through `4915667b` (#1406) and the #1437 squash
  `b91a6b07`; the relevant tests passed in the focused run.

### Landed-since contradiction

The stale note remains labeled “Proposed” / “build started at Slice 1” and points
at retired `workflow/*` paths at
`74a125ad:docs/design-notes/2026-06-25-blank-slate-universe-brain.md:3-6`.
More importantly, it makes the learned self-model the chatbot persona voice and
routes connector onboarding to that persona at lines 77-100, then treats stronger
chatbot embodiment as a separate client gate at lines 126-149.

The host-approved later design reverses that surface:

- `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md:27-45`
  says the assigned universe intelligence is the personified agent and the
  chatbot is a relay.
- The same note at lines 304-335 says the universe intelligence is the sole brain
  writer; chatbot/app brain writes relay through `converse`.
- The behavior exists in `tinyassets/universe_intelligence.py:408-423` and the
  relay guards at `tests/test_universe_write_boundary.py:185-346`.

The non-contradictory blank-brain principle therefore needs no resurrection from
#1397, while the rest of that proposed note would misstate current architecture.

**Action:** post the INVERTED verdict; do not auto-merge or rewrite the stale PR.
Leave closure to a human. If a canonical blank-brain history note is ever wanted,
write it from current relay/converse code and the as-built OpenSpec baseline rather
than merging this proposal.

## Mutation record

No PR was closed, merged, rebased, or enrolled by this audit. Required verdict
comments are required for all three PRs because every verdict is
ALREADY-LANDED/INVERTED.

The audit is committed on `audit/2026-07-22-stale-pr-triage`. GitHub delivery
was blocked in this session:
`gh auth status` reported no authenticated host, HTTPS push could not connect to
`github.com:443`, and the authenticated connector's branch-creation mutation was
cancelled before creating remote state. Consequently, **no verdict comment was
posted, no remote branch was created, and no draft PR was opened**. A pickup must
push this commit (or recreate its one-file tree), post the three verdicts above,
and open the required draft PR; it must still not close or merge any stale PR.
