# Direct version-one agent reply validation

September11,2026, local feature checkout, parentd5ef5c5d. Implements the
independent provider-boundary diagnosis's internal storage correction only.
No public/storage shape, stored byte format, provider registration, inference
authority, workflow or model selection changes.

The journal no longer reconstructs a synthetic HTTP response and invokes a
provider wire decoder. It validates captured context and canonical reply state
directly. The wire decoder shares those state semantics; source/call checks,
unknown-field holds and exact tool argument strings remain unchanged. Version1
retains its historical finish labels; this is not a new universal journal format.

tests/_agent_reply_legacy_oracle.py freezes the parent decoder and loader as an
executable differential specification. It does not call the new reply-state
helper. The new suite compares4800 wire combinations, persisted acceptance and
bytes, corrupt record variants, invalid identities and a wire-decoder-disabled
storage read. Unknown/held records are never promoted by this refactor.

Verification, Windows and actual Docker Linux via WSL Ubuntu:
- pytest -q tests/test_agent_reply_record_contract.py tests/test_agent_chat_codec.py
  tests/test_agent_turn_journal.py tests/test_agent_chat_portable_history.py
  tests/test_agent_inference.py tests/test_interactive_http_agent.py
  --tb=short --show-capture=no:259Windows passes33.58s,259Linux passes29.89s,
  zero skips. Linux command uses scripts/linux_oracle.py with -rs;
  Python3.11.16/git2.47.3/bwrap0.12.0.
- packaging/claude-plugin/build_plugin.py:419files, import probe-ok;
  only the two changed canonical runtime files differ in the generated mirror.
- Ruff changed import formatting only; final check before commit.

Independent exact-head implementation review pending. The remaining provider
ratchet loci, generic discovery descriptor, native explicit choices, release CI,
deployment and rendered model-picker acceptance remain open. No release claimed.
