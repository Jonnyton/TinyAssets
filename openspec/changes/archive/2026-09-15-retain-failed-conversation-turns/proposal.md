## Why

A failed authorized chat turn currently returns before conversation persistence.
After refresh or another successful message, neither the owner nor their agent
can see the failed request or its diagnostic, as observed in the app's September
14, 2026 Claude/Automatic failure discussion. Enable ordinary conversation about
what went wrong without losing the user's words or inventing a successful reply.

## What Changes

- Persist admitted owner messages and safe typed terminal-failure notices together
  in the existing principal-scoped conversation store and retention boundary.
- Project platform notices into history, agent memory and lossless retrieval,
  clearly distinct from owner speech, model answers and execution receipts.
- Report whether the failed turn was saved; keep transport uncertainty and
  explicit retry distinct from confirmed terminal failure. Never auto-replay.
- Preserve legacy reads and success behavior; exclude raw provider errors,
  attempts, secrets and authority from durable failure metadata.
- Automation context now reads the persisted owner's principal session only;
  previously it included every session in that universe. Non-principal channel
  sessions are deliberately excluded, not silently treated as owner authority.

## Capabilities

### New Capabilities

- `conversation-failure-history`: owner-scoped durable evidence of terminal
  chat failures, with safe diagnostics and honest UI/memory projections.

### Modified Capabilities

None. Successful answering-model observations remain governed by
`agent-model-selection`; retained failure notices never become answering receipts.

## Impact

Existing conversation store/schema, memory message representation, read-only
retrieval/status projection, authenticated converse error envelope and app history
rendering/recovery. No new MCP handle, dependency, provider integration, model
authority, user workflow edit or background-self implementation.

Owner: codex. Branch: codex/retain-failed-conversation-turns. One future PR.
Separate from bootstrap3853, test repair3854, capture repair3855 and the unrelated
FIFO executor change. Existing deliverables are waiting on review/CI; this
proposal does not reopen their reviews or gate their landing.
