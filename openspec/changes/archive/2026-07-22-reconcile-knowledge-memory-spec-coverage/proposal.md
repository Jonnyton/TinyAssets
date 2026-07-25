## Why

The canonical knowledge/memory capability covers retrieval, scope, notes, and daemon-wiki scaffolding, but omits shipped mini-Brain, episodic, project-memory, versioning, legacy learning, and helper-library behavior. This leaves current behavior—and important limitations such as marker-only promotion, volatile unscoped learning, and non-atomic legacy writes—outside the as-built contract while a separate future OKF design could be mistaken for shipped functionality.

## What Changes

- Add as-built requirements for the soul-scoped host-local mini-Brain: typed capture, review/promotion lifecycle, hybrid search, bounded prompt packets, caller-owned replay evaluation, dispatch hints, and status observability.
- Add as-built requirements for episodic storage and migration, fantasy phase context assembly, project-scoped versioned key/value memory, draft-output versions, node-scope manifest parsing, and the standalone temporal/consolidation helpers.
- Add as-built requirements for the fantasy chapter-learning loop, heuristic craft/criteria surfacing, episodic promotion-candidate scans, and reflexion.
- State the shipped limitations precisely: incomplete sub-tier enforcement, caller-supplied identifiers, non-atomic write paths, volatile process-global learning state, advisory-only weights, return-only candidates, library-only helpers, and placeholder memory-tool envelopes.
- Keep `brain-okf-canonical-store` entirely future-owned; this change makes no claim of OKF canonicality, projection durability, crash recovery, federation, or automatic closed-loop learning.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `knowledge-retrieval-and-memory`: expand the as-built contract to cover the shipped memory and learning surfaces that currently have no canonical requirements.

## Impact

This is a specification-only reconciliation. It modifies the canonical `knowledge-retrieval-and-memory` requirement set and records evidence from `tinyassets/daemon_brain.py`, `tinyassets/daemon_memory.py`, `tinyassets/memory/`, `tinyassets/learning/`, the fantasy-domain phase integration, related API routes, and focused tests. Runtime code and public MCP behavior do not change.
