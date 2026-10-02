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
- [x] 1.4 `tests/test_box_provider_contract.py`: the driver-agnostic suite. Result in the Linux
      oracle (`scripts/linux_oracle.py`, python 3.11.16, uid 1001, 2026-10-02): 31 passed,
      1 skipped. The skip is the bound test; the local driver declares no bound.
- [x] 1.5 Mutation evidence: six guards were removed one at a time, and each turned its test red
      (design D3).

## PR 2: gVisor driver

- [ ] 2.1 `tinyassets/boxes/gvisor.py`:
      - rootful runsc on the systrap platform;
      - a distinct uid and user namespace per box;
      - `--network=none`, with the egress socket over host-uds;
      - an XFS project quota as the hard disk bound;
      - `boxd` inside the box, reached over a host-uds RPC.
- [ ] 2.2 The contract suite on gVisor in the Linux oracle, including the bound test.
- [ ] 2.3 Measure start, exec and idle memory against the spike baselines
      (`target-architecture` `evidence.md` E4).
- [ ] 2.4 Sync the spec, and archive this change once PR 2 lands.
