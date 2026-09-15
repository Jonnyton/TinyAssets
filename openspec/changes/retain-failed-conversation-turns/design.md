## Context

Source reverified on production/main89a335578a1576a1b4253375e6d900a770338009,
September15,2026 UTC. The goal-ledger checkout has older runtime sources; use
this isolated worktree, not its line numbers. `universe_server.converse`2415
returns errors before record_exchange2435. Store record_exchange332 atomically
stores founder/universe and prunes to400rows. Readers are conversation_store,
conversation_retrieval, api/status1730 and conversation_memory. Additional
consumers verified after Fable review: shared_self68 uses the same principal
reader/formatter; automation_context44 currently selects all sessions raw. App
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
   Speaker is the discriminator; failure_json is optional validated detail,
   never the authority for labelling a row as platform speech. Preserve normal
   success record_exchange signature/semantics. Never dedupe by
   text: repeated user sends are distinct turns. Both paths share400-row
   retention. If a writable legacy store cannot gain optional failure metadata,
   save the fixed platform-authored text-only pair under speaker `platform`,
   as success does for missing execution metadata. A failed pair write still
   rolls back without a half-turn. No metadata is misrepresented as persisted.
3. Record only after authenticated principal, owned universe and interlocutor
   admission pass, when the real call ends in an observed exception/known setup
   hold. Derive safe notice separately from existing raw diagnosis envelopes.
   Use separate pure `exception -> safe code` and `safe code -> fixed sentence`
   functions, never filtering raw notice text. The closed code set covers
   existing _TURN_ENDED_FAILURE_CLASSES plus native_auth_clue/setup_required/
   unknown. The existing unknown live error text can differ from its safe
   retained notice; new failure metadata and notice never contain raw strings.
   Add optional `turn_failure` and `history_saved` to the existing error/hold
   response; retain existing keys for clients. Persistence failure returns the
   original usable failure and `history_saved=false`, never replaces it with
   success or hides unsaved history. No persistence on pre-auth, invalid model
   preference or unowned-universe refusal. No new MCP action or authority.
4. Read-only access introspects column availability without DDL; legacy stores
   remain readable. Msg gains optional validated failure metadata. Status peek,
   lossless paging/chunk reads, next-turn memory, shared-self context and
   automation context expose the platform type
   within existing ACL, limits and untrusted fences. Unknown/corrupt metadata
   never becomes an execution receipt or owner speech. Text remains available
   with a platform-notice label; no new trusted-system prompt content. Test all
   five consumers, not only the UI-facing paths. Shared-self workflow definitions
   are untouched; only the platform's shared reader/formatter is in scope.
   The existing automation reader's all-session query is not authority to expose
   a newly retained failed request to another principal: bind its conversation
   query to persisted automation.owner_principal_id (verified in automations260)
   using the same principal session scheme, with no caller-selected override.
   Missing owner identity fails closed. Verify this tightening against existing
   automation fixtures before implementation; do not widen its read authority.
5. App live error and history rendering label platform notices clearly and never
   update the actual answering-model indicator from them. `history_saved=true`
   confirms receipt of a terminal failure, not absence of side effects: preserve
   “check progress before retrying.” Keep an explicit user resend affordance;
   no automatic resend on refresh, later send or model change. On saved failure,
   forget the local in-flight slot immediately and render recovery from the
   platform row paired with its adjacent preceding founder row. The atomic pair
   preserves adjacency; shared timestamps preserve existing stable row order.
   Never resend a truncated peek or guess a missing preceding row: show that the
   full original must be retrieved before retrying. Test page-boundary and
   long-message cases as well as the normal full-text resend button. Failed-store or
   transport-unknown paths retain current local recovery with honest unsaved/
   unconfirmed labels. Founder matching MUST require speaker `founder`, not
   merely non-universe. A retained failure must not make recovery show the same
   user prompt twice or falsely claim a model reply arrived.
6. Store deletion/retention remain the existing universe/account and working-
   memory boundaries; do not silently route working memory into the separately
   signed custody store. Verify existing deletion paths cover the database and
   new column; do not invent a new export/deletion authority in this slice.

## Risks / Trade-offs

- New metadata adds schema work: owner-authorized writes only; readonly legacy,
  optional-column fallback and failed-pair rollback tests prove no destructive reads.
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
Rollback by disabling/reverting the new failure writer while retaining the
platform-aware reader/renderer, database bytes and additive column; no DROP or
delete. A blind whole-release rollback to the old UI mislabels existing platform
rows and is not the rollback plan. Treat reader and UI support as durable once
rows exist; prove writer rollback does not change their attribution.

## Open Questions

Fable5.1 round1 completed281s/exit0 ADAPT. Required reader inventory,
speaker-vs-metadata discriminator, saved-failure resend carrier and pure safe
mapping adaptations accepted above. Use shared pair-writer extraction to retain
one transaction/retry/retention boundary. Reviewer did not trace deletion end to
end; acceptance still must. Lead adds truncated-retry safety and explicit owner
filtering for automation context after reading that consumer. Codes alone do not
prove zero side effects: only proven pre-admission refusals may say work never
started; otherwise retain uncertainty. No runtime implementation yet.
