# Postmortem — partial compose overlay took production down

`current: 2026-08-06` — self-inflicted, detected and recovered within the same
session. `tinyassets.io/mcp` served **502** for roughly 12 minutes.

## What happened

Deploying the pre-merge Slack agent as an add-on service:

```bash
docker compose -p tinyassets -f compose.slack.yml up -d --force-recreate
```

destroyed `tinyassets-daemon`, `tinyassets-tunnel`, `tinyassets-logs` and all
four workers, then SIGKILLed the slack agent itself. The public MCP endpoint
returned 502 until recovery.

## Cause

Docker Compose treats a project's desired state as **exactly what the supplied
file declares**. The production stack is project `tinyassets` from
`/opt/tinyassets/compose.yml`. Supplying a *different* `-f` file under the
**same `-p`** told Compose the project should contain only `slack-agent`, so it
converged the project by removing everything else.

`--force-recreate` is not the cause and removing it would not have helped.
Sharing a project name with a partial file is the whole cause.

`docker events` shows the signature clearly — an orderly `stop` → `die` →
`destroy` for each container rather than crash/OOM:

```
die tinyassets-worker-claude-2 / destroy tinyassets-worker-claude-2
stop tinyassets-daemon / die tinyassets-daemon / destroy tinyassets-daemon
```

## The warning that was already there

An earlier `up` on the same project printed:

> `Found orphan containers ([tinyassets-worker-claude-2 … tinyassets-daemon])
> for this project. If you removed or renamed this service in your compose
> file, you can run this command with the --remove-orphans flag to clean it up.`

That warning was the outage predicting itself: Compose was reporting that it
considered the entire production stack to be stray members of this project. It
was read as noise.

## Recovery

The stack is owned by a systemd unit, so the canonical recovery is **not** a
hand-run `compose up`:

```bash
sudo systemctl start tinyassets-daemon      # healthy in ~25s
```

`systemctl is-active tinyassets-daemon` returning `inactive dead` while the
containers are missing is the diagnostic: something took the project down, and
the unit is the way back.

Verified after recovery: `HTTP 200` on `https://tinyassets.io/mcp`, and
`scripts/mcp_public_canary.py --assert-handles` exits 0, so the canonical seven
handles are intact (hard rule 11).

## Fix

Run add-on services in their **own** compose project, with shared resources
declared `external` so they can attach:

```yaml
volumes:
  tinyassets-data: {name: tinyassets-data, external: true}
networks:
  default: {name: tinyassets-net, external: true}
```

```bash
docker compose -p tinyassets-slack -f compose.slack.yml up -d
```

Proven rather than assumed: the exact command that caused the outage was
re-run under the new project name, and all eight containers survived.

## Durable fix

The overlay only exists because PR #2348 has not merged. `deploy/compose.yml`
already carries the `slack-agent` service behind `profiles: ["slack"]`, so
landing it removes the second file — and this failure mode — entirely. Overlays
sharing a project with the main stack are a temporary shape and should be
treated as one.

## Generalisation

Any tool whose verb is *"make reality match this file"* deletes what the file
omits. Before pointing one at shared infrastructure, establish what it thinks
the **scope** is. For Compose the scope is `-p`, not `-f`.
