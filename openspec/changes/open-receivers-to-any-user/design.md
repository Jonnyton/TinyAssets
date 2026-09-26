# Design — opening a receiver to any authenticated user

Every decision below is pinned to code on `origin/main` at 31a1776c. Where the
obvious shape was rejected, the reason is the existing code, not taste.

## 1. `open_to_all` as its own column, not `allowed_senders: ["*"]`

Rejected: a wildcard sentinel in the sender list.

`tinyassets/storage/receiver_links.py:66-69`:

```python
def _name(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or value == "*":
        raise ValueError("a non-empty exact principal/resource name is required")
```

`"*"` is *already explicitly refused*, and `_name` is the single validator for
principal ids, universe ids, branch ids, node ids, link ids, occurrence ids and
both sides of an output mapping. Admitting `"*"` into `allowed_senders` means
either relaxing `_name` for every one of those positions, or growing a second
name validator — a second definition of "what is a legal principal name". Both
are worse than a column.

It is also the wrong data type for the fact. "Anyone may send" is a policy the
owner chose, not a principal who exists. Keeping it out of the identity list means
`allowed_senders` still round-trips as exact names, so an owner can open a
receiver, close it again, and still have their enumerated list intact.

Chosen: `graph_receivers.open_to_all INTEGER NOT NULL DEFAULT 0`. The payload
field is `open_to_all` rather than `open` — `open` shadows a builtin at every
Python call site it would pass through, and an agent composing JSON benefits from
the field saying what it opens to.

## 2. Two flags, because the founder's vocabulary has three states

The founder's principle is that a node is private by default and exposure is the
owner's explicit choice of *visible, accessible or interactable*. Those are not
one switch:

| | `discoverable=0` | `discoverable=1` |
|---|---|---|
| `open_to_all=0` | private (today's only state) | listed; strangers read the contract, delivery refuses |
| `open_to_all=1` | open by id only — the owner hands the id out themselves | listed and open |

Both default to 0, so every receiver that exists today keeps exactly its current
behaviour. "Listed but closed" is how an owner invites a request for access
without accepting traffic; "open but unlisted" is how an owner opens a receiver to
a group they tell directly. Collapsing them would force an owner who wants either
one to accept the other.

The predicates split to match:

- `_permitted_receiver` (deliver / connect an output) — `open_to_all` or an
  enumerated sender. **Interaction.**
- `_visible_receiver` (inspect one by id, appear in discovery) — additionally
  `discoverable`. **Visibility.**

`resolve_link_in_transaction` keeps calling `_permitted_receiver`, so acceptance
authority is unchanged in shape: the sender must still be permitted at the moment
of acceptance, and closing a receiver stops in-flight senders immediately.

## 3. Attribution reaches the run only through fields the receiver declares

The requirement is that the owner's downstream nodes can act on who sent a
deliverable. The tempting shape — inject `sender_id` into the receiver's run
inputs unconditionally — is unsafe here, for a reason that is in the code:

- `tinyassets/storage/deliveries.py:173` `_run_inputs` documents "The receiver's
  own run row never carries a sender identifier."
- `tinyassets/runs.py:788` `inputs = run.get("inputs") or {}` feeds a run row's
  stored inputs straight back into `_invoke_prepared_branch` on the waiting-run
  resume path.

So an undeclared key written into a run row's inputs can reach a graph whose
state schema has no channel for it. Chosen instead:

- Two reserved names, `delivery_sender_id` and `delivery_sender_universe_id`.
- `save_receiver` **refuses** either name in `input_keys`, so they can never enter
  the advertised contract. `connect_output` already validates a mapping against
  the contract (`mapped - accepted` in `storage/receiver_links.py connect_output`),
  so a sender cannot map an output onto an attribution field even by trying — the
  refusal is structural, not a filter.
- At acceptance, each reserved name the *receiver's own pinned snapshot* declares
  in `state_schema` is filled from the link row (`link["owner_id"]`,
  `link["universe_id"]` — server-side trusted data, never the request payload).

The run row and the executing inputs therefore stay the same shape, and a receiver
that does not declare the fields is unaffected. Attribution is still
unconditional where it is authoritative: `graph_deliveries` has always stored
`sender_id`/`sender_universe_id`, and this change adds them to the receiver's side
of the receipt, which returned neither before (`_receipt` in
`storage/deliveries.py`) — an owner literally could not see who sent them
anything.

Consequence, stated rather than hidden: `accept_in_transaction`'s replay digest
covers `inputs`, so attribution now participates in it. A replay of an occurrence
accepted before this deploy, against a receiver whose snapshot happens to declare
a reserved name, conflicts loudly (`occurrence_conflict`). It cannot silently
accept a second run.

## 4. Per-sender rate limit — usage, not structure

An open receiver with no bound is an abuse hole, and the platform floor is
"do not affect other users": a stranger must not be able to burn the owner's run
admission budget without limit.

- `graph_receivers.sender_rate_limit INTEGER NOT NULL DEFAULT 60`, owner-set at
  create/update, validated `1 <= n <= 100000`.
- Window: `SENDER_RATE_WINDOW_SECONDS = 3600`, rolling, counted from
  `graph_deliveries.accepted_at`.
- Keyed on `sender_id` alone, not `(sender_id, sender_universe_id)` — otherwise a
  sender multiplies their budget by founding universes.
- Checked **before** `engine_admissions.admit_detail`, inside the acceptance
  transaction, and only on the `prior is None` branch: a replay of an
  already-accepted occurrence neither consumes budget nor is refused.
- Refusal is `receiver_sender_rate_limit_exceeded`, surfaced through the existing
  `invalid_delivery_request` detail channel. No silent drop.

There is no "off". The ceiling is high enough to be effectively unlimited for a
sender the owner trusts, and one code path serves every account — a closed
receiver gets the same rule as an open one.

## 5. Discovery is a read action, not a new handle

`discover_receivers` joins `READ_ACTIONS` in `api/deliveries.py`, which registers
it into `_RUN_ACTIONS` automatically (`api/runs.py:2649`). It is reached as
`read_graph target="receivers"`, with the existing `query` and `limit`
parameters. The canonical six handles are untouched.

It requires `_require_admin` on the *caller's own* universe, matching
`get_delivery`/`list_output_links`: discovery is an act by an authenticated
universe owner, consistent with "no anonymous actions".

The returned row is the sender view only. Notably it does **not** add
`universe_id`: that field is in `_receiver_view(private=True)` today and
deliberately absent from the sender view, and discovery is not a reason to
weaken a boundary a test already pins. `owner_id` is the owner label a sender
needs to decide whether to send. A non-discoverable receiver never appears, and a
revoked one never appears.

## 6. Guidance

A fourth `write_graph` handbook chapter, `delivering`, appended after
`workspaces`: build a receiver on one of your own steps, open it, find other
people's, connect an output, send, and read what came back. Plus one line in
`control_station`'s **Multiplayer model** section — the place an agent reads when
a user asks about other users.

Vendor-neutral, and deliberately *not* coached toward bug reports or any other
use: the primitive is "a deliverable from someone else's universe arrives in
mine", and naming a use would narrow what agents build with it.

The chapter goes in the handbook rather than the resident description because its
absence produces an *absent* call (the agent fetches, or reaches for a webhook and
can be pointed) rather than a *wrong* one — the split rule recorded in
`openspec/specs/served-agent-tool-guidance/spec.md`. The resident index gains a
bullet naming it, and `tests/test_served_tool_guidance.py::CHAPTER_ORDER` gains
`"delivering"`, which is the deliberate part: that constant is how the suite
asserts the index and the handbook agree.

## Migration

`graph_receivers` gains three columns. `links.transaction` runs
`executescript(_SCHEMA)` before `BEGIN IMMEDIATE`, so the additive
`PRAGMA table_info` + `ALTER TABLE ADD COLUMN` pass goes there, matching
`tinyassets/automations.py:377-382`. No `CHECK` on the added columns — SQLite's
`ADD COLUMN` cannot carry one, and a constraint present on fresh databases but
absent on migrated ones is two definitions of one rule; the bounds are validated
in `save_receiver` where they can name themselves.

The existing `INSERT INTO graph_receivers VALUES (?,?,...)` is **positional** and
would silently mis-assign every column after a schema change, so it becomes an
explicit column list in the same edit.
