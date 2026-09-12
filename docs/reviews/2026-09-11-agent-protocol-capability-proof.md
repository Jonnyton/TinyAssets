# Installed agent protocol capability dispatch

September11,2026, feature parentb835dec1. Implements the accepted internal
provider-boundary diagnosis: request encoding, HTTP response decoding and
discovery executor-tool evidence now use one installed WireProtocol/AgentCodec
contract. Usage interpretation is declared by DiscoveryProtocol rather than an
inference-layer provider-name branch. Existing text encoder/header lookup shapes
remain intact; supported public protocol names, definitions, profile payloads,
grants, spending constraints and journal bytes are unchanged.

Seven focused cases prove real writer/router/adapter/journal/tool composition
with an unfamiliar synthetic installed discovery-profile name, declared optional
usage interpretation, actual-model receipts, missing-codec rejection despite a
captured tool claim, and remote metadata unable to enable executor capability.
An absent usage decoder reports unknown, not zero. Synthetic registry injection
is not a claim that users can already publish arbitrary protocol implementations.

Expanded verification:
python -m pytest -q tests/test_agent_protocol_capability.py
tests/test_agent_inference.py tests/test_protocol_encoders.py
tests/test_api_key_http_provider.py tests/test_discovery_snapshot.py
tests/test_model_discovery_capability.py tests/test_selected_model_authority.py
tests/test_interactive_http_agent.py tests/test_agent_chat_codec.py
tests/test_agent_chat_portable_history.py tests/test_agent_reply_record_contract.py
tests/test_agent_turn_journal.py --tb=short --show-capture=no

- Windows444passed63.49s, zero skips.
- Actual Docker Linux via WSL Ubuntu/scripts/linux_oracle.py, same files with -rs:
  444passed40.94s, zero skips; Python3.11.16/git2.47.3/bwrap0.12.0.
- Plugin build419files, importprobeOK. Ruff clean.

The unchanged channel-agnostic check still fails at six file/vendor loci:
config(2), agent_chat_codec(1), discovery_protocols(2), protocol_encoders(1).
General inference and HTTP execution no longer branch on provider names;
remaining named protocol/semantics are concentrated at their actual boundary.
The new central registry occurrence and usage callback increase those boundary
counts; no baseline increase, exemption or claim that the whole gate is green.
The extensible public discovery descriptor still needs pre-build review, and
native explicit choices, release CI/deploy and rendered acceptance remain open.
Independent exact-head review pending; this proof is not release approval.
