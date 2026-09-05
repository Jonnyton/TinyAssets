# Codex catalogue compatibility — independent Claude review

Date: 2026-09-05 00:10 UTC. Environment: Windows working tree,
`codex/provider-catalogue-compat`, PR #2964. Author: Codex; reviewer: Claude
subscription subprocess through `scripts/peer_agent.py`, read-only, no delegates.
Reviewed implementation `11ff44b4` plus the four-file round-two follow-up diff
(smoke fixture, platform keepalive, provider tests, compatibility tests).

## Review history

1. Shape ADAPT: approve CLI 0.153.4 and explicit workspace-write with unchanged
   headless Never approval; also update keepalive, prove real CLI startup rather
   than help parsing, compare feature defaults, and retain scrubbed structured
   failures on both nonzero paths. All incorporated.
2. Implementation ADAPT: implementation correct and fixture credential-safe;
   add actual MCP bearer and outgoing tool-spec assertions, propagate three
   account/plugin disables into keepalive, and assert disables on non-served
   launches. All incorporated, with the baseline distinction below.
3. Final APPROVE: reviewer checked the complete four-file follow-up, shared
   provider launch args and OS sandbox mounts. No remaining review blocker and
   no fourth review warranted. Linux CI remains the landing gate.

## Evidence-backed disagreement resolved

The proposed test classified native `apply_patch` as a shell-execution tool.
Real, credential-free CLI comparisons reproduced that tool on both deployed
0.135.0 and candidate 0.153.4, with shell tools disabled. The reviewer accepted
this as unchanged baseline behavior, not an authority expansion. The universe
and credential files remain read-only inside the outer jail; chat workspace is
scratch tmpfs. The smoke reports native file patching explicitly and rejects
actual shell-execution tools instead of inventing a new unsupported flag or
custom model catalogue to hide baseline behavior.

Final reviewer positions:

- AGREE: inspect real model-request tool specs recursively and fail closed if
  they cannot be inspected; reject shell, local_shell, exec_command, write_stdin,
  and unified_exec; verify the fixture bearer on every MCP request.
- AGREE: keepalive disables account apps, plugins, and remote plugins.
- AGREE: both non-served launch variants assert those adjacent argument pairs.
- AGREE with DISAGREE_EVIDENCE: baseline native patching remains contained by
  unchanged read-only universe/auth mounts and scratch chat workspace.

The substantive final verdict was recovered from transcript
`f8dad2d5-764f-4b96-8356-94edd68910d2` because the wrapper retained an unrelated
closing-hook message. That closing message's incorrect reference to a slow-exit
line is not evidence; the actual code sends both nonzero exits through
`_codex_failure_excerpt`, as accepted in the implementation review.

## Verification and limits

Windows focused suite: 189 passed, 3 skipped; follow-up selection: 83 passed.
Ruff, actionlint, plugin mirror/import probe passed. Exact command:
`python scripts/codex_cli_smoke.py npm.cmd exec --yes
--package=@openai/codex@0.153.4 -- codex` (also run with 0.135.0).
Both reported MCP bearer delivered, no shell specs, fake auth refused,
`native_file_patch_advertised=True`. No user credentials or model inference;
fresh home and allowlisted environment, local fake MCP and model endpoints.

PR Linux Docker run `33931379361` installed 0.153.4 and passed the original
startup smoke. The strengthened final smoke must pass the next CI image build.
Local Linux oracle was attempted but Docker Desktop's engine was unavailable.
No live app/checklist recovery is claimed by this review. The configured default
model is absent from the visible catalogue; that alone does not prove it is
rejected by model inference, so model selection remains untouched pending the
exact app retest.

VERDICT: APPROVE
