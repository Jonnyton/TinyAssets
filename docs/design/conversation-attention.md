# Conversation unread indicator

Each successful owner-scoped engine tool result carries a separate small
`conversation_indicator` text block. The count refreshes after the call, including
inside a long native-agent turn. It counts retained conversation messages whose
complete bodies this reader has not fetched. It is an observation, never consent.

The existing `read_graph target="conversation"` query accepts
`query="reader:background"` (or another name, 1–64 ASCII letters, digits, underscores
or hyphens). This selects a durable reader for the current MCP session; selecting
the same name next turn resumes its receipts. Without a name, receipts belong to
the current MCP session, so foreground reads cannot clear background unread state.
A missing session or unavailable store produces an unknown count, never zero.

Receipts live in `.conversation_attention.db` in the already verified founder
home, keyed by principal session, reader and message ID. They contain covered
character ranges, not conversation text. The transcript remains read-only.
A new reader conservatively counts all retained messages as unread; it does not
assume that prompt-injected history was consumed. `next_unread_id` identifies the
oldest pending message for exact retrieval. Deleted transcript rows no longer count.
Named readers are explicitly user-selected bookkeeping, not a new authority scope.

Only exact bodies surviving the tool-result ceiling acknowledge reads. Catalogs,
errors, capped results and incomplete chunks never clear a message. Out-of-order
and overlapping chunks merge transactionally. Reading a newer message cannot clear
an older unread message. An arrival after an observation appears at the next tool
boundary. This does not interrupt a model mid-generation or a running tool.

The middleware reuses current serving authority and the existing founder-home
check before reading metadata. A metadata failure preserves the completed tool
result and reports unavailable, avoiding accidental replay of a completed write.
It preserves original content blocks, structured output and untrusted envelopes.

Validation: SQLite receipt tests and middleware boundary tests. Deployment
acceptance: start background reader, send a foreground message during the same
long turn, observe a rising count on the next tool result, read that exact message,
and observe the decrement. Read it in the foreground first and verify that the
background count remains. Repeat after a background-session restart.

Initial implementation needs repository CI and a deployed real-user pass; neither
is implied by a local helper test.
