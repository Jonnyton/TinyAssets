# Next resource boundary: independent design review, not implementation

September 9 UTC, review against the d22c1105-era tree. Command:
`python scripts/peer_agent.py claude --out output/resource-boundary-next-review.md --prompt-file output/resource-boundary-next-brief.md --timeout 480`.
Completed exit 0 in 298 seconds. The wrapper final is only a stop-hook
acknowledgment; the substantive assistant-text review is in Claude session
`b49f6c0d-7c59-4197-859a-74f096ca943e`, read after terminal completion.
This record summarizes its **VERDICT: ADAPT**, not an implementation approval.

## Independent findings

- The current `provider_admission.py` counter is per-process. Persistent engine
  children launch providers through their own imported module counters, while
  daemon status reads its own counter. Six per process is not six for the shared
  capacity domain. Reverify exact live process count rather than assert it from
  a compose comment.
- Reviewer recommends stable kernel-held slot files beneath canonical data_dir,
  replacing rather than supplementing the existing counter; never unlink slot
  files. Preserve nested-call headroom, cancellation and configured total.
- Reviewer proposes passing held descriptors through provider launches so a
  parent exit does not immediately release live descendant occupancy on POSIX.
  It identifies current plain Claude process termination and existing graph/
  workspace descriptor inheritance as source to inspect.
- Required proof includes cross-process capacity, holder death/descendant life,
  limit lowering, no cleanup unlinking slot files, and shared status readback.
  No new ledger, provider authority or PLAN change is recommended.

## Main-agent disposition before any build

Accept the shared-dependency localization, not every proposed mechanism without
proof. The following are review questions to resolve against source and Linux
tests, not already reproduced defects or license to weaken desktop support:

1. A child can close inherited descriptors or spawn with close_fds; inheritance
   into the first CLI is not proof of occupancy through arbitrary descendants.
   Explicit unlock would also defeat a surviving shared open-description lock.
2. Simply restricting acquisition to low slot indices after a limit decrease
   may admit more low-slot work while high-slot holders drain. Compare the
   exact existing drain contract, not just whether new high indices are used.
3. Per-host desktop engine children and differing data roots need verification;
   do not accept the review's Windows single-process premise without evidence.
4. Existing bubblewrap coverage is conditional. Verify all provider launch paths,
   generic provider compatibility and descendant cleanup before generalizing.

No runtime code, storage schema, capacity number, provider authority or PLAN
was changed for this design review. The five newly authorized app capability
gaps also require implementation; none is closed by this design note.

## Reproduced process-local occupancy: September 9, 2026 07:03 UTC

Windows, Python 3.14, unchanged runtime at c5266c50. Command:
`python output/probe-provider-cross-process-capacity.py` (local diagnostic).
Two independent Python processes each entered the real provider_slot context
with TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS=1 and stayed inside until the
parent released them through stdin. Both reported limit1/live1/admitted1 while
the parent observed two simultaneous holders. Both probe children exited.
No provider CLI, production work, workflow, credential or external request was
launched. This converts the process-local counter premise from source inference
to an executable local reproduction; it does not establish live host topology,
descendant containment, a replacement design, or shared-capacity enforcement.

## Execution-lifetime follow-up: September 9, 2026 07:38 UTC

The main agent reproduced early release with the actual Claude adapter's
cancellation cleanup, a synthetic Python CLI, and the actual admission context
on Windows/Python 3.14. Command: `python -m
output.probe-provider-descendant-lifetime` (local diagnostic, no real provider).
The slot moved from live=1 to live=0 on cancellation while the fixture descendant
still answered a private loopback ping. Diagnostic cleanup then observed that
descendant exit. Full scope and unsuccessful fixture-initialization attempts are
recorded in `docs/concerns/2026-08-31-cancel-is-advisory-and-the-timeout-is-doing-its-job.md`.

This changes the next implementation decision: replacing `_live` with kernel
locks alone cannot satisfy the stated physical-lifetime contract. Do not ship
that as shared physical capacity or remove another guard on its strength.
The independent lifecycle follow-up is investigating the smallest reusable
execution owner; its pending output is not an approval.

Additional source mapping (same unchanged runtime; not live topology evidence):

- `storage.data_dir` resolves a platform default independent of CWD when the
  environment variable is absent. A proposed slot namespace must call it rather
  than implement its own fallback.
- `engine_mcp_http._EngineServer.start` copies the parent environment and sets
  the selected data root explicitly. Its child therefore inherits the configured
  provider limits today; its module-local counter is nevertheless independent.
- Claude's stdio engine configuration forwards an explicitly set data-root env;
  its route-file lookup and Codex's route-file lookup still use `.` when the env
  is absent. That route lookup is not evidence of a canonical shared root and
  must not be copied into the capacity resolver.
- Three router admission contexts wrap `provider.complete` without checking the
  provider class. These contexts also cover HTTP/local-server calls; a process
  count description is not sufficient for every registered execution class.
- `singleton_lock.release_singleton_lock` unlinks its lock path. Do not reuse
  that release helper for stable slot identities: release/reacquisition must not
  create multiple inodes representing the same slot.

PLAN.md was freshly read in full before this next-boundary design work. No PLAN,
quota, schema, provider authority or production state has changed here.

### Independent lifecycle follow-up and disposition

Command: `python scripts/peer_agent.py claude --out
output/provider-capacity-lifecycle-review.md --prompt-file
output/provider-capacity-lifecycle-brief.md --timeout 420`. Completed exit 0 in
284 seconds on September 9, 2026. The wrapper's final text was a stop-hook
acknowledgment; the substantive review was recovered from the same session,
`a7185f56-4f27-4f0a-bed8-00bda6e1a2c2`. No second dispatch or implementation
was performed. Unrelated dispatch summaries in the stop-hook output are not
evidence for this lane.

The reviewer returned **ADAPT**. It agreed that the current direct-process
cleanup does not own every descendant, identified the three class-neutral router
admission contexts and the persistent engine child's independent counter, and
recommended count-based kernel slots under an admission mutex. Counting occupied
slots across all existing indices, rather than restricting admission to low
indices, preserves drain-after-limit-lowering behavior. Shared occupancy and
process-local duration/admission samples must be labelled separately.

The main agent accepts that exclusion/drain design, but **does not accept the
recommended release scope as implementation approval**:

- The reviewer explicitly limits descriptor-handoff coverage to descendants that
  retain the descriptor, not the whole execution tree. Its assertion about typical
  Node/Rust inheritance is not a proof for arbitrary connected CLIs.
- The suggested Windows parent-death xfail and documented desktop gap do not meet
  this goal. Do not quarantine the missing behavior or ask the owner to accept a
  weaker platform merely to ship the counter replacement.
- Existing Codex bubblewrap arguments are conditional on the sandbox configuration
  and capability check, not proof that every detected/registered CLI runs inside
  them. Source arguments alone are not a parent-death/reap ordering proof.
- The proposed exclusion of HTTP providers from a CLI-sized bound needs a real
  connection/dispatch boundary before it replaces a guard. A provider-name or
  class-name exception is not the native-unit policy requested by the owner.

The next implementation contract is recorded in the parent change's
`shared-provider-capacity-design.md`. This review is the second design round;
do not restart an unlimited review loop or call it APPROVE.
