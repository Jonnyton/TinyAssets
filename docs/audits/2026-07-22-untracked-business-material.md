# Audit: 22 fundraising files on zero refs, hidden under agent scratch — 2026-07-22

**Status:** audit complete. `.gitignore` gap closed in the landing PR; the 22 files were **not** committed and **not** moved. Durable storage is a host decision (§6).
**Auditor:** claude-code, primary checkout `C:/Users/Jonathan/Projects/TinyAssets`, 2026-07-22.
**Scope note — deliberately reduced:** this repository is **public**, so this document publishes **only what the `.gitignore` change itself already discloses**: the three top-level directory names, file counts, and aggregate sizes. Individual filenames, per-file sizes and dates, and the absolute host path are **withheld**, and no file's contents were ever opened. An earlier draft of this audit carried a full per-file table; that was reduced after cross-family review (§8). The bar for a public audit of private material is "enough that the problem cannot be forgotten," not "enough to enumerate the assets."

## 1. Ground facts

- **Repository is PUBLIC.** `gh repo view` → `Jonnyton/TinyAssets`, `visibility=PUBLIC` (verified 2026-07-22).
- **22 files exist on zero refs.** Enumerated every ref with
  `git for-each-ref refs/remotes/origin refs/heads` (171 refs) and ran
  `git ls-tree -r --name-only` against each. None of the paths in §2 appear on
  any ref, local or remote. They exist in exactly one dirty working tree on one
  machine.
- **They were not covered by `.gitignore`** before this audit's PR. Their absence
  from git was an accident of nobody having run `git add`, not a decision.
- **They are ~5 weeks old.** mtimes span 2026-06-17 → 2026-06-19. They have been
  in this state, unnoticed, for over a month.
- **The primary checkout is 15 commits behind `origin/main` and dirty.** It is
  nonetheless the only place these files exist, so it must not be cleaned.

## 2. Inventory (aggregate only)

| Directory | Files | Bytes |
|---|---|---|
| `data-room/` | 11 | 8,325 |
| `pitch-deck/` | 9 | 788,752 |
| `investor-list/` | 2 | 15,881 |
| **Total** | **22** | **812,958 (794 KB)** |

Composition, without enumerating filenames: mostly small Markdown, plus one
spreadsheet and three binary presentation files which account for ~91% of the
bytes. mtimes span 2026-06-17 → 2026-06-19.

These three directory names are named in `.gitignore` by necessity — an ignore
rule cannot exist without them — so publishing them here adds nothing. The
per-file listing is withheld per the scope note.

No file's contents were opened at any point during this audit; the binary
formats in particular were never parsed.

## 3. The mechanism that hid them

`git status --porcelain --untracked-files=all` in the primary checkout reported
**7,553 untracked files** at audit time. Breakdown:

| Top-level path | Count | Ignored before this PR? |
|---|---|---|
| `codex-tmp/` | 4,025 | **no** |
| `.tmp/` | 3,492 | **no** |
| `data-room/`, `pitch-deck/`, `investor-list/` | 22 | no |
| `docs/audits/`, `scripts/` | 7 | no (real in-flight work) |
| `.codex-worktrees/`, `.codex-scratch-*` (+`.zip`), `.claude/.fleet_floor_state.json` | 5 | no |
| `.agents/` (village-inbox runtime) | 2 | no — and stays unignored, see §5 |

All counts above come from **one** snapshot totalling 7,553; they sum exactly.
**99.6% of `git status` was agent scratch.** The existing `.gitignore` covered
`.pytest-tmp/`, `.codex-test-tmp/`, `.workflow-test-data/`, and `.codex/` — but
two near-miss gaps let the highest-volume producers through:

- `.tmp-*` (line 64, under *OS / editor*) does **not** match `.tmp/`.
- `.codex/` does **not** match `codex-tmp/`.

Real, unversioned, business-critical work was therefore a needle in a haystack.

**The count is not stable.** Three measurements minutes apart during this audit
returned 4,699 → 6,784 → 7,553. Agent lanes generate scratch continuously, so
the haystack grows on its own while the needles do not move. Any "I'd have
noticed" intuition should be discounted accordingly.

**Some scratch is not even readable.** `codex-tmp/pytest-*` and several `.tmp/*`
subdirectories return `Permission denied` — created under the
`CodexSandboxOffline` token, carrying ACLs the interactive user cannot read or
delete (AGENTS.md § *Sandbox test-temp hygiene*). `git status` emits a wall of
`warning: could not open directory` lines before its output, further burying the
signal.

## 4. Why this is urgent rather than tidy

This is the third instance of the same class in 24 hours, and the first two were
found **by accident**:

- **PR #1489** (merged 2026-07-22T01:21Z) recovered `command_center/` — 26 files,
  37 tests, a working feature — which *"existed in zero commits anywhere in the
  repo"* and survived only as untracked files in a stale checkout. Its body:
  *"One `git reset --hard`, one `git clean`, or one fresh clone and it was gone
  permanently."*
- **PR #1490** (merged 2026-07-22T00:41Z) recovered 32 documents on the same
  basis: *"a `git clean` away from gone."*

Both PR bodies verified via `gh pr view` on 2026-07-22.

Nothing about the repository changed after those two landed to make the next
instance findable. The 22 files in §2 were in the identical position while both
recoveries were being merged.

**Confirming datapoint:** once the scratch rules are applied, the untracked list
drops to **9 files** — and all 9 are themselves real unversioned work: four
`scripts/*.py`, three `docs/audits/2026-07-22-*.md`, and two
`.agents/village-inbox/*.md` host-message files. Several correspond to lanes
that `provider_context_feed.py` reports as *"wrote it, opened no PR"*. Removing
the noise immediately surfaced a second tier of the same problem. That is the
argument for the change in one number: **7,553 → 9**, where every one of the 9
is something a person would want to see.

## 5. What the landing PR changes

Two committed files: `.gitignore` and this audit.

- **New *Agent scratch dirs* section** — `.tmp/`, `codex-tmp/`,
  `.codex-worktrees/`, `.codex-scratch-*`, `.claude/.fleet_floor_state.json`.
  Commented with the near-miss explanation so a future reader does not
  "simplify" `.tmp/` into the existing `.tmp-*`.
- **`.agents/village-inbox/` deliberately NOT ignored.** It pattern-matches as
  scratch and appeared in the first draft of this change. It is not scratch:
  `command_center/collector.py` writes host→agent messages there and
  `ideas/2026-07-19-agent-village-command-center.md` calls it *"durable, agents
  can poll"*. Ignoring it would have hidden durable state — the precise failure
  this section exists to prevent — in the very code PR #1489 recovered, for 2
  files (572 B) of volume benefit. Caught by cross-family review (§8); an
  in-file comment now records the reasoning.
- **New *Fundraising / company material* section** under the existing
  *Personal docs (not part of the engine)* precedent — `data-room/`,
  `pitch-deck/`, `investor-list/`. This makes their exclusion from a public repo
  a **recorded decision** rather than an accident.

Safety checks performed before writing the rules:

- `git ls-files --error-unmatch` returned **zero tracked files** for every
  candidate path — no new rule shadows tracked content.
- The load-bearing comment block declaring `branches/`, `goals/`, `nodes/`
  intentionally **not** ignored (per PLAN.md *"GitHub as the canonical shared
  state"*) is untouched.
- No business file was staged. Confirmed with `git diff --cached --name-only`.

Measured effect, single consistent snapshot:

| Measurement | Untracked count |
|---|---|
| Before | 7,553 |
| After scratch rules only | 31 (= 22 business + 9 real-work stragglers) |
| After both rule sets (this PR) | 9 |

## 6. What this does NOT fix — host action required

**`.gitignore` does not back anything up. For these files it arguably makes the
risk worse:** `git clean -xdff` uses `-x` to target *ignored* files specifically,
so the 22 files move from "cleaned only by `-xdff`" to "cleaned by `-xdff`, and
now invisible in `git status` while they wait." The protection this PR adds is
against *accidental commit to a public repo*, not against *deletion*.

**Nor does it enforce "must never land."** `git add --force` stages ignored
paths by design. An ignore rule is defense-in-depth against the accidental
`git add .`; it is not a control against a deliberate or scripted add.
Relocation out of a public checkout is the only real control — which is why §6
is a host action and not a follow-up nicety.

After this PR, the exposure is unchanged in substance:

> 794 KB of fundraising material — a cap table, an investor pipeline, and three
> pitch decks — exists in exactly one directory, on one machine, with no version
> control and no backup.

**Host ask (one decision):** choose a durable home outside this repository for
`data-room/`, `pitch-deck/`, and `investor-list/` — a private Git repo, a cloud
drive folder, or an encrypted archive — and move them there.

No agent should perform that move: every option routes company-confidential
material to an external service, which is a publishing decision reserved to the
host. This audit deliberately stops at naming the ask.

Until it is done, treat the primary checkout at
`C:/Users/Jonathan/Projects/TinyAssets` as holding unbacked-up company data:
do not run `git clean`, `git reset --hard`, `git restore`, or `git checkout --`
there (already AGENTS.md Hard Rule 13, reinforced here for this specific
reason), and do not delete the checkout.

## 7. Follow-ups

- **Host action:** durable storage for the 22 files (§6). Until closed, the
  single-copy exposure stands.
- **Triage the 7 stragglers** surfaced in §4 — 4 scripts and 3 audit documents
  currently on zero refs. Likely in-flight lane work per
  `provider_context_feed.py`, but that is an assumption, not a verification.
- **Structural gap remains.** Three instances in 24 hours were all caught by a
  human or an agent happening to look. Nothing detects "file on zero refs, older
  than N days" on a schedule. A periodic check would convert this class from
  luck-dependent to routine; not proposed here to keep this PR small.
- **Branch history carries the reduced-away detail** (§8). Host decision.

## 8. Cross-family review

Dispatched to Codex (`scripts/codex_review.py`, read-only, diff-based) before
this audit was presented. **Verdict: `adapt`** — four required changes, all
accepted, all applied above:

1. **`.agents/village-inbox/` misclassified as scratch.** Confirmed against
   `command_center/collector.py` and the design note; rule dropped, comment
   added (§5). This was the highest-value finding — the change would have
   re-created its own bug class.
2. **Public audit was over-specific.** The first draft published a per-file
   table with exact filenames, sizes, and dates, plus the absolute host path,
   for private fundraising material in a public repo. Reduced to directory
   aggregates (§2 scope note).
3. **Count drift.** The §3 breakdown mixed an early snapshot into a later
   total, and inverted the two largest producers. Re-measured from a single
   snapshot; the figures now sum to 7,553 exactly.
4. **`.gitignore` ≠ enforcement.** `git add --force` bypasses it; noted in §6.

Codex independently validated: repository visibility is public; PRs #1489/#1490
and their quoted premises are accurate; 22 files totalling 812,958 B exist only
under the primary checkout across 218 local roots scanned; no business-path
object exists on any current ref; `branches/`, `goals/`, `nodes/` remain
visible; focused test run `79 passed`.

Codex also advised shipping the scratch rules separately from the fundraising
rules, so the latter do not land before storage is resolved. Not applied
unilaterally — the PR is draft and blocked on §6 either way, and splitting is
the host's call. Noted here so the option is not lost.

**Disclosure — the reduced detail is already public.** The first commit on this
branch (`39fe9509`) contained the full per-file table and was pushed to this
public repository before the review returned. Reduction happened in a follow-up
commit, so the detail remains reachable in this branch's history. Removing it
would require a force-push or branch deletion — both destructive operations that
AGENTS.md Hard Rule 13 reserves for an explicit host request, so **no cleanup
was attempted**. `main` is unaffected: this PR is draft and unmerged. The host
may (a) leave it, (b) authorize a force-push, or (c) delete the branch and
re-open from a squashed commit. Contents were never published in any commit.
