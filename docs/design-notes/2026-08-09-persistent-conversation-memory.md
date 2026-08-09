# Persistent conversation memory — session-anchored store + reconstruction

**Date:** 2026-08-09
**Origin:** u-tiny's own diagnosis in Slack (thread 1786225160.311419). The agent
is not a persistent conversational agent — every turn is rebuilt from scratch.
Its honest gap, in its own words: *"The sliding window injection is built but not
the session-anchored persistence layer."* Founder goal to the agent: *"build out
this solution and push it through your own patch automation, evolving yourself."*

## The persistent issue

Memory today has three layers: (1) soul files (slow facts), (2) a **Slack-only
"dumb sliding-window cut"** loaded from `conversations.history` each turn (the
2026-08-08 hotfix), (3) discipline-dependent workspace writes. Failure modes:

1. **The MCP `converse` path has NO memory at all** — only the Slack ingress path
   got the hotfix (`universe_server.converse` → `_converse_impl` with no
   `conversation_history`).
2. **Not durable** — the Slack pull depends on bot-token scopes + rate limits and
   is re-fetched every turn; the platform owns no copy of its own conversation.
3. **Not session-anchored / surface-agnostic** — there is no `(session_id,
   turn, role, content)` store, so nothing beyond the window survives and no
   compression/summary layer can be built on top.

## The solution shape (Vercel AI SDK + own repo, per the agent)

`ChatbotMessagePersistence` + `ChatbotResumeStreams` + `WorkflowAgent` durable
sessions → **thread identity → persistent message store → intelligent
reconstruction at turn start.** This note builds Layers 1–2; Layer 4
(compression branch) and Layer 5 (WorkflowAgent durable-step retry) are deferred
follow-ups — the compression branch is the natural first *self-evolution patch*
the agent pushes through its own patch loop.

## Build

New module `tinyassets/conversation_store.py`:

- SQLite DB at `<universe_dir>/.conversation_memory.db` (per-universe isolation,
  same dir the vault/soul already live in).
- Schema: `conversation_turns(id INTEGER PK AUTOINCREMENT, session_id TEXT,
  turn_no INTEGER, speaker TEXT, content TEXT, ts REAL)`, index `(session_id,
  turn_no)`.
- `record_turn(universe_dir, session_id, speaker, text, *, ts=None) -> int`:
  append with next `turn_no` for the session; no-op on empty text; best-effort
  (a store failure never breaks the reply).
- `load_recent(universe_dir, session_id, *, limit=DEFAULT_LIMIT) -> list[Msg]`:
  return the last `limit` turns oldest-first as `conversation_memory.Msg`, for
  the existing bounded formatter.
- Reuses `conversation_memory.Msg` + `format_history` (the untrusted-fence,
  not-consent, char-cap formatter already reviewed by Codex 2026-08-08).

Session ids: Slack `slack:<channel>` (DM timeline — matches the current
`thread_ts=""` behavior). MCP converse `converse:<universe_id>` (founder home).

Wiring (both paths, identical order):
1. `history = load_recent(store, session_id)` — PRIOR turns only.
2. Slack cold-store backfill: if the store has no prior turns for this session,
   fall back to the existing `load_thread_history` Slack pull so live threads are
   not blank right after deploy. (MCP has no backfill source; fresh is fine.)
3. `record_turn(session_id, founder, prompt)` — the current turn.
4. `reply = converse(..., conversation_history=history)`.
5. `record_turn(session_id, universe, reply)`.

`conversation_history` is PRIOR turns; the current `founder_message` stays clean
(so `extract_learning` is unaffected), exactly as the hotfix already arranges.

## Invariants preserved

- **Memory is never consent.** Reuses the fenced UNTRUSTED formatter; a "yes" in
  history is spent. Costly actions still record fresh consent this turn.
- **Founder-gated.** History injection stays gated to granted (founder) turns in
  `converse`; the store is per-universe. Tier-preserving multi-party history is a
  later follow-up (unchanged from the hotfix's posture).
- **Best-effort, fail-open to "no memory".** A store read/write failure logs and
  proceeds blind — never loses the reply. `fail loudly` (hard rule 8) applies to
  real output; memory is a bonus layer, so its failure mode is "no memory this
  turn", matching the existing hotfix contract.
- **Not the custody store.** `conversation_custody.py` is a privacy/export/delete
  store behind one-use grants — a different concern. This working-memory store is
  separate and lightweight; they are not merged.

## Out of scope (deferred / Phase B self-evolution candidates)

- Layer 4 compression/summary branch (evaluator_optimizer shape).
- Layer 5 durable-step retry (a failed costly action's intent survives + resumes).
- Heartbeat / "am I stuck?" signal + background parallelism (the agent's other
  two asks in the same thread).
