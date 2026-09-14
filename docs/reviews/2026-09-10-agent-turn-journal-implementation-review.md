**Review of 6ce30ad0dd20aab49cb7434a6f2449f51aeb8a30 against 7470b3d4**

Scope confirmed: 11 files, all additive. The four plugin mirrors are byte-identical to the canonical modules. The codec file is untouched. The shape review doc exists at the cited path.

**Tests actually run (Windows, this worktree, 2026-09-09)**

```
python -m pytest tests/test_agent_turn_journal.py -q --basetemp=C:/Users/Jonathan/AppData/Local/Temp/ta-pt-rev-6ce30ad0
48 passed in 1.97s   (0 skipped)
```

I did not run the account-deletion or scoped-reset tests per the constraint. I read the new deletion test and the sweep code instead. The Docker Linux group is yours.

**Contract checks**

- **AGREE, whole-batch receipt.** Round update plus every planned tool row are one transaction in `finish_inference` (`tinyassets/storage/agent_turn_journal.py:389-408`). The trigger-fault test proves rollback of the entire batch.
- **AGREE, commit-before-start.** `start_tool` flips planned to started and commits before returning. Earlier calls must be completed and the target must be planned, so no skip, reorder, or reuse of a started row (`agent_turn_journal.py:420-438`).
- **AGREE, CAS dispatch winner.** Every mutation reads under `BEGIN IMMEDIATE`, compares the Python-side generation, then bumps it with a guarded UPDATE that raises on a zero rowcount (`agent_turn_journal.py:236-247`). The thread race test yields exactly one applied.
- **AGREE, idempotent finalize.** Both finalizers test a terminal target for byte-identical payload before touching the generation, so a stale-generation exact replay reads already_applied and any differing replay reads conflict (`agent_turn_journal.py:384-388`, `475-488`). No path moves started or a held state back to planned.
- **AGREE, non-text known results.** Stored projection keeps the standard content-block union minus `meta`, plus structuredContent and isError. Kind is derived from the stored JSON on read, never from the caller. Non-text completion holds as held_unsupported_result with the result retained (`agent_turn_records.py:196-245`).
- **AGREE, strict snapshot validation.** Reads re-run the strict JSON parser, re-decode the reply through the unchanged codec, cross-check duplicated identity and state columns, enforce the completed-prefix rule and the derived frontier against the state column, and collapse every failure to one fixed error (`agent_turn_journal.py:82-209`). The corruption tests cover the important columns.
- **AGREE, deletion.** All three tables are owner-keyed in the person-keyed exception map, the main sweep ORs universe and owner predicates per table and counts before deleting, and both child FKs cascade. The new test exercises current home, former home, and a preserved other owner (`tinyassets/account_deletion.py:126-129`, `503-531`).
- **AGREE, scoped-reset holds.** Classification is preserve_or_block with explicit matching-turn inspection scoped by exact owner and home. Ready, inference_started, tools_pending, and held_tool_unknown block. Corrupt matching data blocks. Inspection is read-only and runs on the Row-factory read-only connection (`tinyassets/scoped_reset.py:1017-1019`, `1298`).
- **AGREE, no authority minted.** No credentials, capability, endpoint, or budget reference is stored. No FK to reservation rows. Wire call ids are data, not identity. Round and call ordinal are the durable key.

**Mandatory fixes**

None. I found nothing that contradicts the applied contract or breaks single-owner safety.

**Non-gating follow-ups for the executor integration**

- `reset_blockers` dereferences a possibly-None read if a turn row vanishes between the id scan and the per-turn read (`agent_turn_journal.py:263-264`). Today that surfaces as an uncaught AttributeError, which is fail-closed but uncontrolled. A `continue` on None is the fix.
- A turn left in `ready` with zero rounds blocks scoped reset forever, and `held_transport` is terminal in this store. The executor slice needs a reviewed abandon or retry transition gated on fresh admission. Do not add it here.
- Account deletion never consults turn state and also removes another owner's turns in the deleted home without a blocker, unlike `user_requests`. Decide that policy once the executor can create such rows.
- Every mutation re-validates the whole turn history, including pydantic and codec re-decode of every prior round and tool, inside the global write lock. Cost is linear in history. Frontier-only validation on mutation paths would bound it without adding a shape cap.
- The records module reaches into four underscore-private codec helpers. Fine for now since the codec is frozen, but name them as an internal API when the executor lands.
- `get` opens a deferred transaction and relies on connection close to end it. Harmless but worth an explicit rollback.
- Test gap: no concurrent `begin_round` race test for the partial unique index plus CAS, and no Linux evidence yet in this tree.

VERDICT: APPROVE
