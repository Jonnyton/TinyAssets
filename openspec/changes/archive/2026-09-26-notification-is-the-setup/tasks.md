# Tasks: notification-is-the-setup (Slice 6)

Owner: claude-code. One PR. Tier 2 (see proposal). Cross-family review owed.

- [x] 1. `sys_connect_llm` uses the `connect` action with `setup.primary`
  (from the installed preset, unpowered only) and `setup.shapes`.
- [x] 2. Delete the full-page connect view, vendor cards, raw-deposit select
  and their JS; unpowered sign-in lands in chat with the request open first.
- [x] 3. Guided sign-in panel inside the request: begin, callback redemption,
  automatic finish of the returned free-model request, one-tap Finish
  connecting, key shortcut.
- [x] 4. Only `status: "answered"` is success; re-read serving either way.
- [x] 5. API key / own-server shapes: one `connect` ask answered in the same tap.
- [x] 6. Fold the single pending free-model request into the setup while unpowered.
- [x] 7. Grant sentence without internal ids; `setup_required` for a turn
  refused before any call; Account `label`.
- [x] 8. Tests: server round trip with no model call, reconnect after
  disconnect, rail executed under node, endpoint shape executed, red on main.
- [x] 9. Cross-family review, run AFTER the code shipped (#3964 / `be32f2a2`)
  rather than before it, because nobody reviewed this one on the way in. Codex
  (`gpt-6-astra`) was asked the narrow question that mattered at this point: does
  the code that shipped actually do what this delta claims, since the delta was
  about to become as-built truth. Verdict summarised on the sync PR; the
  transcript is deliberately not committed.

  It returned BLOCK on a **P0 in live code**: every setup panel cleared its own
  credential field on SUBMIT, and only the hosted panel cleared its own on
  sign-out -- so a key pasted into "Other ways to connect" and never submitted
  stayed readable from the DOM on the signed-out page. Fixed here, as a RULE over
  `input[type="password"]` rather than for the one field named: the same defect
  held for all six credential fields the page declares, and a hand-list would stop
  covering the seventh. `tests/test_app_signout_clears_typed_credentials.py`
  derives the field set from the page and goes red on all six without the fix.

  Three findings became SPEC text rather than code, per the lane's instruction
  (code only for a P0), because the alternative was asserting guarantees the
  shipped code does not meet:

  * "Only an explicit answer counts" holds on the guided path and not on the
    API-key path, so the requirement now says which path, and what the other does.
    Filed: `docs/concerns/2026-09-26-endpoint-setup-failure-is-weaker-than-the-guided-path.md`;
  * the fold selects a `bind_model_access` request by action type and by there
    being exactly one, not by free-only access -- so the requirement describes
    that, and names the approval sentence as what carries the free-only promise;
  * a successful setup does not clear the rail's open-entry id, so the powered
    entry MAY stay expanded; the scenario says MAY rather than promising a
    collapse that does not happen.

  One stored requirement had to be MODIFIED, which is the finding worth keeping:
  "Manual OpenRouter acquisition preserves free-model approval" still promised
  that access changes only after a SEPARATE explicit approval, and the shipped
  manual-key handler answers the prepared request in the same tap. The server's
  half is unchanged and still inert; the sentence about a second approval is not.
- [ ] 10. Live acceptance on the free-only second account (see design.md) --
  the lead's, not this lane's.
- [x] 11. Sync the delta into `openspec/specs/onboarding-connection-progress`
  and archive.

  Written from what SHIPPED, not from the delta alone. Checked before applying:

  * the five ADDED titles collide with none of the seven stored ones, so they
    append rather than silently redefining anything;
  * both REMOVED requirements name behaviour that is verifiably GONE from the app
    (`Enable Claude`, `Saving token`, the hosted setup card and the vendor cards
    return zero hits in `tinyassets/onboarding/`), which is what makes removing
    them honest. A REMOVED requirement whose behaviour is still live would be
    drift in the dangerous direction -- `retire-activation-layer` is archived with
    its removal NOT applied for exactly that reason, and its concern file says so;
  * `setup.primary` really carries all five fields the requirement claims
    (`_first_power_preset` returns `preset_id`, `name`, `label`, `manage_url`,
    `manual_key`), so the requirement is not describing a field that does not
    exist;
  * the capability's Purpose named a subscription flow this slice deleted, so it
    is rewritten. A Purpose describing a screen that no longer exists is the part
    of a spec a reader trusts first.
