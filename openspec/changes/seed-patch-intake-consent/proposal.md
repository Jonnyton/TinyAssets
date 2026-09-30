# A new universe is offered one connection at first sign-in: reporting gaps

## Why

Founder, 2026-09-30: *"for new users the request that enables connection to the
tinyassets universe for patch requests should be already there when they first
login just like the connect another llm one is already there from the start."*

A patch request (bug, missing capability, idea) is how a user's universe tells
TinyAssets about a gap. It files one itself, mid-turn, without interrupting its
user. The receiving side is an ordinary user's intake — the founder's universe
built it through the app like anybody else, and its owner's gate decides each
request.

Today a new universe has no connection to it and nothing tells it one exists.
Live on the free account (`u-01ky3zh1arr8qth8jee7zx63pq`, 2026-09-30) the
universe therefore **invented** a pending request asking its user for a bearer
token: a credential field for an address that needs no credential, and a help
link that 404ed. A universe cannot ask for a connection nobody told it about.

Sending a patch request means sending the user's words to **another user**, so
the yes is the user's to give, not the platform's to assume. The
"Connect another LLM" entry is already platform-raised in the same rail; this is
the same move for the same reason.

## What Changes

- **Configuration names the intake.** `TINYASSETS_PATCH_INTAKE_RECEIVER_ID`
  (plus a display-only `TINYASSETS_PATCH_INTAKE_LABEL`). No universe id in code:
  the founder's universe is one intake owner, so the platform names *which*
  intake it offers. Unset → nothing is offered and nothing is claimed. Present
  but invalid → logged loudly, nothing seeded, and every delivery to the intake
  refused (misconfiguration must not open a gate).
- **A seeded consent request.** The rail read (`list_requests`) seeds one
  platform-origin pending request per universe: plain language, **no fields**,
  nothing to paste. Same code path for every account, so it is there at a new
  user's first sign-in and an existing user's next one, with no migration.
  Idempotent on four checks (no intake / grant already held / an ask already
  pending / this intake already answered), keyed on the intake's **address**
  rather than the request's dedupe key — a dedupe key is a hash of the rendered
  text, so rewording a title would re-ask a user who already declined.
- **Approving records exactly one grant.** Sink `patch_intake`, destination the
  intake's `receiver_id`. `effector_consents` matches destinations exactly and
  has no wildcards, so "send-only access to that one intake, nothing else" is
  structural. Before writing it, the answer re-checks that the row still names
  the intake this deployment offers and that the intake actually accepts this
  sender; any miss leaves the request **pending** rather than consuming the yes.
- **The grant is the authority.** A delivery to the configured intake with no
  active grant is refused (`patch_intake_consent_required`), on both the
  acceptance path and the file-copy path that runs above it. Every *other*
  receiver is untouched: those are ones the universe found itself, where the
  receiving owner's own exposure is the only authority there is, and no consent
  is held here for it.
- **Served guidance.** `read_graph target="pending_requests"` carries a
  `patch_intake` block (`receiver_id`, `label`, `granted`, `how`), and the
  `write_graph.delivering` chapter gains the patch-request section: how to file
  one when the grant is held, and — when it is not — to point the user at the
  seeded request instead of inventing a credential ask.

## Impact

Authority: one new consent sink (`patch_intake`) and one new pending-request
action type (`grant_patch_intake`). No new MCP handle, no storage-schema change,
no migration.

Code:
- `tinyassets/patch_intake.py` (new): configuration, the grant, the seeding
  decision, the rail view, the delivery fence.
- `tinyassets/api/pending_requests.py`: action validation, grant sentence,
  answer execution, seeding + the rail block.
- `tinyassets/api/deliveries.py`: the fence on both acceptance paths.
- `tinyassets/storage/pending_requests.py`: `find_by_action_type`.
- `tinyassets/engine_mcp_server.py`: the `delivering` chapter section and its
  resident index line.

Cross-user floor: unchanged in every direction except the one narrowed here.
Nothing private rides along — the intake owner sees the fields the sender maps
and nothing else, and `delivery_sender_id`/`delivery_sender_universe_id` stay
platform-filled and unforgeable.
