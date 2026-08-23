# A third compute access method: run a provider's agent SDK/CLI on the user's key

## Why

A user can build a Claude compute node two ways today only as a SINGLE-COMPLETION
provider: `api_key_http` + `anthropic_messages` (the Messages API). But the founder
wants the **SDK path also** — a Claude compute node that runs the **Claude Agent SDK**
(the `claude` CLI / agent harness), which gives the agentic tool-use loop, not just one
completion. The two existing access methods don't fit: `api_key_http` is a single
`.complete()` over the credential-blind proxy (no agent loop), and `subscription_cli`
runs the vendor CLI keyed by a subscription **OAuth snapshot** — a user bringing an
**API key** has no OAuth snapshot. So the SDK path needs a third access method.

This is the "agentic-over-API harness" the compute-agnostic notes flagged as separate,
now scoped to the concrete first case: Claude Agent SDK on a user's Anthropic API key.

## What changes

Add an `sdk` access method + a `ClaudeSdkProvider` executor, alongside `api_key_http`
and `subscription_cli` (deterministic selection, no cross-method fallback):

1. **`sdk` access method, protocol `cli:claude` (extensible to other agent SDKs).**
   `connect_compute(access_method="sdk", protocol="cli:claude", model="claude-…",
   ref=<grant_id>)` where `ref` is a granted http/compute connection carrying the
   user's Anthropic API key. Registration stays candidate-only + owner-gated, exactly
   like the other access methods.
2. **`ClaudeSdkProvider`** runs the `claude` CLI / Agent SDK as an isolated subprocess
   with `ANTHROPIC_API_KEY` = the user's key, resolved from the grant at call time —
   giving the agent loop (tools/brain) rather than one completion. Reuses the existing
   `claude_provider` subprocess plumbing (`subprocess_env_for_provider`, sandbox flags,
   `--strict-mcp-config`) but sources the credential from the grant, not an OAuth
   subscription snapshot.
3. **Credential model — LOCAL-BROKER + capability token (Codex reject 2026-08-23 of
   the naive env-injection; corrected shape).** The SDK runs ARBITRARY TOOLS
   (shell/code); putting the raw `ANTHROPIC_API_KEY` in that process env is unsafe —
   tool children inherit/read it and crash dumps / `/proc` / tool output can leak a
   long-lived key ("never logged" is not credible across an attacker-influenced
   process boundary). subscription_cli is NOT sufficient precedent (a long-lived API
   key has a larger blast radius than a scoped OAuth session). Correct shape: the
   vendor key stays BROKER-SIDE. Point the SDK at a loopback endpoint
   (`ANTHROPIC_BASE_URL=http://127.0.0.1:<port>`) with a SINGLE-RUN CAPABILITY TOKEN
   as its `ANTHROPIC_API_KEY`; the local broker (an extension of the existing
   credential-blind broker) validates the token, injects the REAL vendor key, and
   forwards to `api.anthropic.com` — restricted by universe, grant, provider,
   allowed endpoints, model, budget, expiry, and concurrency. The sandbox DENIES the
   SDK/tool subprocesses direct Anthropic egress and blocks them from reading the SDK
   env or reaching the broker except via the capability token. FEASIBILITY GATE:
   requires the pinned Claude SDK/CLI to honor a custom base URL (`ANTHROPIC_BASE_URL`,
   which it does); if a pinned version does not, the access method is redesigned around
   RESTRICTED (non-arbitrary) tools or not shipped.

## Boundaries (defer, do not duplicate)

- Served-authority wiring for `sdk` reuses the `serve-open-compute-provider`
  `connection_grant` authority path (this change adds the executor + access method, not
  a new authority system).
- The credential deposit stays the browser-form / connect_http path (no new secret
  surface); this change only RESOLVES the granted key into the executor subprocess.
- OS-isolation of the engine turn (`engine-os-sandbox`) is the deeper defense and is
  not superseded here; the SDK subprocess inherits whatever sandbox the CLI path uses.

## Security invariants (must hold)

- The REAL vendor key never enters the SDK/tool process — it stays broker-side; the
  SDK only ever holds a single-run capability token bound to (universe, grant,
  provider, model, budget, expiry, concurrency).
- The sandbox denies the SDK/tool subprocesses direct Anthropic egress and blocks
  them from reading the SDK env or reaching the broker except via the capability token.
- Grant ownership, universe binding, revocation, protocol, and credential version are
  revalidated at invocation AND at each broker request; mid-run revocation/races
  fail closed.
- Clean, allowlisted environment: isolated temporary HOME/config; ambient API/OAuth
  credentials, credential helpers, and inherited proxy settings removed; no
  cross-method fallback to an ambient credential.
- Lifecycle hygiene: process-tree termination, timeout/cancellation, temp-state
  deletion, crash-dump suppression, output/error/tool-result redaction, best-effort
  memory cleanup.
- `sdk` selection is grant-gated + universe-isolated exactly like `api_key_http`.
- Hard Rule #3 stays intact for the PLATFORM writer (codex/claude via subscription
  CLI); `sdk` is USER-brought compute on the user's own key, the sanctioned extension.

## Gate

Authority/credential-sensitive → Codex SHAPE review of this design before build
(done: reject of naive env-injection → local-broker shape folded above), a SECOND
shape review of the corrected local-broker design before build, then exact-diff
review before merge; full provider/compute suite zero-new-failures + tests (capability
token never carries the vendor key, sandbox egress-deny, grant revalidation +
mid-run-revocation fail-closed, clean-env, no cross-method fallback, lifecycle
cleanup). Dogfood: build a Claude SDK node, run an agentic turn on the local broker.

## Codex shape review — 2026-08-23: VERDICT reject (naive design) → corrected above

Rejected the first draft's raw-key-in-subprocess model and gave the correct shape:
- subscription_cli is not sufficient precedent (long-lived key = larger blast radius).
- Env injection is incompatible with arbitrary tools (children read the key; dumps/
  /proc/tool-output leak it) → keep the vendor key broker-side.
- Local broker + custom base URL + single-run capability token (scoped by universe/
  grant/provider/endpoints/model/budget/expiry/concurrency).
- Sandbox must deny direct Anthropic egress + isolate the SDK env/broker from tools.
- Revalidate grant/universe/revocation/version at invocation + broker; fail closed on
  mid-run revocation/races.
- Clean allowlisted env (temp HOME/config; strip ambient creds/helpers/proxies; no
  fallback); process-tree termination, temp deletion, crash-dump suppression, output
  redaction, memory cleanup.
- If a pinned SDK can't use a custom endpoint: restricted (non-arbitrary) tools only,
  or don't ship this access method.
All folded into "What changes" #3 + the invariants. A SECOND Codex shape review of the
corrected local-broker design is required before implementation.
