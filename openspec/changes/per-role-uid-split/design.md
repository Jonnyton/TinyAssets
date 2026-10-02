## Context

`broker-streaming-contract` design §Roles: "the owner process and boxhostd run as DISTINCT uids …
a connection from an unmapped uid is refused." The broker maps uid to role from static
configuration via `SO_PEERCRED`. A uid cannot be faked by a process that lacks `CAP_SETUID`, but
every process in the daemon container is uid 1001 today, so the map cannot tell the owner from its
children. `start_broker` refuses on purpose (v1 deviation (c)).

Production facts (2026-10-02, read-only `docker inspect` / `docker exec id` / `stat`):
- the daemon is `User: tinyassets` (1001), with `CapDrop: [ALL]`, `no-new-privileges=true`,
  seccomp and apparmor unconfined (bubblewrap needs that);
- the `/data` volume and every store in it are owned by `workflow` (uid 1001 on the host),
  0644/0755.

## Goals / Non-goals

- **Goal:** distinct kernel uids for the owner (daemon), the broker and engine/provider children.
  The owner cannot become the broker, a child cannot become either, and the broker serves.
- **Goal:** no new long-lived privileged surface beyond one small, auditable launcher.
- **Non-goal:** per-command-center uids for user content. Boxes (S4/S5) bring their own isolation;
  this change only reserves their uid range.
- **Non-goal:** splitting containers. One container, several uids, keeps the shared volume and the
  existing deploy transaction.

## Decisions

### D1. The uid map (agreed with agent-loop and openshell-spike before build)

| Role | uid:gid | Owns |
|---|---|---|
| owner (daemon, frontends, scheduler) | 1001:1001 `tinyassets` | `/data` (unchanged) |
| broker | 1002:1002 `ta-broker` | `/data/.broker/` (0700), the vault directories (0700) |
| engine / provider children | 1003:1003 `ta-engine` | nothing; writes only in workspaces through group `ta-work` |
| boxhostd (S4/S5) | 1004 reserved | — |
| per-box uids | 200000–299999 reserved | openshell-spike defines |

Group `ta-work` (gid 1100): owner and engine are members. Workspace roots are `2770 1001:1100`,
with setgid so new files inherit the group.

### D2. A root launcher, and the daemon keeps no capability

The container starts as root under tini with `cap_drop: ALL` and
`cap_add: [SETUID, SETGID, CHOWN]`, plus `no-new-privileges`. That flag still allows
`setuid()`/`setgid()` with the capability; it only forbids gaining privilege through setuid
binaries. `deploy/docker-entrypoint.sh` (root) does five things:
1. runs the idempotent ownership migration (D4) under the shared layout lock;
2. starts the **launcher**: `python -m tinyassets.role_launcher`, root, with SETUID/SETGID only;
3. the launcher starts the broker with `setresgid/setresuid(1002)`, `PR_SET_NO_NEW_PRIVS`, and the
   capabilities dropped to none;
4. the launcher starts the daemon as 1001 with no capabilities;
5. the launcher serves a Unix socket at `/run/tinyassets/launcher.sock`, root 0600 plus an ACL for
   1001. It accepts only from `SO_PEERCRED` uid 1001, and only `SPAWN{kind, argv-template-id,
   args}` for an allowlisted child kind. It starts that child as 1003 with no capabilities, passes
   the stdio fds back over the socket (`SCM_RIGHTS`), and reports exit status.

Why not give the daemon `CAP_SETUID`: with it, the daemon could `setuid(1002)` and read the vault,
which defeats the owner/broker split the broker's role map exists for.

Why not user namespaces: a child in a user namespace mapped to outer 1001 appears to the broker as
1001 (`SO_PEERCRED` translates to the receiver's namespace). Only distinct kernel uids separate.

### D3. Who spawns what

The spawn sites move to the launcher client, one call shape:
`launcher.spawn(kind, args) -> Popen-like`. Kinds:
- `provider-cli` (`providers/owned_process.py`, inside the existing bubblewrap jail);
- `engine-mcp` (`engine_mcp_http.py`);
- `node-sandbox` (`node_sandbox.py`);
- `workspace-worker` (the `workspace_*_process.py` modules).

Kinds and argv templates are a static table in the launcher, not caller-supplied strings. The
`multiprocessing` spawn children that stay in-process (the brokered proxy worker until S6 2.8
deletes it) remain uid 1001 and are not given broker access.

### D4. Volume migration

Idempotent, under the exclusive layout lock, at container start before any role runs:
- `/data/.broker/` and the vault directories (credential-vault paths) → `1002:1002 0700`;
- workspace roots → `1001:1100 2770`, contents `g+rw` (for directories, `g+rwxs`);
- everything else is left as is (1001).

Rollback to an older image, which runs everything as 1001: the vault directory is 1002-owned and
0700, so the old daemon cannot read it. So the migration also writes the vault directory with an
ACL granting 1001 read until the broker is proven. That ACL is removed in the change that makes the
broker the only path (S6 2.8). This is recorded as the one temporary widening.

### D5. The broker's role map and the refusal

`start_broker` checks `os.getuid() == 1001` and that the broker answered with peer uid 1002.
Only then does it start `BrokerSupervisor`. Otherwise it raises `BrokerUidSplitRequired`, exactly
as today, so a dev host or a misdeploy fails closed.

## Risks / Trade-offs

- **The launcher is root-adjacent code.** It is kept to one file (no imports beyond stdlib), a
  static allowlist, no shell, `execve` with an explicit environment
  (`platform_secrets.child_env()`), and a cross-family security refute before build.
- **Bubblewrap under a non-owner uid.** The provider jail binds workspace paths. Group access must
  cover what the jail needs, and the Linux oracle (non-root, like production) proves it.
- **The migration touches every workspace file once.** Bounded by the volume size (about 1.8 GB).
  It runs under the layout lock, and backups skip while it holds that lock.

## Verification

- Prod read-only first: `docker exec … ps -eo uid,comm` shows 1001/1002/1003 per role after
  deploy, and `stat` shows the broker-owned vault.
- A child kind spawned as 1003 cannot read `/data/.broker/owner.json` (EACCES), proven in the
  oracle and on prod by a probe child.
- `TINYASSETS_CREDENTIAL_BROKER=process` starts and serves one owner stream, with per-turn RSS
  measured (the target is about 100 KiB per stream versus 29 MiB per worker).
