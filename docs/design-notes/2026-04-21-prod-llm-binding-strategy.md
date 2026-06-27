---
title: Prod LLM binding strategy — minimum viable two-provider stance
date: 2026-04-21
author: navigator
status: superseded
status_detail: Superseded 2026-04-30 by PLAN.md subscription-first provider auth policy.
related:
  - tinyassets/providers/router.py
  - domains/fantasy_daemon/phases/_provider_stub.py
  - PLAN.md § Providers
---

# Prod LLM Binding Strategy

> Superseded 2026-04-30: this note describes the earlier API-key binding
> strategy. Cloud daemons now run LLM execution through host subscription
> auth only; API-key provider env vars are scrubbed before default-daemon LLM
> execution.

## Current state (diagnosis)

`get_status` reports `llm_endpoint_bound=unset`. The daemon is starved — no provider
is reachable, so every writer/judge call hits `AllProvidersExhaustedError` immediately.

**Root cause — two gaps:**

### Gap 1: Gemini / Groq / Grok are in the fallback chain but never registered

`router.py` line 52:
```python
"writer": ["claude-code", "codex", "gemini-free", "groq-free", "grok-free", "ollama-local"],
```

`_provider_stub.py` registers only `ClaudeProvider`, `CodexProvider`, `OllamaProvider`
at startup (lines 51–71). `GeminiProvider` / `GroqProvider` / `GrokProvider` are
defined as classes but **never instantiated or registered in any production path**.
The fallback chain names them — but when the router iterates the chain, it calls
`self._providers.get("gemini-free")` which returns `None`, logs "not in registry,
skipping," and moves on. They are phantom entries.

### Gap 2: `ollama-local` is the chain's terminal backstop, but 960 MB RAM = no go

The router docstring reads: "Hard invariant: every call has a fallback chain that
terminates at `ollama-local`. The system NEVER stops due to provider unavailability
unless local models are also down."

This invariant **does not hold on the prod Droplet**. The smallest usable Ollama model
(Phi-3 mini 3.8B, q4) requires ~2.5 GB RAM. The Droplet has 960 MB. Ollama cannot
run. The chain terminates in `AllProvidersExhaustedError`, not in a degraded response.

### Net effect

Historical note: with Task #35 (codex CLI in image + `OPENAI_API_KEY`) landing,
the daemon had exactly one provider, `codex`. That path is no longer approved
for default daemons; use subscription-backed Claude/Codex auth instead.

---

## Question 1: Fallback behavior when codex hits rate limit

Rate-limit path in `codex_provider.py`:
```python
if proc.returncode != 0:
    raise ProviderError(f"codex exec exit {proc.returncode}: {stderr}")
```

A 429 from OpenAI surfaces as `ProviderError` (not `ProviderUnavailableError`), which
triggers `COOLDOWN_OTHER` in the quota tracker. From `router.py`:

```python
except ProviderError as exc:
    self._quota.cooldown(provider_name, COOLDOWN_OTHER)
```

`COOLDOWN_OTHER` duration (from `tinyassets/providers/quota.py` — need to verify):
typically 30–60s. During cooldown, `quota.available("codex")` returns False, the
router skips codex, finds no other registered providers, and raises
`AllProvidersExhaustedError`. The daemon's node gets an exception, which propagates
to the LangGraph error handler.

**Degradation behavior is NOT graceful for writer role.** For judge role, the router
returns `DEGRADED_JUDGE_RESPONSE` (a sentinel) when all providers exhausted — so
judging degrades softly. Writing fails hard. A single OpenAI rate limit event stalls
all in-progress scenes until the cooldown expires.

---

## Question 2: Minimum two-provider prod stance

### Candidate A: Gemini free tier (recommended)

**What it needs:** `GEMINI_API_KEY` env var + `google-genai` package in image +
register `GeminiProvider` at startup.

**Free tier limits (current as of 2026-04-21):** Gemini 2.5 Flash — 15 RPM, 1,500
RPD, 1M TPD. At the daemon's typical call cadence (~1 scene per few minutes), this
covers sustained overnight runs without exhausting the daily quota.

**Model family:** Google (different from OpenAI). Adds genuine judge diversity — the
main reason for multi-provider setup beyond resilience. The fallback chain already
prioritizes Gemini as the first fallback after codex for writer role and the second
for judge role.

**Registration gap:** trivially fixed — add `GeminiProvider` to `_provider_stub.py`
startup registration (same pattern as Codex). One try/except block, ~6 lines.

**Host touchpoint:** mint a free Gemini API key at `aistudio.google.com` (~2 min) +
add `GEMINI_API_KEY` to `/etc/tinyassets/env` on the Droplet. No OAuth device flow;
Google AI Studio API keys are a simple web form.

### Candidate B: Groq free tier

**What it needs:** `GROQ_API_KEY` + `groq` package + register `GroqProvider`.

**Free tier limits:** 14,400 RPD, 6,000 RPM on Llama 3.3-70B. Extremely generous
— well beyond prod daemon needs.

**Model family:** Meta Llama (third family, after OpenAI + Google). Maximum judge
diversity when all three are present.

**Host touchpoint:** mint key at `console.groq.com` (~2 min). No OAuth — API key
form. Same `GROQ_API_KEY` env var as the provider already expects.

### Recommendation: Gemini + Groq both, simultaneously

Both are free, both take ~2 min to mint, both require only an env var + package in
the image. There's no reason to pick one and defer the other. With Task #35 landing
codex, adding Gemini + Groq gives a three-provider chain (OpenAI / Google / Meta)
covering writer fallback and genuine judge ensemble diversity. This is the minimum
viable state the router was designed for.

**Combined dev work:** add `GeminiProvider` + `GroqProvider` to `_provider_stub.py`
startup registration. Ensure `google-genai` + `groq` packages are in the Docker
image (`[gemini]` and `[groq]` optional deps already exist in `pyproject.toml` —
confirm they're in the image's install target). ~15 lines of code, one image rebuild.

---

## Question 3: Can API keys be minted autonomously?

**Gemini:** No autonomous path. `aistudio.google.com` requires Google account login
+ consent screen. No OAuth device flow for API key issuance. **Host touchpoint is
irreducible: ~2 min on the web.** Google Cloud service accounts with programmatic
key generation exist, but require project setup and billing — heavier than needed.

**Groq:** No autonomous path. `console.groq.com` requires account creation + email
verification. **Host touchpoint: ~2 min.** No OAuth device flow exposed publicly.

**Grok (xAI):** Same shape — `console.x.ai` requires account + waitlist. Currently
the most friction of the three; skip for now.

**Minimum host touchpoint for two-provider stance:**
1. `aistudio.google.com` → Create API key → copy `GEMINI_API_KEY`.
2. `console.groq.com` → Create API key → copy `GROQ_API_KEY`.
3. SSH to Droplet → `echo "GEMINI_API_KEY=..." >> /etc/tinyassets/env` × 2.
4. `docker compose restart` to reload env.

Total: ~10 min. No CLI tooling needed; pure web + SSH.

---

## Question 4: Remote LLM via another TinyAssets daemon (host pool path)

**Design state (PLAN.md § Multiplayer Daemon Platform):**

> Every daemon host declares capabilities (node types, LLM models, price), visibility
> (`self` / `network` / `paid`), and heartbeat state to the control plane. Daemons
> are execution-tier, not control-plane.

The paid-market dispatch design (Track D, partially shipped) has daemons polling
for work and hosting declaring LLM capabilities. In the full vision: if the prod
Droplet's codex hits rate limit, the daemon could re-queue the work and another host
daemon (with Gemini bound) picks it up.

**Current reality:** Track D Wave 1 (host-pool registration + bid polling — commit
`72e86a2`) landed the data structures and heartbeat shape but does NOT yet have:
- A control plane that receives host declarations and routes work cross-host.
- A protocol for one daemon delegating a writer call to another daemon's LLM.
- Any network path between daemons (they're isolated on separate Droplets with no
  shared RPC surface).

**Verdict on Question 4:** The host-pool design has a *conceptual* answer to this
class of problem (multi-host dispatch → different LLM bindings), but the
implementation gap is large — likely 2–4 dev-weeks to reach the point where cross-
host LLM delegation is reliable. It does NOT leapfrog the current problem.

The right reading of the host-pool path is: it makes the LLM-binding problem
eventually *self-healing* at platform scale (more hosts = more provider diversity).
It does not solve the single-host starved-daemon problem today.

**Near-term verdict:** solve with env vars + registration fix (Questions 2–3). The
host-pool path is the right *long-term architecture*; don't block a 10-minute fix on
a 2-week implementation.

---

## Summary and proposed action

| Gap | Fix | Effort | Host touchpoint |
|---|---|---|---|
| Gemini/Groq never registered | Add to `_provider_stub.py` startup + image deps | ~15 LOC + 1 rebuild | Mint 2 API keys (~10 min) + add to env |
| Ollama backstop unreachable on 960MB | Accept: ollama not viable at current tier; remove from chain or leave as phantom (harmless skip) | 0–2 LOC | None |
| Single-provider writer stall on rate-limit | Solved by adding Gemini + Groq (fallback chain becomes 3-provider) | — | — |
| Judge ensemble single-response | Solved by same: 3 providers → 3-way ensemble possible | — | — |

**Proposed minimum state (dev task, ~1h):**

1. Add `GeminiProvider` + `GroqProvider` to `_provider_stub.py` startup registration
   block (same guard pattern as CodexProvider).
2. Confirm `google-genai` + `groq` packages included in Docker image install target
   (check `pyproject.toml [gemini]`/`[groq]` extras are in Dockerfile `pip install`
   line).
3. Document `GEMINI_API_KEY` + `GROQ_API_KEY` in AGENTS.md env-var table (they're
   already listed but worth verifying the "Provider API keys" section is current).

**Host task (~10 min):**

1. Mint Gemini key: `aistudio.google.com` → API keys → Create.
2. Mint Groq key: `console.groq.com` → API keys → Create.
3. On Droplet: append both to `/etc/tinyassets/env`.
4. `docker compose restart`.
5. Probe: `python scripts/mcp_probe.py` → confirm `llm_endpoint_bound` changes from
   `unset`.

**Ollama:** leave as phantom chain entry for now. The router silently skips
unregistered providers; no harm. If the Droplet is ever upgraded to 4GB+, Ollama
registration becomes viable by adding it to the startup block.

**Host-pool / remote-LLM:** correct long-term architecture once Track D has a
cross-host dispatch wire. Not a dependency for today.
