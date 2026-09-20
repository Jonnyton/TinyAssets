# `ta-op` native test plan and driver

**Nothing in this file has been run.** It is authored for the coordinator to
inspect and execute. No static assertion anywhere in this change is claimed as
native runtime proof: `tests/test_ta_op_modes.py` proves the *table* is
coherent, `tests/test_drop_first_exec_gate.py` proves the *gate* fires, and
neither says anything about what the binary does on a running kernel. Only the
rows below can do that, and all of them need Linux.

The driver is `deploy/native/ta_op_native_check.sh`. It takes a path to a
compiled `ta-op` and runs the rows that the *current* privilege context can
reach, skipping the rest loudly by name — a skipped row prints `SKIP` with the
reason, never a pass.

## Build (unprivileged, ordinary compiler; safe anywhere with gcc)

```
gcc -static -O2 -Wall -Wextra -Werror -o /tmp/ta-op deploy/native/ta_op.c
ldd /tmp/ta-op   # must say: not a dynamic executable
```

`-Werror` is part of the contract: a warning in a binary that performs a
privilege retirement is a defect.

## Rows

| # | Row | Context needed | Expected |
|---|---|---|---|
| 1 | unknown mode | any | exit 78, `TA_OP_REFUSED:unknown-mode`, no exec |
| 2 | wrong arity (`pulse extra`, bare `printenv`) | any | exit 78, `TA_OP_REFUSED:arity` |
| 3 | malformed NAME (`printenv 'a b'`, `printenv lower`, `printenv 9X`) | any | exit 78, `TA_OP_REFUSED:env-name` |
| 4 | no mode at all | any | exit 78, `TA_OP_REFUSED:no-mode` |
| 5 | unexpected entry uid | Linux, run as a uid that is neither 0 nor 1001 | exit 78, `TA_OP_REFUSED:unexpected-entry-uid` |
| 6 | **rootless exact groups** — uid/gid 1001, `Groups: 1001` | Linux container matching production posture (`--user 1001:1001`, `--cap-drop ALL`, `--security-opt no-new-privileges`) | `version` exits 0 and prints `ta-op 1 modes=8` |
| 7 | rootless with a foreign supplementary group | same, plus `--group-add 65534` | exit 78, `TA_OP_REFUSED:legacy-entry-unexpected-group` |
| 8 | **mutation control** — rootless entry into a container with caps | `--user 1001:1001 --cap-add SYS_ADMIN` | exit 78, `TA_OP_REFUSED:legacy-entry-caps-not-empty`. *Without this row the legacy branch is decorative.* |
| 9 | rootless without NNP | `--user 1001:1001 --cap-drop ALL` and no `no-new-privileges` | exit 78 at `nnp-readback` |
| 10 | **root + exactly five caps** | `--user 0 --cap-drop ALL --cap-add CHOWN --cap-add SETGID --cap-add SETUID --cap-add SETPCAP --cap-add SYS_ADMIN` | full drop runs; the child reports uid/gid 1001, `Groups:` empty, all five cap sets 0, `NoNewPrivs: 1` |
| 11 | root with a sixth cap | row 10 plus `--cap-add NET_ADMIN` | exit 78, `TA_OP_REFUSED:exact-five-caps` |
| 12 | root with four caps | row 10 minus `--cap-add CHOWN` | exit 78, `TA_OP_REFUSED:exact-five-caps` |
| 13 | **post-drop target identity** | row 10 with a mode whose target prints `/proc/self/status` | the *target*, not the wrapper, reads uid/gid 1001 and all-zero caps |
| 14 | **descriptor boundary** | any Linux, invoked with an extra open fd (`exec 9< /etc/hostname`) | fd 9 is absent from the target's `/proc/self/fd` |
| 15 | **loader / env boundary** | any Linux | `strace -f -e trace=openat` shows no `ld.so`, no `/etc/nsswitch.conf`, no `/etc/passwd`, no `/etc/group`, no `/app` or `/data` path opened before the `execve` |
| 16 | `env-summary` filtering | any Linux | with `FOO=1 TINYASSETS_GOAL_POOL=off SECRET=ollama-token` set, prints exactly `TINYASSETS_GOAL_POOL=off` — the value containing `ollama` is NOT printed |
| 17 | wrapper is not setuid/setgid | any | `stat -c %a` is `555` and `%U` is `root` on the installed path |

Rows 1–4 and 16 run unprivileged on any Linux box with no container at all.
Rows 6–13 need a disposable container; per the coordinator's note the exclusive
local container slot may be held by another cohort, so they queue.

**Do not run rows that execute a keepalive provider.** `claude-keepalive` and
`codex-keepalive` are migrated by argv only; nothing in this plan invokes a
provider, and the driver refuses those two modes outright.

## Remaining proof this plan does NOT supply

- The production image actually building with the new builder stage (CI).
- `python scripts/deployed_sha.py --assert-contains <sha>` after deploy.
- The live public canary and a rendered `ui-test` conversation.
- The `ta-op pulse` healthcheck going green on the real daemon.
