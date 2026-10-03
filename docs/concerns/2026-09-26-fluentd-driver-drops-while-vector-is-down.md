---
severity: P2
title: The fluentd driver drops silently while Vector is down
filed: '2026-09-26'
summary: the journal is durable but everything upstream of the sidecar is not, so "the evidence is in the journal" holds only for the intervals Vector was running; the clean fix is blocked on the Alpine Vector image having no `journalctl`
---

# The fluentd log driver drops silently while the Vector sidecar is down

**Filed:** 2026-09-26 · **Severity:** P2

## Finding

Every long-running container in `deploy/compose.yml` (`daemon`, `cloudflared`,
`slack-agent`) forwards its stdout through Docker's **asynchronous** fluentd
logging driver to the Vector sidecar on `127.0.0.1:24224`:

```yaml
x-tinyassets-log-forwarding: &tinyassets_log_forwarding
  driver: fluentd
  options:
    fluentd-address: "127.0.0.1:24224"
    fluentd-async: "true"
    tag: "{{.Name}}"
```

With `fluentd-async: "true"`, a container whose listener is unreachable does not
block and does not fail — the driver buffers in memory and, past its ring buffer,
**discards** log events. Nothing surfaces: the container is healthy, the deploy is
green, and there is no error anywhere attributable to the loss.

So the durability this repo now has is conditional on `tinyassets-logs` being up.
The whole chain is:

```
daemon stdout → fluentd driver → tinyassets-logs (Vector) → Vector stdout
              → journald driver → host journal  (durable, survives recreates)
```

The journal is durable, but everything upstream of Vector is not. While Vector is
down, restarting, or force-recreated, the journal receives nothing and the loss is
unrecoverable — it never reached a disk.

This predates the 2026-09-26 journald work and is not caused by it. It is filed
because that work makes the journal the *stated* durable home, and a reader who
takes that at face value will over-trust it: "the evidence is in the journal" is
true only for the intervals Vector was running.

## Why it was not fixed in the same change

The clean fix is to invert the topology — put the app containers on the
`journald` driver so the kernel-side journal is the primary sink, and have Vector
*read* the journal for its Better Stack forwarding. Vector supports a `journald`
source, so this is a supported shape, not a workaround.

It is blocked on the image. Vector's `journald` source **shells out to the
`journalctl` binary**, and the pinned sidecar image is
`timberio/vector:0.40.0-alpine`, where systemd and therefore `journalctl` do not
exist. Making this work needs either:

- a non-Alpine Vector image (Debian-based `timberio/vector:*-debian`), plus a
  read-only mount of `/var/log/journal` and `/run/log/journal`; or
- dropping the Vector hop entirely and accepting that Better Stack forwarding
  goes away unless something else ships the journal.

Both are larger than a logging-driver change and both touch the deploy validator,
which asserts the `logs` service's bind mounts are **exactly** the three Vector
config files (`deploy/deploy_fail_safe.sh`) — so a new mount is a deliberate
validator change, not an incidental one.

## Blast radius today

Bounded, and smaller than it looks:

- Vector runs under `restart: unless-stopped`, so an ordinary crash costs seconds.
- The window that matters is a **deploy**: `deploy_fail_safe.sh` force-recreates
  `tinyassets-logs` whenever a Vector input changes, and container output during
  that recreate is lost.
- The nightly off-box log tier reads the journal, so a gap here is a gap in the
  shipped bundle too, silently and with no marker in its manifest.

## What would close it

1. Move `daemon`/`cloudflared`/`slack-agent` to `driver: journald` with per-service
   tags, so the primary sink needs no sidecar to be alive.
2. Re-point Vector's source from `fluent` to `journald` on a Debian-based image,
   with `/var/log/journal:ro` mounted, and extend the `deploy_fail_safe.sh` mount
   allowlist to match.
3. Verify by stopping `tinyassets-logs` and confirming `journalctl
   CONTAINER_NAME=tinyassets-daemon` still records lines written while it was down.

Until then, treat a gap in `journalctl CONTAINER_NAME=tinyassets-logs` around a
deploy as expected rather than as evidence that nothing happened.
