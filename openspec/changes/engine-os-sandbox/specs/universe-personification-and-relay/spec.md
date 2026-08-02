## MODIFIED Requirements

### Requirement: The engine turn is confined by a fail-closed sandbox

Every universe-intelligence engine turn SHALL derive an immutable
trusted-callsite logical `ExecutionRequirement` with
`workload=inference_only`, `profile=provider_cli`, exact policy, isolation,
empty-projection, egress, credential, and authority-evidence references plus
digests. `provider_cli` is an execution profile, not a workload. For an
ordinary provider-backed turn, the #1784/R2-1a owner SHALL seal the requirement
into its router-minted immutable `ProviderInvocation` and
`ProviderExecutor.start()` SHALL consume it at launch admission. For an
`accepted_market` turn, the connector/distributed-execution owners SHALL seal
the same logical requirement into the B2/B13 execution capsule before
pre-routing; that path SHALL NOT create an ordinary `ProviderInvocation`,
enter `ProviderExecutor`, or consult an ordinary provider chain. Neither the
founder message, universe content, provider configuration, routing policy,
environment, nor an assigned provider may supply, lower, or replace the
logical requirement.

The trusted call site SHALL assemble the reply and learning-extraction prompts
from the admitted universe grounding files before launch. Model-controlled
work SHALL receive no universe-directory, repository-root,
current-working-directory, credential/vault, auth-home, or host-path
projection and SHALL expose no Bash, filesystem, WebFetch, scheduling,
messaging, MCP, or future unenumerated tool. A complete universe root SHALL
never be projected because it may contain credential and provider-child
descendants. The credential-vault-owned requirement SHALL prove that no raw
key, token, auth file, or other recoverable credential material reaches
model-controlled work; this lane defines no credential-delivery mechanism.

The combined pre-launch and post-launch checks SHALL require the
distributed-execution-owned backend binding and request-bound evidence to
prove the complete `os_isolated` guarantee set for the exact execution:
kernel-enforced daemon separation, exact default-deny filesystem projection,
exact default-deny network enforcement, explicit resource limits, absent
platform secrets and undeclared devices, bounded cleanup, and evidence bound
to the logical requirement and actual launch. A `vm_isolated` label is
stronger only when the combined checks prove every base guarantee plus a
distinct guest-kernel boundary and default-deny host-device passthrough.
Acceptance compares proved property-set inclusion, not labels or booleans.

Every resolved policy, isolation, projection, egress, credential, and
authority reference/digest SHALL match the logical requirement. Pre-launch
admission SHALL validate trusted requirement/capsule data, profile and
enforcement-mechanism support, exact planned launch configuration, current
capability/self-test evidence, and the backend protocol's commitment to
return request-bound launch evidence. Pre-launch admission SHALL NOT attest
the future execution, enforcement, cleanup, or result. Missing, stale,
mismatched, untrusted, malformed, or unknown pre-launch data SHALL raise the
shared non-fallbackable `ExecutionAdmissionError` before launch.

Post-launch validation SHALL then verify returned evidence bound to the same
requirement/capsule and actual execution and SHALL alone prove the complete
guarantee set for that execution. Missing or invalid actual-launch evidence
SHALL raise
`ExecutionAdmissionError(reason=backend_evidence_invalid)` and the model
output SHALL NOT become a successful reply, learning result, or fallback
input. Admission errors in either phase SHALL terminate the turn, cross
universe and graph boundaries unchanged, and SHALL NOT become provider
cooldown, retry, alternate provider, local fallback, explicit fallback,
degraded output, or fallback prose. Authority errors, provider errors after
successful pre-launch admission, and accepted-market/backend execution
failures remain distinct.

Cached sandbox status and installed-executable probes SHALL be diagnostic only
and SHALL NOT derive, satisfy, or attest this requirement. No
platform-specific downgrade, CLI-only mode, in-process execution, or same-UID
child process proves the required guarantee set.

#### Scenario: both universe turns use tool-denied inference

- **WHEN** `converse` runs its reply turn and learning-extraction turn
- **THEN** each trusted call site derives `inference_only/provider_cli/tool_denied` with matching isolation, projection, egress, credential, and authority-evidence references/digests
- **AND** an ordinary provider invocation or accepted-market B2/B13 capsule carries that same logical requirement to admission
- **AND** neither turn exposes a provider tool

#### Scenario: accepted-market inference stays before ordinary routing

- **WHEN** an accepted-market universe runs a reply or learning turn
- **THEN** B2/B13 seals the logical requirement into its execution capsule before pre-routing
- **AND** no ordinary `ProviderInvocation`, `ProviderExecutor`, role chain, policy chain, or provider fallback is used

#### Scenario: prompt grounding does not project the universe root

- **WHEN** trusted code grounds a universe turn in selected OKF files
- **THEN** it injects admitted content into the prompt before launch
- **AND** the execution workspace projection remains empty
- **AND** the universe root and its credential, vault, provider-child, and auth descendants are absent

#### Scenario: unavailable or unknown isolation terminates the turn

- **WHEN** the requirement, one of its bound references/digests, or current backend profile/guarantee evidence is missing, stale, mismatched, malformed, unknown, or fails property-set inclusion
- **THEN** execution admission raises shared `ExecutionAdmissionError` before launch
- **AND** the reply and learning turn do not retry or fall back through another provider or execution mode

#### Scenario: invalid actual-launch evidence cannot succeed

- **WHEN** post-launch validation cannot bind returned evidence to the admitted requirement/capsule and actual execution
- **THEN** it raises `ExecutionAdmissionError(reason=backend_evidence_invalid)`
- **AND** no provider output becomes a reply, learning result, success, or fallback input

#### Scenario: diagnostic availability grants no execution authority

- **WHEN** a cached sandbox diagnostic reports an available host executable
- **THEN** that result does not satisfy execution admission or select a backend
- **AND** only an explicit distributed-execution-owned backend profile/guarantee binding with request-bound evidence can satisfy the requirement
