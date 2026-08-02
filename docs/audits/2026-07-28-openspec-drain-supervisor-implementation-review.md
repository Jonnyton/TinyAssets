Review complete. All verification steps were run in this worktree on 2026-07-28: focused tests 36/36 pass, `ruff check` clean, `openspec validate add-openspec-drain-supervisor --strict` valid, skill mirrors byte-identical, `check_cross_provider_drift.py` clean, and a live `--dry-run` into a temp dir outside the repo produced correct state/prompt artifacts with exit 0.

# Exact-diff review: add-openspec-drain-supervisor (base `origin/main@6e09027c`)

## Checklist verification

1. **Marker parsing — verified strict.** `parse_result` (`scripts/openspec_drain_supervisor.py:42-65`) requires exactly one marker that is also the final non-empty line, rejects any `<`/`>`/`|` in the marker (kills template echoes and `MERGED|PARTIAL`), rejects `[peer_agent] ERROR` blocks, fullmatch-anchors status/target/PR, requires a real target + GitHub PR URL for MERGED/PARTIAL, and requires double dashes for NO_CANDIDATE. Tests cover all six reject shapes (`tests/test_openspec_drain_supervisor.py:52-68`).
2. **One run identity + own-claim resume — verified.** Identity `drain-<run-id>` is minted once (`:296-315`), preserved by `--resume` (which also enforces provider/model match, `:400-408`), and the brief mandates resume-first in *both* branches — explicit `resume_target` and the "search STATUS for an existing claim" fallback that covers the mid-slice-timeout case where the controller doesn't know the target (`:73-81`, `:101-102`).
3. **Controller-side merge proof — verified.** MERGED/PARTIAL call `verify_merged` (`gh pr view --json state,mergedAt`, PR-state not branch ancestry, `:124-145`); unverified reports become `merge-verification-failed` with a failure strike and never increment slices (`:160-164`), with tests (`:94-107`, `:137-171`).
4. **Loop-safety — mostly verified, one gap (M1 below).** Fatal 127 stops immediately; plain failures/invalid results redispatch but are capped at `--max-failures` by `budget_reason`; transient and BLOCKED/NO_CANDIDATE paths idle interruptibly, deadline-capped. No sub-second hot loop exists anywhere. The gap: repeated same-target PARTIAL.
5. **Lock/state/stop/resume — adequate for v1.** O_EXCL lock with explicit-only recovery, atomic temp+`os.replace` state writes, stop marker polled ≤5s during idle, lock released in `finally`, crash leaves an inspectable lock + resumable state. PID is recorded but not liveness-checked on recovery (L3).
6. **No injection/secret/deletion hazards found.** Everything is list-argv, no shell. The only worker-authored value reaching a command line is the PR URL, fullmatch-constrained (`https://github.com/…/pull/N` — can't start with `-`, no whitespace) before `gh pr view`. Targets fed back into prompts are regex-constrained tokens. Deletions are limited to the run's own lock/stop files. No secrets touched.
7. **CLI defaults and runbook — verified working.** Dry-run with defaults works; `output/` is gitignored (`.gitignore:71`) so state is untracked as the spec requires; the PowerShell runbook (worktree setup, `Start-Process` array args, status/stop) is syntactically sound and the argument names all exist.
8. **Sequential, peer_agent-reusing, not the fleet — verified.** Stdlib-only, one blocking `peer_agent.py` subprocess per attempt (`:325-362`, flags all match `peer_agent.py`'s surface), no concurrency primitive anywhere, `fleet_supervisor.py` untouched, mutual-exclusion warning documented.
9. **Tests are behavioral.** They exercise the parse contract, governance-brief content, verification gating, budget/exit-code semantics, lock exclusion, and an end-to-end `main()` dry-run — not helper echoes. Gap noted in L4.

All 14 delta-spec scenarios trace to implemented behavior; all seven findings from the prior Claude ADAPT review (F1–F7) are genuinely folded, not just claimed.

## Blockers

None.

## Adapt-level findings

**M1 — Repeated same-target `PARTIAL` redispatches with no wait and no budget, forever.** `scripts/openspec_drain_supervisor.py:512-513`: a verified PARTIAL resets `consecutive_failures` (`:170-173`) and `continue`s immediately; only BLOCKED/NO_CANDIDATE idle (`:514-519`). If foldback is persistently wedged (e.g. an archive validation error or STATUS conflict), every honest worker returns PARTIAL for the same target and the controller burns back-to-back worker runs until `--hours` expires — dozens of subscription dispatches with no terminal signal. This is exactly review point 4's PARTIAL case. **Fix (small):** in `_run`, remember the prior attempt's `(status, resume_target)`; on a repeated same-target PARTIAL, either `wait_interruptibly` the idle interval before redispatch, or count the Nth consecutive same-target PARTIAL (N=3ish) as a failure strike.

**M2 — Transient classification uses bare `auth` substring over provider stderr, in a codebase saturated with "authority".** `TRANSIENT_PATTERNS` at `:30` (`"auth"` also makes `"unauthorized"` redundant) is matched at `:198` against text that, for exit-2 failures, embeds up to 1500 chars of provider stderr (`peer_agent.py:301-302`) or, in the fallback, full stdout+stderr (`:451-455`). `peer_agent.py:50-53` documents this exact false-positive class and deliberately confines its own heuristic to stderr. A persistent genuine failure whose stderr mentions "authority"/"authorized" is classified transient every time: no strike is ever consumed (`:467-468`), so the failure budget never fires and the day is silently spent idling in 30-minute intervals. Bounded and visible in `state.json`, but it defeats `--max-failures` for a whole error family. **Fix:** tighten to word-ish patterns (`"unauthorized"`, `"rate limit"`, `"rate-limit"`, `"login"`, `"401"`; drop bare `"auth"`), and/or cap consecutive transients (e.g. the 4th in a row consumes a strike).

## Non-blocking findings

- **L3** — `RunLock.acquire` with `recover=True` unlinks unconditionally (`:269-270`); PID is persisted but never liveness-checked, and two simultaneous `--recover-stale-lock` invocations can both win. Runbook discipline mitigates; a `psutil`-free `pid` existence check would be a cheap hardening.
- **L4** — No test drives the real dispatch loop with a stubbed `_dispatch` (the `--once` result path, transient-idle path, and merge-verify integration inside `_run`, roughly `:445-519`, are covered only indirectly). One monkeypatched once-mode test would close it.
- **L5** — `--run-dir` default (`:534`) resolves against the launcher's cwd, not `--repo`; launching from elsewhere silently puts state outside the controller worktree. Runbook always passes it explicitly; consider defaulting relative to `--repo`.
- **L6** — On the outer `worker_timeout + 90` supervisor timeout (`:354`), `subprocess.run` kills only the `peer_agent.py` python; on Windows its CLI grandchild tree can be orphaned. Requires peer_agent's own kill path to have already failed, so rare; worth a runbook line at most.
- The prompt-echo trap cuts conservatively: a worker that succeeds but also quotes the template in a fenced block gets rejected as invalid (two markers). That's as-specced fail-closed behavior; the "Do not print any other DRAIN_RESULT line" instruction (`:120`) is the right mitigation.

The architecture is sound, the prior review's adaptations are all genuinely implemented, and safety claims match the verified host reality. M1 and M2 should be folded before the first unattended all-day run (both are small, localized changes with obvious tests); everything else can ride along or follow.

VERDICT: ADAPT

## Follow-up review (2026-07-28, Windows 11)

Claude re-reviewed the M1/M2 fixes and confirmed both were closed, along with
the dispatch integration test, repo-relative run directory, and timeout process
tree cleanup. Its follow-up verdict remained `ADAPT` for one blocker discovered
by an empirical detached-process probe:

- Windows `os.kill(pid, 0)` uses console-control semantics and can classify an
  unrelated live process as dead. In the documented `Start-Process` topology,
  `--recover-stale-lock` could therefore remove a live controller lock and
  start a second controller.

The review also recommended rejecting foreign/stale merged PRs, bounding
post-kill pipe collection, aligning status/stop default paths, and documenting
failure-budget resume behavior. All were accepted for the final adaptation.
The gate requires a Windows process-handle probe, a real detached-process
regression test, and a final re-review before approval.

## Final opposite-provider gate

`VERDICT: APPROVE` (Claude, 2026-07-28, Windows 11).

Claude independently reproduced the old detached-process failure, then verified
the replacement `OpenProcess` / `GetExitCodeProcess` probe reads the detached
live PID as alive, the terminated PID as dead, and access-denied PID 4 as alive
(fail closed). It also verified:

- foreign and pre-run merged PRs are rejected;
- repeated same-target `PARTIAL` and repeated provider transients are budgeted;
- timeout process-tree cleanup and post-kill collection are finite;
- run/status/stop defaults resolve under the selected repository;
- 46 focused tests, Ruff, strict OpenSpec validation, skill mirror equality,
  and cross-provider drift checks pass.

No blocker remains. The two-simultaneous-manual-recovery race is retained as a
documented low-probability residual; recovery is a host-only operation after
proving the recorded controller is dead, never part of the normal drain loop.
