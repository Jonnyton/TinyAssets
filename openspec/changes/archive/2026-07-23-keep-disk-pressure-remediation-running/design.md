## Context

The disk-watch oneshot declares three `ExecStart` commands in the required
alert, rotation, and auto-prune order. systemd stops a sequential oneshot after
an unaccepted non-zero result, while `disk_watch.py` deliberately uses status 1
to signal that pressure was detected. The current unit therefore lets the alert
signal prevent its own remediation.

## Goals / Non-Goals

**Goals:**

- Keep status 1 visible as an intentional, documented result while allowing
  systemd to continue the ordered oneshot.
- Continue failing the unit for unexpected statuses outside the accepted set.
- Prove both accepted status and command order in the repository sentinel test.

**Non-Goals:**

- Changing `disk_watch.py` return values or issue behavior.
- Changing rotation, auto-prune, timer cadence, or cleanup scope.
- Installing, enabling, or verifying the unit on a live host.

## Decisions

Add `SuccessExitStatus=1` to the oneshot service. This is systemd's native
declaration that status 1 is successful for the unit, so no shell wrapper,
ignore-failure prefix, or script-level semantic change is needed. The three
plain `ExecStart` entries remain in their current order.

The focused test parses the service's non-comment directives and asserts that
the accepted status exists and the three `ExecStart` values appear in exact
order. This avoids a false-green substring check that would pass if comments
claimed an ordering the unit did not declare.

Alternatives rejected:

- Prefixing only the alert command with `-` would also ignore unexpected alert
  failures, not just its intentional status 1.
- Making `disk_watch.py` return 0 under pressure would erase its established
  command-line signal.
- Wrapping the chain in a shell command would add quoting and error-propagation
  complexity without improving the unit contract.

## Risks / Trade-offs

- `SuccessExitStatus` applies to every process in the service, so a later
  command returning 1 is also accepted. This is narrower than ignoring all
  failures; statuses other than 0 or 1 still fail the unit.
- Repository validation cannot prove a host has installed or enabled the
  updated unit. The spec and handoff retain that distinction explicitly.

## Migration Plan

Land the repository unit and regression test together. Host installation and
activation remain a separate operational action. Rollback removes
`SuccessExitStatus=1`, restoring the known stop-on-alert behavior without data
migration.

## Open Questions

None.
