# Claude implementation review — capability-first Voice tap

Date: 2026-09-04

Reviewer: Claude Opus, isolated read-only CLI session

Reviewed tree: uncommitted `codex/voice-capability-first-tap` working tree after the capability-first implementation and before the adaptations below

Verdict: **ADAPT**

The normal `peer_agent.py` dispatch was attempted first. Its default model alias exited with no result, and a retry inherited unrelated Claude task context. The valid review was therefore run in a fresh non-persistent Claude CLI session from an external temporary directory with read-only access to this worktree. The reviewer read the working-tree files directly because Git commands were permission-blocked.

## Structured findings

1. **AGREE — disabled-session capability discovery is read-only and does not widen authority.** `voice_capability` resolves only the current serving authority and performs founder-home, admin ACL, grant, connection, capability, URL, method, and endpoint-policy reads before returning a secret-free status. It does not construct the proxy, dereference a credential, or make an outbound request.
2. **AGREE — `subscription_cli` routes the Voice tap to the existing connection surface without microphone or session access.** The server returns `provider_voice_unsupported` plus `existing_connection_surface`; the browser renders `Voice · Connect` and passes explicit user-owned-authority guidance to `showConnect`.
3. **AGREE — a compatible binding cannot start while session switches are off.** The status response is `state: disabled`; session creation fails at its first gate; the route returns 404 before reading the offer; and the browser test proves no disclosure, microphone request, connection navigation, or session request.
4. **AGREE — disclosure-then-start remains intact when switches and a compatible current binding are present.** Acceptance re-reads capability and refuses a changed disclosure identity before start.
5. **AGREE — no fallback, separate Voice credential, platform credential, or platform-paid path was introduced.** Resolution inspects exactly one current provider and the proxy remains pinned to its exact connection and grant.
6. **DISAGREE_EVIDENCE — one spec promise exceeded the implementation.** `voice_authority_invalid` returned `remediation: none`, so a revoked or rotated grant could leave the Voice button permanently disabled even though reconnecting through the existing surface was the correct remedy. The reviewer also found that a transient status failure left the client in a disabled `checking` state until reload, and that the now-always-reachable status endpoint lacked a per-identity work bound.

## Adaptations applied

- `voice_authority_invalid` now uses `existing_connection_surface`; no authority check was relaxed.
- Every inactive Voice tap now re-runs capability discovery. The `checking` state remains tappable, so a transient failure is recoverable without reload.
- Authenticated status checks are capped at 60 per identity per minute before home-universe or capability resolution, with bounded limiter memory.
- Browser coverage now separately proves: unsupported provider with session flags off opens setup; compatible provider with session flags off remains closed; a transient `checking` state retries; neither path requests microphone access.

Post-adaptation verification on 2026-09-04:

```text
python -m pytest -q tests/test_realtime_voice.py tests/test_onboarding_app.py
125 passed in 13.81s

python -m ruff check tinyassets/onboarding/realtime_voice.py tinyassets/onboarding/__init__.py tests/test_realtime_voice.py tests/test_onboarding_app.py
All checks passed!

python packaging/claude-plugin/build_plugin.py
Import probe: probe-ok

openspec validate negotiate-user-owned-voice-capability --strict
Change 'negotiate-user-owned-voice-capability' is valid
```

The review's blocking findings are resolved in the working tree. A fresh exact-head check is still required after commit because the public app and authenticated status route changed after this verdict.
