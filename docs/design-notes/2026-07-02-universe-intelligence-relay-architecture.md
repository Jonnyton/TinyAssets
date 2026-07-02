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
- The chatbot MCP **relay is the *main* path** — but the **direct-control route
  stays open** (host clarification 2026-07-02, §12): a founder who wants to take
  actions themselves through the chatbot, or who does not host a daemon, keeps
  the action tools. Relay is the default, not the only mode. What the chatbot
  stops doing is *embodying* (pretending to BE the universe) — not *acting*.

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

## 11. Host decisions (2026-07-02) — resolving §9

1. **Availability = 24/7, proactive.** The universe intelligence runs
   continuously on the founder's assigned engine, *always proactively acting on
   the founder's / company's behalf, carrying out its vision* — not on-demand
   per turn. Confirms the persistent-loop model (generalize `DaemonController`).
2. **Credential custody — RESEARCHED (2026-07-02, pending Codex confirmation).**
   Full note: `docs/design-notes/2026-07-02-universe-engine-credential-custody-research.md`.
   **Load-bearing finding (contradicts the "subscription is fine" assumption):**
   custodying a *founder's* personal Claude Pro/Max or ChatGPT Plus **subscription**
   and driving it 24/7 server-side is **ToS-blocked on both providers** (Anthropic:
   automation only via API key, OAuth tokens exclusively for Claude Code/Claude.ai;
   OpenAI: ChatGPT subs individual-use, automation → API key). So the lawful,
   device-independent, per-founder 24/7 engines are only **API key** and
   **self-hosted endpoint**; personal-subscription survives *only* as the
   platform's own first-party engine for **the platform's own universe** (Tiny, the
   current droplet model) — **there is NO platform-provided free engine for
   founders** (host correction 2026-07-02, §12).
   **Recommended engine model for the universe intelligence (24/7 + app):** (i) BYO
   API key (primary sanctioned path) → per-universe vault under **envelope
   encryption**; (ii) BYO self-hosted endpoint (`OLLAMA_HOST`/`ANTHROPIC_BASE_URL`
   + token); (iii) rent a daemon from the market. **The zero-engine path is not a
   platform default — it is chatbot-in-session** (the chatbot's own LLM, interactive
   only, §12). **Do not build founder-subscription custody.**
   **Substrate is ~70% built:** `tinyassets/credential_vault.py` is per-universe +
   READ-wired into providers, but has 3 gaps — (a) base64-not-encrypted at rest,
   (b) no write surface (`write_credential_vault` uncalled), (c) **Gap A** (engine
   selection + cred resolution both process-global → shared MCP server can't pick
   the right founder's engine/creds per request). Gap A is the hard prerequisite.
   **Needs host decision:** confirm the ToS stance; approve **per-universe
   relaxation of `TINYASSETS_ALLOW_API_KEY_PROVIDERS`** (a real subscription-only
   policy change); pick secret backend. Hard Rule #3 (CLI-only for the *primary
   writer*) stays for the platform's own first-party engine; a founder's BYO
   API-key engine is a documented exception (flag if it needs an SDK path → Rule #3
   amendment).
3. **Write-authorization rule (host-stated, crisp):** write access to a universe
   is restricted to **(a) the universe's own intelligence** and/or **(b) the
   chatbot/app authenticated with the founder's WorkOS.** Two write principals;
   everything else is read-or-denied. (Relay-handle *shape* still deferred — "a
   clean elegant way may reveal itself as we build" — but this rule constrains it.)
4. **Zero-daemons-for-authoring — RESOLVED by rule #3.** The principle: basic
   create/edit works with *no* AI/daemon running (a browser user or an OSS cloner
   can make/edit universes without hosting a model). Rule #3 preserves it: the
   founder writes directly via **WorkOS** (principal b) — they do **not** need the
   always-on intelligence to be the one writing. The intelligence is *a* write
   principal, not the *only* one. Nothing breaks; confirmed consistent.

## 12. Executor spectrum + market (host clarification 2026-07-02)

The relay is the *main* path, but the chatbot's **direct-control route stays
open**. The mental model is **one shared universe brain** (soul/persona/memory/
goals/state) with many **surfaces** and **executors** around it, all aware of
each other:

- **Concurrent shared awareness.** A founder can build a branch directly via the
  chatbot *while* the daemon runs autonomously; the daemon is aware of that
  in-progress work the whole time (shared brain/state). On completion the chatbot
  **attaches** the branch to the universe + goals and the daemon **adopts** it
  like any branch it already runs. Requires: the brain is the single shared
  read/write substrate; the daemon observes founder-side work, not just its own.
- **Brain vs compute (host correction 2026-07-02).** The platform provides the
  **brain**; **compute is always brought, never zero** — because the only two ways
  to be a user each carry an LLM: the **chatbot** *is* an LLM (host client's own,
  in-session), and the **app** is a thin client onto the founder's **assigned
  engine**. There is NO platform-provided free/default engine for founders. (The
  platform's droplet subscription runs the platform's *own* universe, Tiny — not a
  per-founder default.) "Bring nothing → platform runs it for free" does not exist.
- **Compute for the *universe intelligence* (needed for the app + 24/7):** brought
  by the founder —
  1. **Host your own daemon** (their machine/cloud, their engine).
  2. **BYO engine** — API key / self-hosted endpoint (§11#2).
  3. **Rent from the live market** — other users host daemons; the founder sets
     their universe to run at the current market rate (e.g. "GLM 5.2") with a
     **spending cap**. No self-hosting, no BYO-engine. **This is the clean answer
     to the §11#2 ToS custody problem:** the market host runs *their own* engine
     legally + gets paid; the platform never custodies a founder's subscription.
- **Compute with NO assigned engine = the chatbot's own LLM (in-session only):**
  the chatbot runs branches itself via **subagents** (uses the host client's LLM
  → ToS-fine), possibly even running the universe's main daemon that way. The
  seeded subagent *is* the in-session intelligence, and the chatbot **relays** its
  first-person output — so even this case obeys the one rule (render, never
  embody). Interactive only; no 24/7.
- **The autonomy line:** only **24/7 background** / app-reachability needs a
  brought engine (owned / BYO / market-rented). Everything else is reachable
  interactively via the chatbot's own LLM. "Zero daemons for authoring" = this.
- **Mostly existing substrate.** This is the PLAN **Daemon Platform** (runtime
  instances bound to provider/model/executor; file-locked claim across cloud+host
  executors; capacity-bounded fleets) + the **paid market** (inbox + bid
  matching; `branch_tasks.claim_task`; `market` goals/bid actions;
  `daemon_summon` universe-scoped w/ provider+model), **unified** with the
  universe intelligence. The reshape does not invent a market; it routes the
  universe's own daemon through the one that exists. Market-rate rental with a
  founder spending cap + market-run of the *universe daemon itself* are the main
  new capabilities to design against that substrate.
- **Correction to §7/§8:** the chatbot is NOT demoted to onboard+relay-only. It
  keeps its action tools (direct control) as a secondary path; only *embodiment*
  is removed. The MVP relay is additive, not a removal of control.
