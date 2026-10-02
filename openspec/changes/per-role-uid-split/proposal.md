## Why

The credential broker (S6, `broker-streaming-contract`, #4299) authenticates its callers by the
kernel uid on its socket (`SO_PEERCRED`). In production today every role runs as one uid (1001):
the daemon, its engine and provider children, and the workspace workers. A same-uid child can
therefore read the daemon's `owner.json` and act as the owner on the broker's owner channel. So
the broker refuses to start (`BrokerUidSplitRequired`, deviation (c)). The broker is also what
cuts the per-turn memory of a model round from about 29 MiB (one Python worker per proxy) to about
100 KiB (one stream), so this split gates both a security boundary and the platform's memory
headroom.

Measured on prod (2026-10-02, read-only):
- the daemon container runs as `tinyassets` (1001), with `cap_drop: ALL` and
  `no-new-privileges`;
- `/data` and every store in it are owned by that uid;
- no process in the container can change uid today.

## What Changes

- **A uid per role, enforced by the kernel.** Owner/daemon 1001 (unchanged, it owns `/data`);
  broker 1002; engine and provider children 1003. The box-host and per-box ranges are reserved
  for S4/S5 and agreed with `openshell-spike`.
- **A tiny root launcher, not a privileged daemon.** The container starts as root with only
  `CAP_SETUID`/`CAP_SETGID`. The launcher starts the broker and the daemon as their own uids, then
  serves exactly one request from the daemon: "spawn this allowlisted child as 1003". The daemon
  keeps no capability, so it cannot become the broker's uid and read the vault.
- **Volume permissions to match.** The broker's state and vault directories are owned by 1002 and
  0700. Child-writable workspaces get a shared group with setgid directories. Everything else
  stays owned by 1001. A startup migration fixes ownership idempotently, under the layout lock.
- `start_broker` replaces its refusal with `BrokerSupervisor(...).start()` when it observes
  distinct uids. It still refuses when it does not.

## Impact

- Deploy shape: `deploy/compose.yml` (daemon `user:` and capabilities), `Dockerfile` (users,
  launcher), `deploy/docker-entrypoint.sh`, and the deploy validator's capability assertions.
- Permissions: the volume gets a one-time chown/chgrp migration. Rollback leaves the files readable
  by 1001 (group plus owner), so an older image still runs.
- Code: `tinyassets/broker/supervisor.py` (refusal → start), and the spawn sites that start engine
  and provider children (`providers/owned_process.py`, `engine_mcp_http.py`, `node_sandbox.py`,
  the workspace workers) go through the launcher client.
- Specs: new capability `runtime-process-roles`. `credential-vault` gains the broker-owned vault
  directory.
