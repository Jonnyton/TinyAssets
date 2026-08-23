# Design — compute-agnostic provider set

Scope of THIS change (narrow, per Codex shape review): the **provider
descriptor/executor registry**, **capability observations**, and the **atomic
migration** of existing provider identities into it. It does NOT own selection,
`allowed_providers` authority, credential custody, or the connect UX — those stay
with their owners and consume this substrate. An umbrella roadmap (proposal.md)
coordinates the full program.

## 1. Ownership / state model (sole writer per transition)

```
provider definition ──(register)──▶ credential binding ──(deposit, custody owner)──▶
  enrolled assignment ──(enroll)──▶ selected policy ──(select)──▶ frozen invocation
```

| State | Sole writer | This change? |
|---|---|---|
| **provider definition** (descriptor: endpoint, protocol shape, model, access method) | this change (registry) | **YES — owns it** |
| **credential binding** (secret → opaque reference) | `retire-mcp-provider-secret-deposit` (custody owner) | no — consumes the reference |
| **enrolled assignment** (`provider_work_enrollment`, requester-owned) | existing enrollment | no — reads it |
| **selected policy** (`preferred_provider` + `accepted_fallbacks`) | `user-assigned-llm-policy` | no — provides the open set it ranges over |
| **`allowed_providers` ceiling / admission / launch barrier** | `constrain-set-engine-provider-authority` (merged) | no — never re-writes |
| **frozen invocation** (executor selection at call time) | this change (executor registry) | **YES — owns the executor dispatch** |

**Registration creates ONLY a candidate.** A registered provider definition is not
enrolled, authorized, selected, or routable until the downstream owners act. This is
the invariant that keeps the registry from becoming a back-door authority.

## 2. Provider definition (immutable descriptor)

A `ProviderDefinition` is immutable and content-addressed:

```
ProviderDefinition:
  id:            server-issued, stable (never a user-chosen label)   # allowed_providers resolves THIS
  access_method: "subscription_cli" | "api_key_http"                 # provenance — determines the executor
  protocol:      "openai_chat" | "anthropic_messages" | "cli:codex"  # request/response shape
  endpoint:      normalized HTTPS origin + path (api_key_http only)   # bound to the credential ref
  model:         string
  credential_ref: opaque, tuple-bound (host/principal/universe/provider/assignment-gen)
  visibility:    "private" | "commons"                                # commons = remixable descriptor ONLY
  created_by, created_at
```

`credential_ref` is **immutably bound to `endpoint` + assignment generation**, so
changing `base_url` on a re-register cannot redirect an existing key at a new host
(mirrors the connect_http policy-immutable rule). A **commons/remixed** definition
carries the descriptor only — **never auto-binds the original owner's credential**;
the remixer must supply their own via the custody owner.

## 3. Access-method executors (replaces per-vendor modules)

One executor per access method, selected DETERMINISTICALLY by
`definition.access_method` — **no fallback across methods on ambient credentials**
(Hard Rule #3 evolution):

- **`subscription_cli` → CLI adapter.** The existing `CodexProvider` (and any future
  vendor CLI that permits third-party subscription use) preserved verbatim behind the
  executor interface: `codex exec`, sealed `CODEX_HOME`, sandbox/tool restrictions,
  auth-health probes, budget fencing, telemetry, exact provider identity. `codex`
  stays a stable provider/binding identity.
- **`api_key_http` → protocol encoder over the outbound proxy.** A small protocol
  encoder (`openai_chat`, `anthropic_messages`) — **NOT a vendor SDK** — because an
  SDK accepting an arbitrary `base_url` would bypass SSRF + the credential-blind
  proxy. It emits a request the way `authenticated_external_call` does and sends it
  through the SAME SSRF-hardened outbound substrate (`ConnectionLedger` + credential-
  blind proxy). Compute HTTP **consumes** that substrate; it does not duplicate the
  ledger or reuse a credential-bearing MCP op.

Executor interface (minimal): `execute(invocation, credential_ref) -> response`.
The invocation carries a reference + provenance, never secret material; the secret
is resolved only at the transport-owned boundary (custody owner's proxy).

## 4. Routing equation (the router filters, never synthesizes)

```
effective_candidates =
    selected_ordered_candidates            # from user-assigned-llm-policy (ordered)
  ∩ allowed_providers_ceiling              # from constrain-set-engine-provider-authority
  ∩ live_requester_owned_enrollment       # from provider_work_enrollment
  ∩ request_invocation_capability         # from §5 observations (filter only)
```

The use-case-aware router picks WITHIN `effective_candidates`, in the selected order,
and **never adds a candidate** the selection didn't produce. The **privacy ceiling
dominates** capability routing — capability can only narrow, never widen or override
a privacy exclusion. Empty effective set → fail closed, naming which input emptied it
(mirrors `user-assigned-llm-policy` 2.3/2.4). No fallback to an unselected provider.

## 5. Capability observations + compliance advisories (NEITHER is authority)

Split, per Codex. Neither can grant, widen, or veto execution authority — they can
only **narrow** an already-authorized route, or inform the UX.

- **Capability observations** (minimal — no policy engine, no synthetic "cheap
  validity" completions):
  - user-declared capabilities on the definition, validated only when actually
    exercised (a mismatch surfaces at call time, it does not pre-authorize);
  - passive health / rate-limit observations recorded from REAL calls;
  - at most ONE optional, bounded, same-origin `/models` probe with a TTL, per-owner
    rate/concurrency/cost limited, cached keyed by connection generation.
- **Compliance advisories** ("what's allowed"): freshness-stamped records with
  provenance (e.g. "Anthropic prohibits third-party subscription OAuth, verified
  2026-08-22"). Advisory metadata only. A HARD prohibition is enforced at the
  access-method/connect boundary (it refuses the route), never as a routing-time
  authority grant. Advisories decay — treated like the AGENTS.md audit-freshness rule.

## 6. Migration matrix (atomic; preserve live serving)

| Today | After | Invariant preserved |
|---|---|---|
| `CodexProvider` (`codex_provider.py`) | `subscription_cli` executor, same class behind the interface | codex identity, sandbox, auth-health, budget, telemetry |
| `_SUPPORTED_SERVICES=("claude","codex")` (`llm_deposit.py`) | retired/narrowed by the **custody owner**, not generalized here | no broadened secret-ingress path |
| named `gemini/groq/grok/ollama` providers | `api_key_http` provider definitions (openai_chat protocol) | behavior differential-tested vs the old modules |
| static role chains (`router.py:180`) | open router over §4 equation | fail-loud, cooldown, hard-pin, privacy allowlist kept |
| direct `CodexProvider()` construction (`call.py:166`) | via the executor registry | standalone/live registration still works |
| serving binding accepts only `claude-code`/`codex` (`provider_serving_binding.py:209`) | accepts any registered definition id; codex/claude-code ids unchanged | existing binding IDs stable |
| `connect_http` / `ConnectionLedger` / credential-blind proxy | **consumed** by `api_key_http` | outbound authority not duplicated |

`retire-cloud-worker-fleet` (approved, unmerged) is the execution-half of this
migration (queued execution resolves each workflow's serving credential); land it
first, then build the registry on top.

## 7. Security requirements (blocking)

All `api_key_http` traffic inherits the connect_http substrate guarantees: exact
HTTPS origin/path binding, DNS revalidation, private/loopback/link-local/metadata
blocking (v4+v6), redirects disabled, environment proxies disabled, bounded response
bodies + timeouts, structured (not arbitrary) headers. Plus:
- credential ref immutably bound to endpoint + assignment generation (base_url change
  can't redirect a key);
- commons/remixed definitions never auto-bind private credentials;
- capability probes per-owner rate/concurrency/cost limited, caches keyed by
  connection generation;
- `allowed_providers` resolves server-issued ids, never user labels;
- privacy ceiling dominates capability routing.

## 8. Out of scope (owned elsewhere / later)

Selection UX + toggle (`user-assigned-llm-policy`); API-key custody direct-to-executor
store (`retire-mcp-provider-secret-deposit`); the connect UX + Claude-premise correction
(`byo-llm-connect-flow`); a dedicated policy-update op for connect_http; non-OpenAI/
non-Anthropic protocol encoders beyond the first two.
