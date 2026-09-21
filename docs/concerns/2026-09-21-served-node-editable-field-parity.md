# Existing workflows cannot edit all ordinary node configuration

**Filed / verified:** 2026-09-21 UTC, deployed `f5c5e5ec9003`, ordinary primary
app conversation and matching source tree. Separate from the now-working
effects edit; do not describe every node field as editable.

## Evidence

The app's 00:03 PDT report, after successfully editing effects/code on existing
branch `99fbd37d31e3` and running `3bade2d341e84935`, reports this refusal:

> patch update_node may not set 'output_keys' on the served edit surface

It reused an existing output key and restored the original branch content.
The result proves effects editing; it does not make the output-key refusal go away.

Independent Claude Fable review of candidate `1ba6ee40` also found
`timeout_seconds` is not served-editable. A node whose timeout exceeds the
workspace maximum cannot lower it in place before adding a workspace binding.

Source read at the identical deployed tree: `_SERVED_PATCH_UPDATE_NODE_ALLOWED`
in `tinyassets/engine_mcp_server.py` admits only content/model/effects/workspace
fields. Canonical `_apply_node_updates` in `tinyassets/api/branches.py` already
validates `output_keys` and `timeout_seconds`. Verified with `rg -n` for these
symbols/fields. This is an adapter parity issue, not an absent primitive.

## Required outcome

An owner can revise ordinary execution configuration of an existing workflow
without recreating its nodes or branch, using canonical validation. Assess the
general served/canonical editable-field contract rather than adding one field
per symptom. Preserve authorship, record ACLs, universe pinning, immutable
admitted runs, person-only grants, sandboxing and runtime resource/consent gates.
Do not expose authority metadata simply because canonical storage accepts it.

Public-surface proposal/design and cross-family shape review precede widening.
Acceptance: ordinary app agent edits its own output mapping and timeout in place,
reads them back and runs successfully; malformed and unauthorized changes refuse
atomically. Operators do not edit private workflows for the agent.
