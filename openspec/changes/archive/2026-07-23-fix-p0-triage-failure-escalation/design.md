## Context

The issue-scoped P0 workflow classifies a live outage, executes one bounded
repair, and then decides recovery from the canonical MCP re-probe. Today a
repair shell failure terminates the job before that decision. The
provider-exhaustion page also calls `pushover_page.py` with an invented
title/message/priority interface instead of its issue/run/probe CLI contract.

## Goals / Non-Goals

**Goals:**

- Keep every bounded class response observable while guaranteeing canonical
  re-probe runs after a response failure.
- Use the existing Pushover CLI and preserve paging whether the optional worker
  pause gate is on or off.
- Make persistent red both `needs-human` and a failed workflow run.
- Make a provider-exhaustion paging failure visible without allowing it to
  suppress canonical re-probe or persistent-red escalation.
- Prove the exact uptime alarm-sink behavior under GitHub's bounded queued-run
  model, including paging decisions against shared incident comments.

**Non-Goals:**

- Change Pushover's implementation or flags, repair semantics, secrets, or
  the existing issue-scoped concurrency group.
- Add cross-issue host locking, retry loops, or a general workflow simulator.

## Decisions

### Continue only the bounded repair/restart steps

Class-specific repair and generic restart steps use GitHub Actions
`continue-on-error: true`; their non-zero outcome remains visible in the
summary, then re-probe runs. The post-probe GitHub-script steps remain the
authority: green closes from actual probe truth; red labels `needs-human` and
sets a non-zero process exit.

Alternative: use `if: always()` on re-probe alone. Rejected because an earlier
failed repair would still leave intermediate workflow state less explicit and
can complicate the post-repair intent; continuation preserves a straight-line,
auditable failure path.

### Adapt the workflow to the existing paging contract

The provider-exhaustion step supplies issue number, run URL, canonical probe
URL, exit code, kind, and `--first-alarm`/`--dry-run` only where the existing
CLI defines them. It does not invent presentation flags. Paging remains outside
the auto-repair gate so warn-only provider exhaustion still reaches the host.
The page step uses `continue-on-error: true` rather than swallowing a non-zero
exit, preserving the visible failed-step outcome while allowing the later
canonical re-probe to remain the recovery authority.

### §14 proof assessment

The §14 platform requirement applies to this uptime control path: a false
incident or duplicate emergency page under overlapping canary runs is an outage
of the alarm surface. The proof executes the extracted `alarm-sink` GitHub
script in Node while a shared in-memory GitHub REST model carries labels,
issues, comments, and prior-run conclusions between invocations. A small
scheduler models GitHub Actions' documented concurrency behavior for one group:
one running run plus one pending run, with a later pending arrival replacing the
older pending run when `cancel-in-progress: false`.

This is intentionally not a claim that local tests reproduce GitHub's scheduler
implementation. The exact sink code and shared incident transitions are
executed; only dispatch coalescing is modeled. The durable audit records the
schedule, assertions, Windows command, and that limitation.

## Risks / Trade-offs

- [A repair fails and the service is still red] → Re-probe reaches the failed
  escalation path with diagnostics instead of silently ending mid-triage.
- [Pushover secrets are missing] → Preserve the warning and continue to
  re-probe; missing credentials cannot suppress the outage decision.
- [A real page would wake the host during tests] → Test the unchanged CLI with
  `--dry-run` and inspect exact workflow arguments.
- [A Pushover page command fails] → Leave the failed page step visible with
  `continue-on-error`, then run canonical re-probe and incident escalation.
