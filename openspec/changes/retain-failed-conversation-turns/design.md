## Context

Source reverified on production/main89a335578a1576a1b4253375e6d900a770338009,
September15,2026 UTC. The goal-ledger checkout has older runtime sources; use
this isolated worktree, not its line numbers. `universe_server.converse`2415
returns errors before record_exchange2435. Store record_exchange332 atomically
stores founder/universe and prunes to400rows. Readers are conversation_store,
conversation_retrieval, api/status1730 and conversation_memory. App
renderConverse2000 preserves a failed turn only locally; loadHistory3941 and
restoreInflight3972 treat every non-universe speaker as founder.

The existing `_served_failure_notice` can return exception text in its unknown
case. Its output and `_served_failure_diagnosis` MUST NOT be copied into durable
metadata wholesale. An allowlisted platform-authored representation is required.

## Goals / Non-Goals

Goals: owner can refresh, send another message, and ask their agent what failed;
the original message survives verbatim with a correctly attributed safe notice.
All existing owner/session and untrusted-memory boundaries remain.

Non-goals: replay/idempotent execution service; crash-complete journaling before
execution; raw attempt logs; restoring deleted history; changing provider
permissions, default/fallback behavior, FIFO executor or private workflows.

## Decisions

1. Add optional `failure_json TEXT NOT NULL DEFAULT ''` to the same conversation
   table. Define a small validated version1 object with kind `turn_failed` and
   an allowlisted code, not arbitrary provider/class/text fields. Code mapping
   renders a fixed safe message. Codes cover evidenced auth/usage/timeout/
   platform/setup cases and explicit `unknown`. Native provider sign-in clues
   retain their uncertainty; they do not become proven credential diagnoses.
   No execution receipt is stored on a failure notice. Use speaker `platform`,
   not `universe`, `assistant` or privileged LLM system instructions.
   Alternative rejected: encoding diagnostics in an answering receipt or raw
   JSON in content; both confuse type/authority and can leak provider payloads.
2. Reuse the exchange transaction boundary via an internal pair writer and a
   failure entry point. Insert owner text verbatim plus platform notice in one
   transaction under the current universe/session lock and BEGIN IMMEDIATE.
   Preserve normal success record_exchange signature/semantics. Never dedupe by
   text: repeated user sends are distinct turns. Both paths share400-row
   retention. Failure metadata migration unavailable means this failure pair
   is not saved, not an untyped pseudo-answer; rollback leaves no half-turn.
3. Record only after authenticated principal, owned universe and interlocutor
   admission pass, when the real call ends in an observed exception/known setup
   hold. Derive safe notice separately from existing raw diagnosis envelopes.
   Add optional `turn_failure` and `history_saved` to the existing error/hold
   response; retain existing keys for clients. Persistence failure returns the
   original usable failure and `history_saved=false`, never replaces it with
   success or hides unsaved history. No persistence on pre-auth, invalid model
   preference or unowned-universe refusal. No new MCP action or authority.
4. Read-only access introspects column availability without DDL; legacy stores
   remain readable. Msg gains optional validated failure metadata. Status peek,
   lossless paging/chunk reads and next-turn memory expose the platform type
   within existing ACL, limits and untrusted fences. Unknown/corrupt metadata
   never becomes an execution receipt or owner speech. Text remains available
   with a platform-notice label; no new trusted-system prompt content.
5. App live error and history rendering label platform notices clearly and never
   update the actual answering-model indicator from them. `history_saved=true`
   confirms receipt of a terminal failure, not absence of side effects: preserve
   “check progress before retrying.” Keep an explicit user resend affordance;
   no automatic resend on refresh, later send or model change. Failed-store or
   transport-unknown paths retain current local recovery with honest unsaved/
   unconfirmed labels. Founder matching MUST require speaker `founder`, not
   merely non-universe. A retained failure must not make recovery show the same
   user prompt twice or falsely claim a model reply arrived.
6. Store deletion/retention remain the existing universe/account and working-
   memory boundaries; do not silently route working memory into the separately
   signed custody store. Verify existing deletion paths cover the database and
   new column; do not invent a new export/deletion authority in this slice.

## Risks / Trade-offs

- New metadata adds schema work: owner-authorized writes only; readonly legacy
  tests and failed-migration rollback prove no destructive read behavior.
- A crash before terminal recording remains unknown: no promise of exactly-once
  execution or that failed work took no action.
- 400-row retention means old failures eventually expire just like old replies.
  No new indefinite retention or summaries replacing authoritative user input.
- UI's recent peek is capped: test full retrieval plus next-turn context, not
  just one browser bubble. Preserve uploaded text at rest, even if display is
  bounded and marked truncated.
- Raw exceptions remain an existing response concern, not permission to persist
  them. This new sink is allowlist-only and has sentinel-leak tests.

## Migration Plan

Fable shape/basic-safety review before code. Implement and test typed boundaries,
then exact-head independent review before ready. Additive column needs no data
backfill. Linux/Windows tests, canonical plugin rebuild, public canary and live
deployed-SHA checks remain gates. Final rendered conversation asks naturally
about a prior failed turn after refresh and a successful subsequent message.
No intentionally expensive or side-effecting workflow to induce failure.
Rollback code via normal reviewed revert while retaining database bytes/new
column; no DROP/delete. Old UI may mislabel new platform rows, so treat UI and
server deployment as one release and validate rollback display before shipping.

## Open Questions

Fable to confirm the smallest safe representation and rollback display strategy,
whether generic pair writer extraction is preferable to a narrow failure writer,
and precise UI recovery correlation without introducing execution idempotency.
No implementation approval claimed; adjust this proposal to that review first.
