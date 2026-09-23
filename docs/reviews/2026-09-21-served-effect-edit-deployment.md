# Served effects/workspace editing: deployed acceptance

Verified September 21, 2026 UTC. Scope: PR3903, existing served branch edits;
not every node field, automatic queuing, provider reliability or onboarding.

## Reviewed tree and release

- Candidate 1ba6ee40bd81fa1fa2ab2ba8cb2f06c79a1b52b7; independent Claude Fable
  exact-head review approved, including 16 new tests.
  Receipt: https://github.com/Jonnyton/TinyAssets/pull/3903#issuecomment-5756259761
- Merged f5c5e5ec9003eed7111c3f78217a45e46f366924 at 06:47:04 UTC.
  `git diff --exit-code 1ba6ee40 f5c5e5ec` returned 0 (identical entire tree).
- Required CI35568305517 passed: 19,812 passed, 100 skipped, 10 deselected,
  5 failed/2 errors in the existing quarantine; zero new failures or stale entries.
  Slow tests, invariants and declared scope passed.
- Windows focused regressions: 191 passed, 14 skipped. Linux oracle: 204 passed,
  1 skipped, Python3.11.15/git2.47.3/bubblewrap0.12.0.
  Focused commands are in 2026-09-21-served-effect-edit-verification.md.
- Image35569965210 and deploy35570168336 succeeded. Hosted authenticated
  `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp --assert-handles`
  passed at 06:51 UTC; `python scripts/deployed_sha.py --assert-contains f5c5e5ec9003eed7111c3f78217a45e46f366924`
  confirmed production containment at 06:51:06 UTC.

## Rendered app acceptance

Chrome extension, existing primary TinyAssets app conversation. No operator
edited a workflow or called the MCP directly for this proof. After deployment,
sent exactly **Retest your workflow checklist** once at 23:51 PDT September20.
Natural follow-ups asked the app agent to edit its own existing test and restore it.

- 23:58 PDT: effect declaration accepted on original branch 99fbd37d31e3.
  Run7b8d8fb7f11a4d18 correctly refused no_matching_packet: unchanged code
  emitted ordinary data, not the newly declared packet. Agent restored it.
- 00:03 PDT September21: compatible effects/code edit on the same branch,
  version cf951981, run3bade2d341e84935 **completed**. Workspace create/discard
  used lease generation130. Restored original content hash4c342216.
- 00:06 PDT: agent corrected its earlier claim: the previous run had not
  changed the workspace field. Separate test changed hold_workspace.workspace
  from create_workspace to empty string, read back version580f9eaa, and
  rund35d8357fc8a4555 **completed**, both nodes ran. Restored the binding and
  original content hash4c342216. This proves persistent clearing and compatible
  execution, not that code without workspace access exercises every runtime gate.

Agent explicitly retired its effects-edit issue. Source/unit/Linux tests cover
malformed/foreign refusal and runtime authority; the rendered tests prove actual
same-branch use. The declarations grant no credentials, consent or execution rights.

No post-fix independent customer clean use was visible in the inspected history.
That watch remains in docs/concerns/2026-09-21-effect-edit-organic-use-watch.md.
Output-key and timeout editing were separately open at this review; both were
accepted September23 in docs/reviews/2026-09-23-node-edit-parity-lead-review.md. The retest also
surfaced an unrelated sequential provider_idle_timeout; successful retries do
not close provider reliability. The full platform goal remains open.

## Specification closeout

Synced the already-reviewed requirement into live-mcp-connector-surface without
altering other requirements; archived edit-served-node-effects. This closeout
is documentation-only and does not extend PR3903's approval to new runtime code.
