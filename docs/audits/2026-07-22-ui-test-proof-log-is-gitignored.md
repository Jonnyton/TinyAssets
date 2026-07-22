# The final-acceptance proof is written to a path that has never been in git

**Filed:** 2026-07-22 · **Provider:** claude-code · **Lane:** `claude/uitest-proof-durability`
**Evidence environment:** Windows checkout `C:/Users/Jonathan/Projects/TinyAssets`, `origin/main` at
`144eaba7`, fetched 2026-07-22. Every command below is reproducible from a fresh clone except the
`ls`/`wc` on the untracked file, which is the point of the finding.

**Status:** audit + recommendation. The three file edits this implies (`AGENTS.md`, `.gitignore`,
`STATUS.md`) are **not** made here — all three are contended by open PRs. They are routed as
verbatim proposed text in the PR body for the lanes that own them.

---

## 1. The gap

`AGENTS.md` §"Quality Gates" (`origin/main:AGENTS.md:269`) makes a browser-rendered chatbot
conversation the **final acceptance gate** for a large class of changes, and names exactly one place
to record it:

> **Final chatbot-surface verification is a rendered chatbot conversation through the live
> connector.** For changes affecting public MCP behavior, chatbot UX, connector tool descriptions,
> user-visible node/workflow state, or `tinyassets.io`, final acceptance must use a real
> browser-rendered chatbot conversation with the installed TinyAssets MCP connector at
> `https://tinyassets.io/mcp`, following `ui-test`. … **Log the rendered prompt/result in
> `output/user_sim_session.md`** and include a trace or screenshot path when available.

That path is gitignored, and always has been:

```console
$ git check-ignore -v output/user_sim_session.md
.gitignore:70:output/	output/user_sim_session.md

$ ls -la output/user_sim_session.md
-rw-r--r-- 1 Jonathan 197121 302351 Jul 21 21:23 output/user_sim_session.md

$ git ls-tree --name-only origin/main output/
                                                  # empty — nothing under output/ is tracked

$ git log --all --oneline --diff-filter=A -- output/user_sim_session.md
                                                  # empty — never added on ANY ref, ever
```

The artifact is real, large, and actively written: 302,351 bytes / 2,861 lines, modified today. It
grew ~7 KB during the few hours this audit was being prepared. And it is **invisible to every other
provider, every reviewer, every fresh clone, and every future session.** The gate runs; the gate
produces no durable evidence.

The `ui-test` skill states the contradiction in its own words
(`origin/main:.agents/skills/ui-test/SKILL.md:223`, mirrored at `.claude/skills/ui-test/SKILL.md:223`):

> `output/user_sim_session.md` is the durable transcript between you and the lead.

It is not durable. It is one machine's scratch file.

## 2. This is load-bearing, not theoretical

A live concern already rests on it — `origin/main:STATUS.md:18`:

> [filed:2026-07-14 verified:2026-07-14] Watch: anonymous-write gate LIVE + `ui-test` PASSED
> (Claude.ai rendered convo: reads rich, anonymous write rejected w/ actionable OAuth guidance,
> nothing persisted; log output/user_sim_session.md). …

The sole proof behind "`ui-test` PASSED" is a file nobody but this one checkout can read. Per
`AGENTS.md` §"Truth And Freshness" — *"Verification claims must be freshness-stamped. If a claim
depends on tests, lint, runtime behavior, or environment state, include the date, environment, and
evidence/command"* — an unreadable log cannot discharge that claim. §"Post-fix clean-use evidence"
raises the bar further, requiring real-user evidence be recorded and freshness-stamped.

And the blast radius is much wider than one concern. **45 tracked files cite
`output/user_sim_session.md`** (42 excluding three archived `.cowork-uploads/` duplicates), of which
**27 are under `docs/`** — audits, design notes, exec plans, and ops runbooks that name it as their
evidence base:

```console
$ git grep -il 'user_sim_session' origin/main -- | wc -l
45
```

`docs/audits/2026-04-26-user-capability-axis-implications.md` cites it down to a line number
(`L1775`). `docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md` row R8 rests
its "landed" verdict on it. The entire `docs/audits/user-chat-intelligence/` series — 13 files — is
built on it. **None of those citations can be followed by anyone.** They are dangling references to a
file that has never existed in the repository.

The project already classifies this shape as a defect. `AGENTS.md` §"Multi-Session Steering":
*"Durable coordination belongs in files, not private chat memory"* and *"A useful idea left only in
chat is lost work."* A gitignored proof log is the same failure with extra steps — it has a filename,
which makes it look durable, which is worse than obviously-ephemeral chat.

## 3. Secrets check on the existing log — one real finding

Required before proposing anything be committed. Scanned all 2,861 lines.

**No credential material.** Zero matches for `sk-`, `ghp_`/`gho_`/`github_pat_`, `xoxb-`, `AKIA…`,
`AIza…`, JWT triplets, `client_secret`, `refresh_token`, `access_token`, `Authorization:` headers, or
PEM private-key blocks. The three keyword hits are all benign prose — e.g. line 2224 records
*"OAuth client id/secret left BLANK (server advertises PRM)"*, which is a config observation, and
lines 2538/2562 discuss bearer-token *semantics* without containing one.

**But it contains a live third-party account identifier.** Line 2639, captured off a real OAuth
consent screen during a live write-gate test:

```
  3. [Connect] -> new tab -> accounts.google.com "Choose an account to continue
     to WorkOS" (simkalholdingsllc@gmail.com)
```

This is a Google account email, distinct from the repo owner's, transcribed verbatim from a rendered
consent dialog. It appears **nowhere in `origin/main`** (`git grep -il` on the tracked tree returns
nothing). Also present: 3 live universe ULIDs and 9 run ids — lower sensitivity, but they are
production identifiers for a live service.

The repo is public-draft by default (`AGENTS.md` Hard Rule 12). **Conclusion: this file must not be
committed as-is.** That is not a stylistic objection; it is the deciding constraint, and it rules out
the most obvious fix on its own.

This is also a *predictable* property, not an accident of this one file. A ui-test transcript is a
verbatim capture of a real browser session against a live authenticated service. Capturing account
identifiers is what it is *for*. Any design that commits raw ui-test transcripts wholesale will keep
re-acquiring this problem.

## 4. Recommendation

**Keep `output/` gitignored. Add a tracked `docs/proofs/ui-test/` holding one dated, curated file per
accepted proof.**

- `output/user_sim_session.md` stays exactly as it is: a host-local, rolling, append-only working
  transcript, and the raw capture surface `ui-test` writes to during a mission. Nothing about the
  running of a mission changes.
- At the moment a ui-test **discharges an acceptance gate**, the tester writes one file:
  `docs/proofs/ui-test/<YYYY-MM-DD>-<slug>.md`. It carries date, environment (which chatbot, which
  connector URL), **the build sha under test**, the prompts typed, the rendered-result summary, the
  verdict, and a screenshot/trace path. It is redacted by construction — a template field for
  "account used" says *role* ("a fresh non-founder Google account"), never the address.
- The proof file is referenced from the STATUS concern or PR it discharges, so the claim and its
  evidence are linked in both directions.

Why this shape:

1. **It mirrors a convention already proven in this repo.** `docs/audits/` holds 89 tracked
   dated files under exactly this naming pattern, written by many lanes, and has never been a
   coordination problem.
2. **It mirrors the repo's most recent decision about append-only agent logs.** PR #1523
   (`.agents/activity.d/`) replaced a single shared append-only log with one file per lane, for the
   same structural reason: lanes appending to one file collide *by construction*, and the collision
   rate scales with lane count.
3. **It makes the freshness stamp mechanically possible.** A dated file with an environment and a sha
   is what §"Truth And Freshness" is asking for. A rolling transcript is not.
4. **It composes with PR #1504** rather than competing — see §6.

## 5. Options weighed and rejected

**(a) Commit the log — `git add -f`, or un-ignore it with a `!output/user_sim_session.md` negation
while `output/` stays ignored.** This is the reflexive fix and it is wrong on three independent
grounds, any one of which is disqualifying:

- *Secrets.* It carries the OAuth-captured account email from §3. Blocking.
- *Merge topology.* 2,861 lines, append-only, many lanes. Every lane appends to the same final hunk,
  so two lanes conflict structurally, not semantically. This repo established that empirically **this
  week**: PR #1523 documents `.agents/activity.log` conflicting in PR #1506 and PR #1507
  simultaneously, one rebase surviving six minutes before re-breaking. Note the trap here — the
  obvious mitigation, `merge=union` in `.gitattributes`, **does not work on GitHub**: git reads
  `.gitattributes` from the working tree, and a bare server-side merge has none, so the union driver
  is never loaded. #1523 proved this with a bare-repo `git merge-tree` check before abandoning it.
  Anyone reaching for union-merge here would be re-deriving a dead end this repo already walked.
- *Granularity.* A reviewer needs "the proof for change X", not a 302 KB haystack. A gate whose
  evidence requires a full-text search of a rolling transcript is barely better than no evidence.

**(b) A tracked manifest/index that references untracked bulk.** Rejected: the bulk *is* the
evidence. An index pointing at a file nobody else has is the identical defect with an extra hop —
it converts an unreadable claim into a readable pointer to an unreadable claim.

**(c) Do nothing; treat the log as intentionally local.** Rejected: `AGENTS.md` cites it as the
place the gate is discharged, eleven tracked files cite it as an evidence base, and a live STATUS
concern rests on it. If it were genuinely intended as scratch, those citations are all wrong and
should be removed — which is a strictly larger change than adding a proofs directory.

## 6. Relationship to open lanes

**PR #1504** (`ui-test: merged is not deployed — verify the build under test`) — **distinct and
complementary. Verified, not assumed:** its diff touches only the two `ui-test/SKILL.md` mirrors, and
its two `user_sim_session` occurrences are unchanged *context* lines (leading space in the diff), not
additions. It does not relocate the log. #1504 governs **which build** a ui-test runs against; this
lane governs **where the proof is recorded**. They compose: the proof template here carries a
`build sha under test` field, which is precisely the fact #1504 exists to make testers establish.
Without a durable proof file, #1504's requirement is verified and then immediately forgotten.

**PR #1523** (`.agents/activity.d/`) — prior art, and the source of the union-merge dead end
documented in §5(a). Adopted, not duplicated: this lane applies the same one-file-per-unit shape to a
different surface and does not touch `.agents/`.

**PR #1517** (`.gitignore`) — owns `.gitignore`. Its diff does not touch `output/`; it adds an
agent-scratch section. The recommendation here needs **no** `.gitignore` change (see §7), so the two
lanes do not interact.

**PR #1512** (`AGENTS.md`) and **PR #1507** (`STATUS.md`, `CONFLICTING/DIRTY`) own the other two
contended files. Proposed text for both is routed through this lane's PR body.

## 7. What the implied edits are

Only one is a code change, and it is not in a contended file:

- **New:** `docs/proofs/ui-test/README.md` + `.gitkeep` — made in this lane's PR.
- **`AGENTS.md` §"Quality Gates"** — repoint the logging sentence. Proposed verbatim in the PR body,
  for #1512.
- **`.gitignore`** — **no change needed.** `docs/` is not ignored, so `docs/proofs/` is tracked
  automatically. Keeping `output/` fully ignored is the recommendation, not an obstacle to it. This
  is a deliberate property of choosing shape (a) over a negation rule: it keeps this lane out of
  #1517's file entirely.
- **`STATUS.md`** — a concern recording that pre-2026-07-22 ui-test verdicts have no retrievable
  proof. Proposed verbatim in the PR body, for #1507.
- **`ui-test` SKILL.md (both mirrors)** — the "durable transcript" line needs correcting, but both
  mirrors are in **PR #1504's** write-set. Routed to that lane rather than edited here.

## 8. Residual / not addressed

- **Retroactive proof is not recoverable.** Every ui-test verdict before this convention lands —
  including the 2026-07-14 anonymous-write-gate watch item — has no durable evidence and cannot
  acquire any after the fact. The honest remedy is to re-verify, not to back-fill a proof file from a
  local transcript. The proposed STATUS concern says so explicitly.
- **Redaction-at-write-time means the committed proof is a curated attestation, not a raw capture.**
  That is a real weakening, and it is the deliberate trade for not publishing PII. It is mitigated,
  not eliminated, by requiring the build sha, environment, and a screenshot/trace path — a reader can
  check the sha and re-run the mission, which is a stronger check than reading someone else's
  transcript anyway. The raw capture still exists locally for the tester's own session.
- **No helper script.** PR #1523 shipped `scripts/activity_append.py` alongside its directory. The
  equivalent here (`scripts/ui_test_proof.py` scaffolding a template from the canary's reported sha)
  is a reasonable follow-up but is deliberately out of this lane's scope, which is the finding and
  the shape.
