## MODIFIED Requirements

### Requirement: The engine turn is confined by a fail-closed sandbox

Every universe-intelligence engine turn SHALL derive an immutable trusted-callsite `ExecutionRequirement` with `workload=inference_only`, `profile=provider_cli`, an exact `tool_denied` policy digest, `minimum_isolation=os_isolated`, a closed empty-projection reference and digest, a scoped-egress requirement reference and digest, closed credential delivery `none|opaque_brokered`, and the #1784-owned authority-evidence reference. `provider_cli` is an execution profile, not a workload. The requirement SHALL be attached to the router-minted immutable `ProviderInvocation` owned by provider routing and consumed by `ProviderExecutor.start()` at launch admission. Neither the founder message, universe content, provider configuration, routing policy, environment, nor an assigned provider may supply, lower, or replace it.

The trusted call site SHALL assemble the reply and learning-extraction prompts from the admitted universe grounding files before provider launch. The provider process SHALL receive no universe-directory, repository-root, current-working-directory, credential/vault, auth-home, or host-path projection and SHALL expose no Bash, filesystem, WebFetch, scheduling, messaging, MCP, or future unenumerated tool. A complete universe root SHALL never be projected because it may contain credential and provider-child descendants. `opaque_brokered` credential delivery SHALL expose no raw key, token, auth file, or other recoverable credential material to model-controlled work.

Admission SHALL use the closed isolation order `os_isolated < vm_isolated` and succeed only when the selected backend's distributed-execution-owned profile/tier binding supports `provider_cli`, meets or exceeds `os_isolated`, and every resolved policy, projection, and egress digest plus credential-delivery class and authority-evidence reference matches the immutable requirement. Missing, stale, mismatched, or unknown requirement fields, backend binding, profile support, policy, projection, egress, credential delivery, authority evidence, or tier SHALL raise the consumed non-fallbackable execution-admission exception before provider launch. That exception SHALL terminate the turn, cross universe and graph boundaries unchanged, and SHALL NOT become provider cooldown, retry, alternate provider, local fallback, explicit fallback, degraded output, or fallback prose. Provider errors after successful admission remain distinct.

Cached sandbox status and installed-executable probes SHALL be diagnostic only and SHALL NOT derive, satisfy, or attest this requirement. No platform-specific downgrade, CLI-only mode, in-process execution, or same-UID child process satisfies `os_isolated`.

#### Scenario: both universe turns use tool-denied inference

- **WHEN** `converse` runs its reply turn and learning-extraction turn
- **THEN** each trusted call site derives `inference_only/provider_cli/tool_denied/os_isolated` with matching policy, projection, egress, credential-delivery, and authority-evidence references
- **AND** each immutable provider invocation carries that requirement to executor admission
- **AND** neither turn exposes a provider tool

#### Scenario: prompt grounding does not project the universe root

- **WHEN** trusted code grounds a universe turn in selected OKF files
- **THEN** it injects admitted content into the prompt before launch
- **AND** the execution workspace projection remains empty
- **AND** the universe root and its credential, vault, provider-child, and auth descendants are absent

#### Scenario: unavailable or unknown isolation terminates the turn

- **WHEN** the requirement, one of its bound references/digests, or the backend profile/tier binding is missing, stale, mismatched, unknown, or below `os_isolated`
- **THEN** execution admission raises the consumed non-fallbackable admission exception before provider launch
- **AND** the reply and learning turn do not retry or fall back through another provider or execution mode

#### Scenario: diagnostic availability grants no execution authority

- **WHEN** a cached sandbox diagnostic reports an available host executable
- **THEN** that result does not satisfy execution admission or select a backend
- **AND** only an explicit distributed-execution-owned backend profile/tier binding can satisfy the requirement
