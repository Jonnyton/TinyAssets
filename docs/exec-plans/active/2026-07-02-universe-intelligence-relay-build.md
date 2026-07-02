# Build plan — Universe Intelligence + Relay reshape

- **Status:** ACTIVE build plan. Design: `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md` (host-approved via steering 2026-07-02). Codex design review ADAPT folded.
- **Goal of this plan:** build the reshape to a **first testable milestone (M1)** the host can drive locally (clean-slate onboard → create universe → assign engine → talk to the engine-backed personified intelligence via chatbot relay).
- **Method:** vertical slices, dependency-ordered; a developer subagent per slice + Codex/verifier review between slices; worktree `permissions-fail-closed` (branch `claude/founder-identity-allslices`); local `ui-test` after M1. NOT live — local host only until the host says otherwise.

## M1 — first testable milestone

> **A founder, from a clean slate, creates a universe, gives it a BYO API-key engine, and converses with its engine-backed personified universe intelligence through the chatbot — which relays (renders its first-person output), never embodies. The intelligence gets to know its founder and can take an action.**

Out of M1 (later slices): market-rented daemon, host-your-own-daemon onboard, market-subscription-contribution, 24/7 persistent loop, app channel, concurrent-awareness/attach-handoff, foundation-merge-prep.

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

### S3 — Daemon-class auth path (Gap B)
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

**→ M1 testable.** Then local `ui-test`: clean slate → create → assign key → converse → it gets to know the founder.

## Later slices (post-M1, host-prioritized)
S6 market-rented daemon · S7 host-your-own-daemon onboard · S8 market-subscription-contribution (which subs to offer when idle) · S9 24/7 persistent loop · S10 app channel · S11 concurrent-awareness + branch attach-handoff · S12 foundation-merge-prep (fail-open fallback, rename-orphans, rebase) — gated on a *later, explicit* host merge approval.

## Notes
- Foundation blockers (fail-open optional-mode fallback; rename-orphans; rebase) are **merge-prep, not local-test blockers** — local test runs WorkOS mode. Deferred to S12.
- `universe-personification` OpenSpec amended to the relay model as part of S5.
- Each slice: red→green→commit; Codex/verifier review before the next slice; checkpoint every 2 slices.
