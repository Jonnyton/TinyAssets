# Drop-first operational exec amendment

Approved shape. `docs/reviews/2026-09-20-drop-first-ops-shape-disposition.md`
carries the coordinator disposition, the `DISAGREE_EVIDENCE` correction to the
legacy-entry predicate, and the opposite-family compatibility review's
`APPROVE` with two binding conditions. Both conditions are implemented here.
Shape review is closed; this file records what was built and why, so the delta
scenarios below can be synced when the change lands.

This is the fourth item in the prerequisite chain at `design.md:416-418`:
*fixed static bootstrap* (done), *five-set privilege retirement* (done),
*tini/entrypoint handoff* (Fable's lane), then **supported drop-first
exec/healthcheck migration plus tested gate** — this amendment. It is an
operational prerequisite, not an inventory-only ratchet: it supplies the
runtime the callsites must call, and migrates every one of them.

## What changed

| Artifact | Role |
|---|---|
| `deploy/native/ta_op.c` | the wrapper: guard, retirement, readback, fixed exec |
| `deploy/native/ta_op_modes.tsv` | the closed mode table, single source |
| `Dockerfile` (builder + runtime) | static compile in the existing builder stage; install root-owned `0555` at `/usr/local/libexec/ta-op` |
| `scripts/check_drop_first_exec.py` + `scripts/invariants/drop_first_exec.py` | the repo gate, registered in the invariant framework (so `invariants.yml` runs it) |
| `scripts/droplet.py`, `deploy/apply-daemon-env-remote.sh`, `deploy/compose.yml`, both keepalive workflows, `scripts/workspace_bwrap_oracle.py` | the migrated real callers |
| `deploy/DEPLOY.md`, `deploy/README.md`, `deploy/tinyassets-env.template`, `.github/workflows/apply-daemon-env.yml` | migrated runbooks + the rollback-pairing correction |

Untouched on purpose: `Config.User`, `cap_add`, `no-new-privileges`, root-start,
any readiness flag, any control-margin value, every keepalive **schedule** and
**enabled state** (argv migration only), and every managed resource family.

## The two entry identities

`getuid()==0` — managed-bootstrap entry, for after the root-start flip.
Requires *exactly* the five caps (`0x2001c1`) permitted/effective/bounding with
inheritable and ambient empty; then NNP, keepcaps clear, ambient clear, whole
bounding set dropped to `cap_last_cap`, `setgroups(0)`,
`setresgid`/`setresuid(1001)`, explicit `capset` zero — and reads every one of
them back, plus a `setuid(0)` that must fail `EPERM`, before any runtime target
exists.

`getuid()==1001` — **legacy-rootless verification**, which is production today.
Asserts all four UID and all four GID positions are 1001, all five cap sets are
0 and `NoNewPrivs` is 1, and permits supplementary groups only when the list is
empty **or is exactly the same primary gid 1001**.

The `Groups: 1001` predicate is not a guess: the coordinator's read-only
production command at ~10:09 UTC on 2026-09-20 —
`python scripts/droplet.py ssh -- 'docker exec tinyassets-daemon cat /proc/self/status'`
— returned `Groups: 1001`. Requiring an empty group list would refuse a healthy
production daemon. A supplementary entry equal to the primary gid conveys no
authority the in-force `setresgid(1001)` does not; `/app` and `/data` are
group-owned by that primary gid. Any other gid is refused.

**This branch is labelled what it is.** Nothing is dropped, because nothing is
held. It is *not* a managed-bootstrap drop receipt and must never be cited as
one. Its value is that a bare `docker exec` asserted none of this.

Anything other than uid 0 or 1001 is refused (exit 78).

## Closed mode table

Eight fixed modes, each preserving the argv a real caller runs today:
`version`, `env-summary` (in-wrapper builtins), `pulse`, `canary`, `printenv`,
`claude-keepalive`, `codex-keepalive`, `bwrap-oracle`. No mode accepts an
executable path, an interpreter switch or a shell string. `printenv` is the
only mode with an operand: one `^[A-Z_][A-Z0-9_]*$` NAME, validated after the
drop. Unknown mode, wrong arity and malformed NAME all fail closed before the
guard even runs.

`env-summary` satisfies the reviewer's binding condition (b): it is an
**in-wrapper post-drop print**, never an exec of `printenv | grep | sort`. The
four flag families (`AUTO_SHIP`, `OLLAMA`, `PIN_WRITER`, `GOAL_POOL`) are
compiled in and matched against the **name** only. This is strictly less
exposure than today's callsite, which pipes the whole environment across ssh.

## Env-apply preflight — binding condition (a)

`deploy/apply-daemon-env-remote.sh:88` was
`docker exec "$DAEMON_CONTAINER" printenv "$1" 2>/dev/null || true`: a missing
wrapper returns the empty string, the caller reads that as "key unset", and
mutates plus restarts on a false premise. The version preflight therefore sits
**above** that read and above every mutation, checks the `ta-op 1 ` banner (not
merely the exit status), and refuses with `exit 1` — no restart, no bare
`printenv` fallback. This is what makes a merge-before-image-arrival safe.

## Rollback pairing

The compose healthcheck now runs `/usr/local/libexec/ta-op pulse`, a binary
that exists only in images built from this commit. That is safe because
`deploy_fail_safe.sh` restores the runtime bundle (which carries `compose.yml`)
**before** `set_image` converges the previous image, on both the internal
failure path and the `--restore-bundle` public-canary path.

The carve-out is stated, not hidden: the bundle is restored only when this run
installed one, so a **manual or image-only downgrade** leaves the new
`compose.yml` against an old image and the probe fails on a missing binary.
`deploy/DEPLOY.md` says so and says to downgrade the compose bundle in the same
step. Rollback semantics were not loosened to mask it.

## Gate scope, stated honestly

The gate governs repo-authored invocations. Two residuals are named rather than
papered over:

1. `scripts/droplet.py ssh -- <cmd>` forwards an arbitrary remote command, and
   any admin holding `~/.ssh/tinyassets_deploy_ed25519` already has arbitrary
   root SSH on the droplet. **Ad-hoc admin SSH is outside the repo gate by
   construction.** After a future root-start flip those ad-hoc execs would run
   as root; that residual belongs to the root-start decision, not here.
2. A `-t`/`-it` exec (the interactive `claude auth login` on a fresh volume) is
   reported as a **note**, not a violation. The carve-out is structural — a TTY
   allocation no workflow, timer or CI runner can use — not an allowlist of
   callsites. There is no grandfather list: every non-interactive callsite in
   the repo was migrated in this change. Whether the interactive login should
   instead become a ninth fixed mode is a shape question left to the
   coordinator; inventing a mode outside the reviewed table was not in scope.
   Filed as `docs/concerns/2026-09-20-ta-op-interactive-tty-carveout.md` — the
   structural argument holds for today's rootless posture and does NOT survive
   a root-start flip, so the decision is owed before that flip, not after.

## One citation to avoid in the D2 regression

`output/claude-handoff-reaping-result.md` (Fable's lane, `714e9683`) records
`app-pulse` manual exit 1. That is a `network none`, token-less fixture
container and the failure is a missing `git_sha`, not missing authorization.
It is **not** evidence about the production `--pulse-only` healthcheck that
`ta-op pulse` now wraps, in either direction.

---

## Delta scenarios (to sync into `openspec/specs/` on land)

### ADDED Requirement: Repo-authored operational execs into the daemon reach their target only after a verified identity retirement

The production image SHALL carry a statically linked, root-owned `0555`
wrapper at `/usr/local/libexec/ta-op`, outside every directory chowned to the
runtime user, and every repo-authored `docker exec` into the daemon container
SHALL invoke it with a mode declared in `deploy/native/ta_op_modes.tsv`.

#### Scenario: Managed-bootstrap entry retires every set before the target exists
- **WHEN** the wrapper starts with `getuid()==0`
- **THEN** it SHALL refuse unless exactly `CAP_CHOWN`, `CAP_SETGID`,
  `CAP_SETUID`, `CAP_SETPCAP` and `CAP_SYS_ADMIN` are permitted, effective and
  bounding with inheritable and ambient empty
- **AND** it SHALL set no-new-privileges, clear keepcaps and ambient, drop the
  whole bounding set, clear supplementary groups, set all three GIDs then all
  three UIDs to 1001, zero every capability set, and read all of that back —
  including a `setuid(0)` that fails `EPERM` — before it execs anything.

#### Scenario: Legacy-rootless entry verifies and is not labelled a drop
- **WHEN** the wrapper starts with `getuid()==1001`
- **THEN** it SHALL require all four UID and all four GID positions to equal
  1001, all five capability sets to be zero, `NoNewPrivs` to be 1, and the
  supplementary group list to be empty or to contain only gid 1001
- **AND** any other supplementary gid SHALL be refused
- **AND** the result SHALL be recorded as legacy-rootless verification, never
  as a managed-bootstrap drop receipt.

#### Scenario: Any other entry identity is refused
- **WHEN** the wrapper starts with a uid other than 0 or 1001
- **THEN** it SHALL exit 78 without execing.

#### Scenario: The mode table is closed
- **WHEN** the wrapper is invoked with an undeclared mode, the wrong argument
  count for a declared mode, or a `printenv` operand that does not match
  `^[A-Z_][A-Z0-9_]*$`
- **THEN** it SHALL exit 78 without execing
- **AND** no mode SHALL accept an executable path, an interpreter switch or a
  shell string.

#### Scenario: The filtered environment summary never leaves the wrapper
- **WHEN** `env-summary` runs
- **THEN** the wrapper SHALL print, after the identity retirement, only those
  environment entries whose NAME matches the compiled-in flag families, sorted
  in-process
- **AND** it SHALL NOT exec a shell, a pipeline, or a full `printenv`.

#### Scenario: Descriptors do not survive into the target
- **WHEN** the wrapper execs a runtime target
- **THEN** every descriptor above standard error SHALL have been closed first.

### ADDED Requirement: Environment application refuses before mutating when the wrapper is absent

The remote env-apply helper SHALL verify the wrapper's fixed version route in
the running daemon before its first read of the running process and before any
environment or service mutation.

#### Scenario: Absent or unacceptable wrapper aborts pre-mutation
- **WHEN** the version route is missing, errors, or returns an unexpected banner
- **THEN** the helper SHALL abort with a non-zero status before writing the env
  file and before restarting the daemon
- **AND** it SHALL NOT fall back to an unwrapped `printenv` read.

### MODIFIED Requirement: The daemon healthcheck runs the drop-first pulse route

The daemon healthcheck SHALL invoke `/usr/local/libexec/ta-op pulse` in exec
form, with no shell fallback.

#### Scenario: Rollback restores the compose bundle before the image
- **WHEN** a deploy rolls back, on either the internal-failure path or the
  public-canary `--restore-bundle` path, and that run installed a bundle
- **THEN** the runtime bundle SHALL be restored before the previous image is
  recorded and converged
- **AND** documentation SHALL state that a manual or image-only downgrade does
  not preserve the pair and must downgrade the compose bundle in the same step.
