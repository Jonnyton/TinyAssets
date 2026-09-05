# Verification

## 2026-09-04 production dark deployment

- Environment: production at `https://tinyassets.io/mcp` and `https://tinyassets.io/mcp/app`.
- Merge: PR #2841 merged as `84ee8ae6847dc4aa929b025ad65ea47fe9e96449` at `2026-09-04T06:28:16Z`.
- Deployment command: `gh run view 33844772622 --json status,conclusion,headSha,event,workflowName,jobs`.
  Result: `Deploy prod` completed successfully for the exact merge SHA at
  `2026-09-04T06:33:31Z`; the fail-safe deploy reported a healthy container on
  image digest `sha256:9fcbecabd921b12397f3d447157e9be228a43885841e4712975da1f6a2e782d0`.
- Release receipt command: `gh run view 33844772622 --log`.
  Result: the deploy published `release-state.git_sha` equal to the exact merge
  SHA, with `active_identity_status=running_healthy` and
  `forward_deploy_status=succeeded`.
- Public canary: the same authenticated deploy job ran
  `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles`
  successfully after the container became healthy. The local shell did not
  contain the canary bearer, so no unauthenticated local rerun is represented as
  equivalent evidence.
- Individual production gate check:
  `python scripts/droplet.py ssh -- 'for k in TINYASSETS_REALTIME_VOICE_ENABLED TINYASSETS_ALLOW_REALTIME_VOICE_API; ... docker exec tinyassets-daemon printenv "$k" ...; done'`.
  Result: both `TINYASSETS_REALTIME_VOICE_ENABLED` and
  `TINYASSETS_ALLOW_REALTIME_VOICE_API` are unset in the running container, so
  each independently retains its default-off behavior.
- Dark-state source check: `Invoke-WebRequest https://tinyassets.io/mcp/app`
  returned HTTP 200 and the served configuration contained
  `"voice": {"enabled": false, ...}`.
- Rendered check: a host-visible browser loaded the signed-in founder app. The
  single Voice control was present beside the composer, disabled, and the
  rendered status read `Voice is not enabled on this TinyAssets host.` No Voice
  control was clicked and no microphone, provider, credential, or disclosure
  action occurred.
- Authenticated binding check: from that signed-in app, the founder universe was
  asked in ordinary user language to inspect its live serving binding without
  changing anything. Its rendered answer identified `codex` via
  `subscription_cli` as the active binding. It identified the only visible
  `openai_chat` HTTP registration as the inactive old
  `plug-and-play-test-model` artifact. The current binding is therefore not an
  eligible `api_key_http` Voice bridge, and no ready-state or microphone proof
  is presently available.
- CI follow-up: the original desktop release run `33843457460` and its first
  bounded rerun ended without a retained lifecycle verdict. PR #2936 repaired
  the Windows lifecycle supervisor's unbounded capture and process-tree close
  path. Its exact-head rerun `33919243682`, job `101175830777`, completed the
  Windows install/probe/repair/uninstall lifecycle in 50 seconds. The repair
  merged as `2102d6308a79babe6ffcc196e434f1e054986b33`; production reported that
  revision after the authenticated public canary passed on 2026-09-04.

## 2026-09-04 capability-first tap follow-up

- Merge: PR #2924 merged as
  `2bdb7c47577d66e4bfb8fb8de00b6eac606ab76b` at `2026-09-04T19:29:20Z`.
- CI: required tests passed in 15m41s; slow tests, invariants, the browser
  trust-boundary contract, bundle/plugin import probes, Linux/macOS/Windows
  builds, signing checks, and the unsigned Windows install check all passed.
- Cross-family review: Claude returned `ADAPT`; its authority-remediation,
  transient-retry, and status-rate-limit findings were applied. An isolated
  exact-head follow-up returned `APPROVE` for implementation commit `16c06450`.
  A final exact-head receipt review returned `APPROVE` for `319922c9` and is
  recorded on PR #2924.
- Deployment command: `gh run view 33911684121 --log`. Result: the fail-safe
  deploy reported healthy image
  `sha256:af26db43eff2325084353bb3c1e10dfb0a17151882308eb033c0d316cd636d2d`.
  Its authenticated `mcp_public_canary.py --assert-handles` passed, and its
  protected `deployed_sha.py --assert-contains` reported production exactly at
  merge `2bdb7c47577d66e4bfb8fb8de00b6eac606ab76b`.
- Rendered signed-in app proof: the current `codex/subscription_cli` binding
  rendered an enabled `Open provider connection for Voice` control. One tap
  opened the pre-existing provider connection view and explained that compatible
  realtime authority must be user-owned and that TinyAssets will not switch
  providers automatically. No disclosure, microphone prompt, Voice session,
  provider change, or credential action occurred.
- Both Voice-specific production switches remain off.

At the time of this proof, task 5.4 was blocked on the existing provider flow
establishing an eligible current provider and Jonathan explicitly authorizing
the bounded live microphone proof. The later live user correction below
supersedes the provider prerequisite: the compatible user-owned capability is
now present, while the redundant host switch is the remaining implementation
blocker.

## 2026-09-04 live user correction

- Actual user result: a universe powered by the user's ChatGPT connection
  rendered `Voice is not enabled on this TinyAssets host.` from the composer
  Voice control.
- Root cause: `voice_capability()` returned `voice_disabled` only after the
  exact current-provider connection and `tinyassets.voice.v1` capability had
  already validated. The two legacy Voice-specific host switches therefore
  overrode valid user authority and created the dead end; the deterministic
  browser test explicitly expected that failure.
- Corrected contract: the exact user-owned current-provider capability is the
  Voice readiness authority. The generic outbound HTTP switch remains the
  fail-closed transport gate. No platform credential, platform-paid usage,
  implicit provider switch, or second Voice credential path is introduced.
- Acceptance boundary: deploy the correction and prove the authenticated
  rendered app reaches `ready`; stop before microphone permission for
  Jonathan's explicit bounded live test.

### Focused correction verification

- Environment: Windows development worktree on 2026-09-04, based on
  `d8a48fb2` before the correction commit.
- `python packaging/claude-plugin/build_plugin.py` rebuilt the packaged runtime
  mirror and its import probe returned `probe-ok`.
- `python -m pytest -q tests/test_realtime_voice.py tests/test_onboarding_app.py
  tests/test_apply_daemon_env_voice_flags.py tests/test_mirror_parity_gate.py
  tests/test_pre_commit_mirror_parity.py tests/test_invariants_framework.py`
  passed: `163 passed in 33.52s`.
- `python -m ruff check tinyassets/onboarding/realtime_voice.py
  tests/test_realtime_voice.py tests/test_onboarding_app.py
  tests/test_apply_daemon_env_voice_flags.py` passed.
- `python scripts/openspec_flow.py check-change
  negotiate-user-owned-voice-capability --provider codex` returned `ALLOWED`;
  `openspec validate negotiate-user-owned-voice-capability --strict` passed;
  and `git diff --check` passed.
- The first cross-family correction review returned `ADAPT`. Its three narrow
  findings are applied: an explicit `CFG.voice.enabled=false` browser arm,
  non-contradictory transport-unavailable copy in both runtime mirrors, and the
  explicit founder decision boundary in `docs/host-actions.md`. A clean
  exact-head review of implementation commit `eee23c43` returned `APPROVE`
  after confirming all three resolutions and the unchanged authority,
  credential, SSRF, cross-user, transport-gate, and session-time revalidation
  boundaries. Its non-blocking catalog note was also applied by documenting
  `TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED` in the canonical environment
  reference.
