# App feedback inbox

The app feedback flow stores private support tickets under the configured data directory. It does not invoke an LLM, execute a patch, or grant external-write authority.

Deployment requires TINYASSETS_FEEDBACK_REVIEWER set to the authenticated principal ID of the designated support reviewer. Without it, submission returns 503, while users can still read or delete existing tickets. The setting is server configuration, never a value accepted from a report. Changing it immediately changes reviewer access.

Users open Feedback from the chat or subscription screen. They receive a durable ticket ID, can add details, inspect status history, download JSON, or delete a ticket. The reviewer uses Support inbox and updates statuses with a note. Reports are preserved verbatim; rendering uses textContent.

Agent access uses the existing handles:
- read_graph target=feedback: own tickets; ticket_id selects a full ticket.
- read_graph target=feedback_inbox: reviewer-only inbox.
- output_offset paginates lists or Unicode characters for a selected ticket; output_max_chars bounds ticket chunks.
- write_graph target=feedback operation=submit/update/reply/delete with payload_json.
- submit payload: submission object and idempotency_key.
- update payload: ticket_id, revision, status, optional note.
- reply payload: ticket_id, revision, note.
- delete payload: ticket_id.

Reads and write receipts containing report content use an untrusted envelope. Report text is never a founder instruction. Status updates are review records, not evidence that a patch was built or deployed.

The SQLite store is the current single-data-volume bridge. Back it up using the same data-volume backup policy; deletion erases active records, and backups expire under that policy. Account deletion includes a dedicated feedback phase. If moving to multiple data roots, migrate to the shared transactional store before enabling intake on multiple replicas.

Before landing: dependency-backed route/graph tests, cross-family review, plugin parity, and a real browser round-trip after deployment. Isolated stdlib storage tests alone do not prove middleware, rendering, deployment, or end-to-end routing.
