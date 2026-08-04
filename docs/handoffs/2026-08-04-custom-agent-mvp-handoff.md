# Custom-agent MVP handoff

**Date:** 2026-08-04 (America/Los_Angeles)
**Scope:** remixed universe agents → private bindings → secure cloud execution → app conversations → workflow iteration
**Handoff status:** **incomplete for live customer acceptance**; code foundations are substantially landed, but deployment and rendered proof remain open.

## Executive summary

The approved first demo is a remixed, always-on Slack intelligence agent. A user discovers a public agent, blends components from other users, customizes it, creates a private universe binding, talks to it through Slack, watches it draft/test/evaluate/revise a workflow, approves activation, turns off their computer, and later receives a scheduled result. A second account can remix only the portable public definition—not goals, conversations, credentials, destinations, or runtime state.

The repository now has the immutable definition/interchange substrate, private binding and runtime-authority foundations, app ingress/custody/reply/outbound seams, and cloud queue/runtime foundations. The final customer path is not yet proven: the cloud cutover, a real registered requester binding, workflow-iteration successor, rendered Slack conversation, 24-hour PC-off run, export/re-import, second-account remix, and post-fix organic use are still required.

## What is landed

| Area | Evidence | Truth |
|---|---|---|
| Public custom-agent definitions, private bindings, remix lineage | `openspec/specs/universe-custom-agents/spec.md`, `tinyassets/custom_agents.py` | Landed and locally tested; no finite starter catalog |
| Foreign import/export and cross-user blending | `openspec/changes/agent-interchange-pipeline/tasks.md`, `tests/load/test_agent_interchange_load.py` | Implementation and local load evidence landed; live cross-user proof remains open |
| Immutable runtime manifest/compiler/principal | `openspec/changes/activate-custom-agent-runtime-core/` | Dark runtime foundations landed; deployment/live proof remains open |
| Cloud continuation/epoch-2 consumer | `docs/audits/2026-08-03-cloud-drain-epoch2-consumer.md` | Local shaped-load evidence landed; production activation/cutover remains open |
| App ingress, custody, mapping, reply authority, outbound receipt | PRs #2246, #2260, #2268, #2274 and corresponding OpenSpec changes | Server-owned dark seams landed; real app effect/rendered conversation remains open |
| Provider enrollment shape hardening | PR #2281, merged commit [`c5358941`](https://github.com/Jonnyton/TinyAssets/commit/c53589418427b34d9d4d83eefff42586f52cad40) | Landed on `main`; hosted gates green; exact-head Claude security review **APPROVE** |

The #2281 repair specifically rejects malformed enrollment shapes instead of coercing them: strings cannot stand in for lists, `None` cannot stand in for required strings, booleans cannot stand in for integers, wildcard owners remain forbidden, ambiguous entries fail closed, and the packaged mirror is byte-identical.

## What remains open

### 1. Cloud binding and cutover

OpenSpec: `openspec/changes/activate-requester-owned-cloud-compute-binding/`, tasks 3.2–3.3.

Required evidence:

- focused resolver/bind tests, strict OpenSpec, lint, and the concurrency/load proof;
- dark deployment with the correct production secret propagation;
- public canary on the deployed revision;
- one explicit owner enrollment reconciled through the rendered connector;
- single-active tray-to-cloud cutover with no overlap.

Do not claim this from local tests or a dark code path. Production evidence in the epoch-2 audit explicitly says deployment, public canary, rendered phone control, tray cutover, and PC-off proof are not yet run.

### 2. Workflow iteration successor

The coordination contract (`activate-custom-agent-runtimes`, tasks 2.3 and 2.5) requires a separately admitted successor for:

`drafted → tested → evaluated → revision proposed → owner approved/rejected → activation`.

The successor must reuse ordinary Branch/Run/evaluator/Gate owners, keep tests effect-free by default, freeze evaluation criteria, preserve prior versions, and prevent silent self-modification. A draft OpenSpec proposal was structurally validated during this session but was intentionally not claimed or committed because the current Codex identity already owns the active cloud-binding change. Create/admit it only after that ownership handoff.

### 3. Live acceptance

The V1 acceptance boundary is intentionally stronger than unit tests:

- rendered Claude.ai or ChatGPT connector conversation through the live installed connector;
- real Slack ingress/reply, including duplicate-delivery recovery;
- a real other-creator remix and private binding;
- workflow draft, bounded dry test, frozen evaluation, evidence-backed revision, approval, and activation;
- continuous 24-hour computer-off scheduled run including worker restart;
- canonical export/re-import and second-account remix isolation;
- post-fix organic-use evidence, or a dated monitoring row explicitly saying none exists.

No live Slack message, production secret, cloud cutover, or connector installation was performed by this session.

## Ownership and collision boundaries

- **Cloud activation/drain:** existing cloud-drain owner and the `activate-requester-owned-cloud-compute-binding` change. Do not edit its declared runtime/deploy files from an unrelated branch.
- **App conversation/custody:** existing app ingress, mapping, custody, reply-authority, and outbound-adapter lanes. Do not create a second webhook verifier, inbox, custody issuer, reply gate, or MCP handle.
- **Workflow iteration:** next successor after cloud/runtime and Branch/run/evaluation authority handoffs. Use a separate OpenSpec change and exact file claim.
- **Live proof:** host/browser route. Direct MCP calls, local scripts, and DOM-only checks are supporting evidence only.

## Recommended next sequence

1. Re-read `STATUS.md`, run `scripts/claim_check.py`, and confirm the cloud-binding row has been handed off or released.
2. Finish OpenSpec task 3.2 for the cloud-binding change, including fresh exact-head review and §14 evidence.
3. Perform the authorized dark deployment/canary and rendered owner-enrollment proof; record the exact deployed revision and environment.
4. Admit `enable-custom-agent-workflow-iteration` with the owner/file boundary above; implement tests first and reuse existing authority owners.
5. Run the rendered Slack golden path and PC-off/restart window; write `output/user_sim_session.md` and a dated audit artifact.
6. Sync delta specs, archive completed changes, delete landed rows from `STATUS.md`, and leave only concrete monitoring/host-action rows.

## Useful verification commands

```powershell
git fetch origin --prune
git log -1 --oneline origin/main
gh pr view 2281 --json state,mergedAt,mergeCommit
python scripts/claim_check.py --provider <provider>
openspec list --json
openspec validate activate-requester-owned-cloud-compute-binding --strict
python -m pytest -q tests/test_provider_work_enrollment.py tests/test_cloud_automation_api.py
python -m ruff check tinyassets/provider_work_enrollment.py tests/test_provider_work_enrollment.py
```

For the final user surface, follow `.agents/skills/ui-test/SKILL.md`: use one visible Claude.ai/ChatGPT mission tab, a real installed connector, user-like prompts, and log rendered results. Do not replace that proof with a direct MCP call.

## Non-claims

This handoff does **not** claim that the full MVP is built, deployed, activated, or customer-proven. It records a strong dark foundation and one merged security repair, while keeping the exact production and user-evidence gaps visible for the next operator.
