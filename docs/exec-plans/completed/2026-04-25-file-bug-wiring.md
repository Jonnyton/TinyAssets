# Retired: `file_bug` to `bug_investigation` forward-trigger wiring

**Status:** superseded and retired by
`openspec/changes/archive/2026-08-26-retire-cheat-loop/` (2026-07-28).

This historical plan proposed a privileged platform-owned automation in which a
wiki filing automatically enqueued `bug_investigation` and later appended an
Investigation or Patch Packet. That product direction is retired. Do not restore
its forward trigger, startup backfill, safety-net subscription, receipt writer,
or Patch Packet write-back.

Recurring investigation or repair behavior belongs in ordinary user-created
workflows assembled from the same public, remixable, copyable primitives as any
other task automation. `file_bug` remains an ordinary typed filing operation.

Historical implementation detail remains available in git history before this
tombstone; it is not current build authority.
