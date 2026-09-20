# Adapter integration detail (unshipped)

Continues the approved v1 descriptive Branch consumer, not a foreign code loader.
The exact storage checkpoint remains frozen at 2ca96c52 for independent review;
this later working-tree preparation is not covered by that review.

Public component vocabulary implementing the reviewed semantic fields:

```json
{
  "kind": "tinyassets.turn-graph.v1",
  "version": 1,
  "branch_version_id": "immutable published version ID",
  "content_hash": "64 lowercase hex characters",
  "input_map": {"message": "message_field", "history": "history_field"},
  "reply_key": "terminal_text_field"
}
```

Exactly these fields are supported. `message` mapping is mandatory; `history` is
optional and exposes only the same already-authorized, bounded receiver context
captured once at reservation. Destinations must be distinct literal field names,
never expressions. The snapshot's real preflight remains authoritative. Mapping
does not make undeclared or missing typed inputs valid. Unknown component fields,
versions/kinds and nested executable references refuse; unrelated components stay
portable/inert. The component grants no model, resource, source or creator access.

The existing receiver-owned non-serving `app_experience` binding carries optional
`configuration.turn_consumer` with exact fields: version=1, state="active",
component_key, definition_fingerprint. Explicit disable replaces that document
with exactly `{ "version": 1, "state": "disabled" }` and does not require the
previous source to remain readable/compatible. Both states retain current owner,
creator/updater, configured/non-serving and no-provider-ref checks. Import,
discovery, ordinary layout installation and absence of this field never activate
a turn handler. Multiple active installations or truncated inventories hold;
definition fingerprint mismatch holds rather than silently refreshing selection.

`consumer_selection.resolve_selection_in_transaction` reads the already-held
author transaction; it performs no writes, opens no second connection and grants
no source execution. Source-current-access and active version/hash validation from
the storage checkpoint still precede snapshot use. Shared prepared-start callback
rechecks these facts using supplied author/runs connections, never reenters an
author writer or reset barrier. Its result is selection DATA, not authority.

Next integration: common run-input envelope/guard from file/cloud lanes;
server-captured model preference DATA and actual producer receipt; canonical
request/status routes and trusted owner controls. These are not implemented by
the selection parser alone. No real user account, public definition or private
workflow is changed to prove the parser; isolated platform tests use temp stores.

2026-09-19 checkpoint evidence: selection parser initially failed its 14 new
tests before implementation; additional unsafe disabled-selection cases included.
The source legacy-NULL/empty visibility pair both failed PermissionError before
the parity correction, then passed without weakening foreign-private refusal.
`python -m pytest -q tests/test_conversation_run_admissions.py
tests/test_consumer_selection.py`: Windows 57 passed in 17.98s; identical Linux
working-tree cohort 57 passed in 23.11s, zero skips, using the established read-only
WSL Docker image sha256:1b69d8536490285c7c7a13f1efe53ebe847696a99ae567dbbd2b9761ee0c530a.
Ruff on those modules/tests and plugin build/import probe passed. This is dark
unit/integration evidence, not live/public acceptance or model-bridge approval.

## Common envelope integration checkpoint (2026-09-19, unshipped)

Provenance merge 32063ed1 contains file/cloud checkpoint 1e035411; its sole merge
conflict was the concern-index adjacent rows, both preserved. No runtime merge
resolution was authored. `scope_from_transactions` borrows supplied author/runs
transactions, checks exact database/home/admin, and neither opens nor commits a
connection nor reacquires a barrier. Seven missing-helper red tests preceded it.
The first integrated Windows/Linux cohort was 88/88 passed, zero skips.

`consumer_runtime` remains dark: explicit schema initialization and atomic
reservation of the canonical correlation plus the SAME common run envelope; no
start/queue/invoke API. Six missing-module red tests preceded implementation.
Current selection/source/hash/mapped-input validation consumes the worker's
supplied connections. Same-key replay precedes current defaults/installation.
The expanded six-file Windows cohort passed 96 tests in 40.30s, zero skips.
This includes common-worker actual graph tests, NOT an activated consumer end to
end: provider preference binding and public routes are not implemented yet.

Two additional acceptance regressions then exposed a common-envelope dependency:
`tests/test_consumer_run_envelope.py -k 'empty_common or account_erasure'` failed
2 tests on 2026-09-19 Windows. Merely initializing an empty `run_input_admissions`
table yields `unclassified root run-history table: run_input_admissions` in the
existing scoped reset planner. After a receiver home rebind, real account erasure
fails `store:runs` with IntegrityError: the old-home envelope does not follow its
owner and retains a FK to an owner-deleted run. File-custody owner accepted this
dependency and owns shared table classification/owner erasure. Keep these tests
red until that dependency is merged; do not bypass reset or widen home-DB erasure.
Cross-owner file copies and physical cleanup remain that lane's separate proof.

Correction integrated at 96646657 (provenance cherry-pick of file89b5ea23). Both
retained consumer regressions now pass. Account erasure retains BOTH explicit
canonical owner_user_id and common-envelope owner_id classifications. The only
source conflict was their adjacent entries; both were preserved. No custody
service/runtime was copied, and the receipt document imports only the intended
shared-envelope correction, not its unrelated parent checkpoint.
