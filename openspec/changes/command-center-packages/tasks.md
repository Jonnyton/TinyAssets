# Tasks: command-center-packages

## 1. Build
- [x] 1.1 `tinyassets/command_center_packages.py`: the manifest, the walk and scrub (publish profile), the blob store with ownership, the ingestion boundary, and the consent pins (quarantine and activation). Register the `packages` storage store.
- [x] 1.2 Extend the `publish` ask with the optional `package` block:
  - the snapshot covers the blob;
  - the tab lists the included and excluded files;
  - the consent record is pinned outside the folder, and the rail renders from it;
  - the blob is stored, quota-gated, before anything is minted.
- [x] 1.3 Add the `install` ask:
  - capture runs the boundary, plans destinations and pins the record;
  - the answer re-plans, claims, reserves storage and materialises;
  - automations are created paused;
  - activation resumes from recorded progress.
- [x] 1.4 Add `browse_commons kind="packages"`, and update the served `systems` chapter to name the package publish and install.

## 2. Prove
- [x] 2.1 Two-user round trip through the real handlers (`tests/test_command_center_packages.py`):
  - A publishes and B installs;
  - B resumes the copied heartbeat, which runs to completion on B's own model;
  - A's private items are absent;
  - escaping and colliding packages are refused before quarantine;
  - an over-quota package is refused with its size named.
- [x] 2.2 Mutation check (2026-10-01, Windows host, scratchpad `mutate.py`): 28 mutations of the scrub, the consent gate, the boundary, install, the round-1 fixes and the lead's switches and flags. 27 went red.
  - `boundary: traversal allowed` stayed green: the hidden-component rule refuses `..` as well, so it is defence in depth.
  - The comment-only decoy stayed green.
- [ ] 2.3 gpt-6-astra refute (at most 3 rounds):
  - design round 1: ADAPT, folded (see the design's review log);
  - code round 1: ADAPT, all 10 folded (the design's review log);
  - code round 2: pending.
- [ ] 2.4 Linux oracle on the changed tests and their importers; deploy; `deployed_sha.py --assert-contains`; the lead's founder-account village test.

## 3. Land
- [ ] 3.1 Sync the deltas into `universe-agent-harness` and `universe-custom-agents`, then archive.
