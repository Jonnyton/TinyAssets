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
  broker 1002; engine and provider children 1003. Three service groups carry the cross-uid access
  the split needs: `ta-work` (1100) for workspaces, `ta-brk` (1101) for the broker socket,
  `ta-vault` (1102) for vault reads. The box-host and per-box ranges are reserved for S4/S5 and
  agreed with `openshell-spike`.
- **A tiny root launcher, not a privileged daemon.** The container starts as root with exactly the
  five capabilities `deploy/native/ta_op.c` already asserts on root entry. The launcher starts the
  broker and the daemon as their own uids, then serves exactly one request from the daemon's own
  pid: "spawn this allowlisted child as 1003". The daemon keeps no capability, so it cannot become
  the broker's uid and read the vault.
- **No owner-writable path on a privileged chain.** The entrypoint moves out of `/app` (where the
  image chowns it to 1001) to a root-owned path; the launcher runs `python -I -S` from a root-owned
  file so `PYTHONPATH=/app` and every `site-packages` `.pth` are out of the privileged process;
  `/app` itself becomes root-owned and read-only, with the owner's `HOME` moved to
  `/home/tinyassets`. Each child's environment is built from a per-kind **allowlist** — not from
  `platform_secrets.child_env`, which is a denylist — with that denylist still applied on top.
- **Owner-reachable IPC separated from private broker state.** The broker's own state stays
  1002-only at `/data/.broker/` 0700. The sockets move to the `/run` tmpfs with group `ta-brk`, and
  the launcher — not the owner — starts, restarts and stops the broker. The owner's
  `(socket, generation, token)` is held in process memory and `owner.json` is deleted.
- **Volume permissions to match, with one rule: the migration never changes the owner of a path an
  older image reads.** The vault keeps owner 1001 and gains group `ta-vault` at 0640, so the owner
  stays its only writer and the broker becomes a read-only consumer; child-writable workspaces get
  `ta-work` with setgid directories. Only `/data/.broker/**`, which no older image opens, changes
  owner. A startup migration applies this idempotently under the exclusive layout lock, refusing
  symlinks and hardlinks rather than following them.
- `start_broker` replaces its refusal with the launcher-mediated start when it observes distinct
  uids. It still refuses when it does not.

## Impact

- **Deploy shape:** `Dockerfile` (users and groups, `/app` ownership, `HOME`, the launcher and the
  relocated entrypoint), `deploy/docker-entrypoint.sh` (install path only — contents unchanged),
  `deploy/compose.yml` (root entry, `cap_add`, `HOME`), and the deploy validator's capability
  assertions.
- **Rollback is free, not staged.** Because no path an older image reads changes owner, an older
  image that runs everything as 1001 still reads and writes every store. There is no reverse
  migration and no temporary permission widening.
- **Code:** `tinyassets/role_launcher` ships as a root-owned file, not an importable module;
  `tinyassets/broker/supervisor.py` (refusal → launcher-mediated start; `owner.json`, `stop()` and
  `read_owner` deleted); `tinyassets/broker/process.py` (the generation is minted by the broker, so
  `lease_verifier` loses its `owner_generation` parameter); `tinyassets/credential_vault.py` (two
  `_chmod_best_effort` calls 0600 → 0640, for the setgid group read);
  `tinyassets/storage/outbound_connections.py` (the brokered channel reads the fence from the live
  supervisor, and the legacy proxy worker refuses to spawn while the broker is selected);
  `tinyassets/workspace_worker.py` (its channel becomes an inherited socketpair so it can run as
  1003); and the spawn sites that start engine and provider children
  (`providers/owned_process.py`, `engine_mcp_http.py`, `node_sandbox.py`) go through the launcher
  client. New gate: `scripts/check_privileged_chain.py`.
- **Dependencies:** lands after #4299 (the broker) and #4267 (`platform_secrets`), amending both.
- **Specs:** new capability `runtime-process-roles`. `credential-vault` gains the vault's
  broker-readable group and the owner-only writer rule.
