# Storage observation freshness MVP verification

September 18, 2026 UTC. This is additive observation metadata, not completion of
the resource-policy or owner-attributed storage objective. No cleanup, quota,
workflow, credential or private conversation change. Independent review, required
CI, deployment and rendered acceptance remain release gates owned by the lead.

## Focused evidence

Command (Windows Python 3.14 and Linux Python 3.11.16):

```
python -m pytest -q tests/test_storage_observation_freshness.py tests/test_storage_snapshot_cache.py tests/test_storage_inspect.py tests/test_resource_usage_status.py tests/test_api_status.py tests/test_get_status_primitive.py
```

Windows: **128 passed, 3 skipped**, 14.30s. Linux: **131 passed**, 11.83s.
The Linux run used `scripts/linux_oracle.py -- -q` with the same six files through
native Ubuntu WSL Docker, git 2.47.3 and bubblewrap 0.12.0, working-tree contents.
All nine new cases passed, including failure/zero-capacity unavailable evidence,
retained cached capture time, elapsed age, expiry, TTL settings and privacy scope.
Existing status embedding and universe-overlay integration tests also passed.

`python -m ruff check tinyassets/storage/__init__.py tests/test_storage_observation_freshness.py tests/test_storage_snapshot_cache.py`,
plugin generation/import probe, `git diff --check`, and strict validation of
`observe-attributable-storage` passed. Main capability spec synchronized additively.

## Baseline comparison for corrected test

The first Windows run had **127 passed, 3 skipped, 1 failed**: existing
`test_a_caller_cannot_poison_the_next_callers_snapshot` wrote `critical` then
asserted actual pressure was not `critical`. The local volume was already
critical, so its premise was environmental. Reproduced the same single failure
on unchanged storage/cache-test source in the separate delivery worktree with:

```
python -m pytest -q tests/test_storage_snapshot_cache.py::test_a_caller_cannot_poison_the_next_callers_snapshot
```

That baseline returned **1 failed**, 0.44s, at the identical assertion. The test
now poisons with a non-enum sentinel, retaining the deep-copy isolation assertion
without assuming the host's free-space state. Production pressure behavior is
unchanged. No baseline code or delivery PR files were edited.

## Read-only production diagnostic motivating this slice

Before implementation, `scripts/droplet.py ssh` ran host/container `df -B1` and
the existing `inspect_storage_utilization` in a fresh container process. Host `/`
and container `/data` agreed: total 52,626,063,360 bytes, available 12,430,667,776,
df 76%; runtime reported 0.7638 and pressure `ok`, canonical root `/data`, TTL
unset (60s default). Enumerated transcripts were 148,570,936 bytes and wiki
9,948,377 bytes. This does not inventory Docker images or full host ownership.
No private contents were read. A service-principal served-status attempt returned
403; no claim is made about the private app's actual tool response or memory.
