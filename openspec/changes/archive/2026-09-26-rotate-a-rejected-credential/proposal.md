# Rotate a rejected credential

A connection's stored secret died on the provider side — one key hit its
expiry, another was revoked by the user at the provider. The platform sent it
correctly (`Authorization: Bearer`, `storage/outbound_connections.py`), the far
side answered 401, and the owner was never given a way to replace it. The
connection stayed dead for ten days.

## The problem

Three separate gaps, each of which alone would have been survivable.

1. **A delivered 401 has no class of its own.** `_classify_external_write`
   (`tinyassets/runs.py`) folds it into `external_write_failed`, which
   `ACTIONABLE_BY` maps to `chatbot` and `EXTERNAL_WRITE_FAILED_ACTION`
   answers with "fix that and run again yourself … try at most twice … then
   stop and report". So the agent retried the same dead key, then narrated
   "please reconnect" in chat prose and raised no card. Worse for a revoked
   token: the body's own word "revoked" trips `_EXTERNAL_WRITE_REFUSED_WORDS`,
   so it classifies as `external_write_refused`, whose action tells the agent to
   raise `extend_http` — widening a grant when the key is gone.

2. **There is no one-step replace.** The repair paths are `remove_http` then
   `connect_http` re-carrying every endpoint and scope, or a `connect_http`
   whose whole allow-list matches the stored one exactly (any real difference is
   `connection_conflict`). The served guidance also, correctly, discourages
   asking for a key twice — so the agent had nothing safe to raise. The owner
   read "remove" as deletion and dismissed three such cards.

3. **Nothing knows how old a key is.** An http vault record is
   `{credential_type, service, destination, token}`. No deposit time, so no
   surface can warn before an expiry, and the first news of one is a failed run.

## What changes

1. **A failure class of its own: `credential_rejected`, `actionable_by: user`.**
   Triggered by a DELIVERED 401, and by a delivered 403 only where the body
   unambiguously says the credential itself is invalid, revoked or expired. Its
   suggested action is to raise the replace card for that destination now — not
   to retry, not to narrate, not to widen. The `external_write_errors` row for a
   delivered failure now names the `destination`, so the card can be raised
   without guessing which connection failed.

2. **`rotate_http`: one card, one paste.** A pending-request action carrying a
   destination and one secret field. It replaces the secret in the vault and
   writes NOTHING to the connection ledger, so the connection id, the grant, the
   endpoints, the scopes, the access mode and the git host are unchanged by
   construction. Card text is plain: `<destination> stopped accepting its key.
   Paste a new one.` It supersedes remove+connect as the repair path, and the
   served guidance says so.

3. **`deposited_at` on every http vault record.** Stamped by the one builder all
   three secret writers now use (deposit, rotation, oauth2 refresh), because the
   merge replaces the whole slot and a field only one writer sets would vanish
   on the next write by another. The expiry warning itself is out of scope; this
   is the field it needs.

## What does not change

The six public MCP handles. No new served operation: rotation rides the request
rail exactly as `remove_http` does, so the agent still cannot touch a credential
on its own. `external_write_failed` and `external_write_refused` keep every
string that does not describe a dead credential.
