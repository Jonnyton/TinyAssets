## 1. Design (this change)

- [x] 1.1 Proposal, design and spec delta; uid map agreed with agent-loop and openshell-spike.
- [x] 1.2 Cross-family security refute of the design. Round 1 returned ADAPT with four P1s, each
      now closed: the privileged chain (D2, task 2.1/2.3), owner-reachable IPC (D6, task 2.4/2.6),
      the migration (D4, task 2.4), and the owner trust class (D7, task 2.5/2.6).

## 2. Build (Codex implements; deploy-incident reviews and verifies)

Lands after #4299 (the broker) and #4267 (`platform_secrets`), amending both.

- [ ] 2.1 **Image: users, groups, and a root-owned privileged chain** (closes P1-1, part 1)
      - users 1002 `ta-broker`, 1003 `ta-engine`; groups 1100 `ta-work`, 1101 `ta-brk`,
        1102 `ta-vault`, with **no** supplementary membership in `/etc/group` — `ta_op.c:240-243`
        refuses a second gid and the healthcheck runs through it, so the launcher sets groups
        instead (D1).
      - `ta-entry.sh`, `ta-launch.py` install root-owned `0555` under `/usr/local/libexec`;
        `broker_main.py` ships root-owned `0555`.
      - `Dockerfile:339` chowns `/data` only; `/app` stays root-owned and read-only; `HOME` moves
        to `/home/tinyassets` (1001:1001 `0700`).
      - *Precondition:* enumerate every runtime write under `/app` first (daemon, healthcheck,
        provider jail, node sandbox). If one is load-bearing, take D2's fallback — a root-owned
        `/opt/tinyassets` copy plus a byte-parity gate — and record which was used.
- [ ] 2.2 **`ta-launch.py`: the launcher** (closes P1-1, part 2)
      - stdlib-only, run `-I -S -B`; static kind/argv table; no shell string in either direction.
      - `SO_PEERCRED` **uid-and-pid** check against the daemon it started, so no other process at
        1001 can request a spawn.
      - per-kind **allowlist** environment with `CHILD_FORBIDDEN_ENV` applied on top —
        `platform_secrets.child_env` is a denylist (`platform_secrets.py:53-55`) and must not be
        the basis for a privileged exec.
      - per-kind `setgroups`/`setresgid`/`setresuid` with `/proc/self/status` readbacks; full
        capability drop with readbacks; `PR_SET_NO_NEW_PRIVS`; `PR_SET_DUMPABLE(0)` on broker and
        daemon; `/proc/self/fd` sweep keeping only each kind's declared descriptors
        (`provider-cli` needs bubblewrap's seccomp fds, `owned_process.py:651`); listening socket
        `FD_CLOEXEC` and never in any kind's passed set.
      - unit tests in the Linux oracle.
- [ ] 2.3 **Chain verification** (closes P1-1, part 3)
      - the launcher `lstat`s itself, the interpreter, `broker_main.py`, every privileged
        `sys.path` entry **and every ancestor directory of each**, refusing on a symlink, a
        non-root owner, or a group/other-writable mode — before it binds a socket.
      - `scripts/check_privileged_chain.py` asserts the same against the built image, wired into
        the docker-build CI job, so the runtime refusal is a backstop not the only check.
- [ ] 2.4 **Volume migration and vault permissions** (closes P1-3)
      - D4's exact inventory, under the exclusive layout lock, idempotent, with
        `"roles": {"state": "migrating"}` in `/data/.layout.json` for crash recovery.
      - traversal holds directory fds with `O_NOFOLLOW|O_DIRECTORY`, uses `*at()`/`lchown` only,
        and **refuses** on any symlink in the set, any regular file with `st_nlink > 1`, and
        anything that is not a directory or regular file.
      - assert D4's rollback invariant as a test over the inventory table: no path an older image
        reads changes owner, so there is no reverse migration and no temporary widening.
      - `credential_vault.py`: the two `_chmod_best_effort(..., 0o600)` calls on the write path
        (the temp file and the committed file, around 624 and 632) become `0o640`, so the setgid
        `ta-vault` group read survives every deposit.
      - confirm read-only on prod that `/data` is `ext4` with ACL support so `g:1102:x` gives the
        broker traverse on `/data/<cc>/` without widening `other`; else mode `2711`, recorded.
- [ ] 2.5 **Spawn sites through the launcher** (closes P1-4, part 1)
      - `provider-cli` (`owned_process.py:539,650-652`), `engine-mcp` (`engine_mcp_http.py:277`),
        `node-sandbox` (`node_sandbox.py`) move to the launcher client at 1003.
      - `workspace-worker` to 1003: its `multiprocessing.Pipe` channel
        (`workspace_worker.py:677-684`) becomes a pre-connected `socketpair` passed by
        `SCM_RIGHTS` and `run_workspace_worker` reads it from that descriptor. Differential-test
        the new channel against the current one through the existing injectable `spawn=`
        (`workspace_worker.py:667`).
- [ ] 2.6 **`start_broker`, the in-memory fence, and the legacy path** (closes P1-2 and P1-4, part 2)
      - launcher-mediated start when the uids are distinct; refuse otherwise.
      - delete `owner.json`, `OWNER_FILE`, `read_owner` and `stop()`'s terminate-and-unlink
        (`supervisor.py:125-132,150-159`); the socket and the `(generation, token)` pair live in
        memory, and `_broker_channel` (`outbound_connections.py:1086-1108`) takes them from the
        live supervisor instead of re-reading a file at 1097 and 1103. Update
        `tests/test_broker_process.py:57-59,98-129`.
      - amend #4299: the broker mints the generation from its persisted fence, so `lease_verifier`
        (`broker/process.py:40-48`) loses its `owner_generation` parameter and `--generation`
        leaves the broker's argv.
      - the legacy per-grant proxy worker refuses to spawn while `broker_selected()`
        (`outbound_connections.py:5338`), so the two credential paths never coexist at uid 1001.
        Test both directions.
- [ ] 2.7 **Entrypoint, compose, and the capability set**
      - start as root with `cap_add: [CHOWN, SETUID, SETGID, SETPCAP, SYS_ADMIN]` — exactly
        `ta_op.c`'s `MASK` (81-82), because that file asserts set equality on root entry.
      - `deploy/docker-entrypoint.sh` keeps its contents; only its install path changes.
      - `HOME` updated in `deploy/compose.yml` (today `HOME: /app`, compose:147); the deploy
        validator's capability assertions updated.
      - decide `CAP_SYS_ADMIN`: prove what needs it or remove it from both `cap_add` and `MASK`
        in one commit. Never diverge from `ta-op` silently.
- [ ] 2.8 **Oracle proofs** (non-root, like production)
      - a 1003 child gets `EACCES` on `/data/.broker/state/fence.json` and on
        `/data/<cc>/.credential-vault.json`.
      - the broker reads the vault and **cannot write** it; the provider jail works under 1003
        with group workspace access.
      - enumerate which `provider_jail` binds the 1003 child must **write** (the
        `.runtime/provider-launch-credentials` snapshot in particular) and set `2770/0660` for
        exactly those, `2750/0640` for the rest — measured, not guessed.
      - `ta-op pulse` stays green on the new root entry, and `PR_SET_DUMPABLE(0)` on the daemon
        breaks no 1001 reader of its `/proc`. The healthcheck is the deploy's own gate, so both
        are proven before the deploy.
- [ ] 2.9 Prod verification: per-role uids in `ps`, the broker serves one owner stream, the
      measured RSS per stream; `deployed_sha` and canary.
- [ ] 2.10 Spec sync and archive.
