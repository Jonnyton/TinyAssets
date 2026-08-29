## 1. One trusted writer

- [ ] 1.1 `write_brain` records a bounded per-turn proposal and returns `{"status": "proposed"}`; it no longer calls `commit_learning`. Verify: a test that goes red if `write_brain` reaches `commit_learning` (mutation: restore the call); proposal captured with the section cap enforced.
- [ ] 1.2 `extract_learning` takes the founder utterance and the proposal only (reply and tool output removed from its inputs); commits only the grounded subset with `source="founder utterance <turn_id>"` and the utterance digest; empty utterance → proposal dropped with a logged reason. Verify: injected proposal not in the utterance is dropped; a founder-stated fact is kept; reply-only content is not persisted; `read_brain` shows provenance.

## 2. Untrusted by construction

- [ ] 2.1 `read_commons_shape` and fetched content return the untrusted envelope; one line in the persona prompt names it. Verify: envelope shape test; an end-to-end test where a commons shape containing instructions is read during a turn and no brain file changes.

## 3. Prove and close

- [ ] 3.1 Codex refutation; live proof through the app: (a) tell the universe a fact, next turn it knows it and `read_brain` shows the turn; (b) have it read a commons shape seeded with an instruction, confirm nothing persisted. Sync deltas, delete `docs/concerns/2026-08-24-write-brain-prompt-injection.md`, archive.
