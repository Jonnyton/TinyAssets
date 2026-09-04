# Canary healthcheck helper landing receipt

**Date:** 2026-09-03  
**Author family:** Codex  
**Review family:** Claude  
**Implementation head:** `e2975f7aeb69eb38880e9f8f54e6c508f3fdff33`  
**Verdict:** APPROVE for the exact implementation head above and the receipt-only
PR head named by the `Drain-Review-Head` line in pull request #2808.

## Scope

Production deploy run 33828208714 rolled the candidate image back after its
container healthcheck stayed unhealthy. The healthcheck executes
`/app/scripts/mcp_public_canary.py`, which imports `_canary_common`; the runtime
image copied the first file but not its helper. This patch copies the missing
stdlib-only helper beside the healthcheck script and adds a regression assertion
for the complete in-image module pair.

## Independent review

A read-only Claude reviewer inspected the full diff from
`1b2d33ce76e74c402c46b05f10989935462fa73b` through the implementation head,
reran the focused Dockerfile test, and returned `AGREE` / `VERDICT: APPROVE`.

The reviewer confirmed:

- `mcp_public_canary.py` inserts its own directory into `sys.path`, so copying
  `_canary_common.py` to the same `/app/scripts/` directory is the correct fix;
- the compose healthcheck invokes that exact script path;
- `_canary_common.py` is stdlib-only and reads the canary bearer from the
  environment without embedding or exposing a secret;
- the two-file diff contains no unrelated behavior;
- the static Dockerfile regression test matches the established shape-test
  convention and catches deletion or renaming of either required copy.

## Verification

- 50 focused Dockerfile and image-workflow tests passed on Windows/Python 3.11+.
- The independent reviewer reran `tests/test_dockerfile_shape.py`: 44 passed.
- Ruff and `git diff --check` passed.
- Both pull-request Linux buildx smoke jobs passed in 1m08s.
- The earlier deployment's fail-safe rollback restored the previous image
  healthy before this fix was prepared.

The later receipt-only commit changes no image or test behavior. The PR body
binds that final documentation head to this artifact without requiring a
self-referential commit hash.
