# Basic user capabilities: checklist

The founder's standing goal (2026-09-24): every basic capability a user should
have, whether or not a current user is blocked by it, carried until it is
**cleared**. Cleared means deployed, succeeds through the real app,
regressions green and spec synced. Derived from PLAN.md and specs in
[the gap audit](../../../docs/reviews/2026-09-24-capability-gap-audit.md) (C-numbers).
Detailed per-slice evidence while Codex worked lives on the unpushed branch
`codex/connect-cross-user-nodes`
(`openspec/changes/consolidate-platform-resource-policy/remaining-work.md` and
`completed-work.md`). This file is the list on `main`.

Update it in the same PR that clears or adds an item. Delete a row when it is
cleared, and add one line to the completion record.

## Open: ranked by what depends on it

| # | Capability | Acceptance (through the real app) |
|---|---|---|
| C27 | Give, see and revoke what your agent may do (channel consent, full-channel access, withdraw stale asks) | The app agent reads what it holds, changes one channel policy and withdraws its own stale request; readback matches |
| C16 | Scheduled and event-triggered runs fire as the owner with no host online | A scheduled run and an inbound-webhook run each complete as the owner while no host is online |
| C26 | Connect any external service (OAuth2 refresh, form bodies, inbound signature verification) | A Google-OAuth channel still works after 1 h of token expiry; a form-encoded call succeeds; a signed webhook is verified |
| C6 | Connect ANY compute source through vendor-neutral primitives, with no vendor code (PR #3949 directive) | The user's agent connects a provider the platform has never seen (OAuth or API key plus a standard protocol, or a command adapter) and it answers a turn with tools, with no platform patch |
| C2 | Same account, same universe from any client (Claude, ChatGPT, app, phone) | The same user reaches the same universe from ChatGPT and Claude, and sees the same history |
| C29a | A send never vanishes silently (idle-tab 503 dropped two sends, 2026-09-24) | A send that fails leaves the text visible with "not sent, send again"; no silent drop |
| C13 | Parallel and sequential runs are reliable | 20 consecutive checklist runs with no timeout and no replay. Progress 2026-09-24: cause found and fixed (PR3953: workflow nodes ran the CLI in /app with tools, and the model explored the source); since then 21/23 clean including 5 simultaneous (56-108s), sequential 18 clean in a row. Close after a few more ordinary retests with 0 timeouts |
| C9 | Connections stay alive: generic OAuth token refresh for any connection | An OAuth-connected compute source or channel keeps working past token expiry across concurrent turns, with no reconnect and no vendor code |
| C7 | Choose, see and switch models; defaults, fallback, failover | The actual source and model are shown; the selection, default and order are honored; failover on limit |
| C8 | Connection progress; disconnect and reconnect | Saving, binding and result are visible, with bounded waits; access is preserved on refusal |
| C5/C1 | First power with no LLM call: OpenRouter free or the user's own OpenRouter account at sign-in | A new free user signs in, authorizes OpenRouter, returns automatically, and gets a free-model answer with tools; no key paste |
| C15 | Resume an interrupted run on its admitted version | Interrupt a run, resume it, and it runs the admitted version, not the edited draft |
| C22 | Get outputs back: download run files, and a notice when background work finishes | Download a file a run produced; a notice arrives when a background run ends |
| C20 | Publish and remix any shape (workflow, agent, design) across users | User B remixes User A's published workflow into B's own universe; B's data is kept and nothing is inherited |
| C28 | Deliver work between different owners' nodes | Two owners send and process, inspect both receipts, and verify rejection, duplicates and revocation. Needs MULTI-USER live testing with two real accounts — e.g. owner A builds an intake node with conditions; owner B delivers a bug report to it through the app. There is no platform feedback inbox; see the C28 shape note below |
| C17 | Concurrent edits do not silently overwrite | A stale-read patch is refused with the current version |
| C18 | Version history and rollback | The agent lists versions and rolls back; the run uses the rolled-back version |
| C30 | Stop a running turn | Stop mid-turn; the provider process ends within seconds and the turn is recorded as user-stopped |
| C4 | Export your own data and workflows | Export a universe bundle from the app and re-import it into a fresh universe |
| C3 | Delete your account or any data | Delete through the app; no residue is readable and no other user is affected |
| C31 | Memory: the universe keeps what you tell it, and you can inspect and correct it | Tell it a fact, open a fresh thread, it recalls the fact; correct it and it stays corrected |
| C24 | Cloud dependencies and previews for your own work | The agent installs an admitted dependency and produces a usable preview capture (compose it from C22) |
| C25 | See status, usage and limits | The app explains actual storage, admissions and limits for this universe |
| C32 | Everything works with no host online (cloud-only) | Authenticated uptime probes plus ordinary cloud-only use pass |
| C33 | Design, share and switch your own app experience | A user redesigns their app UI through their universe — any interactive UI they can imagine, e.g. an office-building simulation, including opening sessions with other agents in their universe from within it — shares it, and a second user switches to it on the fly and back |

## Shape carried from closed PRs

Directional decisions the acceptance column cannot hold. Each names the row it
binds and where it came from; the row above is still the pass/fail bar. Only C33
adds a row — the founder added that capability on 2026-09-26; the rest bind to
rows that already existed.

### C4 — export is the universe folder, not a second envelope

PR #3840 built a separate portable "project" envelope with its own descriptor,
inventory and digest, and was closed. The keep is the direction, not the
envelope: **the export is built from the universe folder itself**, which is
already the harness (skills, prompts, extensions, workflows, bin, notes, wiki,
brain files). A second container is a second definition of the same folder, and
the repo has paid for that shape before.

The exclusion rule, which is the part worth pinning:

- **In** — public source and deliberate seed assets.
- **Out** — private bindings, credentials, run state, and **every entry the
  jail already masks**. That set is not hand-listed here either: it is the one
  in [`universe-harness-four-tools/design.md` D2](../universe-harness-four-tools/design.md)
  (the credential vault, the per-universe authority databases, `.runtime/`, and
  every hidden root entry). One definition, read by both.

**Edits carry a stale-digest refusal.** An edit submits the digest it read; a
digest that no longer matches is refused with the current one rather than
applied, which is C17's rule on this surface. Unrelated bytes and the descriptor
are preserved, and a no-op edit changes nothing.

### C3 — deletion erases what the user reported, too

**Account deletion must erase the feedback and bug reports the user submitted.**
Carried from PR #3747, which was closed. Anything less makes "we deleted your
data" false, which is exactly what `/legal` and the Play deletion path promise.

Already satisfied by construction, with one condition to check when feedback
storage lands: `account_deletion` derives its row set from the live schema, so a
table keyed by `universe_id` or by one of `PRINCIPAL_KEYS` is covered the day
its migration lands. The condition is that feedback rows are keyed that way and
are not added to `PRESERVED_TABLES`. A satellite store needs the satellite
sweep. No hand-written table list — see the module docstring on why.

### C28 — feedback is a delivery between two owners' nodes

**There is no platform feedback inbox.** Founder, 2026-09-26, correcting the
direction on this row. PR #3747 built one configured global reviewer
(`TINYASSETS_FEEDBACK_REVIEWER`, a principal id read from server env) and was
closed; the shape is not a smaller version of that.

Feedback flows through the **general user-to-user channels**, with no surface
built for feedback specifically:

- Any user builds a node that **accepts deliverables under conditions they build
  into it**. The conditions are the author's, not the platform's.
- The founder's own account builds a bug and feedback intake node **exactly like
  any user would** — same primitives, same authoring contracts, no reserved path.
- The same mechanism serves shared projects, or any other reason users connect
  nodes between universes. Feedback is one use of it, not its purpose.

That is C28 (deliver work between different owners' nodes), and it **should
already be possible** with what is built. So the work here is not a feature: it
is **multi-user live testing** — two real accounts, an intake node with
author-set conditions on one, a delivery from the other through the app. The C28
acceptance row above now carries that case.

Same rule as the first-party parity requirement in
[`composable-ui-experiences/design.md`](../composable-ui-experiences/design.md):
the platform does not get a path a user cannot author. A platform-held inbox
would have been exactly that path.

### C33 — the app experience is the user's to design, share and switch

New row above, founder 2026-09-26. The app UI is not a platform layout with user
themes on top: a user **redesigns their app experience through their universe**,
and it can be any interactive UI they can imagine — an office-building
simulation, a command centre, something nobody has named — including **opening
sessions with other agents in their universe from inside it**. Then they share
it, and another user **switches to it on the fly and back**. Switching is part of
the capability, not a later nicety; an experience you cannot leave is a
replacement, not a choice.

**Start from the prototype, not from scratch.** PR #3842 was closed, but its
inert experience preview is the working starting point — editable composition,
desktop/phone layouts, typed fixture actions, unknown components preserved, and
it sends no actions and grants no authority. Branch
`tiny/u-01kxm1vszd/refine-experience-primitives`; design in
[`composable-ui-experiences/`](../composable-ui-experiences/design.md).

**The no-privileged-path line holds** and is what makes this row reachable at
all: the platform's own app experiences use the same authoring contracts as
users, so a user's redesign is not a lesser tier of the same surface. That
requirement is in `composable-ui-experiences/design.md` under "Composition
model"; do not weaken it to ship a first-party layout faster.

### C24 — the network this row needs

Installing an admitted dependency needs network from inside the jail, which the
four tools do not have today. That is scoping, not policy: see
[`universe-harness-four-tools/design.md` D7](../universe-harness-four-tools/design.md)
— limit, never forbid. C24 is the use case that turns per-tenant egress from
speculative work into a build; do not relax the jail's `share_net` globally to
clear it.

## Completion record

- C10 Build workflows from primitives, with no graph-size cap (spec synced; the agent builds its own probes)
- C11 Edit in place: content, model, effects, workspace, outputs, timeout, execution choices (PR3900/3903/3924/3942; 2026-09-23 23:26 PDT app acceptance)
- C12 Run and read outputs and node status (PR3902)
- C14 Cancel, including a workspace wait (PR3927)
- C19 Delete a workflow
- C21 Upload files for runs (PR3896/3897)
- C23 Durable workspace waiting (PR3950 + nomination fix PR3969). Live 2026-09-24 15:38 PDT: two contending runs both completed and the queue handed off in 0.13s. Restart survival is Linux-oracle proven, not live-induced
- C29 Converse; replies survive refresh and long replies (PR3907/3916/3891). Partly reopened as C29a.
