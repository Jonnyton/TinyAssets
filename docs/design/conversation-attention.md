# Conversation unread indicator

Every JSON engine tool result carries `owner_unread` as its first key. It is the
number of the owner's own messages in their thread of this universe that the
universe has not read. The count refreshes after each call, so a long-running
agent notices new messages at its next tool boundary. It is an observation,
never consent. Results whose text is a file's or a command's bytes (`read`,
`write`, `edit`, `bash`) carry no field. A count that cannot be read is left off
rather than reported as zero.

There is one reader per thread: the universe. Its background wakes and its chat
turns are one self, and they share no narrower durable identity. An agent node
opens a fresh MCP session for every served call, and a chat turn opens one per
turn, so a per-session reader would restart at "all history unread" on every
call. A turn's own prompt is not a receipt, so answering a message in chat does
not take it out of the count.

Only the owner's messages (speaker `founder`) recorded at or after
`UNREAD_EPOCH` (2026-09-30Z) count. Replies, platform notices and history from
before the counter shipped are not news.

A message is read only once the exact chunks a served
`read_graph target="conversation"` returned cover its whole text. Catalogues,
errors, capped results and partial chunks never clear it. A message that arrives
during a read is not in that payload, so it stays unread. Reading a newer message
cannot clear an older one.

Receipts live in `.conversation_attention.db` in the verified founder home. They
are keyed by the owner's thread and message ID, and hold covered character
ranges, not text. The transcript stays read-only. The count is cached against
both stores' file signatures, so an unchanged call costs `stat`s, and only a call
that returned a message body writes.

Scope comes only from the verified server pins and current serving authority.
It never comes from tool arguments.

Deployment acceptance: during a long background turn, send a message. The next
tool result must show `owner_unread` rising. Read that exact message, and the
next result must show it falling.
