# Build plan — Universe Intelligence + Relay reshape

- **Status:** ACTIVE build plan. Design: `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md` (host-approved via steering 2026-07-02). Codex design review ADAPT folded.
- **Goal of this plan:** build the reshape to a **first testable milestone (M1)** the host can drive locally (clean-slate onboard → create universe → assign engine → talk to the engine-backed personified intelligence via chatbot relay).
- **Method:** vertical slices, dependency-ordered; a developer subagent per slice + Codex/verifier review between slices; worktree `permissions-fail-closed` (branch `claude/founder-identity-allslices`); local `ui-test` after M1. NOT live — local host only until the host says otherwise.

## M1 — first testable milestone (host chose FULL onboard, 2026-07-02)

> **A founder, from a clean slate, creates a universe and goes through the full
> onboard: choose how the universe runs — assign an engine (BYO API key / BYO
> self-hosted endpoint / rent a daemon from the market at rate + cap) and/or host
> their own daemon — and choose which of their subscriptions to offer the market
> when idle. Then they converse with the engine-backed personified universe
> intelligence through the chatbot, which relays (renders first-person), never
> embodies. The intelligence gets to know its founder and can take an action.**

The host explicitly wants the *whole* onboard felt in the first test, not a minimal
core (they rejected testing a half-build). This makes M1 large — see the honest
scale note below.

**Still out of M1 (genuinely separable):** the 24/7 always-on autonomous loop (M1
uses turn-scoped intelligence — enough to converse + act), the native app channel,
concurrent-awareness + branch attach-handoff, and foundation-merge-prep. These do
not gate the onboard-feel test.

**Scale honesty:** M1 spans ~8 slices incl. a paid-market path (rent a daemon) and
host-your-own-daemon — a multi-session build. For the local test the "market" can
start as a single local/mock host so the rent-a-daemon flow is exercisable without
a second real operator; real multi-operator market matching is a hardening follow-up.

## Slices to M1 (dependency-ordered)

### S1 — Per-universe engine resolution (Gap A) — *the prerequisite*
Router resolves the engine from the request's `universe_id`, not the process-global
`runtime.universe_config` singleton; `credential_vault` per-universe resolution
likewise off the request universe, not the global `TINYASSETS_UNIVERSE` env.
- **Files:** `tinyassets/providers/router.py`, `tinyassets/credential_vault.py` (~:360), `tinyassets/auth/middleware.py` (universe context), tests.
- **Accept:** two concurrent requests for different universes resolve different engines; no bleed (extend `test_multi_tenant_isolation.py`).

### S2 — Engine assignment at create + vault write surface (BYO API key)
`_action_create_universe` writes `config.yaml` (`preferred_writer`/`allowed_providers`)
from a founder-supplied engine choice; add a founder-WorkOS-gated deposit path wiring
`write_credential_vault`; per-universe relaxation of `TINYASSETS_ALLOW_API_KEY_PROVIDERS`.
- **Files:** `tinyassets/api/universe.py` (create + deposit action), `tinyassets/credential_vault.py` (write surface), `tinyassets/config.py`, `tinyassets/providers/base.py` (per-universe api-key gate), tests.
- **Accept:** creating a universe with an API key writes `config.yaml` + a vault record; the universe's engine resolves to that key (via S1); anon cannot deposit.

### S3 — Daemon-class MCP auth path (Gap B) — **DEFERRED to post-M1 (S12 hardening)**
**Reprioritized 2026-07-02 after seam-map:** the daemon-scope bug only bites the
MCP *transport* path; in-process daemon writes already bypass the gate. The
universe intelligence (S4) acts IN-PROCESS, scoped to its own universe by
construction (S1 UniverseContext) — it never hits the transport auth gate — so
Gap B does not block the onboard. Still a real foundation bug for EXTERNAL MCP
callers (daemon-memory writes fail under WorkOS; read variants anon-open, no
ownership check). Fix = daemon-identity contextvar/capability + a guarded
exemption in `_dispatch_scope_error` (`universe.py:5019`/`:5086`), NOT a blanket
action-name exemption (that would make capture/promote anon-callable). Move to
S12 foundation hardening before merge.

_Original spec (for S12):_
An actor/auth path for the intelligence evaluated **before** user-OAuth scope gating,
so daemon-scoped actions (and the intelligence's own actions) don't fail
`auth_scope_required` (Codex-reproduced). 
- **Files:** `tinyassets/api/universe.py` (`_dispatch_scope_error` ordering / daemon exemption ~:121/:4971), `tinyassets/auth/middleware.py`, tests.
- **Accept:** `daemon_memory_capture` + an intelligence action succeed for a daemon actor with no founder token; user-OAuth gating unchanged for user actions.

### S4 — Universe-intelligence runtime (engine-backed, personified, turn-scoped)
A per-universe agent that loads persona (system prompt) + brain, runs on the assigned
engine (S1), processes a founder turn, and can act (S3). M1 = turn-scoped (invoked per
relay turn); the 24/7 persistent loop is a later slice. Generalize `fantasy_daemon`
`DaemonController` rather than build fresh.
- **Files:** `tinyassets/universe_intelligence.py` (new, generalized from DaemonController), persona/self-model load, tests.
- **Accept:** given a universe with engine + persona, a turn produces first-person output grounded in the brain and can call an action.

### S5 — Relay channel + demote embodiment
MCP path: founder turn → S4 intelligence → render first-person output + actions taken.
Rewrite `control_station` + server `instructions` + `meet_universe` from *embody* →
*relay/render*. Decide relay-handle shape (repurpose `run_graph` vs new handle) + update
the `--assert-handles` canary in lockstep (Hard Rule 11).
- **Files:** `tinyassets/universe_server.py` (instructions + handle), `tinyassets/api/prompts.py` (control_station, meet_universe), relay dispatch, `scripts/mcp_public_canary.py` (handle set), tests.
- **Accept:** a chatbot turn through the connector reaches the intelligence and renders its first-person reply; embodiment instructions gone; canary green with the new handle set.

### S6 — Market-rented daemon (engine source) — *in M1*
Founder sets the universe to run at a market rate (e.g. GLM 5.2) with a spending cap;
the paid-market matches a host daemon to run it. Local test: a single local/mock market
host makes the flow exercisable without a second real operator.
- **Files:** `tinyassets/api/market.py`, `tinyassets/branch_tasks.py` (claim), `tinyassets/daemon_registry.py` (`daemon_summon`/runtime_instance), `tinyassets/api/universe.py` (engine-source = market), tests.
- **Accept:** a universe set to market-rented gets a daemon assigned + capped; a turn runs on the rented engine; cap enforced.

### S7 — Host-your-own-daemon onboard — *in M1*
The founder hosts their own daemon as an onboard step (the current pre-hosted daemons
must NOT pre-exist on clean slate; hosting is founder-initiated). Reset clears all
daemons; onboard offers "host a daemon for your universe."
- **Files:** `tinyassets/reset.py` (verify clears daemons), `tinyassets/api/universe.py` (host-daemon onboard action), `fantasy_daemon`/runtime hosting seam, tests.
- **Accept:** clean slate = zero daemons; onboard lets the founder host a daemon bound to their universe; it runs a turn.

### S8 — Market-subscription-contribution — *in M1*
The founder chooses which of their subscriptions/engines to offer the market (and how
much) when not running one of their own universes.
- **Files:** `tinyassets/api/market.py` (offer/contribute), `tinyassets/config.py` (per-founder offer config), `tinyassets/credential_vault.py` (engine ref), tests.
- **Accept:** a founder can list an engine to the market with a cap/rate; it becomes claimable by other universes; togglable.

**→ M1 testable.** Then local `ui-test`: clean slate → create → full onboard (engine choice: key/endpoint/market + host-daemon + market-contribution) → converse → it gets to know the founder.

## Later slices (post-M1)
S9 24/7 persistent loop · S10 app channel · S11 concurrent-awareness + branch attach-handoff · S12 foundation-merge-prep (fail-open fallback, rename-orphans, rebase) — gated on a *later, explicit* host merge approval.

## Notes
- Foundation blockers (fail-open optional-mode fallback; rename-orphans; rebase) are **merge-prep, not local-test blockers** — local test runs WorkOS mode. Deferred to S12.
- `universe-personification` OpenSpec amended to the relay model as part of S5.
- Each slice: red→green→commit; Codex/verifier review before the next slice; checkpoint every 2 slices.
