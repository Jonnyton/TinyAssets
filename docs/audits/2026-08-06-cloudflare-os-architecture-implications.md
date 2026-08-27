# Cloudflare OS — architecture implications for TinyAssets

`initial_provider: claude-code` · `required_reviewer: codex` · **`verdict: adapt`** (2026-08-06)

## Source freshness

| | |
|---|---|
| Canonical | https://github.com/cloudflare/cloudflare-os |
| Homepage | https://os.cloudflare.app |
| License | Apache-2.0 · TypeScript · pnpm monorepo on Cloudflare Workers |
| Created | 2026-04-15 · **pushed 2026-08-06** (same day as this study) |
| Stars | 5,065 |
| Stage | Self-described **early access**; repo is "version 2, a complete rewrite" |
| Read at | 2026-08-06, via GitHub API — README, `packages/` listing, `packages/gatekeeper-slack/README.md`, `docs/observers.md` |

Evidence below is quoted from those files. Anything marked *inference* is mine.

## Executive judgment

Cloudflare OS is the closest public analogue to the surface TinyAssets is
building right now, and it independently arrived at **two of the same answers**,
which is the strongest signal in this study:

1. **Capability-based security for agents, not ACLs.** Their thesis — *"Agents
   cannot simply be treated as users. They must be accountable to a human user,
   while at the same time having their own restricted permissions. The ideal
   security model for all of this is capability-based security, not access
   control lists."* TinyAssets landed a sealed `FounderGrant` capability three
   days ago for exactly this reason. Convergent evolution, not borrowing.
2. **Most-specific-binding-wins routing.** Their Slack gatekeeper grants at
   workspace / conversation / thread granularity and says *"more-specific
   conversation and thread URLs take precedence."* `ChannelRouter` uses the
   same rule (channel > workspace).

The genuinely new ideas — the ones TinyAssets does **not** have — are
asynchronous human-in-the-loop via simulation, and observer/read-through
sharing. Both are directly relevant, and neither is a small build.

**What this does NOT change:** the platform shape. Cloudflare OS is a
per-company deployment where every user runs private instances of apps. That is
a different product from a public commons with lineage and remix. Do not import
the platform; import the primitives.

## Outside system, module by module

| Concern | Cloudflare OS |
|---|---|
| Entry / shell | `workshop-frontend` — agent chat UI |
| Kernel | `workshop-backend` — connects users to Gadgets/Gatekeepers, sandboxes, enforces access |
| "Drivers" | `gatekeeper-*` (19 of them: slack, github, google, notion, linear, confluence, mcp, mcp-portal, scheduler, email, homeassistant, spotify, supabase, zoominfo, cloudflare, context) |
| Process | a **Gadget** — a private per-user instance of an app, in its own sandbox |
| Executable | a **Blueprint** — a template that specifies a whole application, shareable |
| Isolation | every workspace is a Durable Object; every Gadget a Dynamic Worker **Facet** |
| Portability | runs on `workerd` (open source) on your own servers, not only on Cloudflare |

Their own analogy table maps kernel/drivers/shell/processes/executables/users/ACLs
onto these, and lists **agents** as the primitive traditional OSes lack.

### Gatekeepers — "supercharged MCP servers"

Per the README, each gatekeeper: wraps the native API in a clean Cap'n Web API;
handles OAuth; **enforces narrow access to only the specific resource the user
intended**; **logs every action for review**; and gates side-effecting actions
behind human approval.

### The headline innovation: asynchronous approval by simulation

> "When the agent performs an action that requires approval, the Gatekeeper will
> *simulate* the outcome locally, allowing the agent to proceed and queue up more
> actions... Once the agent is done, the user may approve or reject the actions
> in bulk, or one-by-one, but either way, they can do it later."

Their stated motivation is that synchronous approval is what drives people to
`--dangerously-skip-permissions`. That is a real, named failure mode this
project also has exposure to.

### `gatekeeper-slack` — the direct analogue to current work

- **Read-only.** *"never sends or modifies Slack data."*
- **User token (`xoxp-`) via `user_scope`, not a bot token** — *"so the agent
  sees exactly what the connecting user can see."*
- **Token rotation on**, ~12h tokens refreshed via `grant_type=refresh_token`.
- Three grant granularities (workspace / conversation / thread), each a URL
  pattern that drives **both which OAuth scopes are requested and routing**.
- Conversation-scoped search is *"hard-restricted to the bound conversation
  regardless of query."*

## TinyAssets comparison

| Dimension | Cloudflare OS | TinyAssets (verified 2026-08-06) |
|---|---|---|
| Agent authority | capability, per-resource | sealed `FounderGrant` capability + `universe_acl` ACLs — **hybrid** |
| Binding granularity | workspace / conversation / **thread** | workspace / channel (`app_channel_bindings`) — no thread level |
| Scope ↔ binding | one URL pattern drives consent scopes AND routing | routing only; OAuth scopes are global to the app |
| Slack direction | read-only | **posts** — so a bot token is correct here, see below |
| Per-action audit | gatekeeper logs every action for user review | `deliver_app_event` returns a receipt; no user-reviewable action log |
| Side-effect approval | async, simulated, bulk-approved later | none on the chat path |
| Share/remix safety | observers + read-through re-verification | **not found** — see O-1 |
| Isolation | Durable Object / Dynamic Worker Facet per gadget | container + in-process confinement; OS sandbox is a standing P1 |

**On the token difference — this is a legitimate divergence, not a gap.**
`slack_transport.py:43` already says *"Bot tokens only. An `xoxp-` user token
posts under a person's name"*, and `credential_vault.py:475` documents the split.
Their gatekeeper only reads, so a user token correctly bounds visibility to the
connecting human. Ours *posts as the universe*, where a user token would
impersonate the human. Both are right for their direction. The principle worth
importing is the **separation** — read capability and write capability should be
distinct grants — not the specific token type.

## Implications

### A-1 `Adopt` — per-action audit log on the ingress path
The gatekeeper logs every action for the user's review. `deliver_app_event`
currently returns `handled` + a receipt ref and logs only failures. For MCP-chatbot
users, "what has my universe done on my behalf in Slack" is not answerable today.
**Maps to:** `app_ingress.deliver_app_event`, attribution/provenance ledger.
**Smallest slice:** append one row per delivered event (universe, actor, channel,
event id, receipt ref, grant-or-not) to an existing durable store; expose via
`read_graph`. **Risk:** logging user message text into a shared store — log ids
and outcomes, not content. **Verify:** a founder can enumerate their own turns; a
non-owner cannot.

### A-2 `Adapt` — bind scope to the binding, not to the app
Their grant URL drives *which OAuth scopes are requested*. TinyAssets binds a
channel for routing while the Slack app holds workspace-wide scopes, so the
binding narrows *where messages go*, not *what the credential can reach*.
**Maps to:** `app_channel_bindings`, `chat_surface.connect_account`.
**Risk:** re-consent flows on every narrowing. **Defer-adjacent:** worth doing
when the connection record grows a scope column (already flagged in
`DEFAULT_SLACK_CONNECTION`'s docstring as the durable home for per-binding
connection data).

### A-3 `Adapt` — thread-level binding
They bind at thread granularity; we stop at channel. A thread is exactly the unit
a founder would want to hand to one universe without giving it the channel.
**Maps to:** `AppChannelBindingStore` (`channel_id = ''` is already the
workspace-wide row, so the most-specific-wins ladder extends naturally).

### W-1 `Watch` — asynchronous approval by simulation
The strongest idea in the repo, and the one I am least confident about importing.
Simulating an outcome and telling the agent it succeeded means the agent reasons
over **facts that may be revoked**. For a universe that commits durable learning
from a conversation, a rejected action could leave learning grounded in an event
that never happened. Cloudflare's gadgets are largely stateless per action;
TinyAssets' universes are not. **Do not adopt before deciding what happens to
learning committed on top of a simulated action that is later rejected.**
Relevant to the paid-market/effects lanes, not to chat ingress.

### O-1 `Adopt`, pending verification — observer / read-through sharing
`docs/observers.md`: when a Gadget is shared, each gatekeeper verifies the new
user's *own* connected account can already read everything the Gadget has read;
future observations that any observer lacks privileges for are **blocked**; access
is re-checked on every open.

TinyAssets has the same exposure by construction: a universe reads from connected
services under one user's credentials, and its outputs are remixable and can be
public. I searched `tinyassets/` for observer/read-through enforcement and found
none (the `rollback.py` / `runs.py` hits are an unrelated sense of the word).
**I am flagging this as a candidate gap, not a confirmed one** — TinyAssets'
sharing model is nodes/lineage rather than gadget instances, and the visibility
gate may cover it from a different angle. **This is the single most valuable
thing for the reviewer to check.**

### X-1 `Avoid` — the Gadget/Blueprint platform model
Per-user private instances of every app is a coherent answer to *company*
productivity. It is the opposite of a public commons with lineage, attribution
and remix, which is the shape the host has repeatedly steered toward. Importing
it would fork the product thesis.

### X-2 `Avoid` — Workers/Durable Objects/Facets as the isolation answer
Their per-gadget isolation is excellent and rests on runtime features Cloudflare
added *specifically for this*. TinyAssets' standing P1 is an OS sandbox for the
engine turn. Adopting Facets means adopting the Workers runtime as a dependency
of the execution model. `workerd` being open source makes this less absolute than
it looks — worth knowing, not worth pivoting to.

## Cross-provider review gate

`initial_provider: claude-code` → **required reviewer: `codex`** (AGENTS.md
§"Project Skills"). No build work on any row below may start until the review
artifact returns `approve` or `adapt`.

The reviewer should re-read the primary sources and specifically:
1. **Settle O-1.** Does TinyAssets already prevent a shared/remixed artifact from
   exposing data the recipient could not read directly? If not, how large is it?
2. Check whether A-1's audit log duplicates an existing ledger
   (`attribution/`, `runs.py`) rather than needing a new one.
3. Challenge W-1's objection — is "learning grounded in a rejected simulated
   action" actually reachable, or have I over-read it?

## Pickup packet

| | |
|---|---|
| Concept | Gatekeeper-shaped capability discipline for chat ingress |
| Source | this file; https://github.com/cloudflare/cloudflare-os @ 2026-08-06 |
| Initial provider | `claude-code` · Reviewer: `codex` |
| Applies when touching | `app_ingress*`, `app_channel_bindings`, `chat_surface`, sharing/remix visibility, effects approval |
| Next home | `STATUS.md` Work row (review), `ideas/PIPELINE.md` (A-2/A-3/W-1) |
| Exact next action | Codex review artifact answering the three questions above |
| Write boundary | `docs/audits/2026-08-06-cloudflare-os-*.md` only, until verdict |
| Blocked on | cross-provider review |
| Exit check | verdict recorded; O-1 resolved as gap or non-gap with evidence |

## Worktree landing packet

| | |
|---|---|
| Branch | `codex/cloudflare-os-implications-review` (review), then `claude/chat-ingress-audit-log` (A-1) |
| Worktree | `../wf-cloudflare-os-review` |
| Base | `origin/main` |
| Depends | A-1 depends on this review returning `approve`/`adapt`; also on PR #2348's `app_ingress` landing |
| Write-set (A-1) | `tinyassets/api/app_ingress.py`, `tests/test_app_ingress.py` |
| First slice | one audit row per delivered event, ids and outcomes only, no message text |
| Gates | pre-commit: mutation-probe the new guards; pre-push: `test_universe_server_five_handles` (no new MCP handle); pre-live: founder can enumerate own turns, non-owner cannot |
| Fold-back | PR into `main`, retire the STATUS review row, promote A-2/A-3/W-1 to `ideas/PIPELINE.md` |
| PLAN modules | review the storage/provenance and visibility modules before building A-1 |
| Memory refs | `.claude/agent-memory/` — none specific to this source yet |
| Related implications | the `app_ingress` lane in `openspec/changes/archive/2026-08-26-recognize-verified-founder-on-chat-surfaces/tasks.md` §10 |

## Open questions

- O-1 (above) is the load-bearing unknown.
- Cloudflare OS is early access and rewriting fast (v2, pushed daily). Any claim
  here should be re-stamped before it drives a build more than a few weeks out.
- Cap'n Web as the gatekeeper API shape was not studied; it may or may not matter.


---

# Codex review — verdict `adapt` (2026-08-06)

## O-1 is CONFIRMED, and it is a live exposure, not a design question

Codex did not reason about it — it **reproduced** it: *"anonymous search returned
the confidential excerpt and anonymous read returned the complete draft."*

I re-verified the two load-bearing facts independently:

* `visibility.py:88` — `DEFAULT_CREATE_VISIBILITY = "public"`, and
  `PUBLIC = VisibilityLevel("public", True, True, True)`.
* `universe_intelligence.py:549-552` — a FOUNDER turn calls
  `commit_learning(udir, proposed, ...)`. There is no visibility argument, and
  learned canon pages get no restrictive frontmatter, so page visibility defers
  to the universe (`visibility.py:256-288`).

**Chain:** founder says something confidential to their universe → founder tier
commits it as canon → universe is public by default → anonymous `read_page` and
search return it.

**This does not depend on the Slack work.** `converse` is a live canonical
handle, so the chain is reachable through the chatbot today. The un-landed
`app_ingress` adds a second entrance (a private Slack channel), it does not
create the problem.

**Framing that matters for the fix:** public-by-default is a defensible commons
choice and is probably not what should change. What is missing is that input
gathered in a *private* context inherits the public default with **no narrowing
step and no prompt**. Codex also notes `universe_acl`/`public_read` protect the
whole universe, never upstream entitlements — TinyAssets tracks who may read the
destination, never whether a reader could have read every source folded into it.
That is precisely the property Cloudflare's observers enforce.

Scoped out by Codex: legitimate branch remix DOES require the parent version to
be readable first (`branches.py:2426-2435, 2285-2324`), so forking a private
branch is blocked; and `_action_record_remix` copies no content
(`market.py:996-1072`) — it is not an exfiltration path, though it validates
neither artifact existence nor ACL.

## A-1 must EXTEND an existing ledger, not add one

I would have built a duplicate. Codex found:

* `tinyassets/storage/app_events.py:21-37,107-187` — the replay ledger already
  writes one **content-free** row per authenticated event: provider,
  installation, event id/type, timestamp, body digest. A-1 should add delivery
  outcome, routed universe, actor/channel and receipt to **this**.
* `tinyassets/app_outbound_adapter.py:120-203` — an `app_outbound_receipts`
  outcome/digest store already exists and is **not wired into**
  `deliver_app_event` (`app_ingress.py:172-179`). That is a gap in the new code
  from this session, not in the old code.
* Attribution records remix edges and credit, not user actions
  (`attribution/schema.py:32-82`); `runs.py` receipts require a run and accept
  only three provenance types, and chat ingress creates no run.

## W-1: my objection was right about the hazard, wrong about the reason

Codex: not currently reachable. Universe turns allow only `WebFetch` and deny
MCP/remote-effect tools; learning sees only the founder message and the reply and
commits only at founder tier (`universe_intelligence.py:61-93,330-345,531-552`).
A future integration hazard, not a present defect.

## Two factual corrections to my own artifact

1. **"Cloudflare's gadgets are largely stateless per action" is WRONG.** Gadgets
   are Durable-Object-backed persistent applications, and the current code keeps
   provisional state through **accept/revert lifecycles** (`workshop-backend/src/overseer.ts`).
   This inverts my conclusion: they did not avoid the durable-state problem, they
   *solved* it — so the thing to consider adopting is the accept/revert
   lifecycle, not to avoid simulation because we have durable state.
2. **"Each gatekeeper verifies" is overstated.** Enforcement covers in-scope
   bindings; documented strategies include no-op/low-stakes and non-shareable
   resources.

## Resulting priority change

O-1 stops being a research implication and becomes a production concern in its
own lane. It is filed as a STATUS Concern; it must not ride on the chat-ingress
PR.
