<!-- STAGING NOTE (slice 1, 2026-09-20): this branch carries ONLY the installed
helper — Dockerfile, deploy/native/* and tests/test_ta_op_modes.py. The gate
and migration tests named below (tests/test_drop_first_exec_gate.py,
tests/test_drop_first_operational_migration.py) and the caller/healthcheck/
env-apply migration are the deferred second slice and are not in this tree.
The evidence below is unchanged; the citations that do not resolve here are
citations into the source tree at 84c116ae45992a974f6ca9625131b42509b15ae5. -->

<!-- Verbatim copy of the root coordinator's artifact, taken from the root
checkout (worktree 0a7f) on 2026-09-21 so the citation resolves inside this
branch. Authored by root Codex, not by this lane. Nothing below is edited;
every result is LOCAL fixture evidence and is labelled as such by its author. -->

# Drop-first helper: independent local native evidence

Root Codex, September21 2026, approximately00:08–00:11UTC. Source candidate
`20573b0fad515e548f630dba0ec60e429ceb83dd` in `wf-drop-first-ops/TinyAssets`.
This is partial LOCAL diagnostic evidence, not approval, production activation,
deployed-image proof, or a completed user capability.

## Inputs and independent tests

- Corrected Claude implementation: `babda27252b6b9f1eab2d9c26b8cb7d9dbfce930`;
  final docs successor20573b0f; clean tree rechecked during handoff.
- Windows venv Python3.14: `python -m pytest -q
  tests/test_ta_op_modes.py tests/test_drop_first_exec_gate.py
  tests/test_drop_first_operational_migration.py tests/test_dockerfile_shape.py`
  produced87passed, zero skips,1.27s (root run).
- Native WSL Ubuntu Docker base `tinyassets-linux-oracle:7693b1a8f805`, Python3.11.16.
  GCC compiled actual source static with `-O2 -Wall -Wextra -Werror` as UID1001.
  `ldd` said not a dynamic executable; helper `version` said `ta-op 1 modes=9`.
- Source and local fixture copy SHA256 both
  `acf9fc50984121d247b6b42dee5565e86ca1797c7e302b9ad5f5e4d16415a6d7`.

## Current rootless entry

Executed via `wsl -d Ubuntu -- docker run --rm --network none --cap-drop ALL
--security-opt no-new-privileges --memory 256m --pids-limit 64 --user 1001:1001`,
with read-only source mount and existing oracle image. Compiled `/tmp/ta-op`,
then `bash /src/deploy/native/ta_op_native_check.sh /tmp/ta-op`.

Actual driver result:11pass,0fail,1skip (installed ownership not represented),
1NOT_PROVEN (descriptor9 closure). The driver exit0 does NOT establish all
matrix rows. Target identity, loader-order, fake-status mutant controls and
production installed-image checks were not all covered by this driver.

## Actual post-drop exec target

Local-only fixture in ignored `output/ta-op-native-fixture/` builds the exact
helper and substitutes `/usr/bin/printenv` with an assertion probe. It is NOT
the production printenv target and uses no provider/network/host credentials.
Image `ta-op-native-fixture:20573b0f`, ID
`sha256:4f57ecd92f776725b27da1816dd1be019e83ad93763716a7e86702a06c9f64a6`.

Command: `wsl -d Ubuntu -- docker run --rm --network none --cap-drop ALL
--cap-add CHOWN --cap-add SETGID --cap-add SETUID --cap-add SETPCAP
--cap-add SYS_ADMIN --security-opt no-new-privileges --memory 256m
--pids-limit 64 --user 0:0 ta-op-native-fixture:20573b0f printenv PATH`.

Exit0. Actual child PID1 observed all four Uid/Gid values1001, empty Groups,
CapInh/CapPrm/CapEff/CapBnd/CapAmb all0 and NoNewPrivs1. This proves native
post-drop identity for that LOCAL substituted target, not pre-drop loader or
descriptor closure. Initial legacy-Docker build rejected COPY--chmod; changing
fixture installation to RUN chmod built successfully, no runtime change.

## Native entry refusals

Same fixture image, `version`, networknone,256MiB,64PIDs, auto-removed containers:

| Entry variant | Actual exit / evidence |
|---|---|
| UID/GID1001, no capabilities, NNP1 | 0; version success |
| Same plus supplementary group65534 | 78; legacy-entry-unexpected-group |
| UID1001 with SYS_ADMIN retained | 78; legacy-entry-caps-not-empty |
| UID1001 without NNP | 78; nnp-readback |
| Root with only four expected caps (omitCHOWN) | 78; exact-five-caps |
| Root with expected five plusNET_ADMIN | 78; exact-five-caps |
| UID/GID1002 | 78; unexpected-entry-uid |

Fresh `docker ps` after tests was empty. Disposable `--rm` containers removed
only themselves; diagnostic images remain. No production config, image, data,
connection, provider login or private workflow changed.

## Additional native evidence, approximately00:20–00:34UTC

Added a LOCAL static fixed launcher opening descriptor9 without CLOEXEC before
execing the exact helper, then the diagnostic target checks EBADF on fd9.
Image `ta-op-native-fd-fixture:20573b0f` (10b26bb824b6), built offline from the
same base/source. Actual root+exact5caps AND current-rootless runs each printed
`LOCAL_FIXTURE_FD9_OPEN_BEFORE_EXEC`, then target `fd9: closed` with all prior
identity/capability assertions passing. `readelf -l` shows no INTERP header.

For actual syscall ordering, local trace image `ta-op-native-trace-fixture:20573b0f`
(01c0f6a1022b) adds Debian strace6.13 andlibunwind8 to that disposable fixture
only (package installation used network; all actual executions use networknone).
Command uses the earlier256MiB/64PID/rootless/cap-drop-all/NNP posture, entrypoint
`strace`, arguments `-f -e trace=openat,close,execve /usr/local/libexec/fd-launcher`.
Exit0, default seccomp retained. Observed helper opens ONLY/proc/self/status and
/proc/self/fd before `close(9)=0`, then `execve(/usr/bin/printenv)=0`. Dynamic
loader/Python opens occur only AFTER that exec; no NSS/passwd/group/app/data open
before it. Target again observes fd9closed. This supplies native matrix14/15 on
the local legacy-rootless path; root target identity was independently measured.

Crafted-status matrix18 used exact fixed source with compile-time-only override
and old7302c91a source with ONLY the same test-file injection added to read_text.
Fake fourth UID10010: fixed exits78/fs-uid-readback, old prefix implementation
exits0/ta-op1modes8. Both statically compiled as UID1001, warnings fatal. Driver
`output/ta-op-native-fixture/predicate-check.sh`, source mount read-only, same
networknone/capsnone/NNP/256MiB/64PID posture. Installed LOCAL fixture helper
reports mode555,UID0,GID0. Production Dockerfile never defines fake status path.

Independent canonical Linux oracle74313:102passed/1skip3.85s for the four focused
files above plus test_invariants_framework.py. The sole skip is the gate's
git-history base-object control, absent from the oracle's source archive;
independent Windows rerun15125 covers all103passed/zero skips6.80s. No Linux
kernel test is represented by that Windows coverage. Operational rollback/flag
Linux cohort33064 completed:86passed,zero skips,56.24s, using the canonical oracle
with --no-bwrap and tests/test_apply_daemon_env_voice_flags.py,
tests/test_deploy_bundle_validator.py and tests/test_deploy_bundle_transaction.py.
These fixtures changed no production data.

## Still required

Production-image build/installed-image checks and relevant hosted regressions.
Independent exact-head review, PR, normal deployment, protected public gates
and live operational acceptance remain. Root-start production is NOT authorized
by this partial fixture result.
