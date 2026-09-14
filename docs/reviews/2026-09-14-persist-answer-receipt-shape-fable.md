The listed dispatches belong to a different worktree's shared ledger and are outside this review's hard constraints, so per the request I am repeating the full deliverable rather than acting on them.

**Scope check.** No existing durable receipt seam exists. The receipt object is request-owned by design and never persisted, per execution_receipt.py:14-21. The other two table readers, automation_context.py:51-53 and conversation_retrieval.py:34-55, are read-only and select explicit columns. So the proposed optional column on the existing table is the smallest seam. I agree with the shape.

## Findings

- **AGREE, storage.** One text column, empty by default, via the idempotent ALTER pattern already used for ext_id at conversation_store.py:120-124. Fresh databases get it from the CREATE at line 69. Every existing SELECT names its columns, so old readers ignore it. Retention at lines 348-353 deletes whole rows, so metadata leaves with its row.
- **AGREE, atomic pairing.** record_exchange already writes both rows in one BEGIN IMMEDIATE transaction at lines 332-355. The executemany at 339-347 only needs the universe row to carry the JSON and the founder row an empty string.
- **AGREE, projection and browser seams.** The status peek at status.py:1740-1748 and the app's history loop at app.html:3940-3943 are the right places. The renderer at app.html:1974-1988 already treats a missing receipt as unknown and calls observe per reply, so oldest-first restoration makes the latest reply win with no new state.
- **AGREE, refresh ordering.** A same-universe catalogue refresh cannot wipe a restored label. The refresh clears the actual label only on a universe change with an existing snapshot at app.html:2073-2075, and the heartbeat resets only on a universe change at line 2665. Sign-out resets at line 2901, which is the genuine scope reset.
- **DISAGREE_EVIDENCE conversation_store.py:175-176.** The read-only loader returns an empty list on any exception. A widened SELECT against a pre-migration file raises "no such column", so the whole transcript would vanish on refresh until some write migrates the file. The proposal says schema inspection. That must be the concrete mechanism: run PRAGMA table_info on the ro connection, or issue the narrow SELECT on OperationalError. Write the legacy-file test first.
- **DISAGREE_EVIDENCE conversation_memory.py:50-61.** Msg is a frozen, slotted dataclass. Frozen plus eq generates a field-based hash, so a dict-typed receipt field makes instances unhashable at hash time. Use a hashable value: a three-string tuple or a tiny frozen dataclass. Append it last with a None default so positional callers at conversation_store.py:172 and universe_intelligence.py:822-828 keep working.
- **DISAGREE_CONCERN, two definitions of one fact.** The label rules live in execution_receipt.py:8-11 and are mirrored in app.html:1968-1973. The proposal adds a third validation point on read and a fourth in the status projection. Put one server normalizer in execution_receipt.py that accepts any object and returns the closed projection or None. Use it at write in converse, at read in the store, and in the status peek. The store must not grow its own copy.
- **DISAGREE_EVIDENCE universe_server.py:2395-2405.** The immediate projection is computed after record_exchange runs. Reorder so the projection is taken once before persistence, passed in, then reused in the payload. The proposal states this. The current call order is what changes.
- **DISAGREE_EVIDENCE tests/test_onboarding_app.py:1516-1560.** The node shim defines no ModelPicker, and the renderer guards on that at app.html:1986. The claim that the latest restored reply controls the last-answer display is untestable in the shipped-JS harness until the shim stubs a ModelPicker that records observe calls.
- **Minor judgment.** Pre-feature replies will render the existing "Provider and model not reported" footer. That is the honest unknown. Do not add a second string for "not recorded". Founder rows must pass a null detail so they never trigger observe.

## Pre-code adjustments

1. Add the column to the CREATE at conversation_store.py:69 and a guarded ALTER beside line 121. Store the normalized projection JSON verbatim. Empty string means no receipt.
2. In load_recent_readonly, detect the column on the ro connection before selecting it. A legacy file must never return an empty transcript.
3. Give Msg a hashable optional receipt field, defaulted None, in last position.
4. Export one normalizer from execution_receipt.py. It drops any receipt whose keys, lengths, printability, or status-versus-model agreement fail. It never touches message text.
5. In converse, take the projection before record_exchange, pass it as a keyword, reuse the same object in the response.
6. In status.py, emit the receipt only on universe rows that have one, inside the existing fence and cap.
7. In loadHistory, build the detail for universe rows only. Add no new helper, or add its name to the lift list at tests/test_onboarding_app.py:1729-1740.
8. Leave automation_context.py and conversation_retrieval.py untouched. Regenerate the plugin runtime with build_plugin.py and the app checksum after the canonical edits.

## Smallest useful test set

All must be red on the unfixed tree.

- **test_conversation_store.py**: exchange with receipt round-trips on the universe Msg and None on the founder Msg. A legacy file built without the column reads text with None receipts and shows unchanged table_info after the call. Junk JSON, wrong keys, over-length and non-printable labels yield intact text and None. Retention removes receipts with their rows. Injected failure on the second insert leaves no founder row.
- **test_writer_execution_receipt.py**: the normalizer round-trips a projection and rejects extras, an unknown status, and a status that disagrees with model presence.
- **test_converse_handle.py**: the stored receipt equals the immediate one. Extend the record-failure case at line 315 to prove the reply and receipt still return. Extend the degraded case at line 170 to prove nothing is stored.
- **test_get_status_primitive.py**: extend the isolation test at line 688 so principal A's receipt never appears in principal B's peek and founder rows carry no key. Pin that the automation context messages carry no receipt key.
- **test_onboarding_app.py**: history with a known receipt then a later reply without one renders the known footer then the unknown footer, and the stubbed picker's last observed text is unknown. Reuse the HTML and Unicode vectors at lines 1810-1813 through history. Reset then load asserts observe fires after reset.

VERDICT: ADAPT
