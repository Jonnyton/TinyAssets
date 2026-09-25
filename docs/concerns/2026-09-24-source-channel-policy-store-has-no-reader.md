# The source-channel policy store has no reader

**Filed:** 2026-09-24
**Verified:** 2026-09-24, branch `claude/agent-access-controls` on `origin/main`
`7d567926`, command `grep -rn "apply_auto_approval_policy\|get_policy_mode" --include=*.py tinyassets`.
**Severity:** P2. Nothing is unsafe. A control reports success for a setting
that nothing enforces (Hard Rule 8).

## What is true

- `write_graph target=source_channel operation=set_policy` on the connector
  writes `(universe_id, channel_type, mode)` to
  `${data_dir}/.source_channel_policy.db` and replies `policy_set`.
- The only reader of that table is `get_policy_mode`. Its only caller is
  `tinyassets/api/source_channel.py::apply_auto_approval_policy`, and that
  function has **no callers**. It appears only in `__all__`.
- The module docstring (`tinyassets/storage/source_channel_policy.py`) still
  says the policy decides whether a channel "requires explicit approval
  before a node/effector may use it". Since change `sandboxed-code-node`,
  approval gates no code run. The effector consent gates
  (`is_consent_active`) never consult the policy.

So `set_policy mode=auto` changes nothing a user can observe, whatever the
channel. `get_policy` then reads back the setting and makes the control look
real.

## Why it matters now

Capability C27 asks for the owner's agent to "change one channel policy".
Change `agent-access-controls` exposes the channel policy that enforcement
actually reads, which is the consent row (`source_channel action=revoke`,
next to `approve`). It keeps `get_policy`/`set_policy` off the served surface
(design D3). The connector still offers both.

## What would resolve it

One of two:

1. **Delete** `set_policy`/`get_policy`, `apply_auto_approval_policy` and the
   store. The consent row becomes the only per-channel setting.
2. **Rewire** it into a real per-channel policy that an effector gate reads.
   That is an authority change and needs its own OpenSpec change.

Delete this file when either lands.
