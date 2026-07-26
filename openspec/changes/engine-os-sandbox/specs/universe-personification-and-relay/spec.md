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

Admission SHALL require the distributed-execution-owned backend binding and
request-bound evidence to prove the complete `os_isolated` guarantee set:
kernel-enforced daemon separation, exact default-deny filesystem projection,
exact default-deny network enforcement, explicit resource limits, absent
platform secrets and undeclared devices, bounded cleanup, and evidence bound
to the logical requirement and actual launch. A `vm_isolated` label is
stronger only when it proves every base guarantee plus a distinct guest-kernel
boundary and default-deny host-device passthrough. Admission compares proved
property-set inclusion, not labels or booleans.

Every resolved policy, isolation, projection, egress, credential, and
authority reference/digest SHALL match the logical requirement. Missing,
stale, mismatched, untrusted, malformed, or unknown requirement fields or
backend evidence SHALL raise the shared non-fallbackable
`ExecutionAdmissionError` before launch. That error SHALL terminate the turn,
cross universe and graph boundaries unchanged, and SHALL NOT become provider
cooldown, retry, alternate provider, local fallback, explicit fallback,
degraded output, or fallback prose. Authority errors, provider errors after
successful admission, and accepted-market/backend results remain distinct.

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

- **WHEN** the requirement, one of its bound references/digests, or the backend profile/guarantee evidence is missing, stale, mismatched, malformed, unknown, or fails property-set inclusion
- **THEN** execution admission raises shared `ExecutionAdmissionError` before launch
- **AND** the reply and learning turn do not retry or fall back through another provider or execution mode

#### Scenario: diagnostic availability grants no execution authority

- **WHEN** a cached sandbox diagnostic reports an available host executable
- **THEN** that result does not satisfy execution admission or select a backend
- **AND** only an explicit distributed-execution-owned backend profile/guarantee binding with request-bound evidence can satisfy the requirement
