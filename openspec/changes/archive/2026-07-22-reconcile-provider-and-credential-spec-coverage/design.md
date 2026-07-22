## Context

The provider stack already has a common immutable call envelope, explicit
per-universe routing context, provider registration and quota state, structured
exhaustion diagnostics, subscription-auth health, and a credential-vault
environment boundary. The 2026-07-19 baseline captured fallback, allowlist,
pinning, vault storage, materialization, and auth overlay behavior, but not these
later or previously omitted contracts.

This is a documentation-only reconciliation. The controlling evidence is
current code in `tinyassets/providers/`, `tinyassets/credential_vault.py`,
`tinyassets/cloud_worker.py`, and `tinyassets/api/status.py`, together with the
focused provider, credential, and status tests. Pending `R2-1a` may change how
`set_engine` writes `allowed_providers`; it does not own the provider-call or
credential-environment contracts in this lane.

## Goals / Non-Goals

**Goals:**

- Make the common provider input, output, and explicit universe-scoping
  contracts canonical.
- Capture the difference between binary availability, runtime registration,
  quota/cooldown state, authentication health, and final call diagnostics.
- Specify the default-enabled Codex refresh-viability ladder, its disable flag,
  and the deliberate fail-toward-ok treatment of inconclusive live probes.
- Record how worker quarantine and non-blocking status observation consume the
  same auth-health source differently.
- Record both the ordinary missing-credential stripping guard and the partial-
  overlay/unexpected-error paths where host subscription values can survive.

**Non-Goals:**

- Change provider routing, credentials, status payloads, code, or tests.
- Claim that `is_available()` proves login health or endpoint reachability.
- Claim that cooldown/quota state is durable or shared across processes.
- Claim that `get_status` runs the potentially blocking Codex live probe.
- Claim that inconclusive auth evidence is a positive health proof.
- Claim that the current environment overlay is fully fail-closed.
- Resolve pending `R2-1a`, add providers, encrypt the vault, or introduce a
  remote credential service.

## Decisions

### 1. Keep provider envelopes and explicit universe context in provider routing

`UniverseContext`, `ModelConfig`, `ProviderResponse`, and `BaseProvider.complete`
form the routing boundary. The credential capability owns stored records and
environment materialization; it does not own the general model-call contract.

Alternative considered: put `UniverseContext` in `credential-vault` because it
carries `universe_dir`. That would hide its equally important role in preference,
allowlist, timeout, model, and tool-policy routing.

### 2. Separate availability, cooldown, auth health, and exhaustion evidence

The spec will use distinct requirements for the provider contract, runtime
eligibility/diagnostics, and subscription-auth health. A binary's presence,
quota eligibility, login state, and a failed model invocation answer different
operational questions and have different failure semantics.

Alternative considered: one broad "provider health" requirement. That would
incorrectly imply a single authoritative health value and obscure that several
signals are process-local or best-effort.

### 3. Describe Codex viability as a default-enabled conservative layered verdict

Unless `TINYASSETS_AUTH_VIABILITY_PROBE` is explicitly falsy, presence is the
first gate. A recent valid `last_refresh` (or the mtime of a
valid JSON object lacking it) is a fast-path `ok`; stale, corrupt, or suspicious
state consults a TTL-cached verdict or performs a small real `codex exec` probe
when probing is allowed. Only recognized dead-auth evidence yields
`not_logged_in`; timeouts, missing binaries, unexpected exits, and empty output
without an auth signature remain inconclusive and are represented as `ok` with
detail so healthy workers are not falsely quarantined.

Alternative considered: fail closed on every probe failure. A transient
transport or executable problem would then quarantine a healthy subscription
writer before the normal call and loop-stall paths could report the actual
failure. The shipped disable flag is also recorded honestly: when false, a
present Codex auth file returns presence-only `ok` without freshness parsing.

### 4. Keep the live probe out of chatbot status requests

Workers call the probing form before registration/claiming, while status calls
use `allow_probe=False`. Status may consume freshness and cached disk/memory
verdicts, but a stale uncached credential appears as `ok` with a deferred-probe
detail until a worker establishes evidence. The shared verdict file beside
`auth.json` carries a worker's conclusive result across the daemon/worker
process boundary; the in-memory cache is only a read-only-home fallback.

Alternative considered: probe inline from `get_status`. The configured probe
timeout can be two minutes, which would turn a read-only chatbot health request
into a blocking model call.

### 5. Modify the existing vault overlay requirement with exact inheritance limits

The existing overlay requirement already owns process environment construction.
Its full replacement will state that API keys are stripped under the default
subscription-only policy; when a universe is resolved and its vault changes no
host-subscription variable, inherited `CLAUDE_CODE_OAUTH_TOKEN`,
`CLAUDE_CONFIG_DIR`, and `CODEX_HOME` are removed. The check is all-or-nothing:
if the vault changes even one of those variables, unchanged host values survive.
It also runs inside a broad exception handler, so a non-`ValueError`
overlay/import/resolution failure returns the environment without host-variable
removal; malformed-vault `ValueError` still propagates. A host-local call with
no universe keeps host auth, and a vault-supplied replacement remains.

Alternative considered: add an independent leakage requirement. The behavior
is one indivisible ordering contract—strip defaults, apply the universe vault,
then detect and remove unchanged inherited host auth—so splitting it would
duplicate the same boundary.

## Requirement Evidence

| Capability / requirement | Current source owner | Focused evidence |
|---|---|---|
| Provider call envelopes and explicit context | `tinyassets/providers/base.py`, `router.py`, `call.py` | `tests/test_per_universe_engine_resolution.py`, provider tests |
| Registration, quota/cooldown, diagnostics | `tinyassets/providers/call.py`, `quota.py`, `router.py`, `diagnostics.py` | `tests/test_providers.py`, `test_provider_router_bug029.py`, `test_provider_router_diagnostics.py` |
| Cooldown and auth status surfaces | `tinyassets/api/status.py` | `tests/test_api_status.py`, `tests/test_get_status_primitive.py` |
| Subscription auth and Codex viability | `tinyassets/providers/base.py`, `tinyassets/cloud_worker.py` | `tests/test_provider_auth_quarantine.py`, `tests/test_auth_refresh_viability.py` |
| Universe credential env inheritance and limitations | `tinyassets/providers/base.py`, `tinyassets/credential_vault.py` | `tests/test_credential_fail_closed.py`, `tests/test_credential_vault.py`, `tests/test_s2_engine_assignment.py` |

## Risks / Trade-offs

- [Risk] `ok` is mistaken for a live model-call proof. → Mitigation: state that
  inconclusive Codex probes fail toward `ok` and that Claude health is a
  conservative presence check.
- [Risk] A status reader assumes cooldowns are durable fleet state. →
  Mitigation: name their process-local monotonic storage and best-effort empty
  fallback.
- [Risk] Credential stripping is read as unconditional. → Mitigation: specify
  the resolved-universe and all-variables-unchanged conditions, plus the
  partial-overlay, unexpected-error, host-local, and vault-supplied scenarios.
- [Risk] This lane races `R2-1a`. → Mitigation: limit writes to OpenSpec files,
  re-fetch and re-audit the pending row before sync, and avoid modifying the
  allowlist requirements it may change.
- [Trade-off] Status can temporarily report a stale uncached Codex credential
  as `ok` with deferred detail. This preserves latency and avoids false
  quarantine; worker probing is the authoritative path for a conclusive dead
  verdict.

## Migration Plan

1. Draft delta requirements against the two exact existing canonical owners.
2. Map every requirement and limitation to current source and focused tests.
3. Strict-validate the change and obtain independent grounding/ownership review.
4. Re-fetch main and recheck `R2-1a`; adapt only if its landed behavior changes
   a requirement in this lane.
5. Archive the reviewed change to sync canonical specs, validate the complete
   tree, and compare archived deltas with canonical results.
6. Land through the normal PR path and promote the next collision-free coverage
   slice.

Rollback is a documentation revert; no runtime or data migration occurs.

## Open Questions

None for this as-built slice. Durable fleet-wide cooldown state and stronger
credential storage remain future changes rather than hidden assumptions here.
