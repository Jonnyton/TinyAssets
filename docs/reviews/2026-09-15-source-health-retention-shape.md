# Source-health recovery correction: pre-build shape review

September 15, 2026. Independent reviewer: Claude Fable 5.1
(`claude-fable-5-1`) through `scripts/peer_agent.py`, read-only, exit 0.
Reviewed deployed implementation `cee95ccbde4cacee0ef293bcb487302cc4d7e4db`
before the correction. This is approach evidence, not final-head approval.

## Finding and decision

Reviewer verdict: **ADAPT**. Remove the five-minute expiry. Elapsed time is
not evidence that unchanged credentials recovered. The live owner history
showed failures at 16:02, 16:10, 16:19 and 16:26 PDT on September 15,
interleaved with successful Codex replies. The original short recovery proof
did not establish sustained Automatic routing.

Retain the advisory failure until exact-custody success. A new credential
generation/digest is a different key and is eligible immediately. Discard older
generations of the same base/owner/universe/provider/reference when recording
new observations. Preserve the 4096-entry bound, exact owner/source isolation,
explicit selections and saved order. All-hinted candidates remain selectable;
the hint is neither authority nor permission to replay a failed turn.

## Why no new persistence in this correction

Existing reservation records carry exact custody, but their terminal state does
not uniquely identify authentication failures: both a post-launch auth failure
and a successful native call with unknown usage can be INDETERMINATE.
Conversation failure records intentionally omit provider/custody. Deriving
authentication health from either would misclassify outcomes. Adding a durable
terminal reason changes storage/accounting and is not part of this timer fix.

Process restart and bounded eviction can lose the hint. The deployed daemon
uses one serving process; restart loss is not the recurring five-minute loop.
Do not claim restart persistence or actual Claude credential recovery.

## Required proof

- Fake-clock regressions beyond seven minutes and one day.
- Real served-router/plan composition: no replay of uncertain-effect failure;
  later Automatic prefers another accepted source; explicit selection unchanged.
- Successful exact-custody call clears its hint; reconnect creates eligible new
  custody without requiring a successful call first.
- Independent current-head approval, required CI and actual deployed revision.
- Rendered ordinary Automatic messages after the old expiry window, with no
  source/settings workaround. Failed-turn retries are not a passing result.

## Release and rollback

Ship only this recovery correction plus generated plugin parity and tests.
No migration, permission change, new model allowance or private workflow edit.
If this change alters explicit choice or causes new routing failures, revert
this patch through the protected release pipeline to `cee95ccbde4c` behavior;
that restores the known five-minute defect, not a claim of healthy routing.
Canary/deployed-SHA checks and rendered app proof still gate completion.
