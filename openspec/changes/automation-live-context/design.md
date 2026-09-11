# Design

An exact top-level input value `{"$automation_context":"v1"}` becomes an evidence envelope immediately before graph admission, after the existing owner/home checks. Ordinary and nested literal inputs retain their behavior. The persisted automation supplies all scope and previous-run identifiers; callers cannot choose another universe or run. The snapshot reads existing universe files and the conversation SQLite store in read-only mode, checks the authoritative run execution scope, preserves terminal errors and full non-input output, and omits prior input snapshots to avoid recursive growth.

The Branch owns task selection, completion criteria, reaction to signals, and effect declarations. This resolver grants no additional authority and never learns into the brain. All recovered data remains explicitly untrusted evidence. Conversation rows include original speaker, session, row id and timestamp; replayed approvals confer no fresh consent. Read failures and oversized content fail visibly. The last 50 conversation rows are included with an explicit history-gap marker; no claim of complete lifetime history is made. Large artifacts currently block rather than being silently summarized; chunked artifact retrieval remains a follow-up.

No production activation before focused integration tests and independent cross-family review. The final acceptance is a real scheduler tick fetching newly recorded founder context and prior output, performing useful authorized work, then recovering it on a later tick. Local temporary-store tests do not satisfy that acceptance.


2026-09-11 extension: retain last_completed_run separately from the immediate previous_run using the existing attempt ledger. Failed-run evidence remains visible; missing or foreign committed results refuse recovery. No migration. The optional pure commit_artifact helper preserves immutable artifacts and rejects completed work IDs or identical content under renamed IDs. This is an internal artifact checkpoint, not a shared task lock or an exactly-once external effect guarantee.

The required-test runner emits its existing summary as an escaped Checks annotation for clients that cannot download redirected CI logs. Its pass/fail decision is unchanged.
