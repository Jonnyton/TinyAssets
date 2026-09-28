## Why

A source that cannot call its provider's own list-models endpoint offered only the ids
its owner had typed by hand, so a newly released model was invisible until someone
shipped a patch. Founder, 2026-09-26: *"i cant seem to select fable as a user for the
llm"*, against a subscription CLI source listing a provider default and two older ids.

## What Changes

Two mechanisms, split by what is actually public.

**A typed model id is PERSONAL, forever.** An id an owner typed and successfully used
stays on that owner's own list and is never shared with anyone. That is what keeps an
account-bearing selector -- a Bedrock ARN with an account number in it, a personal
deployment name -- private: there is no mechanism that could move it.

**A PROVIDER-LISTED id is shared.** Where a connected source can call its provider's
own list endpoint, its ids already arrive through discovery as `executor_enumerated`
and are public by construction; nothing new is needed. Where a source has NO list
endpoint, a reviewed file in the repo carries the load: `models/<source-kind>.json`,
which users' agents propose additions to by ordinary PR. A CI check refuses a malformed
file; review and merge are the moderation. Only the newest of each class is offered,
derived from the id's own shape.

A listed id is a claim that the id EXISTS, never permission to use it: it appears under
the picker's "needs access" group until the owner grants access, with the existing
one-tap grant.

## What this REPLACES

Three earlier designs in this change directory, each built and then refuted:

* a charset deciding whether an id was safe to share -- it admitted account-bearing
  ARNs and rejected documented selectors like `sonnet[1m]`, and no character rule can
  separate the two without the per-vendor knowledge this capability forbids;
* a distinct-owner threshold -- "used by two owners" does not imply "public", because
  two colleagues share one organisation's private deployment id;
* attestation plus peer confirmation -- it worked, and was over-built for the problem
  (founder: *"that might be over design for the model sharing"*).

The shared database table, the pending state, the confirmations and the promotion
threshold are all deleted. What survives is the owner's own list, the union into the
picker, and the newest-per-class derivation.

## Capabilities

### New Capabilities

None. Sharing is a reviewed file plus the existing PR flow.

### Modified Capabilities

- `provider-capability-negotiation`: a source with no list endpoint gains candidates
  from a reviewed public list instead of only owner-declared ids.

## Impact

Storage: one per-owner table, classified as its owner's data in both deletion sweeps.
Surface: additional rows in the existing advisory model options document -- no new MCP
handle, and no change to what the selection API accepts. Authority: unchanged; an
agent-opened PR to a list file lands through ordinary review with no automatic merge
path and no new permission.

The cross-user floor is met by construction rather than by a check: nothing a user
types is ever shared, and what IS shared is a file a human merged.

Owner: Claude Code; branch `claude/model-catalog`.
