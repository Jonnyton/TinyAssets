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
| C6 | Connect any LLM (API key, compatible endpoint, named-header auth, unanticipated CLI) | A compatible endpoint using a named-header key answers a turn with tools |
| C2 | Same account, same universe from any client (Claude, ChatGPT, app, phone) | The same user reaches the same universe from ChatGPT and Claude, and sees the same history |
| C29a | A send never vanishes silently (idle-tab 503 dropped two sends, 2026-09-24) | A send that fails leaves the text visible with "not sent, send again"; no silent drop |
| C13 | Parallel and sequential runs are reliable | 20 consecutive checklist runs with no timeout and no replay |
| C9 | Credentials stay alive through refresh | A subscription credential survives rotation across concurrent turns without a reconnect (primitive decision pending; see the refresh hold) |
| C7 | Choose, see and switch models; defaults, fallback, failover | The actual source and model are shown; the selection, default and order are honored; failover on limit |
| C8 | Connection progress; disconnect and reconnect | Saving, binding and result are visible, with bounded waits; access is preserved on refusal |
| C5/C1 | Free-only onboarding, pristine first contact | A new free user signs in, authorizes OpenRouter, returns automatically, and gets a free-model answer with tools; no key paste |
| C15 | Resume an interrupted run on its admitted version | Interrupt a run, resume it, and it runs the admitted version, not the edited draft |
| C22 | Get outputs back: download run files, and a notice when background work finishes | Download a file a run produced; a notice arrives when a background run ends |
| C23 | Workspaces, including durable concurrent waiting | Two runs contend; the second waits durably across a restart and proceeds; cancel still works |
| C20 | Publish and remix any shape (workflow, agent, design) across users | User B remixes User A's published workflow into B's own universe; B's data is kept and nothing is inherited |
| C28 | Deliver work between different owners' nodes | Two owners send and process, inspect both receipts, and verify rejection, duplicates and revocation |
| C17 | Concurrent edits do not silently overwrite | A stale-read patch is refused with the current version |
| C18 | Version history and rollback | The agent lists versions and rolls back; the run uses the rolled-back version |
| C30 | Stop a running turn | Stop mid-turn; the provider process ends within seconds and the turn is recorded as user-stopped |
| C4 | Export your own data and workflows | Export a universe bundle from the app and re-import it into a fresh universe |
| C3 | Delete your account or any data | Delete through the app; no residue is readable and no other user is affected |
| C31 | Memory: the universe keeps what you tell it, and you can inspect and correct it | Tell it a fact, open a fresh thread, it recalls the fact; correct it and it stays corrected |
| C24 | Cloud dependencies and previews for your own work | The agent installs an admitted dependency and produces a usable preview capture (compose it from C22) |
| C25 | See status, usage and limits | The app explains actual storage, admissions and limits for this universe |
| C32 | Everything works with no host online (cloud-only) | Authenticated uptime probes plus ordinary cloud-only use pass |

## Completion record

- C10 Build workflows from primitives, with no graph-size cap (spec synced; the agent builds its own probes)
- C11 Edit in place: content, model, effects, workspace, outputs, timeout, execution choices (PR3900/3903/3924/3942; 2026-09-23 23:26 PDT app acceptance)
- C12 Run and read outputs and node status (PR3902)
- C14 Cancel, including a workspace wait (PR3927)
- C19 Delete a workflow
- C21 Upload files for runs (PR3896/3897)
- C29 Converse; replies survive refresh and long replies (PR3907/3916/3891). Partly reopened as C29a.
