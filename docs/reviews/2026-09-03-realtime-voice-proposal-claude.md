# Claude review: first-class Realtime voice proposal

Date: 2026-09-03

> Superseded in part by the founder's later 2026-09-03 authority correction. This review approved
> the earlier proposal shape; it does not approve the revised subscription-compatibility finding,
> capability-status route, or locked-resource UI. See
> `docs/reviews/2026-09-03-realtime-voice-authority-correction-review.md`.

Environment: read-only Claude Sonnet 5 peer in `codex/first-class-voice` at the proposal gate. The peer wrapper's stop hook replaced the saved final message with an unrelated dispatch-ledger tail; this review was recovered verbatim from the same Claude session transcript (`b4fb91f6-48f3-4fc0-84df-10b4e7bb373f`), where it appears as the completed pre-hook answer.

**AGREE** — `converse` remains sole primary writer (Hard Rule 3, PLAN.md:263-275). `realtime-voice-conversation/spec.md:33-44` and `universe-personification-and-relay/spec.md:3-15` both force every spoken turn through `MCP.converse` exactly once and explicitly refuse to store/render an untooled Realtime answer. `provider-routing/spec.md:3-21` blocks the voice allowance from making API-key writers eligible even when `TINYASSETS_ALLOW_REALTIME_VOICE_API` is on. This is the correct shape and matches how the existing text path already refuses non-founder callers (`universe-personification-and-relay/spec.md:125`), so voice's founder-home-only resolution (design.md:44) isn't an invented restriction — it mirrors the current model.

**AGREE** — Credential custody and ambient-key fail-closed behavior is correctly specified. `credential-vault/spec.md:12-16` explicitly refuses to fall back to a process-global `OPENAI_API_KEY` or another universe's credential — this is the exact pattern already established elsewhere in the repo (memory: ambient-credential-fallback-is-an-identity-leak). `no-store` responses, secret redaction from logs/exceptions, and short-lived-only exposure (`credential-vault/spec.md:18-22`) are all fail-closed. The dedicated `TINYASSETS_REALTIME_VOICE_ENABLED` / `TINYASSETS_ALLOW_REALTIME_VOICE_API` two-flag gate (design.md:51-57), rather than overloading `TINYASSETS_ALLOW_API_KEY_PROVIDERS`, correctly avoids widening general API-key routing eligibility as a side effect of enabling voice.

**AGREE** — Feasibility claims (WebRTC + server-minted ephemeral secret, semantic VAD with `interrupt_response`, 60-minute provider ceiling with a local 30-minute cap, bounded reconnect, "guardrail not guarantee" on transcript fidelity) are internally consistent and each has a named, addressed failure mode in design.md:83-92 and the corresponding spec scenarios (`realtime-voice-conversation/spec.md:20-32`, `:46-62`, `:76-88`). Note: I cannot independently verify the cited OpenAI endpoint/model names (`gpt-realtime-2.1`, `/v1/realtime/client_secrets`) against current OpenAI docs — those are past my training cutoff — but the design correctly treats this as external fact to re-verify at implementation time rather than something to take on faith now, and CSP infrastructure to extend already exists (`tinyassets/onboarding/__init__.py:260`), so the plumbing claim is grounded.

**AGREE** — Privacy/retention/rollout is sufficiently specified for a pre-code gate: no raw-audio persistence (`realtime-voice-conversation/spec.md:64-74`), disclosure-before-capture, non-authoritative usage estimates with no promised spend ceiling (explicitly flagged as an open question, design.md:106-107), staged rollout with kill switch and flag-only rollback (design.md:94-101). This is proportionate to "shape before hardening" (AGENTS.md Quality Gates) for a flag-gated, no-live-credential first slice.

**AGREE** — First slice is properly bounded per delivery-flow and Hard Rule 4: tasks 2.x/3.x require deterministic tests with both flags off and no paid call (tasks.md:8-9, 13-15); nothing merges, deploys, spends, or publishes in this slice (proposal.md:13, design.md:96). The founder-decision open question (design.md:105) doesn't block the reversible slice — it ships with a stated safe default (user-owned-only) that's already what the specs encode, consistent with Hard Rule 4's "never block a workflow gate on human input when a safe default exists."

**AGREE** — No conflict with `codex/ios-store-release` found. The proposal explicitly declines to touch signing/enrollment/release-metadata/publication files (proposal.md:34, design.md:81, tasks.md:19) and only hands off permission-string/privacy-copy requirements. I found no existing host-actions.md or concerns/ entry that this proposal contradicts.

**DISAGREE_CONCERN** — `docs/reference/environment-variables.md` (the canonical catalog AGENTS.md's "Configuration" section names) has no task assigned to add `TINYASSETS_REALTIME_VOICE_ENABLED` / `TINYASSETS_ALLOW_REALTIME_VOICE_API` (design.md:53). tasks.md 2.1 covers implementing the flags but not documenting them in the catalog. Minor, non-blocking — easy to fold into task 2.1's PR — but worth naming explicitly so it isn't dropped.

**DISAGREE_CONCERN** — The mismatch-telemetry requirement (`realtime-voice-conversation/spec.md:43-44`, `universe-personification-and-relay/spec.md:11-14`) says content-free mismatch evidence is recorded but doesn't specify where/how that evidence surfaces to an operator (a log line, a metric, a status field?). Given `get_status`'s "trust-critical tools are self-auditing" principle (PLAN.md:559), this should probably be a structured caveat rather than an unspecified sink. Worth a line in design.md before task 3.2, not blocking for the reversible slice since it has no live traffic yet.

No blocking pre-implementation findings.

VERDICT: AGREE
