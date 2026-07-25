# Distributed-Execution Platform — Resume Handoff Spec 2 (night wrap)

**Written:** 2026-07-20 ~00:00 PT (wrapped for the night by host directive).
**Driver on resume:** Kimi Code (kimi-k3), orchestrating Codex (gpt-5.6-sol) + Fable-5 peers via `scripts/peer_agent.py`.
**Prior specs:** `RESUME-SPEC.md` (same dir — read FIRST for the full slice program, gate protocol, guardrails). This doc is only the live-state delta.

---

## 1. TL;DR — where S2 stands tonight

- **S2 (fenced lease store) is in its FIFTH build round.** fix-2 @ `81750d31` → gate REJECT (forged replay receipts). fix-3 @ `01e843ee` → gate REJECT (status-trust + unfiltered ledger event). fix-4 @ `5a307576` → gate REJECT (terminal rows reopenable by doctoring status back to 'leased' + taxonomy F1/F2). **fix-5 was building at wrap time** — see §2.
- **FIX B (daemon claim outage) is DONE and independently verified** (Codex lane: 215p/11 pre-existing failures; Fable: no residuals; dormancy guard fail-closed). Not in the reject chain — it has been stable since fix-2.
- **Blocker: the Claude Max monthly spend limit was hit at ~23:20 PT 2026-07-19.** All Fable lanes park until the host raises it at `claude.ai/settings/usage`. **The dual-family gate REQUIRES Fable-5 — nothing can merge until then.** Codex lanes unaffected.
- Everything else is staged: the fix-5 combined brief is the complete continuation spec; the fix-5 gate briefs will be pre-drafted on the fix-5 commit landing.

**RESUME ACTIONS (in order):**
1. Host raises the Claude monthly limit (one click). Driver re-probes: `echo "say OK" | claude -p --model fable`.
2. Check `output/s2-gate/codex-fix5-build-result.md` — if the fix-5 build completed, review + verify (suites, mutation-RED, ruff), commit, push `HEAD:feat/patch-loop-leasestore`, and dispatch the Codex gate re-review on the new sha (brief template: `output/s2-gate/gate-brief-codex-fix4.md`, sha-substitute).
3. If the build was killed mid-flight: re-dispatch it — `python scripts/peer_agent.py codex --write --cwd ../wf-s2-fix2 --out output/s2-gate/codex-fix5-build-result.md --timeout 3600 --prompt-file output/s2-gate/fix5-build-brief-combined.md`. The worktree's uncommitted partial edits are REFERENCE only (per RESUME-SPEC §5.4 discipline).
4. On Codex approve → Fable-5 gate (`gate-brief-fable-fix3.md` template, re-based) → on approve, merge the two S2 commits into `feat/patch-loop-runner`, push, delete the STATUS row.
5. Recreate the fleet cron if wanted (was deleted at wrap: `*/12 * * * *`, prompt pattern in §6).

## 2. The fix-5 combined brief (the continuation spec)

`C:/Users/Jonathan/Projects/TinyAssets/output/s2-gate/fix5-build-brief-combined.md` — Fable-drafted base + 4 driver addenda:

- **Base (Fable):** taxonomy F1-F3 (submit-path corrupt-hash → 500; precheck masking; stale-lease→API StaleLeaseError), test-quality pins F1-F6, partial UNIQUE indexes.
- **Addendum 1 (gate HIGH):** write-time event-count enforcement — the reopen hole. **Per brief-attack F1: `completed` is TASK-scoped** (terminal absorbing; per-generation scoping is launderable through `claim()`'s reclaim path).
- **Addendum 2 (attacks F1):** ledger-anchored result hash — `content_sha256` on `result_submitted` events; completion compares column vs anchor (the at-rest candidate-swap hole). + outcome enum guard.
- **Addendum 3 (brief-attack F2-F10):** precheck NULL+terminal → corruption; len==0+terminal → corruption; :417 shadowed DiD (dual-site mutation); placement rules (fence-first, before-expiry, before-blob-marks); anchor threat boundary (schema-intact only).
- **Addendum 4 (sqlite research):** migration in ONE `BEGIN IMMEDIATE` transaction with individual `execute()` calls (never `executescript()` — it commits first); `PRAGMA user_version=1`; index validation not IF-EXISTS trust; rollback-before-error-mapping; legacy unanchored events fail typed at init.

The brief's evidence files it cites (all in `output/s2-gate/`): `gate-verdict-codex-fix4.md`, `fable-fix4-brief-attack.md`, `fable-fix4-attacks3.md`, `fable-fix4-taxonomy.md`, `fable-fix4-test-quality.md`, `output/research/sqlite-schema-evolution.md`.

## 3. Artifact map (what's where)

- **Canonical live report:** `output/s2-gate/s2-fix2-report.md` — the review-cycle log with EVERY lane verdict + the §5.3 checklist. Start there.
- **Gate briefs (templates, sha-substitute and go):** `gate-brief-codex-fix4.md`, `gate-brief-fable-fix3.md` (needs re-base), `gate-brief-codex-81750d31.md` (example of a filled one).
- **S4 package:** `s4-lookahead.md` (with driver dispositions on the 6 OPENs), `s4-build-brief.md`, `fable-s4-heartbeat-schema.md` + `-v2.md` (schema-ready), cancellation research confirms v2.
- **S5+ pipeline:** `s6-lookahead.md`, `s7-broker-subspec-draft.md` + `s7-subspec-reconciled.md` (subspec-gaps: 6 named OPENs), `s8-lookahead.md` + `codex-s8-check.md` (errors — needs amendment), `s9-lookahead.md`.
- **Research index:** `output/research/INDEX.md` — every research artifact, verdict, and fold-back point. B3 external-market bridge: `compute-market-interop.md` (federated supply, BYOK, OpenRouter-first) + `market-liquidity-pricing.md` (+ `2026-07-19-b3-liquidity-price-honesty.md`). Host direction recorded in `ideas/INBOX.md` (2026-07-20 entry).
- **Worktree:** `C:/Users/Jonathan/Projects/wf-s2-fix2` (branch `feat/patch-loop-leasestore-fix2`, `_PURPOSE.md` present). Push target: `origin/feat/patch-loop-leasestore` (fast-forward only). Merge target: `feat/patch-loop-runner` (PR #1472).

## 4. Peer-dispatch rules that made this work (keep them)

- `python scripts/peer_agent.py <claude|codex> [--write] --cwd ../wf-s2-fix2 --out <file> --timeout N --prompt-file <brief>`; run backgrounded; the `--out` file is the contract (success = final message; failure = `[peer_agent] ERROR` block + non-zero exit).
- **Anti-deferral clause is mandatory for claude** (it loves dispatching its own sub-reviews and ending with "I'll report when it returns"): "do NOT dispatch sub-reviews; deliver findings NOW."
- **Read-only lanes: tell them to write NO files** (one peer's deliverable was overwritten by the wrapper because it wrote to the --out path itself).
- Claude defaults to `--model fable` (frontier alias); codex inherits `~/.codex/config.toml` model (gpt-5.6-sol). Kimi = driver/third-family only, never self-approves (gate protocol unchanged).
- **Design-gate every build brief with the opposite family BEFORE the build** — three stop/amend cycles tonight each caught a build-shaping defect pre-build (HIGH-2 filter, reopen laundering, executescript migration). Cheaper than a gate reject.
- Long prompts go via `--prompt-file`, not inline (shell quoting + Windows limits).

## 5. State at wrap (process dispositions)

- **fix-5 build (bash-8w2crcka):** STOPPED for the night at ~00:00 PT mid-build (worktree had ~1182 insertions across the 4 fix-5 files — uncommitted, reference only). Resume per §1 step 2/3.
- **Fleet cron:** deleted at wrap (was `a090dfc9`, every 12 min, codex-only lanes). Recreate on resume if continuous fleet is wanted.
- **Goal (goal mode):** active — drive the build through S11 (first B2 live test). Near-term milestone unchanged: S2 merged into `feat/patch-loop-runner` with both-family verdicts.

## 6. Open items parked (do not act without their own process)

- **Claude cap** — host action at `claude.ai/settings/usage` (the only thing standing between fix-5 and a completed dual-family gate).
- **S4 build** starts after S2 merges (brief + schema + dispositions all staged).
- **S7** needs its 6 OPENs resolved before the dual-family implementation gate.
- **S8** lookahead needs an amendment round (codex-s8-check verdict: errors).
- **B3 external-market bridge** — research banked; design phase is S13-16; §6.7/S6/invariant-15 text amendments required before S6 build (sandbox review adapt item).

*End of wrap spec. Start at `output/s2-gate/s2-fix2-report.md`'s review-cycle log, then §1 above.*
