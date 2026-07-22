# Stale non-draft PR disposition — 2026-07-22

**Scope.** The three non-draft PRs open longer than three weeks (#1397, #1432, #1435).
This note records the **disposition** — the action taken — and one corrected verdict.

- Evidence captured: **2026-07-22**, against `origin/main` = `de64fe57`.
- Every row was re-verified in this lane from command output, not inherited.
- A cross-family (Codex, read-only) gate was run to *refute* the verdicts before acting.
  It upheld two and **refuted the third**. See *The corrected verdict*.

## Verdicts and disposition

| PR | Age | mergeable | Real diff (merge-base) | Verdict | Disposition |
|---|---|---|---|---|---|
| [#1435](https://github.com/Jonnyton/TinyAssets/pull/1435) | 22d | CONFLICTING | 6 files, +712 | **Superseded** — shipped as an evolved superset via #1437 | **Closed** |
| [#1432](https://github.com/Jonnyton/TinyAssets/pull/1432) | 22d | CONFLICTING | 2 files, +338 | **Superseded** — note landed byte-identical; tests behind main | **Closed** |
| [#1397](https://github.com/Jonnyton/TinyAssets/pull/1397) | 27d | MERGEABLE | 1 file, +204 | **Not superseded — substantially implemented.** Prior "INVERTED" verdict was wrong | **Left open**; needs a header/path refresh before merge |

## Evidence commands

The naive `git diff origin/main <tip>` reports a stale branch as *deleting* thousands of
lines — an artifact of diff direction, not a real deletion. Always diff from the merge-base:

```bash
export MSYS_NO_PATHCONV=1
for n in 1397 1432 1435; do
  git fetch origin "+refs/pull/$n/head:refs/tmp/pr$n"          # explicit refspec; see Correction 2
  mb=$(git merge-base origin/main refs/tmp/pr$n)
  echo "== $n =="; git diff --shortstat $mb refs/tmp/pr$n
done
```

### #1435 — superseded by an evolved superset

```bash
git log origin/main --oneline --diff-filter=A -- tinyassets/auth/workos_provider.py
# b91a6b07 Founder & universe identity — all slices + multi-tenant + anon-write OAuth challenge (#1437)
git merge-base --is-ancestor b91a6b07 origin/main && echo "on main"
git diff refs/tmp/pr1435:tinyassets/auth/workos_provider.py \
         origin/main:tinyassets/auth/workos_provider.py
```

Main is the *evolved descendant*: it adds `resolve_always_writes() -> True` and
`challenge_unauthenticated()`, neither of which exists in the PR's version. Those two
methods are the anonymous-write gate and the 401 OAuth challenge. All six changed files
differ from main; none is a file main lacks. Landed sha: `b91a6b07` (#1437, 2026-07-15).

### #1432 — half already landed, half inverted

```bash
git rev-parse refs/tmp/pr1432:docs/design-notes/2026-06-30-tinyassets-universe-app-experience.md \
              origin/main:docs/design-notes/2026-06-30-tinyassets-universe-app-experience.md
# identical shas — landed as 07f6ac95 via #1433
git diff --numstat refs/tmp/pr1432:tests/test_universe_write_boundary.py \
                   origin/main:tests/test_universe_write_boundary.py   # 174 / 33
```

The PR's test file marks both cross-founder ownership checks `xfail(strict=True)` and its
header states D0a "is NOT yet enforced". Main's header records the opposite: those markers
were **promoted to permanent hard guards** because the tests now pass. Test count: main 9,
PR 3. Merging would convert two green regression guards back into expected failures — the
`never-game-the-gate-with-xfail` class.

### #1397 — the corrected verdict

My first pass, PR #1511's audit, and the verdict comment posted on the PR at 02:43 today
**all three** concluded "INVERTED premise — the delivery architecture was reversed by the
2026-07-02 relay reshape." The Codex gate refuted that, and re-checking proved Codex right.

The load-bearing check I had not run:

```bash
git grep -rn persona origin/main -- tinyassets/api/status.py
# :1171  "persona stops reciting soul.purpose and speaks its learned self-model."
# :1180  persona = resolve_persona(read_universe_soul(udir), read_self_model(udir))
```

That **is** the note's §9 slice 2 (`get_status.persona` = learned self-model), shipped. Not
reversed — implemented. Checking the rest of its slice plan the same way:

| #1397 slice | State on main |
|---|---|
| 1. OKF self-model bundle + blank seed | shipped — `tinyassets/universe_bundle.py:1,19` |
| 2. `get_status.persona` = learned self-model | shipped — `tinyassets/api/status.py:1171,1180` |
| 3. First-contact curiosity | shipped — `tests/test_persona.py` blank/curious newborn |
| 4. Generic-name-at-birth + identity/operational split | shipped — universe is unnamed at birth |
| 5. Remove `set_persona_name` | shipped — `tests/test_persona.py:318` records it retired |

**Where the "reversal" reading went wrong.** The 2026-07-02 relay reshape moved *embodiment*
from the chatbot to the first-party universe intelligence. #1397 never claimed the chatbot
would embody — it explicitly and repeatedly defers that to a separate gate (lines 42, 101,
128, 200: *"Client-instruction/prompt verification stays a separate acceptance gate"*).
And relay §13 does not reverse its principle 4 — it *continues* it: *"Principal (a) [the
universe's own intelligence] is unchanged and is now the only brain writer."* #1397's
"the brain is the sole author of its own self-model" and relay's "sole brain writer" are
the same commitment, one refining the other.

**What is genuinely stale** — surface only, not premise:

- Status line reads *"Proposed … build started at Slice 1"*. All five slices have shipped.
- It cites five module paths that no longer exist: `workflow/persona.py`,
  `workflow/universe_soul.py`, `workflow/api/status.py`, `workflow/wiki/okf_export.py`,
  `workflow/api/universe.py` (the `workflow/` → `tinyassets/` rename).

**Disposition: left open, not closed.** It is the design record — including a host design
dialogue and a folded Codex ADAPT review — for work that then shipped. That rationale exists
nowhere else in git. Before merge it needs its status line changed to reflect that the build
landed, the five paths repointed at `tinyassets/`, and a one-line footnote that embodiment
was later resolved by the relay reshape. Not done here: rewriting another author's PR is
outside this lane's write-set.

## Corrections to the briefing premise

Recorded because acting on an unverified premise is what this class of task exists to catch.

1. **The sweep hazard is inverted relative to the brief.** The brief warned #1432/#1435
   could be swept into a batch-merge and resolve against files where main is ahead. Both are
   `CONFLICTING` — GitHub cannot auto-merge them, so a sweep would fail, not silently
   regress. The only sweepable one is **#1397**: `MERGEABLE`, non-draft, auto-merge not
   enabled — the one the brief said not to close, and the one now deliberately left open.
   Its draft state was **not** changed unilaterally; flagged below as a host decision.
2. **The briefed reproduce command is unreliable here.** `git fetch origin
   pull/$n/head:refs/tmp/pr$n` succeeded for #1397 but printed
   `- [deleted] (none) -> refs/tmp/pr1432` for the other two, which reads as "the PR head no
   longer exists". It does exist (`git ls-remote origin 'refs/pull/1432/*'`). Use the
   explicit `+refs/pull/N/head:` refspec.
3. **No auto-merge was enabled on any of the three** (`gh pr view <n> --json
   autoMergeRequest` → null), so no `--disable-auto` was needed.

## The finding worth keeping

Three independent passes — PR #1511's audit, the 02:43 verdict comment, and my own first
pass — converged on the same **wrong** verdict for #1397, each citing the same relay-reshape
evidence. Convergence was not corroboration: the later passes inherited the earlier framing
and re-derived it. A single cross-family refutation gate overturned it in one round, by
asking for the one check none of the three had run (does `get_status.persona` still read the
self-model?).

Same-family agreement across three passes is worth roughly one pass. The cheap correction is
a refutation-framed gate to a different model family *before* acting, not another
confirmation pass.

Had the "INVERTED" verdict been executed as written, a 204-line host-ratified design record
for five shipped slices would have been closed as stale.

## Open item for the host

**#1397 is non-draft and `MERGEABLE`.** Given the 2026-07-22 batch that undrafted and
squash-merged 20+ PRs at 1s intervals (three titled "DO NOT MERGE"), leaving it non-draft is
a live hazard, but converting someone else's PR to draft was outside this lane's authority.
Either mark it draft until its header refresh lands, or refresh and merge it.

## Proposed STATUS.md row

Not applied — 16 open PRs touch `STATUS.md` and this lane's write-set excludes it
deliberately. If a janitor pass wants one:

```
| [filed:2026-07-22] #1397 non-draft + MERGEABLE with a stale header (5 shipped slices still labelled "Proposed", 5 retired workflow/* paths) — refresh or mark draft | docs/design-notes/2026-06-25-blank-slate-universe-brain.md | - | host-decision |
```

## Mutation record

- **Closed** #1432 and #1435 with closing comments citing the evidence above.
- **#1397 left open**, unmodified except for a comment correcting the earlier INVERTED
  verdict. Draft state untouched.
- No PR was merged, rebased, or enrolled in auto-merge. `STATUS.md` was not edited.
- Cross-family gate: Codex `exec --sandbox read-only`, verdicts
  A=upheld / B=upheld / **C=refuted**, OVERALL=adapt. Its refutation was accepted and
  changed this lane's action on #1397 from *close* to *leave open*.
