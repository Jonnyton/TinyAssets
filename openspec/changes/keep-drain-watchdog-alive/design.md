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

2. **Use the tray timer as the inner recovery hook.** When health is missing or stale, the tray attempts to start the watchdog no more than once per recovery cooldown. The watchdog lock and supervisor lock remain the authority for single-instance behavior. Tracking a cooldown avoids a five-second process-launch hot loop.

3. **Use a repeating current-user task trigger as the outer recovery hook.** The existing action remains a hidden `wscript.exe` launcher and the task keeps `MultipleInstances IgnoreNew`. A daily trigger repeated every minute for one day supplements the logon trigger. While the tray host is alive the task remains running and repeats are ignored; after it exits, the next trigger can recreate it. Reinstalling remains idempotent.

4. **Keep color semantics truthful.** A live working supervisor is running/green, idle or recovering is waiting/yellow, and stale health remains down/red while recovery is attempted. The hooks repair state; they do not rewrite state labels.

## Risks / Trade-offs

- **[Persistent file lock keeps health stale]** → the watchdog continues and retries on each poll; the tray remains red and bounded relaunch attempts provide diagnostics instead of false green.
- **[Two relaunch paths race]** → named tray mutex, watchdog `RunLock`, supervisor run lock, and `MultipleInstances IgnoreNew` make all launches idempotent.
- **[Periodic trigger consumes Task Scheduler invocations]** → the long-lived task ignores repeats while healthy and uses a one-minute interval only for interactive-session recovery.
- **[Intentional tray exit is later reversed]** → the menu remains explicit that the drain continues; during the temporary local-until-cloud period, observability automatically returns.

## Migration Plan

1. Install the updated scheduled task from the dedicated reviewed worktree.
2. Verify two triggers, hidden action, and current-user principal.
3. Fault-inject watchdog termination and prove fresh health returns without restarting the supervisor.
4. Fault-inject tray termination and prove the scheduled task recreates it without a visible console.
5. Roll back by reinstalling the previous task definition; the supervisor itself remains unaffected.

## Open Questions

None for this bounded local bridge. The local integration is retired only after the cloud drain passes its host-off 24-hour acceptance.
