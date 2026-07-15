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

"Relay" here is **not** the spec's forbidden third-person "the universe says…". The
user still sees first-person "I'm <name>…"; the difference is the *source* is the
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
   **self-hosted endpoint**; personal-subscription survives *only* **self-hosted** —
   your own account on your own infra (e.g. the host runs *his own* subscription on
   the droplet, ToS-clean because it is his own). **There is NO platform-provided
   free engine for founders, and NO privileged "platform universe"** (host
   correction 2026-07-02: clean slate — zero universes until users create them; the
   platform founder's universe, if he creates one and hands it the repo, is *just
   another user's universe*. §12).
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
  engine**. There is NO platform-provided free/default engine for founders, and NO
  privileged "platform universe" (host correction 2026-07-02: **clean slate — zero
  universes until users create them**; the host's droplet subscription is the host's
  *own* self-hosted account, serving whatever universe(s) *he* creates — not a
  per-founder default). "Bring nothing → platform runs it for free" does not exist.
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
  **(Superseded for brain-writes by §13 — see below: the chatbot keeps branch +
  commons direct writes, but brain-writes relay.)**

## 13. Write-model refinement (host directive, 2026-07-02) — the chatbot does not write the brain

Refines §11 #3 and **narrows §12's "chatbot keeps direct-control action tools"**:
for writes **to the universe brain** (soul + private canon), the chatbot does
**not** write directly — it **relays** to the universe intelligence, which is the
**sole writer** of its own brain.

**Rule (host, verbatim intent):** *"for the most part the user chatbot can't
write to the universe/brain. They are there to help you talk to your universe…
this way when things do get written to the universe brain it is always by the
same intelligence whether you use the app or the user chatbot — you're really
talking to the same brain and that same brain is getting to know its founder. The
user chatbot is really just a relay to your universe, and can also design branches
or write to the commons."*

**Why (coherence guarantee, not just compliance):** if BOTH the host chatbot's
own LLM *and* the universe intelligence could write the brain, the self-model is
authored by two different minds → incoherent. Restricting brain-writes to the
universe's own intelligence means the founder's picture is always assembled by one
consistent mind, identically whether reached via app (direct) or chatbot (relay).
This is also the clean resolution of the **Finding A regression** (2026-07-02
live test): the chatbot was told to "save identity to soul," found no reachable
save path, and persisted nothing — worse than before. The fix is not a reachable
chatbot save button; it is that **the chatbot was never supposed to save at all.**
It relays; the universe persists its own learning.

**Write principals, refined:**

| Writer | Brain (soul + private canon) | Branches | Commons (bugs/features/goals) |
|---|---|---|---|
| Universe intelligence (`converse`, assigned engine, in-process) | **YES — sole brain writer** | yes | yes |
| Chatbot / app, founder's WorkOS | **NO — relays via `converse`** | **yes (design branches)** | **yes** |
| Anyone else | no | no | read / file-only |

§11 #3 principal (b) ["chatbot/app with founder's WorkOS"] therefore narrows: its
direct writes are **branches + commons**, not the brain. The brain path for (b) is
**relay**. Principal (a) [the universe's own intelligence] is unchanged and is now
the *only* brain writer.

**Zero-daemons-for-authoring stays intact.** The brain writer is always "the
universe's own intelligence," but that has two instantiations: (i) a brought 24/7
engine (owned / BYO / market-rented) for app + always-on; (ii) for the no-engine
founder, the **in-session** intelligence (the chatbot seeds a subagent on its own
LLM that IS the universe intelligence for that session; the chatbot relays its
output). Either way the *writer* is the universe intelligence, never the chatbot
acting as itself. A browser-only founder still authors — through the relay, not by
the chatbot writing the brain directly.

**Implementation consequences:**
1. **`converse` becomes the brain-writer** (today it returns text only, persists
   nothing — the real gap). Each turn, after replying, the intelligence persists
   what it learned: identity/self facts → governed soul via `apply_soul_edit`
   (`soul_edit.py`); worldbuilding/canon → its own universe wiki. In-process,
   scoped to its own `universe_dir` by construction.
2. **Chatbot brain-write paths close.** `write_page` non-`kind` (private canon)
   stops writing the universe wiki; it relays to `converse`. Brain-targeting
   `write_graph` likewise. **Kept on the chatbot:** `write_graph target=branch`
   (design a branch), `run_graph`, `write_page kind=…` (commons filings),
   `write_graph target=goal` (commons goal), `write_graph target=universe`
   (one-time birth), and `converse` (the relay).
3. **Handle canary (Hard Rule 11).** If the tool catalog's write-surface changes,
   the `--assert-handles` PR-178 drift guard updates in lockstep.

**Open design points for the focused refute pass (Codex):**
- Does the intelligence persist **every** turn, or only on explicit
  confirmation? (Quality + `apply_soul_edit` has no version/lock guard —
  concurrency risk already flagged.)
- Canon-write primitive the in-process intelligence uses (direct wiki write vs a
  shared internal path) + how private-canon `write_page` "relays" (forward content
  to `converse` vs return a relay directive).
- Does `write_graph target=request` (submit a request into the universe) count as
  a brain write that must relay, or is it an action-request that stays?

## 14. Codex focused design-refute (2026-07-02) — ADAPT, build-blocking; folded

Verdict **ADAPT (build-blocking)** (Codex threadId `019f266a`, read-only, real
code re-checked). The core model — chatbot relays; only the universe intelligence
commits soul/private canon — is **sound in intent and not refuted**, but the naive
per-turn auto-persist implementation is unsafe. Adaptations, now build constraints:

1. **Split reply from commit (no blind per-turn persist).** `converse` must not
   auto-write every turn — it is a free-text reply, not a write transaction.
   Produce `{reply, proposed_learning}`; commit only through a structured internal
   `commit_learning` path, grounded in what the founder **explicitly stated** this
   turn (never invented/premature). This is the fix for "hallucinated content →
   brain."
2. **Guard `apply_soul_edit`.** Today it does blind read→write with no
   lock/CAS/version guard and derives the next snapshot number from a directory
   listing (race, `soul_edit.py:197`). Add a per-universe write lock +
   expected-version/hash check + atomic snapshot allocation before it becomes a
   per-turn path. (Pre-existing correctness debt; the reshape makes it load-bearing.)
3. **Typed relay for private canon — do NOT flatten to free-text `converse`.** A
   structured `write_page` carries page/category/filename/content/old_text/
   new_text/expected_sha256/dry_run; forwarding it as a chat string loses the
   intent. Chatbot private-canon `write_page` routes to a typed internal
   `handle_private_canon_write(intent)` on the intelligence returning
   `committed | proposed | rejected`.
4. **Zero-engine authoring = seed notes, not brain commits.** `converse` runs
   server-side via `call_provider`, not the chatbot's in-session LLM; a universe
   with empty `preferred_writer` cannot commit. A no-engine founder (direct WorkOS)
   may write **pending founder seed notes/drafts**, branches, commons, requests —
   but **promotion into governed soul / private canon requires an assigned/running
   intelligence** (`set_engine` first). Preserves zero-daemons-for-authoring
   without letting the chatbot commit the brain. (Amends §13's hand-wavy in-session
   subagent claim for M1.)
5. **Freeze the advertised handle set before build.** Repo is inconsistent —
   comment/canary say "five," but the canary + `test_universe_server_five_handles.py`
   already include `converse` as a sixth. Freeze to **canonical six + `get_status`**;
   update the Hard Rule 11 `--assert-handles` canary/docs in lockstep. Closing
   brain-write *internals* needs no catalog change (handles unchanged); only
   behavior changes.
6. **Crisp write-authorization law (reconciles §11#4 ↔ §13; supersedes on
   conflict):** direct WorkOS (chatbot/app) may write **branches, commons,
   requests, and pending founder seed notes**; only the **assigned/running universe
   intelligence** may promote into **governed soul + private canon**. This answers
   the §13 open question: `write_graph target=request` is an action-request that
   **stays** on the chatbot (not a brain commit).

## 15. Implementation + Codex impl-review (2026-07-02) — APPROVED for live test

Built on `claude/founder-identity-allslices` (5 slices, TDD, 210 affected tests
green, ruff-clean on changed lines, plugin mirror rebuilt):

- **Slice 0** — `soul_edit.apply_soul_edit` guarded: per-universe `_soul_lock`
  (msvcrt/fcntl sidecar) across the read→write→snapshot section (closes the
  snapshot-number race) + optional `expected_versions` compare-and-swap +
  `current_soul_versions` helper.
- **Slice 1** — `universe_intelligence.converse` is now the brain-writer:
  after the reply it runs `extract_learning` (a second, narrow strict-JSON engine
  turn grounded in the founder's explicit words) → `commit_learning` persists
  governed soul via guarded `apply_soul_edit`; wrapped so persistence never
  breaks the reply.
- **Slice 2a** — worldbuilding → the universe's own canon:
  `wiki.write_universe_canon` (first-party, scoped to the universe's wiki root,
  bypasses the external-caller ACL gate like `converse`/`apply_soul_edit`) driven
  by `commit_learning._commit_canon`.
- **Slice 2b** — chatbot brain-writes closed: `universe_server.write_page`
  relays (`relay_to_universe`) any universe-targeted page write/patch;
  commons/`kind=` unchanged. Plus (Codex impl-review #0) the deprecated fat
  `universe` tool's `_BRAIN_WRITE_RELAY_ACTIONS` (`set_premise`/`add_canon`/
  `add_canon_from_path`/`soul.edit`) relay at the MCP wrapper (not `_universe_impl`,
  so app/runtime/`create_universe` are unaffected).
- **Slice 2c** — `prompts.py` control_station + meet_universe reshaped: the
  chatbot RELAYS identity + world to the universe via `converse`; it does not
  route identity to `soul.edit` or canon to `wiki` itself.

**Codex design-refute (§14) = ADAPT (folded). Codex impl-review (thread
019f268b) = REFUTED → fixed → re-review APPROVE for the live browser test:**
- Fixed #0 (legacy `universe`-tool brain-write doors → relay), #2 (patch relay
  no longer flattens partial patches — asks the founder to describe via
  `converse`), #3 (CAS includes implicit `identity.md` when a name is learned).
- **Deferred (Codex-accepted for M1, must-follow-up):**
  (a) authenticated founders cannot free-form commons-write via `write_page`
  (omitted id resolves to home → relays; kept fail-closed to prevent a
  private-canon→public-commons leak) — planned fix: a `scope="commons"` param;
  (b) grounding is prompt-only (no deterministic evidence-quote check) — fine for
  M1 tested with explicit founder facts;
  (c) **legacy `tinyassets/mcp_server.py`** (single-universe daemon server that
  `.mcp.example.json` points at) still exposes direct `set_premise`/`add_canon`
  brain writes — NOT the live surface (`tinyassets.io/mcp` = `universe_server`;
  Docker/tray use it), so non-blocking, but the same directive applies there and
  it needs closing (or the universe-intelligence relay wired into that server).

**Remaining gate:** live rendered-chatbot `ui-test` through the real connector
proving the regression is fixed (identity → soul, world → canon persist; chatbot
relays, never writes the brain) + post-fix clean-use evidence.

## 16. Live chatbot test + fixes (2026-07-03) — sandbox P0 + onboarding UX

First live rendered-chatbot run (fresh founder, local branch server via tunnel).
Regression fix held (identity → soul, world → canon persisted; chatbot relayed).
It surfaced a set of defects, now fixed on the branch:

**Onboarding / relay UX** (`api/prompts.py` control_station, `universe_server.py`
`instructions`, `api/status.py` next_step): the connector dumped a tool inventory
instead of calling `get_status` first; treated first-person as an opt-in menu
("do you want it to speak as itself?"); over-narrated every relayed reply; did the
universe's work (WebFetch'd a founder's link itself instead of relaying); used the
jargon "personify". Now: get_status-first + no tool inventory; first-person is the
DEFAULT the moment the universe exists (no consent menu); thin relay (render + stop);
relay links/files, never fetch/answer them; natural next-step copy.

**P0 — engine isolation.** `converse` runs `claude -p`, which was spawned with the
FULL default toolset and NO cwd isolation → the universe read the platform source +
uncommitted diff, ran Bash/gh, cloned repos, and reached the logged-in claude.ai MCP
account connectors (Google Drive, the TinyAssets MCP itself, `mcp__codex` → code
exec). Fixed (`universe_intelligence._sandboxed_config` + `providers/claude_provider
._sandbox_cli_args`): every universe-intelligence turn runs `cwd=universe_dir`,
`--setting-sources project` (strips user MCP + `bypassPermissions`), `--allowedTools
WebFetch`, and a comprehensive `--disallowedTools` denylist (Bash/**Monitor**/Read/
Write/Edit/Glob/Grep/Task/Workflow/Skill/Cron*/RemoteTrigger/SendMessage/DesignSync/…
+ `mcp__*`). Codex fails closed when asked to sandbox (can't confine); claude fails
closed if `universe_dir` is None. Empirically exploit-proofed: a create-file / run-
Monitor attempt returns CANT with no file created; a repo-read + bash attempt is
denied; WebFetch (the one allowed capability) still works.

**Grounding:** `_LEARNING_SYSTEM` was stamping generic "I am a personified universe
that starts blank" boilerplate as learned identity; added a deterministic
`_is_generic_identity_boilerplate` guard in `commit_learning`.

**Verification:** Codex adversarial review ADAPT (4 findings: codex-provider bypass,
missing-universe_dir fail-open, incomplete denylist, prompt-only grounding) → all
fixed → **APPROVE**; the MCP/Monitor exec vectors were then found + closed
empirically (beyond static review). 96 affected tests green, ruff clean, plugin
mirror rebuilt.

**Residual (production hardening, NOT this pass):**
- **OS sandbox (bwrap/container)** is the durable fix — the CLI has no allow-only
  mode, so isolation rides a denylist that WILL rot as new builtins ship, and a raw
  `Read` tool can't be subtree-confined (so tool-level "own-files" is deferred; the
  universe knows itself via injected context, not a Read tool).
- **WebFetch SSRF guard** — block internal / cloud-metadata IPs (a founder's
  universe can currently fetch arbitrary URLs, incl. `169.254.169.254`).
- Still open from §15: `write_page scope=commons`; legacy `mcp_server.py` doors.
- Not committed; branch remains WIP.
