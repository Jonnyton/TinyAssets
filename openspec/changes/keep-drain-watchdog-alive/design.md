## Context

The tray is the user-visible observer, the Python watchdog owns supervisor attachment/recovery, and a current-user scheduled task owns session startup. On Windows, the tray's periodic read can transiently prevent `os.replace` from replacing `health.json`; after the watchdog's one-second retry budget was exhausted, that observational write exception terminated the watchdog while the supervisor continued. The tray then correctly showed stale health as down but had no recovery action. A separate tray exit also ends the only scheduled-task action until the next sign-in.

## Goals / Non-Goals

**Goals:**

- Keep health-publication contention from terminating the watchdog.
- Relaunch a missing watchdog from the still-live tray without launching a second supervisor.
- Relaunch a missing tray during the current interactive session.
- Preserve truthful running/waiting/down state and existing single-instance locks.

**Non-Goals:**

- Report idle or stale state as green.
- Activate cloud execution or market compute.
- Remove the finite supervisor budgets or provider subscription limits.
- Run the subscription-bound drain as SYSTEM or before interactive sign-in.

## Decisions

1. **Treat health publication as a fallible observation boundary.** The atomic writer retains bounded replace retries, but the main loop catches publication `OSError`, records a bounded diagnostic, and continues. The last complete health document remains readable and becomes stale/down until a later publication succeeds. This is safer than a non-atomic in-place fallback, which could make partial JSON appear current.

2. **Use the tray timer as the inner recovery hook.** When health is missing or stale, the tray attempts to start the watchdog no more than once per recovery cooldown. A present `stop.request` suppresses recovery so “stop until next sign-in” remains authoritative. The watchdog lock and supervisor lock remain the authority for single-instance behavior. Tracking a cooldown avoids a five-second process-launch hot loop.

3. **Separate sign-in startup from the repeating outer guard.** The primary current-user task runs only at logon and may clear a previous session stop by starting the watchdog. A second hidden current-user guard task repeats every minute and launches the tray with `-PreserveStop`; the tray mutex makes healthy invocations no-ops, while a dead tray is recreated without clearing `stop.request`. This distinguishes a new sign-in from a same-session repair without depending on unstable Windows session identifiers.

4. **Keep color semantics truthful.** A live working supervisor is running/green, idle or recovering is waiting/yellow, and stale health remains down/red while recovery is attempted. The hooks repair state; they do not rewrite state labels.

5. **Version and prove activation.** Health includes `watchdog_version=2`. A live reinstall stops only exact-path tray/watchdog observer processes, never the supervisor; registers both task definitions; starts the sign-in task; then requires fresh version-2 health and exactly one tray, watchdog, and supervisor before returning success.

## Risks / Trade-offs

- **[Persistent file lock keeps health stale]** → the watchdog continues and retries on each poll; the tray remains red and bounded relaunch attempts provide diagnostics instead of false green.
- **[Two relaunch paths race]** → named tray mutex, watchdog `RunLock`, supervisor run lock, and task-level `MultipleInstances IgnoreNew` make all launches idempotent.
- **[Periodic guard invokes while healthy]** → the attempted tray immediately exits on the named mutex; the one-minute bridge is retired after cloud host-off acceptance.
- **[Intentional tray exit is later reversed]** → the menu remains explicit that the drain continues; during the temporary local-until-cloud period, observability automatically returns.

## Migration Plan

1. Restack the reviewed change onto current `origin/main` and update the dedicated clean controller checkout to that exact head.
2. Install the two updated scheduled tasks; the installer recycles only the old observer processes and verifies fresh version-2 health with single process cardinality.
3. Verify hidden actions, current-user principals, and next-minute guard scheduling.
4. Fault-inject watchdog termination and prove fresh health returns without restarting the supervisor.
5. Fault-inject tray termination and prove the guard task recreates it without a visible console.
6. Roll back by reinstalling the previous task definitions; the supervisor itself remains unaffected.

## Open Questions

None for this bounded local bridge. The local integration is retired only after the cloud drain passes its host-off 24-hour acceptance.
