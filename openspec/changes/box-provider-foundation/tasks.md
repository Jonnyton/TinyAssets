# Tasks: box-provider-foundation

This change is a slice of `target-architecture` S4 (BoxProvider and its drivers). Re-pointing
the callers (the tool runner and provider launch) is S4's next change, not this one.

## PR 1: interface, box-host record, local driver, contract suite

- [x] 1.1 `tinyassets/boxes/provider.py`: the D2 protocol, types and errors, plus `box_relpath`.
- [x] 1.2 `tinyassets/boxes/state.py`: epochs, generations, op-id outcomes, and the startup sweep
      that marks in-flight operations `unknown_after_restore`.
- [x] 1.3 `tinyassets/boxes/local.py`, which:
      - resolves paths through descriptors, never following a link;
      - checks the handle's owner and epoch;
      - writes atomically;
      - runs execs with a full lifecycle and process-group kill;
      - exports and imports;
      - reports usage in logical bytes;
      - refuses to start without `allow_unisolated=True`.
- [x] 1.4 `tests/test_box_provider_contract.py` (the portable driver contract) and
      `tests/test_box_local_driver.py` (restart, busy, cas-while-running, launch retry and
      descriptor ownership, provoked through the local driver). Linux oracle
      (`scripts/linux_oracle.py`, python 3.11.16, uid 1001, 2026-10-02): 47 passed, 1 skipped.
      The skip is the bound test; the local driver declares no bound.
- [x] 1.5 Mutation evidence: eighteen guards removed one at a time, each turning its test red
      (design D3). The cross-family refute (gpt-6-astra) returned REJECT in all three rounds;
      the contained findings are folded in, and two crash-containment limits are escalated
      to the isolating drivers (design D7).

## PR 2: gVisor driver

- [x] 2.1 Every driver: bounded calls (`BoxDeadline`, `BoxDeadlineBeforeStart`, a provider
      call timeout and `bounded(s)`), a cancel that never waits behind the box lock,
      `BoxHandle.owner_generation` with a per-box owner fence (`StaleOwner`), and
      `try_fence_idle`, the atomic idle proof the per-command-center handover needs
      (design D8).
- [x] 2.2 `tinyassets/boxes/boxd.py`, the in-box agent over `tinyassets/rpc_frames.py`, and
      `tinyassets/boxes/gvisor.py`, the host side (design D9):
      - rootful runsc on systrap;
      - a uid range per box from an allocated slot;
      - a per-box cgroup with memory (no swap past it) and pids limits;
      - `--network=none` plus its own network namespace;
      - an XFS project quota as the hard disk bound;
      - and kill-the-box on destroy, on an unknown outcome, and on host start.
- [x] 2.3 The contract suite on gVisor, including the bound test, plus
      `tests/test_box_gvisor_driver.py` (detached child dies with the box, a new host ends a
      crashed host's boxes, no network, uid per box, memory limit, a hung box is ended).
      Privileged container (oracle image, runsc release-20260928.0, XFS loop mount with
      prjquota, real cgroups, 2026-10-02): 33 passed. Local driver in the Linux oracle: 54
      passed. Mutation: 11 guards removed one at a time, 9 red; the two green are the
      single network layers (three independent layers, design D9).
- [x] 2.4 Measured against E4 (design D9): box start to first answer 468 ms p50, exec `true`
      start-to-exit 41 ms, 4 KiB write 15 ms, read 3.5 ms, `try_fence_idle` 4 ms.
- [ ] 2.5 Sync the spec, and archive this change once PR 2 lands.
