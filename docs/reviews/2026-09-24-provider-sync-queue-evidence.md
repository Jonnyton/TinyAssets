# Provider-sync queue deadline — finalize evidence

Bounded finalize pass over source that was already complete at hand-off. No
rebuild, no redesign, no runtime edit. Root is the independent reviewer and owns
release; **nothing is committed or pushed**.

Worktree `wf-provider-sync-queue-proof`, branch `codex/provider-sync-queue-proof`,
base `ff1320d5cfda9f31e8ec7226fe006e48a7b8be70`.

## Environment

| | |
|---|---|
| Date of this run | 2026-09-23 (PDT) |
| Host | Windows 11 Home 10.0.26200 |
| Python | 3.14.3, `C:/Python314/python` |
| pytest basetemp | `C:/Users/Jonathan/AppData/Local/Temp/ta-finq` — fresh, outside the repo, not `ta-pt`/`ta-pt2` |
| ruff | 0.15.8 |
| Not used | no subagent, no `peer_agent`/`claude`/`codex` subprocess, no new worktree, no full suite, no production/browser, no Docker/WSL/services, no private workflow |

## Commands run in THIS pass (rerun, first-hand)

```
python -m pytest tests/test_provider_sync_queue_deadline.py -q \
  --basetemp=C:/Users/Jonathan/AppData/Local/Temp/ta-finq -p no:randomly
```
→ **6 passed in 4.89s**, exit 0. **0 skipped, 0 xfailed, 0 warnings-as-errors.**
The focused file skips nothing, so `skip_census` has nothing to report for it.

```
python -m ruff check tinyassets/providers/router.py \
  tests/test_provider_sync_queue_deadline.py
```
→ **All checks passed**, exit 0.

Mirror parity — **inspect only, nothing written**: the canonical
`tinyassets/providers/router.py` and the plugin mirror
`packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/providers/router.py`
are byte-identical. `build_plugin.py` was **not** re-run in this pass, so no
unrelated staged file was touched or overwritten.

The six tests, all green here:

1. `test_expired_node_work_does_not_launch_from_the_provider_sync_queue`
2. `test_partial_provider_sync_queue_wait_is_deducted_before_launch`
3. `test_call_already_past_the_pool_worker_entry_settles_untouched`
4. `test_expired_work_does_not_launch_from_call_with_policy_sync_either`
5. `test_an_unqueued_call_keeps_the_callers_own_config`
6. `test_a_caller_without_a_deadline_is_never_refused`

## Evidence carried over — PEER-REPORTED, not rerun here

The following are from the hand-off report `output/sync-queue-fix-result.md` and
were **not** re-executed in this pass (the RED control needs the fix reverted,
which is a runtime edit this pass is not authorized to make; the affected-suite
run exceeds the time budget). They are reported as the peer's evidence, not as
this pass's measurement:

| Run | Command | Peer-reported result |
|---|---|---|
| **RED control** (base router restored, new tests unchanged) | `pytest tests/test_provider_sync_queue_deadline.py -q` | **3 failed, 3 passed** in 5.10s |
| **Fixed** | same | **6 passed** in 4.87s — *independently reproduced here as 6 passed in 4.89s* |
| **Affected suites** | `pytest tests/test_node_timeout.py tests/test_node_timeout_queue_cancellation.py tests/test_provider_stream_and_classify.py tests/test_provider_router_bug029.py tests/test_provider_router_diagnostics.py tests/test_provider_served_router.py tests/test_provider_auth_router_quarantine.py tests/test_provider_sync_queue_deadline.py -q` | **228 passed, 4 skipped** in 32.41s — **4 skips uncharacterized here**, since the run was not repeated |
| **Plugin mirror build** | `python packaging/claude-plugin/build_plugin.py` | Staged 500 files, `Import probe: probe-ok` |

Only the two "rerun, first-hand" commands above are this pass's own evidence.
The 6-green result is the one line that is both peer-reported and independently
reproduced.

## What the change actually claims

- The caller's **explicit** cap (`ModelConfig.absolute_cap_s`) is anchored at
  **submit** into the second (provider-sync) queue, so the wait there is
  measured before the call rather than re-granted at worker pickup. The legacy
  integer `timeout` scalar is never read as a deadline.
- A call whose explicit budget has already elapsed on reaching the worker is
  **refused before any provider is launched** — no expired queued launch. Both
  `call_sync` and `call_with_policy_sync`.
- A partial wait is **subtracted** from the cap handed over, on a new frozen
  config; a deduction can never buy a call more time than it arrived with. A
  wait under the jitter threshold hands the caller's own config through
  untouched.
- A caller with **no** explicit cap is never refused; the 600s default backstop
  is not a deadline.

## What it does NOT claim

- **The new queue guard does not forcibly cancel started work.** The refusal
  sits ahead of `self.call`. Existing reader watchdogs and wrapper cancellation
  still apply; general completion exactly once is not guaranteed. The blocking
  test proves one completion/no replay only in its controlled scenario. No
  async cancellation path is exercised by these six tests.
- **No production incident cause is established.** This is a real defect in the
  second queue, proven by a RED-at-base control (peer-reported). Nothing here
  attributes any observed production latency or outage to it.
- No public surface, schema field, storage shape, authority change, migration,
  or raised timeout/pool/concurrency limit — which is why the as-built spec
  paragraph was written after the fact rather than as a new OpenSpec proposal.

## Spec

`openspec/specs/provider-routing/spec.md` gains one as-built requirement,
"A queued synchronous provider call is measured from submit, not from pickup",
with four scenarios matching the four claims above. Prepared alongside the
candidate; this is not a claim it has shipped. Deployment/live acceptance remain
pending. Root corrected the overbroad started-work completion claim before commit.

## Independent root verification

2026-09-24 UTC, Codex root independently reviewed both wrapper entry checks,
frozen-config replacement, monotonic submit anchor, unchanged reader-drain
margin and all six focused tests. Root ran `python -m pytest -q
tests/test_provider_sync_queue_deadline.py tests/test_node_timeout_queue_cancellation.py
tests/test_node_timeout.py -p no:randomly` with fresh outside-repo basetemp:
34passed0skipped in11.71s on Windows/Python3.14.3. Runtime SHA256b8d2de892385cbb82c0266658df3b4c6676afeffbec09b262de6cc95db16e29d;
test SHA256a9191720c7ee56fd66916c1f4e2cf44eb92a90b1ecc408ca5e1eba38ecab6cad.
Cloud-only Linux candidate submitted35952194290, base099fe185 and patch SHA256
93aa7c28aa8418bda42a6faa26f458656a00871f9512360a8b24ef58a4290983;
not yet a passing result. Source review AGREE; no new basic-safety blocker.
Final exact-head approval and required CI still precede release.
