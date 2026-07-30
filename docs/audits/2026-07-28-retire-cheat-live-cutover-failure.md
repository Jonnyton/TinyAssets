# Retire-cheat-loop live cutover failure

Date: 2026-07-28  
Environment: production (`https://tinyassets.io/mcp`)  
Workflow: `Deploy prod` run `30407316207`, attempt `1`  
Source: `0a8b092b06be730af9724d85ed33a643be5f4ea9`  
Terminal incident: GitHub issue `#1840`

## Outcome

The first task-2.1 stop-writer cutover failed closed. The controller ultimately
stopped all five controlled containers, set each restart policy to `no`, and
persisted `phase=unsafe_fenced`. The canonical MCP surface consequently
returned HTTP 502. The direct tunnel surface continued returning its expected
Cloudflare Access HTTP 403.

This is not task-2.1 completion evidence. It is outage and recovery-design
evidence.

## Proven recovery identity

The durable cleanup identity and fresh registry inspection bind the prior
post-stop-writer image to:

- tag: `35da9d4fc1a1`
- immutable image:
  `ghcr.io/jonnyton/tinyassets-daemon@sha256:a9526b71030edcec0b4b112bf4c22f8dcefedc891ab6064d48050545a551d687`
- embedded revision:
  `35da9d4fc1a1fc51d3db56bf5d1627691f54d894`
- source fence generation: `30407316207-1`

The later source commit `ce83a44f6ddee32dbbcd9796c7dc3e63e046c821`
did not produce a distinct image tag and is not a valid recovery dispatch
identity.

## Passed evidence before failure

- Immutable image:
  `ghcr.io/jonnyton/tinyassets-daemon@sha256:025187ccf7c459d7f99283cd1366a3a7abf2031105cbae591170f7e42af463e1`
- Embedded revision:
  `0a8b092b06be730af9724d85ed33a643be5f4ea9`
- Preflight writer, queue, stray-process, and receipt checks passed.
- Initial post-deploy proof observed exactly the daemon plus four workers on
  the immutable image and revision.
- Receipt snapshot stayed unchanged:
  logical digest
  `765f3164815beaaf8e24267136bf88e0591f6379c589f298184af6f37764ae47`,
  one retained `queued` receipt, latest attempt `2026-07-15`.
- Canonical MCP canary, exact-seven surface assertion, and direct-URL Access
  gate passed.

## Failure chain

1. The post-canary proof reported
   `exactly five safe target containers were not independently proved`.
   Its failure payload omitted the rejected fleet observation, so the exact
   mismatch is not reconstructable from the artifact.
2. Rollback canary passed on the prior stop-writer image/revision, but terminal
   identity remained unproved.
3. Restart-activator restoration immediately compared saved systemd states
   after starting the saved timers. Both static watchdog services were
   transiently `activating` rather than their saved `inactive` state.
4. Conservative cleanup invoked `quiesce-unsafe`. Its evidence proved:
   no named container running, no old container ID running, all five restart
   policies `no`, no masked unit residue, and `writers_fenced=true`.
5. The existing state machine had no authorized exit from `unsafe_fenced`;
   a new deployment preflight therefore could not recover the intentionally
   stopped service.

## Required recovery properties

Recovery must:

- run under the existing production mutation concurrency group and host lock;
- require the exact durable source-run provenance without overwriting it on
  repeated emergency fencing;
- admit only an immutable stop-writer image/revision already bound by the
  fence and verified against repository ancestry;
- re-prove stopped/restart-fenced writers, zero extra or stray volume writers,
  zero retired queue risk, and the unchanged receipt snapshot before start;
- start and prove exactly the daemon plus four workers;
- create those five containers with restart policy `no`, keep systemd boot
  activators fenced, and arm a bounded host-side expiry before starting them;
- persist a `recovery_pending_canary` phase, run both public canaries, and only
  then finalize the same source/recovery generation;
- restore every saved restart policy with an exact read-back proof before
  restoring systemd activators;
- re-fence an unaccepted generation on failure, cancellation, runner loss,
  lease expiry, or the next reconciliation after reboot;
- wait boundedly for exact fleet convergence and saved systemd terminal states,
  while retaining the final rejected observation on failure; and
- return to durable `unsafe_fenced` on any failed or indeterminate recovery.

Deleting/editing the fence state, directly force-starting the host, weakening
the exact-five check, accepting a transient systemd state as final, or
admitting a pre-stop-writer image are prohibited recovery shortcuts.

## Local evidence

The downloaded workflow artifact is retained locally under
`output/deploy-30407316207/`. It contains sanitized JSON evidence for preflight,
post-deploy, post-canary failure, rollback cleanup observation, fence status,
restoration failure, and final emergency fencing.
