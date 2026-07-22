# Audit: 22 fundraising files on zero refs, hidden under agent scratch — 2026-07-22

**Status:** audit complete. `.gitignore` gap closed in the landing PR; the 22 files were **not** committed and **not** moved. Durable storage is a host decision (§6).
**Auditor:** claude-code, primary checkout `C:/Users/Jonathan/Projects/TinyAssets`, 2026-07-22.
**Scope note:** this document lists **paths and file metadata only — never contents**. That is deliberate: someone must be able to learn these files exist, and that they are unbacked-up, without this audit itself becoming the leak. The repository is public.

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

## 2. Inventory (paths + metadata only)

| Path | Bytes | mtime |
|---|---|---|
| `data-room/00-START-HERE.md` | 1,425 | 2026-06-18 |
| `data-room/01-Pitch-Materials/Tiny-One-Pager.md` | 2,585 | 2026-06-18 |
| `data-room/01-Pitch-Materials/_README.md` | 143 | 2026-06-18 |
| `data-room/02-Company-and-Legal/_README.md` | 154 | 2026-06-18 |
| `data-room/03-Cap-Table/Cap-Table-Template.md` | 691 | 2026-06-18 |
| `data-room/04-Financials/_README.md` | 148 | 2026-06-18 |
| `data-room/05-Product-and-Tech/_README.md` | 213 | 2026-06-18 |
| `data-room/06-Team/_README.md` | 134 | 2026-06-18 |
| `data-room/07-Market-and-Traction/_README.md` | 138 | 2026-06-18 |
| `data-room/08-Customers-and-Contracts/_README.md` | 185 | 2026-06-18 |
| `data-room/CHECKLIST.md` | 2,509 | 2026-06-18 |
| `investor-list/00-README.md` | 645 | 2026-06-18 |
| `investor-list/Tiny-Investor-Pipeline.xlsx` | 15,236 | 2026-06-18 |
| `pitch-deck/00-deck-design-playbook.md` | 16,854 | 2026-06-17 |
| `pitch-deck/01-deck-outline.md` | 8,244 | 2026-06-17 |
| `pitch-deck/02-narrative-spine.md` | 10,876 | 2026-06-19 |
| `pitch-deck/03-pitch-deck-review.md` | 4,071 | 2026-06-17 |
| `pitch-deck/04-stage-deck-script.md` | 7,089 | 2026-06-18 |
| `pitch-deck/DESIGN.md` | 6,169 | 2026-06-17 |
| `pitch-deck/Tiny-Recruiting-Deck.pptx` | 217,911 | 2026-06-17 |
| `pitch-deck/Tiny-Send-Deck.pptx` | 129,733 | 2026-06-17 |
| `pitch-deck/Tiny-Stage-Deck.pptx` | 387,805 | 2026-06-19 |

Totals: `data-room/` 11 files / 8,325 B · `pitch-deck/` 9 files / 788,752 B ·
`investor-list/` 2 files / 15,881 B — **22 files, 812,958 B (794 KB)**.

The `.xlsx` and `.pptx` contents were deliberately not opened during this audit.

## 3. The mechanism that hid them

`git status --porcelain --untracked-files=all` in the primary checkout reported
**7,553 untracked files** at audit time. Breakdown:

| Top-level path | Count | Ignored before this PR? |
|---|---|---|
| `.tmp/` | ~7,000+ | **no** |
| `codex-tmp/` | ~1,100+ | **no** |
| `data-room/`, `pitch-deck/`, `investor-list/` | 22 | no |
| `docs/audits/`, `scripts/` | 7 | no (real in-flight work) |
| `.codex-worktrees/`, `.codex-scratch-*`, `.agents/village-inbox/`, `.claude/.fleet_floor_state.json` | ~6 | no |

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
drops to **7 files** — and all 7 are themselves real unversioned work
(`scripts/patch_announcement.py`, `scripts/peer_agent.py`,
`scripts/post_x_update.py`, `scripts/provider_github_bootstrap.py`, and three
`docs/audits/2026-07-22-*.md`). Several correspond to lanes that
`provider_context_feed.py` reports as *"wrote it, opened no PR"*. Removing the
noise immediately surfaced a second tier of the same problem. That is the
argument for the change in one number: **7,553 → 7**.

## 5. What the landing PR changes

One committed file: `.gitignore`.

- **New *Agent scratch dirs* section** — `.tmp/`, `codex-tmp/`,
  `.codex-worktrees/`, `.codex-scratch-*`, `.claude/.fleet_floor_state.json`,
  `.agents/village-inbox/`. Commented with the near-miss explanation so a future
  reader does not "simplify" `.tmp/` into the existing `.tmp-*`.
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
| After scratch rules only | 29 (= 22 business + 7 stragglers) |
| After both rule sets (this PR) | 7 |

## 6. What this does NOT fix — host action required

**`.gitignore` does not back anything up. For these files it arguably makes the
risk worse:** `git clean -xdff` uses `-x` to target *ignored* files specifically,
so the 22 files move from "cleaned only by `-xdff`" to "cleaned by `-xdff`, and
now invisible in `git status` while they wait." The protection this PR adds is
against *accidental commit to a public repo*, not against *deletion*.

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
  luck-dependent to routine; not proposed here to keep this PR to one file.
