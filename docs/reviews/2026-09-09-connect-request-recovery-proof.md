# Connect-request local authority recovery

September 9, 2026, Windows Python 3.14 and supplemental Ubuntu WSL Python
3.11.15. This patch corrects the existing request predicate, not the full
two-request feature or remote provider-health recovery.

## Change

The request rail now uses `resolve_current_serving_provider_authority` with the
authenticated owner and canonical universe directory instead of treating a
surviving serving binding as usable power. It reuses local assignment/custody/
grant validation, makes no upstream inference call and reads no host credentials.
The generic request no longer says only Claude/OpenAI subscriptions are supported.

## Verification

Baseline at 26d50d8f:
`python -m pytest -q tests/test_pending_requests.py tests/test_open_serving_bind.py --tb=short`
returned **50 passed**, 8.25 seconds. New regression tests against that old code
returned **3 failed, 1 passed**: the real revoked grant and rotated credential
reference still looked powered, and the canonical authority seam was unused.
An initial test import was corrected to the repository's `tests.*` package before
this reproduction; collection failure was not evidence of the runtime bug.

After correction, with actual subscription-custody removal/rail repetition added:
`python -m pytest -q tests/test_pending_requests_power.py tests/test_pending_requests.py tests/test_open_serving_bind.py tests/test_provider_serving_binding.py tests/test_mirror_parity_gate.py --tb=short`
returned **83 passed**, 14.52 seconds on Windows. Tests use test-only vault
contents, not production credentials or a real provider call.

`wsl -d Ubuntu -- bash -lc 'cd /mnt/c/Users/Jonathan/.codex/worktrees/0a7f/TinyAssets && bash output/receiver-linux-proof.sh tests/test_pending_requests_power.py tests/test_pending_requests.py tests/test_open_serving_bind.py tests/test_provider_serving_binding.py'`
returned **68 passed**, one upstream warning, no skips, 18.00 seconds; environment
root `/tmp/tiny-receiver-proof.PLtGA4`. This is supplemental Linux evidence.

`python -m pytest -q tests/test_served_failure_notice.py tests/test_mirror_parity_gate.py --tb=short`
returned **19 passed**, 5.92 seconds. Lint passed for both canonical modules and
the new test module. Plugin mirror rebuilt 401 files with a passing import probe;
`git diff --check` passed.

## Open boundaries

- Remote expiration/rejection with unchanged local custody is not detected by
  this check. The existing concern remains open; error copy does not falsely
  promise an already-visible request for every remote auth failure.
- Automatic OpenRouter plus generic-LLM requests, the direct key-page link,
  no-model-needed secure deposit/register/serve chain, existing-connection reuse
  and usable agent capabilities remain required, not accomplished by this patch.
- Independent review is running; no approval, push, CI, deployment or rendered
  post-deploy user recovery is claimed here.
- Rollback is a normal revert of this stateless predicate/copy change through
  the release pipeline. It has no migration or user-record deletion; rolling
  back would restore the known stale-binding recovery limitation.
