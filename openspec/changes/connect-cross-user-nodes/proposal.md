## Why

The owner's September 9 app conversation asks for outputs from one user's nodes
to reach another user's selected nodes under the receiving user's rules. Existing
public workflow reuse, bearer webhooks and sender-only handoffs do not compose
into that ownership boundary; exposing deprecated reporting tools solves the
wrong problem.

## What Changes

- Let an owner expose a chosen node with a versioned input contract and permitted
  sending users, and revoke or revise that exposure.
- Let a sender inspect the permitted contract and connect selected outputs to
  it, including exact file/binary deliverables, without sharing an entire universe.
- Admit native authenticated deliveries durably, execute receiver-authored
  behavior under receiver authority, and expose bounded two-party receipts.
- Preserve occurrence identity through retries and crashes; identical content
  from two intentional sends remains two deliveries.
- Make management, send and readback available through existing canonical graph
  handles and the same served tools for every provider.

This does not implement an issue tracker, report schema, marketing workflow,
provider adapter or user-owned workflow. Deprecated patch-request removal remains
a separate inventory-backed cleanup, tracked in the goal contract.

## Capabilities

### New Capabilities

- None: extend existing graph execution and connector boundaries, not the
  top-level primitive vocabulary.

### Modified Capabilities

- `graph-execution-substrate`: receiver-authorized selected-node entry,
  cross-owner delivery and artifact isolation, durable occurrence/readback.
- `live-mcp-connector-surface`: receiver/link/delivery actions under graph
  handles, exposed equally to the served agent and connector users.

## Impact

Graph models/compiler/preflight, run queue and trigger admission, outbound effect
receipts, owner-scoped storage/artifact access, graph routers and served wrappers,
tests and plugin mirror. Additive storage/authority changes require design and
cross-family shape review before implementation. No PLAN change is proposed.

Owner: Codex/Patches. Intended branch: `codex/connect-cross-user-nodes`.
One intent and one PR: enable receiver-controlled cross-user node delivery.
Acceptance is ordinary conversation between two independently authenticated users,
including file delivery and negative boundary cases, on the verified live deploy.
