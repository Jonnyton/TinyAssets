## Why

PR #2137 merged a security-rejected provider-carrier head whose record-only
mint-grant issuer accepts any self-consistent `launch_started` reservation.
That lets a forged reservation bypass the durable invocation, token, and cost
ledger, so provider activation and cloud cutover must remain paused until the
mint path is store-proven and independently approved.

## What Changes

- Remove the record-only provider-carrier mint-grant issuer.
- Issue one opaque, one-use mint proof only from the transaction that wins the
  durable `reserved` to `launch_started` transition, bound to the exact armed
  reservation digest and issuing process.
- Reject forged records, proof reuse, cross-process/fork reuse, and carrier
  use outside the issuing process before provider selection.
- Publish grant/carrier registry authority only after cleanup is installed,
  and make cleanup tests independent of CPython refcount timing.
- Keep provider activation and cloud cutover paused through focused/parity
  verification and fresh independent review of the exact correction head.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-routing`: Require a background provider carrier to derive its
  one-use mint proof from the winning durable store transition; serialized or
  recomputed receipt, claim, and reservation records grant no mint authority.

## Impact

The correction changes the canonical and packaged provider-work authority
model/store plus focused tests. It introduces no public API, MCP action,
credential path, provider call, or activation; the carrier remains dark until
the parent activation lane completes its independent gates.
