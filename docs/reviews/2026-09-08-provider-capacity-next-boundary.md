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
