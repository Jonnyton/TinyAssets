# Durable answering receipts: implementation evidence

September 14, 2026, Windows Python 3.14. Follow-up to the model-selector release;
separate from PR3844. The Fable5.1 pre-code shape review and dispositions are in
the sibling `2026-09-14-persist-answer-receipt-shape-fable.md` and the change's
`persist-answer-receipts.md`.

Implemented one optional receipt column in the existing conversation store,
an immutable receipt on Msg, own-principal opt-in history projection, and existing
app footer restoration. Receipt labels are observations, never prompts, routing,
permissions or consent. No user workflow, account preference or binding changed.

## Verification

- Before code: existing focused group 259 passed; new behavior regressions
  reproduced the missing persistence/display (10 failures, one preservation pass).
- Final focused command: `python -m pytest -q tests/test_conversation_execution_history.py tests/test_conversation_store.py tests/test_conversation_memory.py tests/test_converse_handle.py tests/test_writer_execution_receipt.py tests/test_get_status_primitive.py tests/test_onboarding_app.py --tb=short`
  returned **287 passed**, no skips, two upstream deprecation warnings, 30.35s.
- Covers legacy read-only schema/no DDL, atomic pairing and rollback, optional
  migration failure preserving text, retention, corrupt receipt rejection,
  immutable metadata, principal isolation, same receipt in immediate/history
  answers, persistence failure not repeating inference, newest unknown winning,
  and Unicode/HTML-looking labels remaining literal with zero child elements.
- Updated the existing timestamp source assertion for the new optional third
  renderer argument; its unchanged date/time conversion assertions still pass.
- Ruff on all nine changed Python modules/tests: pass. OpenSpec strict change
  validation and `git diff --check`: pass.
- `python packaging/claude-plugin/build_plugin.py`: 443 files, import probe pass.
  `python WebSite/brand/render_marks.py`: regenerated the app checksum.

Independent exact-head runtime review, Linux CI, deployment and rendered
post-deploy reload proof remain open. Local tests do not prove those gates.

## Rollback

Deploy the previously verified image using the normal release workflow. Older
readers name their columns and ignore the additional optional receipt column.
Do not remove the column or delete history on rollback. Existing rows, text,
timestamps, account preferences and grants remain intact. A failed migration
warns and allows otherwise-valid text-only storage; it does not invent evidence.
