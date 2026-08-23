# Compute-agnostic provider set (open, user-defined compute + dynamic capability)

## Why

Founder directive (2026-08-22): compute must be user-built and remixable, the
same way outbound channels already are (`connect_http` + `authenticated_external_call`).
Today the platform hard-codes a fixed provider set — `_SUPPORTED_SERVICES =
("claude","codex")` in `api/llm_deposit.py`, and named `gemini/groq/grok/ollama`
providers with fixed role chains in `providers/router.py`. That caps the platform
at providers **we** integrate. The founder's words:

> "providers like kimi we would not need to add them in a patch — a user could set
> up their universe to run on kimi, or any other llm, through their subscription or
> api or sdk or any other known standard — whatever is allowed. They can just build
> a compute node for anything the market wants to provide."

And the guardrail is not static:

> "the 'whatever is allowed' cannot be static — we must leverage the user's
> advantage for capability and get the most out of their subscriptions/compute, for
> different use cases and situations where different rules apply, and always up to
> date."

This is proven necessary: Anthropic's third-party rules changed three times in six
months (Feb ban → May metered credit → June cancel). A hard-coded allowlist would
have been wrong twice.

## What this change owns (the genuinely new concern)

An **open, user-defined provider set** plus a **dynamic capability/policy layer**.
It does NOT re-implement authority, selection, custody, or the connect UX — those
have owners (see *Boundaries* below). It generalizes the *set* those systems range
over, from fixed to open.

1. **Generic compute executors, not per-provider modules.** Replace the bespoke
   `gemini/groq/grok/ollama` providers with a small set of **access-method
   executors** keyed off the connection, not the vendor:
   - **API executor** — a generic OpenAI-compatible client parameterized by
     `{base_url, model, auth}` (covers OpenRouter, Kimi/Moonshot, xAI, Groq, most),
     plus a thin adapter seam for non-OpenAI request/response shapes (e.g. the
     Anthropic Messages API for a Claude *API key*). *(new)*
   - **Subscription/CLI executor** — the existing `codex exec` (and, where a
     provider permits third-party subscription use, its CLI). Preserves **Hard Rule
     #3** (subscription writers stay CLI subprocesses, never an API SDK).
2. **Open provider registration.** A universe owner registers a compute connection
   for ANY reachable provider by describing it (`base_url`/endpoint, model, auth
   method, optional headers) — no code change, no allowlist. A provider we never
   heard of is registered, not enumerated. Remixable like any node.
3. **Dynamic capability discovery.** Learn what a connection can do by *probing*
   (models endpoint, a cheap validity call, rate-limit headers), cached and
   freshness-stamped — never a compiled-in capability table.
4. **Policy ("what's allowed") as refreshable DATA, not code.** Default-allow what
   the user brings when the credential works; known prohibitions (e.g. the Claude
   OAuth relay ban) are advisories that update WITHOUT a code change and are
   freshness-stamped/re-checkable. No compiled allowlist of providers.
5. **Full-replace migration** (host chose "full replace now", 2026-08-22): remove
   `_SUPPORTED_SERVICES` and the named-provider chains; route claude/codex/every
   provider through the unified connection + executor model. The live
   codex-subprocess serving path survives as the subscription executor.
6. **Shared compute-channel commons** (host, 2026-08-22): "when a user connects
   compute to their universe they see all the channels any previous user before
   them has built." Compute connections a user builds are discoverable + remixable
   by later users — the commons/remix pattern already used for outbound channels
   and nodes, applied to compute. A user adds Kimi once; the next user remixes it.
7. **Dogfood-driven acceptance (build AS A USER through the real surfaces):**
   - **OpenAI** built as a user through the **browser chatbot MCP connector**.
   - **Claude (SDK/API key)** and **OpenRouter free APIs** built as a user through
     the **desktop app**. This is the proof the flow is user-buildable across every
     surface — not a platform patch. (Final chatbot-surface `ui-test` applies.)

## Boundaries — what this change does NOT own (defer, do not duplicate)

- **`allowed_providers` authority** → `constrain-set-engine-provider-authority`
  (merged, PR #1784). This change writes NO competing constraint of that field; the
  open set is intersected with the enrolled/authorized set that change owns.
- **Provider selection / the toggle / per-branch+automation policy** →
  `user-assigned-llm-policy`. This change generalizes the *set* selection ranges
  over; it does not add a second selection surface. The founder's "toggle which
  provider runs the agent, default OpenAI when both present" is that change's job.
- **Credential custody** → `retire-mcp-provider-secret-deposit` (BREAKING). Raw
  provider API keys are NOT deposited through MCP/chatbot/the JSON vault. A generic
  provider API key is deposited only through the **secure WorkOS browser form**
  (`connect_deposit.py`); the chatbot surface does selection only. This change adds
  no credential-bearing MCP path.
- **Connect UX** → `byo-llm-connect-flow`, with a REQUIRED correction folded here:
  its "one-click Connect Claude subscription via Anthropic OAuth" premise is false
  (Anthropic prohibits third-party subscription OAuth — verified 2026-08-22).
  Claude is **API-key-only**; the one-tap device flow stays OpenAI-only.
- **`provider-routing`** (as-built) — this change turns its "subscription-only by
  default" requirement into "user-brought compute, subscription OR api OR sdk," and
  its fixed role chains into an open, use-case-aware router, but keeps its
  privacy-allowlist, cooldown, fail-loud, and hard-pin requirements intact.

## Principle changes requiring host approval (host directive 2026-08-22 = approval)

- **Hard Rule #3** ("No API SDKs for primary writer — Claude/Codex use subprocesses")
  evolves to: *subscription-access writers use CLI subprocesses (never an API SDK);
  API-key providers use their API.* Intent preserved; mechanism opened.
- **`provider-routing` "subscription-only by default"** evolves to *user-brought
  compute of any allowed access method*. "No host writer ever" is untouched — it is
  always the user's own compute.

## Impact

- Code: `providers/router.py`, `providers/base.py`, `providers/{gemini,groq,grok,ollama}_provider.py`
  (removed/collapsed into executors), `api/llm_deposit.py` (`_SUPPORTED_SERVICES`
  removed), `connect_deposit.py` (open provider set), and the capability/policy
  resolver (new module).
- Specs: delta against `provider-routing`; coordinates with `user-assigned-llm-policy`,
  `retire-mcp-provider-secret-deposit`, `byo-llm-connect-flow`.
- Security/authority-sensitive → Codex cross-family SHAPE review of this proposal
  before build, exact-diff review before merge.

## Scope decision (host, 2026-08-22): ONE big program that subsumes the unbuilt parts

This is one coherent compute-agnostic program, subsuming the unbuilt parts of
`user-assigned-llm-policy` + `byo-llm-connect-flow`. It still may NOT create a
second writer of `allowed_providers` (constrain-set-engine-provider-authority stays
the owner) or a second custody path (retire-mcp-provider-secret-deposit boundary
holds). The program is largely INTEGRATION of existing lanes, not greenfield.

**Reconciliation with the Codex shape review (which asked for a narrow delta):** one
PROGRAM the user experiences as unified (see-all-channels, toggle, dogfood sequence),
delivered as an UMBRELLA ROADMAP coordinating NARROW changes — each keeping its single
authority owner. This change owns ONLY the provider descriptor/executor registry +
capability observations + atomic migration. `user-assigned-llm-policy` (selection/
toggle) and `byo-llm-connect-flow`/custody stay their own changes, built over this
substrate. Codex's own words: "An umbrella roadmap may coordinate the program, but it
must not become a mega-change or a new authority owner." Founder gets the unified
build + UX; the security ownership boundaries stay intact.

### Existing-lane integration map (do NOT duplicate any of these)

| Lane | State | Role in this program |
|---|---|---|
| `constrain-set-engine-provider-authority` | merged (PR #1784) | Sole owner of `allowed_providers` / admission / launch barrier. Consume, never re-write. |
| `retire-cloud-worker-fleet` (worktree `wf-fleet-removal-complete`, branch `claude/fleet-removal-complete`) | **committed + exact-head-approved, unmerged** | Removes the fixed provider-shaped cloud fleet; queued execution resolves each workflow's assigned serving credential. This IS the migration's execution half. Verify + land it first. |
| `user-assigned-llm-policy` | in-flight, mostly unbuilt | The selection surface + toggle (default OpenAI) + per-branch/automation `preferred_provider`+`accepted_fallbacks`. Subsumed: build it over the open set. |
| `byo-llm-connect-flow` | in-flight, unlanded | The connect UX. Subsumed + corrected (Claude = API-key only; one-tap OAuth = OpenAI only). |
| `retire-mcp-provider-secret-deposit` | in-flight (BREAKING) | Custody boundary. Honor: secrets via the WorkOS browser form, MCP does selection only. |
| `wf-fleet-clean` (branch `claude/retire-cloud-worker-fleet`, dirty) | in-progress variant | Reconcile with `retire-cloud-worker-fleet` before building — likely the same lane mid-edit; do not fork a third copy. |

### Build order (dogfood-gated)

1. Verify + land `retire-cloud-worker-fleet` (credential-driven execution; fail
   closed `no_requester_owned_executor`, no ambient borrow).
2. Open-provider registration + generic API executor + capability probe (the new
   substrate). Differential-test the executor against the current grok/ollama paths.
3. Policy-as-data + use-case router; generalize `user-assigned-llm-policy` selection
   over the open set (toggle, default OpenAI).
4. Generalize the WorkOS browser deposit form to the open set; correct the Claude
   premise. **Dogfood: build OpenAI via the browser chatbot connector.**
5. Shared compute-channel commons (discover + remix others' compute channels).
   **Dogfood: build Claude-API + OpenRouter via the desktop app.**
6. Prune the bespoke providers + `_SUPPORTED_SERVICES`; guard test that no LLM is
   reachable without a universe-authorized, requester-owned provider.

Each slice: Codex exact-diff review before merge; public-surface/chatbot slices get
the live `ui-test`.

## Codex shape review — 2026-08-22: VERDICT adapt (fold before design/spec/tasks)

Core architecture approved (open provider definitions + a few access-method
executors is the right replacement for vendor enumeration). Required shape changes
before build:

1. **Ownership/state model**, naming the sole writer for each transition:
   `provider definition → credential binding → enrolled assignment → selected policy
   → frozen invocation`. Registration creates ONLY a definition/connection candidate
   — it does NOT enroll, authorize, select, or make routable.
2. **Split "policy as data"** into (a) capability OBSERVATIONS and (b) compliance
   ADVISORIES. NEITHER may grant, widen, or veto authority. Hard prohibitions live at
   the access-method/connect boundary and can only NARROW an already-authorized route.
3. **Exact routing equation:** effective set = selected ordered candidates (from
   `user-assigned-llm-policy`) ∩ `allowed_providers` ceiling ∩ live requester-owned
   enrollment ∩ request/invocation capability. The use-case router filters WITHIN that
   set — it never synthesizes candidates. Privacy ceiling dominates capability routing.
4. **Custody deferral:** do NOT generalize `connect_deposit.py` into a provider-API-key
   custodian (today it calls `connect_llm` → writes recoverable material to the JSON
   vault, which `retire-mcp-provider-secret-deposit` forbids for API keys). API-key
   custody (direct-to-executor/native store + opaque tuple-bound reference) is deferred
   to the custody owner. MCP does selection only.
5. **Remote API execution goes through the existing outbound grant + credential-blind
   proxy** (`connect_http`/`ConnectionLedger` substrate) — NO direct SDK/client to an
   arbitrary `base_url` (that bypasses SSRF + the proxy). Prefer a small protocol
   encoder over a vendor SDK.
6. **Atomic migration matrix** preserving `codex` as a stable provider/binding identity,
   `CodexProvider` as the subscription-CLI adapter behind the new executor interface, its
   CLI/sandbox/auth-health/budget/telemetry behavior, existing binding IDs, `connect_http`,
   status surfaces, and fail-loud semantics. Named-provider assumptions also live in
   `router.py:180`, `call.py:166`, `provider_serving_binding.py:209`, `codex_provider.py`,
   `base.py` — the migration must cover them. `_SUPPORTED_SERVICES` is retired/narrowed by
   the custody owner, not generalized here.
7. **Hard Rule #3 with access-method provenance:** `subscription_cli` deterministically
   selects the vendor CLI adapter; `api_key_http` selects an API protocol adapter. NO
   fallback from a failed subscription CLI to an SDK/API on ambient credentials. An
   API-key-backed Claude/OpenAI connection is a distinct binding+credential kind.
8. **Minimal capability discovery** (not a policy engine, no synthetic "cheap validity"
   completions): immutable connection descriptor (server ID, normalized endpoint,
   protocol shape, model, access method, opaque credential ref) + user-declared
   capabilities validated when exercised + passive health/rate observations + at most one
   optional bounded same-origin `/models` probe with TTL. Advisories are freshness-stamped
   with provenance.
9. **Blocking security requirements:** exact HTTPS origin/path binding, DNS revalidation,
   private/loopback/metadata blocking, redirects + env-proxies disabled, bounded
   bodies/timeouts, structured (not arbitrary) headers; a credential reference is
   immutably bound to endpoint + assignment generation (changing `base_url` cannot
   redirect an existing key); public/remixed provider definitions NEVER auto-bind private
   credentials; capability probes are per-owner rate/concurrency/cost limited with caches
   keyed by connection generation; `allowed_providers` resolves server-issued
   connection/binding IDs, never user-chosen labels.

Deliverable discipline (Codex): keep the delivery change narrow; produce a
`provider-routing` delta + design + a ≤12-task build plan before implementation.
