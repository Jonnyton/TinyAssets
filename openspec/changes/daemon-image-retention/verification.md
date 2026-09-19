# Prepared implementation evidence — September 19, 2026 UTC

Environment: isolated `daemon-image-retention-mvp` worktree. No production
commands, credentials, image removal, user workflows or account access.
Registry and Docker responses are synthetic; actual Linux advisory locks and
filesystem semantics are exercised. Installer tests publish into temporary
directories outside the repository, with fake service management, not the host.

## Independent shape review

Substantive Fable5.1 ADAPT recovered from session
`b1ef658a-43e7-45b4-ae82-95066d10e893`, retained verbatim in
`shape-review-recovered.md`. Adopted direct dual locks, outside-lock registry
checks, maximum60-second lock hold, authoritative receipt location and narrow
verified immutable-ID relationships. Corrected two unsupported premises:
zero available is real100% pressure; no snapshotter config does not prove a
classic store. Lead relayed implementation authority after those corrections.
This is **not exact-head approval or deployment approval**.

## Focused checks

Windows:

```
python -m pytest -q tests/test_daemon_image_retention.py tests/test_disk_autoprune.py tests/test_disk_watch.py
```

69 passed,16 POSIX-specific skips,0.90s. Those skipped tests passed on Linux.

The standard `python scripts/linux_oracle.py -- -q ...` entrypoint could not
connect to Windows Docker Desktop's named pipe. The already-running WSL Linux
engine was used directly with the existing oracle-derived image, not a fake
Windows substitute. No new image or engine was installed.

```
wsl -d Ubuntu -- docker run --rm --network=none --memory=2g --pids-limit=1024 --security-opt seccomp=unconfined -v /mnt/c/Users/Jonathan/.codex/worktrees/daemon-image-retention-mvp/TinyAssets:/src:ro --workdir /src -e PYTHONDONTWRITEBYTECODE=1 -e TMPDIR=/tmp tinyassets-workspace-browser-probe:e2d3edcc python -m pytest -q -p no:cacheprovider tests/test_daemon_image_retention.py tests/test_disk_autoprune.py tests/test_disk_watch.py tests/test_host_uptime_installers.py
```

**143 passed, no skips,30.82s**. The image is the same existing diagnostic image
used for the workspace investigation; image ID
`sha256:1b69d8536490285c7c7a13f1efe53ebe847696a99ae567dbbd2b9761ee0c530a`.
Its presence of Chromium is irrelevant to this storage test suite.

Ruff on changed Python files, `git diff --check`, and
`openspec validate daemon-image-retention --strict` passed. No full-suite claim.
Exact-head review and authoritative required CI remain pending.

Follow-up before dispatch: dry-run below the trigger now still verifies and
reports protected refs without selecting/removing anything; effectful below-
threshold runs remain no-op. The three changed-function suites then passed
86 tests/no skips on the same Linux image in5.98s. Installer closure and units
were unchanged from the143-test run. Ruff passed again.

## Release boundary

The helper is dry-run by default; updated units explicitly use `--apply`, but
after the activation amendment BOTH that argument and exact retention-only
operator opt-in are required. Root verifies opt-in absent/0 before installation;
timer enablement cannot itself authorize removal. Actual image-store
mapping and registry availability on the host are unproven here. All live
acceptance rows remain unchecked in tasks.md and operator-acceptance.md.
This implementation does not close the broader resource-limits or cloud-browser
capability; root-run physical-memory delegation remains an independent blocker.

## Default-off activation amendment

Fable exact-head review of the preceding candidate approved the data boundary
but required an installed dry-run before --apply could fire. Inspection found
installer success AND rollback automatically enable all timers; the workflow
invokes it after successful deploy. No no-activate option exists. Global DRY_RUN
does not stop transcript rotation, which checks only its CLI --dry-run.

Lead authorized the smallest fail-safe amendment: exact retention-only opt-in1
AND --apply; absent/0 is read-only, malformed values refuse, opt-in alone cannot
authorize effects. Alarm and rotation behavior remain unchanged. Root performs
installed direct-helper dry-run before changing the opt-in; not a full service
start. Runtime root flags/key updates remain unperformed in this lane.

Same Linux command above:155 passed/no skips,32.92s, including installer closure
and activation matrix. Added explicit transcript-path proof afterward; the
three helper/entrypoint suites then passed98/no skips,7.48s. The transcript test
uses an injected callback and temporary path, not customer data: both retention
opt-in0 and global DRY_RUN1 leave normal rotation enabled, while explicit
rotation --dry-run prevents its callback. Ruff/diff/strict OpenSpec passed.
The amended head needs a fresh exact-head review; the earlier approval is not
relabelled as covering this amendment.
