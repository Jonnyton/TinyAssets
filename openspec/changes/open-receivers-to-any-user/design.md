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

Two things the cross-family review (2026-09-26) corrected here.

**The save-time refusal was not enough.** It only covers receivers created after it
shipped. A receiver predating it could advertise a reserved name as a *file* input,
and `storage/deliveries.py` `_run_inputs` would then replace the injected principal
with the sender's own file reference — forged provenance past a guard that looked
structural. `_refuse_reserved_contract_fields` now checks the ADMITTED contract on
every acceptance, so such a receiver cannot receive at all until its owner renames
the field. Loud refusal, never silent acceptance.

**Replay compares sender content, and carries the stored record forward.**
`accept_in_transaction`'s digest covers `inputs`, so attribution participates in
it. The first shape recomputed attribution on the replay paths in order to compare
— which broke retries of occurrences accepted *before* attribution existed, since
their stored inputs have no such key, and a retry is the normal response to a
timeout. `_replayed_inputs` instead compares only what the SENDER sent against the
stored inputs minus the reserved names, and returns the stored dict unchanged. That
is byte-identical for a pre-upgrade row and a post-upgrade one alike, and a changed
payload still conflicts — on the mapped comparison, and again on the digest, which
also covers the raw request payload.

## 3a. Exposure on update: keep, not replace

The first shape made `update` REPLACE the exposure declaration, arguing consistency
with `allowed_senders`, which is also a full replace. That was wrong, and the
review's counter-argument is the better one: `allowed_senders` is a REQUIRED
argument, so omitting it fails loudly, while the exposure fields are optional with
defaults, so omitting them would *silently* change policy — and silently reset a
deliberately tightened `sender_rate_limit` back to 60, which LOOSENS a bound the
owner chose. Fail-safe in one direction is not fail-safe.

So `None`/absent means KEEP: create takes the private defaults, update preserves
whatever is not mentioned. Closing an exposure is an explicit `false`, and `0` or
`"false"` are refused rather than read as the closed default, so an owner who meant
to close something is told their value was not understood instead of appearing to
have succeeded.

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
- Also checked inside `_transfer_files`' own pre-flight transaction, because that
  runs ABOVE every acceptance fence. Without it a sender past its limit could vary
  occurrence ids and cause copy after copy that acceptance then refused, leaving
  the committed custody objects behind (review finding, 2026-09-26). That
  pre-flight holds the same two writers as acceptance, so a *sequential* sender
  past its limit copies nothing at all. **Residual, stated:** the copy itself
  happens after that transaction closes, so concurrent senders can still produce
  one copy per in-flight request before the window reflects them. Closing that
  remainder needs a capacity reservation spanning the copy, which this change does
  not attempt.
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

The review checked every literal in the chapter against the code and found two
false ones, which is the point of checking. The chapter's own recipe — declare
`{"name": "delivery_sender_id", "type": "str"}` — could not work, because
`project_receiver_entry` preflights presence from the advertised contract plus
schema defaults and the field is neither, so such a receiver was refused with
`MissingRequiredInputs`. `save_receiver` now passes declared attribution names to
projection as presence-only keys (that parameter is documented as
presence-preflight-only) while the contract still excludes them, and the documented
recipe is true. Separately, "lists every receiver" was wrong — the result is capped
— and an agent that believes a capped list is exhaustive tells its user the wrong
thing, so the chapter now says so.

The chapter goes in the handbook rather than the resident description because its
absence produces an *absent* call (the agent fetches, or reaches for a webhook and
can be pointed) rather than a *wrong* one — the split rule recorded in
`openspec/specs/served-agent-tool-guidance/spec.md`. The resident index gains a
bullet naming it, and `tests/test_served_tool_guidance.py::CHAPTER_ORDER` gains
`"delivering"`, which is the deliberate part: that constant is how the suite
asserts the index and the handbook agree.

## Migration

`graph_receivers` gains three columns via a `PRAGMA table_info` +
`ALTER TABLE ADD COLUMN` pass, matching `tinyassets/automations.py:377-382`.

It runs **inside** `BEGIN IMMEDIATE`, unlike `executescript(_SCHEMA)` above it.
`CREATE TABLE IF NOT EXISTS` is idempotent; `ADD COLUMN` has no `IF NOT EXISTS`,
so two openers checking outside the write lock both see the column missing and the
loser raises `duplicate column name` — reproduced by the review against a shared
database. And because that race is timing-dependent, a concurrency test does not
reliably catch the wrong placement: `migrate_in_transaction` therefore *checks*
`conn.in_transaction` and refuses, the same shape as
`storage/deliveries._require_transaction`. The migrated index is created after the
columns it reads, so it can never run against a table mid-migration.

No `CHECK` on the added columns — SQLite's `ADD COLUMN` cannot carry one, and a
constraint present on fresh databases but absent on migrated ones is two
definitions of one rule; the bounds are validated in `save_receiver` where they can
name themselves.

The existing `INSERT INTO graph_receivers VALUES (?,?,...)` is **positional** and
would silently mis-assign every column after a schema change, so it becomes an
explicit column list in the same edit.
