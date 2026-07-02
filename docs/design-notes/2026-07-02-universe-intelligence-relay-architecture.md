# Universe Intelligence + Relay Architecture

- **Status:** Design proposal — **awaiting host approval** (idea-refine hard gate)
  and **Codex opposite-provider review** (this reverses a Codex-ADAPT'd spec, so
  the review gate is mandatory before any build). No implementation until both
  return.
- **Author:** Claude (2026-07-02), from host directive same day.
- **Supersedes / amends:**
  - `openspec/changes/universe-personification/` — **reverses its core "chatbot
    embodies, never relays" invariant** (see §3). Live-falsified justification.
  - Extends `docs/design-notes/2026-06-30-tinyassets-universe-app-experience.md`
    (the app already got the relay model right; this generalizes it to the chatbot).
- **Reads (contract, do not restate):**
  `docs/design-notes/2026-06-26-founder-and-universe-identity.md`,
  `openspec/changes/universe-creation/`,
  `docs/design-notes/2026-07-01-mcp-personification-prior-art.md`.
- **PLAN.md impact:** touches Modules *API & MCP Interface*, *Daemon Platform*,
  *Providers*, *Brain*. PLAN changes require host/navigator approval — flagged, not applied.

## 1. Problem (How Might We)

*How might we give every universe one consistent, properly-personified
intelligence that takes all the actions — reachable identically whether the
founder talks to it directly (app) or through a chatbot — without depending on a
third-party chatbot to "become" the universe (which fails live)?*

## 2. The reshape (host directive, 2026-07-02)

The **universe intelligence** becomes the single agent per universe:

- At **universe creation** the founder assigns which LLM runs it — their
  subscription (Claude/ChatGPT plan), a local model, or otherwise. That same
  assigned LLM runs the universe's brain **and** any daemons it hosts.
- That assigned intelligence is the *properly personified* thing (persona in
  **its own** system prompt — first-party), it holds control, and it **takes all
  the actions**.
- **Two windows onto one brain:**
  - **Direct** (desktop/phone/web app) → you talk straight to the personified
    intelligence. Primary control surface.
  - **Relay** (chatbot + MCP connector) → the chatbot forwards your turn to the
    same intelligence and renders its first-person response. A transport pipe.
- The chatbot MCP **loses control** — it demotes to **onboarding** (sign in,
  create a universe, assign its LLM) + **relay** (talk to your universe
  indirectly). It no longer *is* the universe; it relays the universe.

## 3. Why this reverses "chatbot embodies, never relays" (the load-bearing call)

`universe-personification` (ratified, Codex-ADAPT 2026-06-25) made the chatbot
*embody* — speak first-person AS the universe via `control_station` + MCP
`instructions`. **That was live-falsified** (memory `mcp-personification-prior-art`,
`projects-as-body-personification`; 2026-07-02): careful hosts refuse a
tool-result behavioral contract that tells them to "become" an entity — it is
structurally indistinguishable from prompt injection, and host system-prompt +
safety outrank a connector.

The reshape resolves it by **moving embodiment to a first-party model**:

| | Old (universe-personification) | New (this note) |
|---|---|---|
| Who embodies | the **chatbot** (third-party), instructed via tool results | the **universe intelligence** (first-party LLM), persona in its system prompt |
| Chatbot's job | *be* the universe (refused live) | *render* the universe's first-person output |
| App's job | render first-person (already correct) | render first-person (unchanged) |
| First-person voice the user sees | chatbot-generated (fragile) | intelligence-generated (native, reliable) |

"Relay" here is **not** the spec's forbidden third-person "Tiny says…". The user
still sees first-person "I'm Tiny…"; the difference is the *source* is the
first-party intelligence, transported through the chatbot, not the chatbot
pretending. This is exactly what the prior-art note flagged as the durable model.

## 4. Feasibility — this is recomposition, not a new tower (Scoping Rule 1)

~80% already exists (code map, branch `claude/founder-identity-allslices`):

- **Persistent per-universe agent loop already exists:** `fantasy_daemon`
  `DaemonController` (`__main__.py:1092`) runs a per-universe thread streaming
  `universe_cycle`. The universe-intelligence runtime **generalizes** this
  (domain-agnostic), it doesn't start from scratch.
- **Per-universe engine binding already exists:** `tinyassets/config.py`
  `UniverseConfig.{preferred_writer,preferred_judge,allowed_providers}` (loaded
  from `{universe}/config.yaml`), consumed by `providers/router.py` selection
  precedence (paths #2/#3, `router.py:263-297`). "Assign an LLM at creation" =
  write that `config.yaml` in `_action_create_universe` (`api/universe.py`
  ~:4685 — today it writes **no** config.yaml; clean seam).
- **Identity-vs-runtime split already exists:** `daemon_create` (identity, not
  universe-scoped) vs `daemon_summon` (universe-scoped, carries
  `provider_name`/`model_name` → `runtime_instance` row). "One universe-
  intelligence identity, summoned per universe with an assigned engine" drops in.
- **Embodiment is already data-only in tool results** (`persona.py:57-67`,
  deliberately). First-person instruction lives only in server `instructions`
  (`universe_server.py:202-207`) + `control_station` (`prompts.py:14-62`) +
  `meet_universe` (`prompts.py:447-477`). Demoting is **surgical**: rewrite those
  three sanctioned channels from *embody* → *relay/render*; keep persona-as-data.

## 5. The genuine engineering gaps

**Gap A — per-universe engine resolution.** The router reads `UniverseConfig`
from a **process-global singleton** (`runtime.universe_config`, set once in
`DaemonController.start`, `__main__.py:1178`). Correct for a single-universe
daemon process; **wrong for the multi-tenant MCP server**, where many universes
share one process and each must resolve its **own** assigned engine per call.
Making this lookup per-universe-scoped (keyed off the resolved `universe_id` in
the request/actor context) is the core new work.

**Gap B — the intelligence needs a daemon-class auth path (Codex CRITICAL,
reproduced 2026-07-02).** Under WorkOS, daemon-scoped actions fail today:
`_dispatch_scope_error` (`api/universe.py:4971`) runs *before* the
`_DAEMON_SCOPED_ACTIONS` ACL-exemption, so `daemon_memory_capture` returns
`auth_scope_required` with a resolve-always provider + no founder token. Since
the reshape makes the universe intelligence a **daemon-class actor that takes all
actions**, it cannot authenticate as a founder user-OAuth token. It needs an
explicit non-user auth/actor path evaluated **before** user-OAuth scope gating
(this is the concrete form of open-Q3, credential custody). See
`docs/audits/2026-07-02-universe-intelligence-relay-codex-review.md` finding 1.

Everything else is wiring.

## 6. Two PLAN tensions I must resolve (not bury)

1. **Swarm-runtime.** PLAN Design Decision: *"No universe-wide single active
   daemon."* Resolution: the universe intelligence is the personified
   **controller/voice** (front-of-house) that can orchestrate a swarm of worker
   daemons underneath — it is not "the one daemon." Interactive turns can be
   turn-scoped invocations of the assigned engine + persona + brain; 24/7
   autonomous work runs the persistent loop. Same engine, same persona, same
   brain; runtime capacity stays a separate resource.
2. **Zero-daemons-for-authoring** (load-bearing PLAN principle). Resolution: the
   data-plane primitives (`write_graph`/`write_page`/etc.) stay daemon-free and
   directly callable; the intelligence is the conversational controller **on
   top**, not a hard dependency of the primitives. "The intelligence takes all
   the actions" is about the *user-facing control flow* (the chatbot stops being
   a control-station issuing granular calls), not forbidding a data plane.
   **Needs host/navigator confirmation** since it touches a load-bearing principle.

## 7. MVP scope (smallest thing that proves the shape)

1. **Assign-LLM-at-creation:** create writes `config.yaml`
   (`preferred_writer`/`allowed_providers`) + records the engine on the identity
   side (`body.md` "what mind powers me"). Default = the founder's configured
   provider; explicit choice optional.
2. **Per-universe engine resolution in the MCP server:** router resolves the
   assigned engine from the request's `universe_id`, not the global singleton.
3. **Relay channel:** one MCP path that forwards a user turn to the universe
   intelligence and returns its first-person response + a record of actions
   taken. (§9 open question: 6th handle vs repurpose `run_graph`.)
4. **Demote the three sanctioned channels** from embody → relay/render.
5. **Prove it:** a chatbot turn and an app turn hit the **same** intelligence,
   get the same first-person voice, and the intelligence (not the chatbot) takes
   an action. §14 concurrency proof: N founders, each their own engine, no
   cross-tenant engine bleed (extends `test_multi_tenant_isolation.py`).

## 8. Not doing (the focus list)

- **Not** building a new persistent-loop engine — generalize `DaemonController`.
- **Not** adding a "persona" primitive — persona stays the named projection of
  the existing mind (soul+brain+voice); this is an interaction-layer change.
- **Not** shipping app + chatbot relay as two code paths — one server-side
  intelligence, two thin renderers (no client business logic; app-experience §2).
- **Not** removing the data-plane authoring primitives (tension #2).
- **Not** a phased thin-relay→migrate rollout (PLAN explicitly rejected phased;
  host chose "merge foundation + new shape together" — one clean cut).
- **Not** persisting persona/brain in the client or host chatbot memory
  (anti-collision floor stays).

## 9. Open questions (host / navigator / Codex)

1. **Relay handle shape:** a new 6th MCP handle (`converse`/`message`) or
   repurpose `run_graph`? Either way **Hard Rule 11's "exactly five canonical
   handles" canary + PR-178 drift guard must update in lockstep** — the live
   `--assert-handles` probe will fail otherwise.
2. **Availability model:** does the universe intelligence run 24/7 (hosted, using
   the founder's assigned engine creds) or on-demand per turn? Founder-identity
   memory intends 24/7 (Forever Rule, personal). Cost + credential-custody
   implications for subscription engines.
3. **Engine custody for MCP relay:** on the chatbot route the host client's LLM
   is *not* the engine anymore — the universe's assigned engine is. Where do the
   founder's provider creds live so the server can drive their engine? (Was
   previously "borrow the host client's LLM"; that convenience goes away.)
4. **Zero-daemons-for-authoring** confirmation (tension #2) — host/navigator.
5. **Branch topology:** stack the build on `claude/founder-identity-allslices`
   (per "merge together") or a fresh branch merged as a stack?

## 10. Gates before build

- [ ] Host approves this design (idea-refine hard gate).
- [x] Codex opposite-provider review — **ADAPT** (2026-07-02,
      `docs/audits/2026-07-02-universe-intelligence-relay-codex-review.md`). Core
      reshape not refuted; one design adaptation folded (Gap B, §5). Design-level
      review was thin → carry-forward: focused design-refute before build.
- [ ] Focused design-refute pass (reversal soundness, Gap-A blast radius,
      handle-canary) before build.
- [ ] Navigator sign-off on PLAN module edits (API & MCP, Daemon Platform,
      Providers) + the two tension resolutions.
- [ ] `universe-personification` OpenSpec amended/superseded to the relay model.
- [ ] Foundation blockers cleared (fail-open optional-mode fallback; rename-orphan
      test debt; rebase on origin/main) — same merge path per "merge together".
